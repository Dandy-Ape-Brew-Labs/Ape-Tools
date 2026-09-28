# web-browser-mcp

Python equivalent of `tools/web-browser` exposed as an MCP server (stdio).
Two surfaces over the same Obscura/CDP engine:

- **Interactive tools** — the action protocol from `agent.js` promoted to
  first-class MCP tools. The *calling* agent (Claude, Cursor, …) drives one
  persistent page itself instead of delegating to an embedded model.
- **`browser_browse`** — the autonomous loop itself: an LM Studio model
  (OpenAI-compatible) drives a fresh stealth page through the same JSON
  action protocol and returns `{answer, steps, url, sources, model}`.

This is an additional tool, not a replacement: `web-browser` remains the
self-contained Node CLI; `web-browser-mcp` exists for MCP-capable agents.

## How it works

```
MCP client ──► browser_navigate / browser_snapshot / browser_click / ...
                     │                     │
                     └──► shared page ◄────┘   (Obscura over CDP via Playwright)

browser_browse(task) ──► LLM ──► JSON action ──► fresh page
                          ▲          │
                          └──── observation ───┘
```

Page observations are markdown (`LP.getMarkdown`, `innerText` fallback) plus
numbered interactive elements — `[0] <button> Accept` — collected across
open shadow roots so consent widgets (e.g. DPG Media's myprivacy) are
visible and clickable. `browser_look` returns the screenshot as MCP image
content for vision-capable clients. Mutating actions return a fresh
snapshot, so the agent always has current refs.

## Tools

| Tool | Purpose |
| --- | --- |
| `browser_navigate(url)` | Go to URL; returns a snapshot. |
| `browser_snapshot()` | Markdown + numbered interactive elements. |
| `browser_look()` | Screenshot (image content) + element list. |
| `browser_click(ref?, text?)` | Click by element ref, or by exact visible text (pierces shadow DOM). |
| `browser_click_xy(x, y)` | Click pixel coordinates (last resort). |
| `browser_type(ref, text)` | Fill input element by ref. |
| `browser_press(key)` | Enter, Escape, Tab, … |
| `browser_scroll(direction)` | `down` (default) or `up`. |
| `browser_back()` | History back. |
| `browser_eval(js)` | Evaluate JS; result as JSON. |
| `browser_wait(ms)` | Settle wait (max 10 000). |
| `browser_status()` | Endpoint/model info — never starts the browser. |
| `browser_close()` | Close the shared page. |
| `browser_browse(task, …)` | Autonomous loop; `start_url`, `max_steps` (30), `model`, `vision_model`, `trace`. |

## Setup

```sh
tools/obscura-browse/install.sh   # vendored Obscura binary (as for web-browser)
uv sync                           # playwright + mcp live in the shared venv
```

Client config (Claude Code, Cursor, …):

```json
{ "command": "uv", "args": ["run", "<repo>/tools/web-browser-mcp/server.py"] }
```

`browser_browse` additionally needs the model endpoint — same env vars as
`web-browser`: `LLM_BASE_URL` (default `http://127.0.0.1:1234/v1`),
`AGENT_MODEL` (default `qwen/qwen3-vl-8b`, must be VL to receive
screenshots), `AGENT_VISION_MODEL` for a separate vision side-call model.

`CDP_ENDPOINT` (default `ws://127.0.0.1:9222`) is probed on first use;
`obscura serve --stealth` is auto-started when unreachable, and stopped
again at shutdown when the server spawned it.

## Verify

```sh
uv run tools/web-browser-mcp/server.py --selfcheck   # list MCP tools, no browser
python3 tools/selftest/selftest.py --only web-browser-mcp
```

## Limits

- One shared page per server process — interactive calls are serialized.
- Same as `web-browser`: no hard CAPTCHAs (image puzzles, turnstile); the
  browse loop `fail`s honestly when blocked.
- `browser_browse` depends on the LM Studio endpoint being up.
