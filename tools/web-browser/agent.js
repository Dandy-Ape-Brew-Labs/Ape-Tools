#!/usr/bin/env node
// LLM-driven web browsing agent: LM Studio (OpenAI-compatible) ↔ Obscura over CDP.
// The model acts through a JSON action protocol; page state is fed back as
// markdown snapshots + numbered interactive elements, or screenshots for vision.

import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LLM_BASE_URL = (process.env.LLM_BASE_URL ?? 'http://127.0.0.1:1234/v1').replace(/\/+$/, '');
const AGENT_MODEL = process.env.AGENT_MODEL ?? 'qwen/qwen3-vl-8b';
const VISION_MODEL = process.env.AGENT_VISION_MODEL ?? AGENT_MODEL;
const LLM_TIMEOUT_MS = Number(process.env.LLM_TIMEOUT_MS ?? 180_000);
const CDP_ENDPOINT = process.env.CDP_ENDPOINT ?? 'ws://127.0.0.1:9222';
const MAX_TEXT_CHARS = 9_000;
const MAX_ELEMENTS = 60;
const MAX_HISTORY = 14; // trailing observation turns kept
const MAX_IMAGES = 2; // screenshots kept in history
const MAX_PARSE_RETRIES = 3;

const SYSTEM_PROMPT = `You are a web-browsing agent operating a stealth headless browser.
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
8. If truly blocked (hard CAPTCHA, login wall), use fail.`;

const USAGE = `Usage: agent.js --task "<task>" [--start-url <url>] [--max-steps N] [--model <id>] [--vision-model <id>] [--json] [--trace] [--trace-dir <dir>]

Env: LLM_BASE_URL (default http://127.0.0.1:1234/v1), AGENT_MODEL (default ${AGENT_MODEL}),
     AGENT_VISION_MODEL (default: same as AGENT_MODEL), CDP_ENDPOINT, OBSCURA_BIN.`;

const die = (msg, code = 1) => { console.error(`error: ${msg}`); process.exit(code); };
let TRACE = false;
const trace = (msg) => { if (TRACE) console.error(`agent: ${msg}`); };

// ---------- run trace ----------
// With --trace-dir, every step's full detail is persisted: the raw model
// reply (reasoning included), the parsed action, the complete observation
// text, any screenshot PNG, the vision side-call description, and the URL.

const TRACE_LOG = { dir: null, meta: null, steps: [] };

async function writeTrace(outcome, extra = {}) {
  if (!TRACE_LOG.dir) return;
  const { mkdir, writeFile } = await import('node:fs/promises');
  await mkdir(TRACE_LOG.dir, { recursive: true });
  await writeFile(path.join(TRACE_LOG.dir, 'trace.json'), JSON.stringify({
    outcome, ...TRACE_LOG.meta, steps: TRACE_LOG.steps, ...extra,
  }, null, 2));
}

async function saveShot(png, step) {
  if (!TRACE_LOG.dir) return null;
  const { mkdir, writeFile } = await import('node:fs/promises');
  await mkdir(TRACE_LOG.dir, { recursive: true });
  const name = `step-${String(step).padStart(3, '0')}.png`;
  await writeFile(path.join(TRACE_LOG.dir, name), png);
  return name;
}

// ---------- CLI ----------

function parseArgs(argv) {
  const opts = { task: null, startUrl: null, maxSteps: 30, model: AGENT_MODEL, visionModel: VISION_MODEL, json: false, traceDir: null };
  const take = (i, f) => { if (i + 1 >= argv.length) die(`missing value for ${f}`, 2); return argv[i + 1]; };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '-h': case '--help': console.log(USAGE); process.exit(0);
      case '--task': opts.task = take(i, '--task'); i++; break;
      case '--start-url': opts.startUrl = take(i, '--start-url'); i++; break;
      case '--max-steps': opts.maxSteps = Number(take(i, '--max-steps')); i++; break;
      case '--model': opts.model = take(i, '--model'); i++; break;
      case '--vision-model': opts.visionModel = take(i, '--vision-model'); i++; break;
      case '--json': opts.json = true; break;
      case '--trace': TRACE = true; break;
      case '--trace-dir': opts.traceDir = take(i, '--trace-dir'); i++; break;
      default: die(`unknown flag: ${argv[i]}`, 2);
    }
  }
  if (!opts.task) die('missing --task\n\n' + USAGE, 2);
  return opts;
}

// ---------- Obscura server lifecycle ----------

const findObscuraBin = () => {
  if (process.env.OBSCURA_BIN) return process.env.OBSCURA_BIN;
  const vendored = path.join(REPO_ROOT, 'vendor', 'obscura', 'obscura');
  if (existsSync(vendored)) return vendored;
  return 'obscura';
};

async function endpointReady(httpBase) {
  try {
    const res = await fetch(`${httpBase}/json/version`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch { return false; }
}

async function ensureServer() {
  const wsUrl = new URL(CDP_ENDPOINT);
  const host = wsUrl.hostname === 'localhost' ? '127.0.0.1' : wsUrl.hostname;
  const httpBase = `http://${host}:${wsUrl.port || '9222'}`;
  if (await endpointReady(httpBase)) return null;

  const bin = findObscuraBin();
  const help = spawnSync(bin, ['serve', '--help'], { encoding: 'utf8' });
  if (help.error) die(`cannot run obscura binary '${bin}': ${help.error.message}`);
  const args = ['serve', '--port', wsUrl.port || '9222', '--quiet'];
  if (help.stdout.includes('--stealth')) args.push('--stealth');

  trace(`starting ${bin} ${args.join(' ')}`);
  const child = spawn(bin, args, { stdio: ['ignore', 'ignore', 'inherit'] });
  child.unref();
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) die(`obscura serve exited early with code ${child.exitCode}`);
    if (await endpointReady(httpBase)) return child;
    await new Promise((r) => setTimeout(r, 200));
  }
  child.kill();
  die('timed out waiting for obscura serve');
}

// ---------- LLM ----------

async function chat(messages, model) {
  const res = await fetch(`${LLM_BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, temperature: 0, max_tokens: 2048 }),
    signal: AbortSignal.timeout(LLM_TIMEOUT_MS),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    const err = new Error(`LLM ${res.status}: ${body.slice(0, 300)}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  return data.choices?.[0]?.message?.content ?? '';
}

// Vision side-call: used when AGENT_VISION_MODEL differs from AGENT_MODEL.
// The screenshot goes to the VL model; its textual description re-enters the
// main transcript as an observation.
async function visionDescribe(png, model) {
  return chat([
    {
      role: 'system',
      content: 'You are a vision module for a web-browsing agent. Describe the screenshot precisely and tersely: page type, dialogs/banners/modals, and every clickable control with its visible label text and rough position.',
    },
    {
      role: 'user',
      content: [
        { type: 'text', text: 'Describe this page state.' },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${png.toString('base64')}` } },
      ],
    },
  ], model);
}

// ---------- action parsing ----------

function parseAction(text) {
  const cleaned = text.replace(/```(?:json)?/g, '').trim();
  const start = cleaned.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  for (let i = start; i < cleaned.length; i++) {
    if (cleaned[i] === '{') depth++;
    else if (cleaned[i] === '}') {
      depth--;
      if (depth === 0) {
        try {
          const action = JSON.parse(cleaned.slice(start, i + 1));
          // done/fail answers may follow the JSON object as raw text — this
          // avoids JSON string-escaping bugs entirely (quotes, newlines,
          // embedded JSON in headlines all pass through verbatim).
          const field = action.action === 'done' ? 'answer' : action.action === 'fail' ? 'reason' : null;
          if (field && action[field] === undefined) {
            const rest = cleaned.slice(i + 1).trim();
            if (rest) action[field] = rest;
          }
          return action;
        } catch { return salvageTerminal(cleaned); }
      }
    }
  }
  return salvageTerminal(cleaned);
}

// Models occasionally emit done/fail with malformed inner JSON (unescaped
// quotes in a quoted headline, etc). Salvage the terminal action so the
// answer still reaches the validator instead of dying on parse retries.
function salvageTerminal(cleaned) {
  const action = cleaned.match(/"action"\s*:\s*"(done|fail)"/)?.[1];
  if (!action) return null;
  const out = { action };
  const field = action === 'done' ? 'answer' : 'reason';
  const m = cleaned.match(new RegExp(`"${field}"\\s*:\\s*"(.*)"`, 's'));
  if (m) {
    let v = m[1].replace(/"\s*}\s*$/, '').replace(/"\s*$/, '');
    try { v = JSON.parse(`"${v}"`); } catch { v = v.replace(/\\(["\\])/g, '$1'); }
    // The escaped inner JSON often still carries doubled quotes (""x"") —
    // collapse them so a quoted headline doesn't corrupt the JSON array.
    try { v = JSON.stringify(JSON.parse(v.replace(/""/g, '"'))); } catch { /* keep as-is */ }
    out[field] = v;
  }
  return out;
}

// ---------- page state ----------

// Maps the global ref shown to the model -> the Playwright Frame owning it.
// Rebuilt on every snapshot/look.
const refMap = new Map();

// Collects visible interactive elements, piercing open shadow roots
// (consent widgets like DPG Media's myprivacy render entirely inside them).
// Parameter: startRef — first ref number for this frame's elements.
const ELEMENT_SNAPSHOT_JS = `(startRef) => {
  for (const el of document.querySelectorAll('[data-agent-ref]')) el.removeAttribute('data-agent-ref');
  const sel = 'a[href],button,input,select,textarea,summary,[role="button"],[role="link"],[role="checkbox"],[role="menuitem"],[onclick]';
  const out = [];
  const visit = (el) => {
    if (out.length >= ${MAX_ELEMENTS}) return;
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
}`;

const DEEP_TEXT_JS = `(() => {
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
})()`;

async function collectElements(page) {
  refMap.clear();
  const all = [];
  for (const frame of page.frames()) {
    try {
      const els = await frame.evaluate(`(${ELEMENT_SNAPSHOT_JS})(${all.length})`);
      for (const e of els) { refMap.set(e.ref, frame); all.push(e); }
    } catch { /* cross-origin or dead frame — skip */ }
    if (all.length >= MAX_ELEMENTS) break;
  }
  return all.slice(0, MAX_ELEMENTS);
}

async function getMarkdown(page) {
  try {
    const session = await page.context().newCDPSession(page);
    try {
      const res = await session.send('LP.getMarkdown');
      return res?.markdown ?? res?.content ?? (typeof res === 'string' ? res : null);
    } finally { await session.detach().catch(() => {}); }
  } catch { return null; }
}

const truncate = (s, n) => (s.length > n ? s.slice(0, n) + `\n…[truncated ${s.length - n} chars]` : s);

// Markdown from LP.getMarkdown includes image embeds and full hrefs — on
// boilerplate-heavy pages (PubMed ~55K chars) the real content sits past the
// truncation limit. Strip them; hrefs remain available via INTERACTIVE ELEMENTS.
function cleanMarkdown(md) {
  return md
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[ \t]+/g, ' ')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .join('\n');
}

async function snapshotText(page) {
  const elements = await collectElements(page).catch((e) => `unavailable: ${e.message}`);
  let body = (await getMarkdown(page)) ?? (await page.locator('body').innerText().catch(() => ''));
  if (body) body = cleanMarkdown(body);
  if (body.trim().length < 40) {
    // Consent walls and web components often render inside shadow DOM,
    // invisible to innerText — collect text nodes across shadow trees.
    body = await page.evaluate(DEEP_TEXT_JS).catch(() => body);
  }
  const elStr = Array.isArray(elements)
    ? elements.map((e) => `[${e.ref}] <${e.tag}${e.type ? ` type=${e.type}` : ''}> ${e.text}${e.href ? ` -> ${e.href}` : ''}`).join('\n')
    : String(elements);
  return `URL: ${page.url()}\nTITLE: ${await page.title()}\n\nPAGE CONTENT:\n${truncate(body.trim(), MAX_TEXT_CHARS)}\n\nINTERACTIVE ELEMENTS (use ref for click/type):\n${elStr || '(none)'}`;
}

// ---------- actions ----------

async function execAction(page, action) {
  switch (action.action) {
    case 'navigate':
      await page.goto(action.url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      return { text: `navigated to ${page.url()}` };
    case 'snapshot':
      return { text: await snapshotText(page) };
    case 'look': {
      const png = await page.screenshot({ type: 'png' });
      const elements = await collectElements(page).catch(() => []);
      const elStr = Array.isArray(elements)
        ? elements.map((e) => `[${e.ref}] <${e.tag}> ${e.text}`).join('\n')
        : '';
      const { width, height } = page.viewportSize() ?? { width: 1280, height: 900 };
      return { text: `Screenshot attached (${width}x${height} CSS px — click_xy uses these coordinates).\nINTERACTIVE ELEMENTS:\n${elStr || '(none)'}`, image: png };
    }
    case 'click': {
      if (action.ref !== undefined) {
        const frame = refMap.get(Number(action.ref));
        if (!frame) return { text: `no element with ref ${action.ref} — take a fresh snapshot` };
        await frame.locator(`[data-agent-ref="${action.ref}"]`).click({ timeout: 10_000 });
        return { text: `clicked element ${action.ref}` };
      }
      if (action.text !== undefined) {
        // Playwright locators pierce open shadow DOM — works inside consent widgets.
        const loc = page.getByText(String(action.text), { exact: true }).first();
        await loc.click({ timeout: 10_000 });
        return { text: `clicked '${action.text}'` };
      }
      return { text: 'click needs "ref" or "text"' };
    }
    case 'click_xy':
      await page.mouse.click(Number(action.x), Number(action.y));
      return { text: `clicked at ${action.x},${action.y}` };
    case 'type': {
      const frame = refMap.get(Number(action.ref));
      const sel = `[data-agent-ref="${action.ref}"]`;
      if (!frame) return { text: `no element with ref ${action.ref} — take a fresh snapshot` };
      await frame.locator(sel).fill(String(action.text ?? ''), { timeout: 10_000 });
      return { text: `typed into element ${action.ref}` };
    }
    case 'press':
      await page.keyboard.press(String(action.key));
      return { text: `pressed ${action.key}` };
    case 'scroll':
      await page.mouse.wheel(0, action.dir === 'up' ? -700 : 700);
      return { text: `scrolled ${action.dir ?? 'down'}` };
    case 'back':
      await page.goBack({ waitUntil: 'domcontentloaded', timeout: 15_000 }).catch(() => null);
      return { text: `back to ${page.url()}` };
    case 'eval': {
      const js = String(action.js);
      // `eval "expr"` or `eval "() => expr"` — wrap function expressions so they run.
      const expr = /^\s*(\(|function|async|\w+\s*=>)/.test(js) && /=>|function/.test(js)
        ? `(${js})()`
        : js;
      const result = await page.evaluate(expr);
      return { text: truncate(JSON.stringify(result ?? null), 4_000) };
    }
    case 'wait':
      await new Promise((r) => setTimeout(r, Math.min(Number(action.ms) || 1000, 10_000)));
      return { text: 'waited' };
    default:
      return { text: `unknown action '${action.action}' — reply with one valid JSON action` };
  }
}

// ---------- history ----------

function pruned(messages) {
  // keep system + task, plus the trailing MAX_HISTORY turns
  const head = messages.slice(0, 2);
  const tail = messages.slice(2);
  const kept = tail.slice(-MAX_HISTORY * 2);
  const out = [...head, ...kept];
  // cap the number of screenshots in context
  let images = 0;
  for (let i = out.length - 1; i >= 0; i--) {
    const c = out[i].content;
    if (Array.isArray(c)) {
      const hasImg = c.some((p) => p.type === 'image_url');
      if (hasImg) {
        images++;
        if (images > MAX_IMAGES) {
          out[i] = { ...out[i], content: c.filter((p) => p.type !== 'image_url') };
        }
      }
    }
  }
  return out;
}

// ---------- main loop ----------

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  TRACE_LOG.dir = opts.traceDir;
  TRACE_LOG.meta = {
    task: opts.task,
    startUrl: opts.startUrl,
    model: opts.model,
    visionModel: opts.visionModel,
    startedAt: new Date().toISOString(),
  };
  const server = await ensureServer();
  const stopServer = () => { if (server && server.exitCode === null) server.kill('SIGTERM'); };
  process.on('SIGINT', () => { stopServer(); process.exit(130); });
  process.on('SIGTERM', () => { stopServer(); process.exit(143); });

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: opts.startUrl ? `TASK: ${opts.task}\n\nStart by navigating to ${opts.startUrl}` : `TASK: ${opts.task}` },
  ];
  let visionOk = true;
  let parseFails = 0;
  let lastSig = null;
  let repeats = 0;
  const visited = new Set();
  let browser;

  try {
    browser = await chromium.connectOverCDP({ endpointURL: CDP_ENDPOINT });
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();

    for (let step = 0; step < opts.maxSteps; step++) {
      let reply;
      try {
        reply = await chat(pruned(messages), opts.model);
      } catch (err) {
        if (err?.status === 400 && visionOk) {
          visionOk = false;
          trace('model rejected image input — disabling vision for this run');
          for (const m of messages) {
            if (Array.isArray(m.content)) {
              m.content = m.content.filter((p) => p.type !== 'image_url');
              if (m.content.length === 0) m.content = [{ type: 'text', text: '[screenshot removed — model has no vision]' }];
            }
          }
          messages.push({ role: 'user', content: 'OBSERVATION: vision is unavailable — rely on snapshot and eval only.' });
          continue;
        }
        throw err;
      }
      const entry = { step: step + 1, at: new Date().toISOString(), modelReply: reply };
      const action = parseAction(reply);
      if (!action?.action) {
        entry.error = 'unparseable JSON action';
        TRACE_LOG.steps.push(entry);
        parseFails++;
        trace(`step ${step + 1}: unparseable reply (${reply.slice(0, 120)})`);
        messages.push({ role: 'assistant', content: reply });
        messages.push({ role: 'user', content: 'Reply with exactly ONE JSON action object and nothing else.' });
        if (parseFails > MAX_PARSE_RETRIES) {
          await writeTrace('parse-failure');
          die('model repeatedly failed to emit a JSON action');
        }
        continue;
      }
      parseFails = 0;
      trace(`step ${step + 1}: ${JSON.stringify(action).slice(0, 160)}`);

      // Stuck detection: repeating the same mutating action on the same URL
      // means the model is looping — inject a warning. Observational actions
      // (snapshot/look/wait) don't reset the counter, so click→wait→snapshot→click
      // cycles are still caught; URL changes break the signature naturally.
      const MUTATING = new Set(['navigate', 'click', 'click_xy', 'type', 'press', 'scroll', 'back', 'eval']);
      const sig = `${action.action}|${action.ref ?? ''}|${action.text ?? ''}|${action.x ?? ''}|${action.y ?? ''}|${action.url ?? ''}|${page.url()}`;
      if (MUTATING.has(action.action)) {
        repeats = sig === lastSig ? repeats + 1 : 0;
        lastSig = sig;
      }

      if (action.action === 'done' || action.action === 'fail') {
        entry.action = action;
        if (TRACE_LOG.dir) {
          try {
            entry.screenshot = await saveShot(await page.screenshot({ type: 'png' }), step + 1);
          } catch { /* best-effort */ }
          entry.url = page.url();
        }
        TRACE_LOG.steps.push(entry);
        if (action.action === 'done') {
          visited.add(page.url());
          const result = { answer: String(action.answer ?? ''), steps: step + 1, url: page.url(), sources: [...visited], model: opts.model };
          await writeTrace('done', { result });
          console.log(opts.json ? JSON.stringify(result) : result.answer);
          return;
        }
        await writeTrace('fail', { reason: action.reason ?? 'no reason' });
        die(`agent gave up: ${action.reason ?? 'no reason'}`);
      }

      entry.action = action;
      messages.push({ role: 'assistant', content: reply });
      try {
        const obs = await execAction(page, action);
        if (repeats >= 2) {
          obs.text += `\nWARNING: you have issued this exact action ${repeats + 1} times in a row with no page change. Do NOT repeat it — try a different action, or respond done/fail.`;
        }
        entry.observation = obs.text;
        if (obs.image) entry.screenshot = await saveShot(obs.image, step + 1);
        // Trace runs record the page's visual state after EVERY action, so a
        // failing run is debuggable even when the model never called `look`.
        if (!entry.screenshot && TRACE_LOG.dir) {
          try {
            entry.screenshot = await saveShot(await page.screenshot({ type: 'png' }), step + 1);
          } catch { /* page may be mid-navigation — observation text remains */ }
        }
        if (obs.image && visionOk && opts.visionModel !== opts.model) {
          let desc = '';
          try {
            desc = await visionDescribe(obs.image, opts.visionModel);
          } catch (err) {
            if (err?.status === 400) {
              visionOk = false;
              trace('vision model rejected image — disabling vision');
            } else throw err;
          }
          entry.visionDescription = desc;
          messages.push({ role: 'user', content: `OBSERVATION:\n${obs.text}\n\nVISION DESCRIPTION:\n${desc || '(unavailable)'}` });
        } else if (obs.image && visionOk) {
          messages.push({
            role: 'user',
            content: [
              { type: 'text', text: `OBSERVATION:\n${obs.text}\n\nDecide the next action.` },
              { type: 'image_url', image_url: { url: `data:image/png;base64,${obs.image.toString('base64')}` } },
            ],
          });
        } else {
          if (obs.image) messages.push({ role: 'user', content: `OBSERVATION (vision unavailable):\n${obs.text}` });
          else messages.push({ role: 'user', content: `OBSERVATION:\n${obs.text}` });
        }
      } catch (err) {
        entry.error = String(err?.message ?? err).slice(0, 300);
        messages.push({ role: 'user', content: `OBSERVATION: action failed: ${entry.error}` });
      }
      entry.url = page.url();
      TRACE_LOG.steps.push(entry);
      visited.add(page.url());
    }
    await writeTrace('max-steps');
    die(`exceeded --max-steps ${opts.maxSteps} without a done action`);
  } finally {
    if (browser) await browser.close().catch(() => {});
    stopServer();
  }
}

main().catch(async (err) => {
  if (err?.status === 400 && /image|vision|multimodal/i.test(String(err.message))) {
    console.error('error: model rejected image input — use a vision-capable AGENT_MODEL (e.g. qwen/qwen3-vl-8b)');
  }
  await writeTrace('error', { error: err?.message ?? String(err) }).catch(() => {});
  die(err?.message ?? String(err));
});
