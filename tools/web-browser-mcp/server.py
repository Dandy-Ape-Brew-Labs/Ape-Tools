#!/usr/bin/env python3
"""MCP server driving the Obscura stealth browser over CDP — Python port of
tools/web-browser (agent.js) with two complementary surfaces:

- Interactive tools (browser_navigate, browser_snapshot, browser_look,
  browser_click, ...) expose the same JSON action protocol as first-class
  MCP tools, so the calling agent drives one persistent page itself.
- browser_browse runs the autonomous LM Studio agent loop — the direct
  equivalent of agent.js --task — and returns {answer, steps, url, sources}.

Run:  uv run tools/web-browser-mcp/server.py
      uv run tools/web-browser-mcp/server.py --selfcheck   (list tools, no browser)
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "qwen/qwen3-vl-8b")
VISION_MODEL = os.environ.get("AGENT_VISION_MODEL", AGENT_MODEL)
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_MS", "180000")) / 1000
CDP_ENDPOINT = os.environ.get("CDP_ENDPOINT", "ws://127.0.0.1:9222")
MAX_TEXT_CHARS = 9_000
MAX_ELEMENTS = 60
MAX_HISTORY = 14  # trailing observation turns kept
MAX_IMAGES = 2  # screenshots kept in history
MAX_PARSE_RETRIES = 3
SERVER_READY_TIMEOUT_S = 15

logging.basicConfig(level=logging.INFO, format="browser-mcp: %(message)s")
log = logging.getLogger("browser-mcp")

SYSTEM_PROMPT = """You are a web-browsing agent operating a stealth headless browser.
The user gives you a task requiring real page content. Reply with EXACTLY ONE JSON object per turn — no markdown fences, no commentary.

ACTIONS:
{"action":"navigate","url":"<absolute url>"}     open a page
{"action":"snapshot"}                            get page text + numbered interactive elements
{"action":"look"}                                screenshot the page (cookie walls, popups, CAPTCHAs, visual-only content)
{"action":"click","ref":N}                       click element N from the latest snapshot/look
{"action":"click","text":"Akkoord"}              click an element by its visible text (pierces shadow DOM — best for dialogs)
{"action":"click_xy","x":N,"y":M}                click pixel coordinates (last resort)
{"action":"type","ref":N,"text":"..."}           set text on input element N
{"action":"press","key":"Enter"}                 key press (Enter, Escape, Tab, ...)
{"action":"scroll","dir":"down"}                 scroll down/up
{"action":"back"}                                browser back
{"action":"eval","js":"<expression>"}            evaluate JS, result returned as JSON
{"action":"wait","ms":N}                         wait for the page to settle
{"action":"done"}                                finished — then write the answer as RAW TEXT on the following lines
{"action":"done","answer":"short answer"}        (inline form is fine ONLY for short answers without quotes/newlines)
{"action":"fail","reason":"..."}                 cannot complete

RULES:
1. Prefer snapshot; use look when the page is visual-only or shows a dialog.
2. Cookie/consent walls: click the accept/agree/continue element by ref (or coordinates after look).
3. Collect enough content to answer accurately; follow links when needed. Do not guess.
4. ref numbers refer to the LATEST snapshot or look — take a fresh snapshot after navigation.
5. The answer must satisfy the task format exactly (e.g. raw JSON array when asked). Put it as raw text after the done JSON whenever it contains quotes, newlines, or is longer than a few words.
6. If the page content already contains what the task asks for, respond done immediately — do not keep exploring or interacting.
7. Never repeat an action that did not change the page — try a different approach instead.
8. If truly blocked (hard CAPTCHA, login wall), use fail."""

# ---------- Obscura server lifecycle ----------


def _find_obscura_bin() -> str:
    if os.environ.get("OBSCURA_BIN"):
        return os.environ["OBSCURA_BIN"]
    vendored = REPO_ROOT / "vendor" / "obscura" / "obscura"
    return str(vendored) if vendored.exists() else "obscura"


def _endpoint_ready(http_base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{http_base}/json/version", timeout=1.5) as res:
            return res.status == 200
    except (urllib.error.URLError, OSError):
        return False


_server_proc: subprocess.Popen | None = None


def ensure_server() -> None:
    """Auto-start `obscura serve` when the CDP endpoint is unreachable."""
    global _server_proc
    ws = urllib.parse.urlparse(CDP_ENDPOINT.replace("ws://", "http://").replace("wss://", "https://"))
    host = "127.0.0.1" if ws.hostname == "localhost" else ws.hostname
    port = ws.port or 9222
    http_base = f"{'https' if ws.scheme == 'https' else 'http'}://{host}:{port}"
    if _endpoint_ready(http_base):
        return

    bin_path = _find_obscura_bin()
    try:
        help_out = subprocess.run(
            [bin_path, "serve", "--help"], capture_output=True, text=True
        )
    except OSError as exc:
        raise RuntimeError(f"cannot run obscura binary '{bin_path}': {exc}") from exc
    args = [bin_path, "serve", "--port", str(port), "--quiet"]
    if "--stealth" in help_out.stdout:
        args.append("--stealth")

    log.info("starting %s", " ".join(args))
    _server_proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    import time

    deadline = time.monotonic() + SERVER_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if _server_proc.poll() is not None:
            raise RuntimeError(f"obscura serve exited early with code {_server_proc.returncode}")
        if _endpoint_ready(http_base):
            return
        time.sleep(0.2)
    _server_proc.kill()
    raise RuntimeError("timed out waiting for obscura serve")


def _stop_server() -> None:
    if _server_proc and _server_proc.poll() is None:
        _server_proc.terminate()


# ---------- LLM (OpenAI-compatible chat, stdlib only) ----------


class ChatError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def chat(messages: list[dict], model: str) -> str:
    body = json.dumps(
        {"model": model, "messages": messages, "temperature": 0, "max_tokens": 2048}
    ).encode()
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_S) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise ChatError(f"LLM {exc.code}: {detail}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise ChatError(f"LLM unreachable at {LLM_BASE_URL}: {exc.reason}") from exc
    choices = data.get("choices") or []
    return (choices[0].get("message") or {}).get("content") or ""


def vision_describe(png: bytes, model: str) -> str:
    """Vision side-call: describe a screenshot when the agent model has no vision."""
    return chat(
        [
            {
                "role": "system",
                "content": "You are a vision module for a web-browsing agent. Describe the "
                "screenshot precisely and tersely: page type, dialogs/banners/modals, and "
                "every clickable control with its visible label text and rough position.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this page state."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64.b64encode(png).decode()}"
                        },
                    },
                ],
            },
        ],
        model,
    )


# ---------- action parsing ----------


def parse_action(text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    action = json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    return _salvage_terminal(cleaned)
                # done/fail answers may follow the JSON object as raw text — this
                # avoids JSON string-escaping bugs entirely.
                field = (
                    "answer"
                    if action.get("action") == "done"
                    else "reason"
                    if action.get("action") == "fail"
                    else None
                )
                if field and action.get(field) is None:
                    rest = cleaned[i + 1 :].strip()
                    if rest:
                        action[field] = rest
                return action
    return _salvage_terminal(cleaned)


def _salvage_terminal(cleaned: str) -> dict | None:
    """Salvage a done/fail action with malformed inner JSON (e.g. unescaped quotes)."""
    m = re.search(r'"action"\s*:\s*"(done|fail)"', cleaned)
    if not m:
        return None
    action = m.group(1)
    out: dict = {"action": action}
    field = "answer" if action == "done" else "reason"
    m2 = re.search(rf'"{field}"\s*:\s*"(.*)"', cleaned, re.S)
    if m2:
        v = re.sub(r'"\s*\}\s*$', "", m2.group(1))
        v = re.sub(r'"\s*$', "", v)
        try:
            v = json.loads(f'"{v}"')
        except json.JSONDecodeError:
            v = re.sub(r'\\(["\\])', r"\1", v)
        # The escaped inner JSON often still carries doubled quotes (""x"") —
        # collapse them so a quoted headline doesn't corrupt the JSON array.
        try:
            v = json.dumps(json.loads(v.replace('""', '"')))
        except (json.JSONDecodeError, TypeError):
            pass
        out[field] = v
    return out


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"\n…[truncated {len(s) - n} chars]"


# Markdown from LP.getMarkdown includes image embeds and full hrefs — strip
# them; hrefs remain available via INTERACTIVE ELEMENTS.
def _clean_markdown(md: str) -> str:
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"[ \t]+", " ", md)
    return "\n".join(line.strip() for line in md.split("\n") if line.strip())


# ---------- browser session ----------

# Collects visible interactive elements, piercing open shadow roots
# (consent widgets like DPG Media's myprivacy render entirely inside them).
ELEMENT_SNAPSHOT_JS = """(startRef) => {
  for (const el of document.querySelectorAll('[data-agent-ref]')) el.removeAttribute('data-agent-ref');
  const sel = 'a[href],button,input,select,textarea,summary,[role="button"],[role="link"],[role="checkbox"],[role="menuitem"],[onclick]';
  const out = [];
  const visit = (el) => {
    if (out.length >= MAX_ELEMENTS) return;
    if (el.matches(sel)) {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      if (r.width >= 2 && r.height >= 2 && s.visibility !== 'hidden' && s.display !== 'none') {
        const ref = startRef + out.length;
        el.setAttribute('data-agent-ref', String(ref));
        const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
        out.push({ ref, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') ?? undefined, text, href: el.getAttribute('href')?.slice(0, 120) ?? undefined });
      }
    }
    if (el.shadowRoot) for (const c of el.shadowRoot.querySelectorAll('*')) visit(c);
  };
  for (const el of document.querySelectorAll('*')) visit(el);
  return out;
}""".replace("MAX_ELEMENTS", str(MAX_ELEMENTS))

DEEP_TEXT_JS = """(() => {
  const walk = (n) => {
    let t = '';
    for (const c of n.childNodes) {
      if (c.nodeType === 3) t += ' ' + c.nodeValue;
      else if (c.nodeType === 1) {
        t += ' ' + walk(c);
        if (c.shadowRoot) t += ' ' + walk(c.shadowRoot);
      }
    }
    return t;
  };
  return walk(document.body ?? document.documentElement).replace(/\\s+/g, ' ').trim();
})()"""


class BrowserSession:
    """One browser page plus its ref->frame map, rebuilt on each snapshot."""

    def __init__(self, page):
        self.page = page
        self.ref_map: dict[int, object] = {}

    async def navigate(self, url: str) -> str:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return f"navigated to {self.page.url}"

    async def collect_elements(self) -> list[dict]:
        self.ref_map.clear()
        all_els: list[dict] = []
        for frame in self.page.frames:
            try:
                els = await frame.evaluate(f"({ELEMENT_SNAPSHOT_JS})({len(all_els)})")
                for e in els:
                    self.ref_map[e["ref"]] = frame
                    all_els.append(e)
            except Exception:
                continue  # cross-origin or dead frame — skip
            if len(all_els) >= MAX_ELEMENTS:
                break
        return all_els[:MAX_ELEMENTS]

    async def get_markdown(self) -> str | None:
        try:
            session = await self.page.context.new_cdp_session(self.page)
            try:
                res = await session.send("LP.getMarkdown")
                if isinstance(res, dict):
                    return res.get("markdown") or res.get("content")
                return res if isinstance(res, str) else None
            finally:
                try:
                    await session.detach()
                except Exception:
                    pass
        except Exception:
            return None

    async def snapshot_text(self) -> str:
        try:
            elements = await self.collect_elements()
        except Exception as exc:
            elements = f"unavailable: {exc}"
        body = await self.get_markdown()
        if body is None:
            try:
                body = await self.page.locator("body").inner_text()
            except Exception:
                body = ""
        body = _clean_markdown(body)
        if len(body.strip()) < 40:
            # Consent walls often render inside shadow DOM, invisible to
            # innerText — collect text nodes across shadow trees.
            try:
                body = await self.page.evaluate(DEEP_TEXT_JS)
            except Exception:
                pass
        if isinstance(elements, list):
            lines = []
            for e in elements:
                type_attr = f" type={e['type']}" if e.get("type") else ""
                href = f" -> {e['href']}" if e.get("href") else ""
                lines.append(f"[{e['ref']}] <{e['tag']}{type_attr}> {e['text']}{href}")
            el_str = "\n".join(lines)
        else:
            el_str = str(elements)
        return (
            f"URL: {self.page.url}\nTITLE: {await self.page.title()}\n\n"
            f"PAGE CONTENT:\n{_truncate(body.strip(), MAX_TEXT_CHARS)}\n\n"
            f"INTERACTIVE ELEMENTS (use ref for click/type):\n{el_str or '(none)'}"
        )

    async def look(self) -> tuple[str, bytes]:
        png = await self.page.screenshot(type="png")
        try:
            elements = await self.collect_elements()
            el_str = "\n".join(f"[{e['ref']}] <{e['tag']}> {e['text']}" for e in elements)
        except Exception:
            el_str = ""
        vp = self.page.viewport_size or {"width": 1280, "height": 900}
        text = (
            f"Screenshot attached ({vp['width']}x{vp['height']} CSS px — "
            f"click_xy uses these coordinates).\nINTERACTIVE ELEMENTS:\n{el_str or '(none)'}"
        )
        return text, png

    async def click(self, ref: int | None = None, text: str | None = None) -> str:
        if ref is not None:
            frame = self.ref_map.get(int(ref))
            if frame is None:
                return f"no element with ref {ref} — take a fresh snapshot"
            await frame.locator(f'[data-agent-ref="{ref}"]').click(timeout=10_000)
            return f"clicked element {ref}"
        if text is not None:
            # Playwright locators pierce open shadow DOM — works inside consent widgets.
            await self.page.get_by_text(str(text), exact=True).first.click(timeout=10_000)
            return f"clicked '{text}'"
        return 'click needs "ref" or "text"'

    async def click_xy(self, x: float, y: float) -> str:
        await self.page.mouse.click(float(x), float(y))
        return f"clicked at {x},{y}"

    async def type_text(self, ref: int, text: str) -> str:
        frame = self.ref_map.get(int(ref))
        if frame is None:
            return f"no element with ref {ref} — take a fresh snapshot"
        await frame.locator(f'[data-agent-ref="{ref}"]').fill(str(text), timeout=10_000)
        return f"typed into element {ref}"

    async def press(self, key: str) -> str:
        await self.page.keyboard.press(str(key))
        return f"pressed {key}"

    async def scroll(self, direction: str = "down") -> str:
        await self.page.mouse.wheel(0, -700 if direction == "up" else 700)
        return f"scrolled {direction}"

    async def back(self) -> str:
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=15_000)
        except Exception:
            pass
        return f"back to {self.page.url}"

    async def eval(self, js: str) -> str:
        # `eval "expr"` or `eval "() => expr"` — wrap function expressions so they run.
        expr = (
            f"({js})()"
            if re.match(r"^\s*(\(|function|async|\w+\s*=>)", js) and re.search(r"=>|function", js)
            else js
        )
        result = await self.page.evaluate(expr)
        return _truncate(json.dumps(result if result is not None else None), 4_000)

    async def wait(self, ms: int = 1000) -> str:
        await asyncio.sleep(min(int(ms) if ms else 1000, 10_000) / 1000)
        return "waited"

    async def exec(self, action: dict) -> dict:
        """Dispatch one agent-loop action; returns {text, image?}."""
        name = action.get("action")
        if name == "navigate":
            return {"text": await self.navigate(action["url"])}
        if name == "snapshot":
            return {"text": await self.snapshot_text()}
        if name == "look":
            text, png = await self.look()
            return {"text": text, "image": png}
        if name == "click":
            return {"text": await self.click(action.get("ref"), action.get("text"))}
        if name == "click_xy":
            return {"text": await self.click_xy(action["x"], action["y"])}
        if name == "type":
            return {"text": await self.type_text(action["ref"], action.get("text", ""))}
        if name == "press":
            return {"text": await self.press(action["key"])}
        if name == "scroll":
            return {"text": await self.scroll(action.get("dir", "down"))}
        if name == "back":
            return {"text": await self.back()}
        if name == "eval":
            return {"text": await self.eval(str(action["js"]))}
        if name == "wait":
            return {"text": await self.wait(action.get("ms", 1000))}
        return {"text": f"unknown action '{name}' — reply with one valid JSON action"}


# ---------- connection / session registry ----------

_pw = None
_conn = None
_interactive: BrowserSession | None = None
_op_lock = asyncio.Lock()


async def _playwright():
    global _pw
    if _pw is None:
        from playwright.async_api import async_playwright

        _pw = await async_playwright().start()
    return _pw


async def _connection():
    global _conn
    if _conn is not None and _conn.is_connected():
        return _conn
    await asyncio.to_thread(ensure_server)
    _conn = await (await _playwright()).chromium.connect_over_cdp(
        endpoint_url=CDP_ENDPOINT
    )
    return _conn


async def interactive_session() -> BrowserSession:
    """The persistent page driven by the interactive browser_* tools."""
    global _interactive
    if _interactive is not None and not _interactive.page.is_closed():
        return _interactive
    conn = await _connection()
    context = await conn.new_context(viewport={"width": 1280, "height": 900})
    _interactive = BrowserSession(await context.new_page())
    return _interactive


async def _fresh_session() -> BrowserSession:
    """A throwaway context for browser_browse — doesn't clobber the shared page."""
    conn = await _connection()
    context = await conn.new_context(viewport={"width": 1280, "height": 900})
    return BrowserSession(await context.new_page())


async def _shutdown() -> None:
    global _interactive, _conn, _pw
    try:
        if _interactive is not None:
            await _interactive.page.context.close()
    except Exception:
        pass
    _interactive = None
    try:
        if _conn is not None:
            await _conn.close()
    except Exception:
        pass
    _conn = None
    try:
        if _pw is not None:
            await _pw.stop()
    except Exception:
        pass
    _pw = None
    _stop_server()


# ---------- autonomous browse loop (port of agent.js main) ----------

MUTATING = {"navigate", "click", "click_xy", "type", "press", "scroll", "back", "eval"}


def _pruned(messages: list[dict]) -> list[dict]:
    """Keep system + task, plus the trailing MAX_HISTORY turns and ≤MAX_IMAGES shots."""
    head, tail = messages[:2], messages[2:]
    out = head + tail[-MAX_HISTORY * 2 :]
    images = 0
    for i in range(len(out) - 1, -1, -1):
        content = out[i].get("content")
        if isinstance(content, list) and any(p.get("type") == "image_url" for p in content):
            images += 1
            if images > MAX_IMAGES:
                out[i] = {
                    **out[i],
                    "content": [p for p in content if p.get("type") != "image_url"],
                }
    return out


async def run_browse(
    task: str,
    start_url: str | None,
    max_steps: int,
    model: str,
    vision_model: str,
    trace: bool,
) -> dict:
    session = await _fresh_session()
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"TASK: {task}"
                + (f"\n\nStart by navigating to {start_url}" if start_url else ""),
            },
        ]
        vision_ok = True
        parse_fails = 0
        last_sig = None
        repeats = 0
        visited: set[str] = set()

        for step in range(max_steps):
            try:
                reply = await asyncio.to_thread(chat, _pruned(messages), model)
            except ChatError as exc:
                if exc.status == 400 and vision_ok:
                    vision_ok = False
                    if trace:
                        log.info("model rejected image input — disabling vision for this run")
                    for m in messages:
                        if isinstance(m.get("content"), list):
                            m["content"] = [
                                p for p in m["content"] if p.get("type") != "image_url"
                            ] or [{"type": "text", "text": "[screenshot removed — model has no vision]"}]
                    messages.append(
                        {
                            "role": "user",
                            "content": "OBSERVATION: vision is unavailable — rely on "
                            "snapshot and eval only.",
                        }
                    )
                    continue
                raise

            action = parse_action(reply)
            if not action or not action.get("action"):
                parse_fails += 1
                if trace:
                    log.info("step %d: unparseable reply (%.120s)", step + 1, reply)
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": "Reply with exactly ONE JSON action object and nothing else.",
                    }
                )
                if parse_fails > MAX_PARSE_RETRIES:
                    raise RuntimeError("model repeatedly failed to emit a JSON action")
                continue
            parse_fails = 0
            if trace:
                log.info("step %d: %.160s", step + 1, json.dumps(action))

            # Stuck detection: repeating the same mutating action on the same
            # URL means the model is looping — inject a warning. Observational
            # actions don't reset the counter.
            sig = (
                f"{action.get('action')}|{action.get('ref', '')}|{action.get('text', '')}"
                f"|{action.get('x', '')}|{action.get('y', '')}|{action.get('url', '')}"
                f"|{session.page.url}"
            )
            if action["action"] in MUTATING:
                repeats = repeats + 1 if sig == last_sig else 0
                last_sig = sig

            if action["action"] in ("done", "fail"):
                if action["action"] == "done":
                    visited.add(session.page.url)
                    return {
                        "answer": str(action.get("answer", "")),
                        "steps": step + 1,
                        "url": session.page.url,
                        "sources": sorted(visited),
                        "model": model,
                    }
                raise RuntimeError(f"agent gave up: {action.get('reason', 'no reason')}")

            messages.append({"role": "assistant", "content": reply})
            try:
                obs = await session.exec(action)
                if repeats >= 2:
                    obs["text"] += (
                        f"\nWARNING: you have issued this exact action {repeats + 1} times "
                        "in a row with no page change. Do NOT repeat it — try a different "
                        "action, or respond done/fail."
                    )
                image = obs.get("image")
                if image and vision_ok and vision_model != model:
                    try:
                        desc = await asyncio.to_thread(vision_describe, image, vision_model)
                    except ChatError as exc:
                        if exc.status == 400:
                            vision_ok = False
                            if trace:
                                log.info("vision model rejected image — disabling vision")
                            desc = ""
                        else:
                            raise
                    messages.append(
                        {
                            "role": "user",
                            "content": f"OBSERVATION:\n{obs['text']}\n\n"
                            f"VISION DESCRIPTION:\n{desc or '(unavailable)'}",
                        }
                    )
                elif image and vision_ok:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"OBSERVATION:\n{obs['text']}\n\nDecide the next action.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64,"
                                        + base64.b64encode(image).decode()
                                    },
                                },
                            ],
                        }
                    )
                else:
                    prefix = "OBSERVATION (vision unavailable)" if image else "OBSERVATION"
                    messages.append({"role": "user", "content": f"{prefix}:\n{obs['text']}"})
            except Exception as exc:
                messages.append(
                    {
                        "role": "user",
                        "content": f"OBSERVATION: action failed: {str(exc)[:300]}",
                    }
                )
            visited.add(session.page.url)

        raise RuntimeError(f"exceeded max_steps {max_steps} without a done action")
    finally:
        try:
            await session.page.context.close()
        except Exception:
            pass


# ---------- MCP server ----------

from mcp.server.fastmcp import FastMCP, Image  # noqa: E402


@asynccontextmanager
async def _lifespan(server):
    try:
        yield {}
    finally:
        await _shutdown()


mcp = FastMCP(
    "web-browser-mcp",
    instructions=(
        "Drive the Obscura stealth browser. Interactive tools share one persistent "
        "page: navigate, then snapshot (markdown + numbered element refs) or look "
        "(screenshot), then act via browser_click/type/scroll/eval. For one-shot "
        "tasks, browser_browse runs an autonomous LLM loop and returns the answer."
    ),
    lifespan=_lifespan,
)


async def _with_snapshot(obs: str) -> str:
    """Append a fresh snapshot after a mutating action, or a hint if the page
    is mid-navigation."""
    session = await interactive_session()
    try:
        return obs + "\n\n" + await session.snapshot_text()
    except Exception:
        return obs + "\n\n(page settling — call browser_snapshot for fresh state)"


@mcp.tool()
async def browser_navigate(url: str) -> str:
    """Navigate the shared page to an absolute URL. Returns a page snapshot:
    markdown text plus numbered interactive element refs for browser_click."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.navigate(url))


@mcp.tool()
async def browser_snapshot() -> str:
    """Get the page as markdown text plus numbered interactive elements
    ([0] <button> Accept — use the ref with browser_click/browser_type).
    Pierces shadow DOM, so consent dialogs are included."""
    async with _op_lock:
        session = await interactive_session()
        return await session.snapshot_text()


@mcp.tool()
async def browser_look() -> list:
    """Screenshot the page (for cookie walls, popups, visual-only content)
    plus the numbered interactive elements. The screenshot is returned as
    image content for vision-capable clients."""
    async with _op_lock:
        session = await interactive_session()
        text, png = await session.look()
        return [text, Image(data=png, format="png")]


@mcp.tool()
async def browser_click(ref: int | None = None, text: str | None = None) -> str:
    """Click an element: by ref number from the latest snapshot/look, or by
    its exact visible text (pierces shadow DOM — best for consent dialogs).
    Returns a fresh snapshot."""
    if ref is None and text is None:
        raise ValueError('browser_click needs "ref" or "text"')
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.click(ref, text))


@mcp.tool()
async def browser_click_xy(x: float, y: float) -> str:
    """Click pixel coordinates (last resort — prefer browser_click by ref).
    Coordinates are CSS px as reported by browser_look. Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.click_xy(x, y))


@mcp.tool()
async def browser_type(ref: int, text: str) -> str:
    """Set text on input element ref from the latest snapshot/look.
    Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.type_text(ref, text))


@mcp.tool()
async def browser_press(key: str) -> str:
    """Press a key (Enter, Escape, Tab, ArrowDown, ...). Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.press(key))


@mcp.tool()
async def browser_scroll(direction: str = "down") -> str:
    """Scroll the page up or down to reveal more content. Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.scroll(direction))


@mcp.tool()
async def browser_back() -> str:
    """Browser back navigation. Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.back())


@mcp.tool()
async def browser_eval(js: str) -> str:
    """Evaluate a JavaScript expression in the page; result returned as JSON.
    Function expressions like "() => document.title" are invoked."""
    async with _op_lock:
        session = await interactive_session()
        return await session.eval(js)


@mcp.tool()
async def browser_wait(ms: int = 1000) -> str:
    """Wait for the page to settle (max 10000 ms). Returns a fresh snapshot."""
    async with _op_lock:
        session = await interactive_session()
        return await _with_snapshot(await session.wait(ms))


@mcp.tool()
async def browser_status() -> dict:
    """Report CDP endpoint reachability and the shared page's current URL —
    without starting the server or a page."""
    ws = urllib.parse.urlparse(CDP_ENDPOINT.replace("ws://", "http://"))
    http_base = f"http://{ws.hostname}:{ws.port or 9222}"
    reachable = await asyncio.to_thread(_endpoint_ready, http_base)
    current = None
    if _interactive is not None and not _interactive.page.is_closed():
        current = _interactive.page.url
    return {
        "cdp_endpoint": CDP_ENDPOINT,
        "server_reachable": reachable,
        "page_url": current,
        "llm_base_url": LLM_BASE_URL,
        "agent_model": AGENT_MODEL,
    }


@mcp.tool()
async def browser_close() -> str:
    """Close the shared interactive page. The next browser_* call opens a
    fresh one."""
    global _interactive
    async with _op_lock:
        if _interactive is not None:
            try:
                await _interactive.page.context.close()
            except Exception:
                pass
            _interactive = None
        return "closed"


@mcp.tool()
async def browser_browse(
    task: str,
    start_url: str | None = None,
    max_steps: int = 30,
    model: str | None = None,
    vision_model: str | None = None,
    trace: bool = False,
) -> dict:
    """Autonomous browsing agent — the Python equivalent of web-browser's
    agent.js. An LM Studio model (OpenAI-compatible, LLM_BASE_URL) drives a
    fresh stealth browser page through the JSON action protocol to answer
    `task` using real page content. Returns {answer, steps, url, sources,
    model}; raises on failure. Long-running: each step is one LLM call."""
    return await run_browse(
        task=task,
        start_url=start_url,
        max_steps=max_steps,
        model=model or AGENT_MODEL,
        vision_model=vision_model or VISION_MODEL,
        trace=trace,
    )


# ---------- entry ----------


async def _selfcheck() -> None:
    for tool in await mcp.list_tools():
        first = (tool.description or "").splitlines()[0]
        print(f"{tool.name} — {first}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selfcheck", action="store_true", help="list MCP tools and exit (no browser)"
    )
    args = parser.parse_args()
    if args.selfcheck:
        asyncio.run(_selfcheck())
        return 0

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    mcp.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
