"""Shared helpers for the test-agent harness: LLM chat, reply parsing,
scenario validation, judge calls, sandbox/env setup. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = Path(__file__).resolve().parent

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
AGENT_MODEL = os.environ.get("TEST_AGENT_MODEL", "qwen/qwen3.5-9b")
JUDGE_MODEL = os.environ.get("E2E_JUDGE_MODEL", "qwen/qwen3.5-9b")
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_S", "180"))

# Model-card-recommended sampling, matched on model-id prefix. Qwen3.5
# thinking mode degenerates into repetition loops under greedy decoding;
# the card prescribes temp 0.6/top_p 0.95/top_k 20 for precise tasks.
# LM Studio forwards these fields to the llama.cpp sampler.
MODEL_SAMPLING = {
    "qwen/qwen3.5": {"temperature": 0.6, "top_p": 0.95, "top_k": 20},
}
DEFAULT_SAMPLING = {"temperature": 0}


def sampling_for(model_id: str) -> dict:
    for prefix, params in MODEL_SAMPLING.items():
        if model_id.startswith(prefix):
            return dict(params)
    return dict(DEFAULT_SAMPLING)


# ---------- LLM ----------


class LLMHTTPError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = status
        super().__init__(f"LLM HTTP {status}: {detail}")


def chat(messages: list[dict], tools: list[dict] | None = None,
         model: str | None = None, stream: bool | None = None,
         max_tokens: int = 2048) -> dict:
    """POST /chat/completions. Returns the raw message dict:
    {content?, tool_calls?}. Raises on HTTP/timeout."""
    model_id = model or AGENT_MODEL
    if stream is None:
        stream = model_id.startswith("openai/gpt-oss-")
    body = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
        **sampling_for(model_id),
    }
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_S) as res:
            if stream:
                return parse_stream(res)
            data = json.loads(res.read())
    except urllib.error.HTTPError as exc:
        raise LLMHTTPError(exc.code, exc.read(1000).decode(errors="replace")) from exc
    choice = data["choices"][0]
    msg = choice["message"]
    if choice.get("finish_reason"):
        msg["_finish_reason"] = choice["finish_reason"]
    if data.get("usage"):
        msg["_usage"] = data["usage"]
    return msg


def parse_stream(response) -> dict:
    message: dict = {"role": "assistant", "content": ""}
    calls: dict[int, dict] = {}
    completed = False
    for line in response:
        if not line.startswith(b"data: "):
            continue
        payload = line[6:].strip()
        if payload == b"[DONE]":
            completed = True
            break
        event = json.loads(payload)
        if "error" in event:
            raise LLMHTTPError(500, str(event["error"])[:1000])
        if event.get("usage"):
            message["_usage"] = event["usage"]
        for choice in event.get("choices", []):
            if choice.get("finish_reason"):
                message["_finish_reason"] = choice["finish_reason"]
            delta = choice.get("delta") or {}
            for key in ("content", "reasoning", "reasoning_content"):
                if delta.get(key):
                    message[key] = message.get(key, "") + delta[key]
            for part in delta.get("tool_calls") or []:
                call = calls.setdefault(part["index"],
                                        {"id": "", "type": "function",
                                         "function": {"name": "", "arguments": ""}})
                call["id"] += part.get("id") or ""
                fn = part.get("function") or {}
                call["function"]["name"] += fn.get("name") or ""
                call["function"]["arguments"] += fn.get("arguments") or ""
    if not completed:
        raise ValueError("LLM stream ended before completion")
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    return message


def preflight() -> str | None:
    """Return an error string if the LLM endpoint is unreachable."""
    try:
        req = urllib.request.Request(f"{LLM_BASE_URL}/models")
        with urllib.request.urlopen(req, timeout=5):
            return None
    except Exception as exc:  # noqa: BLE001 — any failure = unreachable
        return f"LLM endpoint {LLM_BASE_URL} unreachable: {exc}"


# ---------- reply parsing (JSON fallback for tool-less models) ----------


def parse_reply(message: dict) -> dict | None:
    """Normalize an assistant message to
    {kind: call|finish|fail, name?, argv?, args?, answer?, reason?}.

    Order: real tool_calls first, then JSON in content."""
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        name = fn.get("name")
        try:
            payload = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            payload = {}
        if name == "tool_call" and isinstance(payload, dict):
            argv = payload.get("argv")
            if argv is not None and (not isinstance(argv, list) or
                                     not all(isinstance(a, str) for a in argv)):
                return None
            return {"kind": "call", "name": payload.get("name"),
                    "args": payload.get("args", ""), "argv": argv}
        if name == "finish":
            return {"kind": "finish", "answer": str(payload.get("answer", ""))}

    content = message.get("content") or ""
    cleaned = re.sub(r"```(?:json)?", "", content).strip()
    obj = _first_json_object(cleaned)
    if obj is None and not cleaned:
        # gpt-oss on LM Studio sometimes returns the reply inside the
        # reasoning field with an empty content channel.
        alt = message.get("reasoning") or message.get("reasoning_content") or ""
        obj = _first_json_object(re.sub(r"```(?:json)?", "", alt).strip())
    if obj is None:
        if cleaned and not cleaned.startswith("{"):
            return {"kind": "finish", "answer": cleaned}
        return None
    action = obj.get("action")
    if "tool" in obj or action == "tool_call":
        argv = obj.get("argv")
        if argv is not None and (not isinstance(argv, list) or
                                 not all(isinstance(a, str) for a in argv)):
            return None
        return {"kind": "call", "name": obj.get("tool") or obj.get("name"),
                "args": obj.get("args", ""), "argv": argv}
    if action in ("done", "finish"):
        answer = obj.get("answer")
        if answer is None:
            # allow raw text after the JSON object
            rest = cleaned[cleaned.index("}") + 1:].strip()
            answer = rest
        return {"kind": "finish", "answer": str(answer or "")}
    if action == "fail":
        return {"kind": "fail", "reason": str(obj.get("reason", ""))}
    if cleaned and not cleaned.startswith("{"):
        return {"kind": "finish", "answer": cleaned}
    return None


def _first_json_object(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ---------- scenario validation ----------


def validate(record: dict, expect: dict, workspace: Path) -> list[str]:
    """Deterministic checks. Returns a list of failure strings."""
    failures: list[str] = []
    invoked = [c["name"] for c in record.get("invocations", [])]
    answer = str(record.get("answer") or "")
    low = answer.lower()

    for tool in expect.get("tools", []):
        if tool not in invoked:
            failures.append(f"expected tool '{tool}' was never invoked")
    if expect.get("tools_any") and not any(
            t in invoked for t in expect["tools_any"]):
        failures.append(
            f"expected one of {expect['tools_any']}, invoked {invoked}")
    for tool in expect.get("tools_forbidden", []):
        if tool in invoked:
            failures.append(f"forbidden tool '{tool}' was invoked")
    for needle in expect.get("answer_contains", []):
        if needle.isdecimal():
            numbers = re.findall(r"\d[\d,_]*\d|\d", answer)
            if needle not in {re.sub(r"[^\d]", "", number) for number in numbers}:
                failures.append(f"answer missing '{needle}'")
        elif needle.lower() not in low:
            failures.append(f"answer missing '{needle}'")
    for rel in expect.get("absent", []):
        path = (workspace / rel).resolve()
        if not path.is_relative_to(workspace.resolve()):
            failures.append(f"invalid absent path '{rel}'")
        elif path.exists():
            failures.append(f"expected '{rel}' to be absent")
    for spec in expect.get("files", []):
        path = workspace / spec["path"]
        if not path.is_file():
            failures.append(f"expected file '{spec['path']}' was not created")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if ("contains" in spec
                and spec["contains"].lower() not in text.lower()):
            failures.append(f"file '{spec['path']}' missing '{spec['contains']}'")
        if "regex" in spec and not re.search(spec["regex"], text):
            failures.append(
                f"file '{spec['path']}' does not match /{spec['regex']}/")
    return failures


JUDGE_PROMPT = """You are grading an AI agent's answer against a rubric.

TASK GIVEN TO AGENT:
__TASK__

RUBRIC:
__RUBRIC__

TOOLS THE AGENT INVOKED:
__TOOLS__

TOOL FAILURES THE AGENT HIT:
__ERRORS__

Note: the failures list shows invocations that errored at least once. A
tool listed there may still have succeeded on a later call — recovered
failures are normal, not hallucination.

AGENT'S ANSWER:
__ANSWER__

Decide whether the answer satisfies the rubric. Reply with ONLY JSON:
{"pass": true, "reason": "..."} or {"pass": false, "reason": "..."}"""


def judge(task: str, rubric: str, answer: str, invocations: list[dict],
          tool_errors: list[dict], model: str | None = None) -> dict:
    tools = ", ".join(dict.fromkeys(i["name"] for i in invocations)) or "(none)"
    errs = "\n".join(f"{e['tool']}: exit {e['exit']} — {e['stderr'][:200]}"
                     for e in tool_errors) or "(none)"
    prompt = (JUDGE_PROMPT.replace("__TASK__", task)
              .replace("__RUBRIC__", rubric)
              .replace("__TOOLS__", tools)
              .replace("__ERRORS__", errs)
              .replace("__ANSWER__", answer))
    raws = []
    for _ in range(2):
        try:
            # Reasoning models burn max_tokens on thinking; give the judge
            # headroom and fall back to scanning reasoning for the verdict.
            msg = chat([{"role": "user", "content": prompt}],
                       model=model or JUDGE_MODEL, max_tokens=8192)
        except Exception as exc:  # noqa: BLE001
            return {"pass": False, "reason": f"judge request failed: {exc}",
                    "prompt": prompt, "raw": raws}
        text = (msg.get("content")
                or msg.get("reasoning")
                or msg.get("reasoning_content") or "")
        raws.append(text)
        m = re.search(r"\{[\s\S]*\}",
                      re.sub(r"```(?:json)?", "", text))
        if m:
            try:
                verdict = json.loads(m.group(0))
                if isinstance(verdict.get("pass"), bool):
                    return {"pass": verdict["pass"],
                            "reason": str(verdict.get("reason", "")),
                            "prompt": prompt, "raw": raws}
            except json.JSONDecodeError:
                pass
    return {"pass": False, "reason": "judge did not return a parseable verdict",
            "prompt": prompt, "raw": raws}


# ---------- manifests / requirements ----------


def load_tool_manifests() -> dict[str, dict]:
    """name -> manifest (with 'dir' added)."""
    out = {}
    for p in sorted((REPO_ROOT / "tools").glob("*/tool.json")):
        try:
            m = json.loads(p.read_text())
            m["dir"] = p.parent.name
            out[m["name"]] = m
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def check_requires(requires: list[str]) -> str | None:
    """Return a skip reason if any requirement is unmet, else None."""
    import shutil
    import subprocess

    for req in requires:
        kind, _, val = req.partition(":")
        if kind == "binary" and not shutil.which(val):
            return f"missing binary: {val}"
        if kind == "env" and not os.environ.get(val):
            return f"missing env: {val}"
        if kind == "file" and not (REPO_ROOT / val).exists():
            return f"missing file: {val}"
        if kind == "gh-auth":
            r = subprocess.run(["gh", "auth", "status"],
                               capture_output=True)
            if r.returncode != 0:
                return "gh not authenticated"
        if kind == "net":
            try:
                req_obj = urllib.request.Request(
                    f"https://{val}", method="HEAD")
                urllib.request.urlopen(req_obj, timeout=5)
            except Exception:
                return f"unreachable: {val}"
        if kind == "systemd-user":
            r = subprocess.run(["systemctl", "--user", "is-system-running"],
                               capture_output=True)
            if r.returncode not in (0, 1):
                return "no systemd --user manager"
        if kind == "ydotoold":
            sock = (Path(f"/run/user/{os.getuid()}/.ydotool_socket")
                    .exists() or Path("/tmp/.ydotool_socket").exists())
            if not sock:
                return "ydotoold not running"
    return None
