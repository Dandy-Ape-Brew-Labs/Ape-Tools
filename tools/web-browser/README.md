# web-browser

An LLM-driven browsing agent. A model served by LM Studio (or any
OpenAI-compatible endpoint) drives the Obscura stealth browser over CDP
through a JSON action protocol, gathers real page content across multiple
pages, and returns an answer to a natural-language task.

## How it works

```
task ──► LLM ──► JSON action ──► Playwright/CDP ──► Obscura
          ▲                        │
          └──── observation ───────┘
            (markdown + numbered elements, or screenshot)
```

The model replies with one JSON action per turn:

- `navigate`, `snapshot`, `look`, `click` (by `ref`, by visible `text`,
  or `click_xy` coordinates), `type`, `press`, `scroll`, `back`, `eval`,
  `wait`, `done`, `fail`

Element collection pierces open shadow roots — consent widgets like DPG
Media's myprivacy (nu.nl) render entirely inside shadow DOM, invisible to
`innerText`/ordinary selectors. Text is likewise collected across shadow
trees when the main DOM is empty. A repeat-action watchdog injects a
warning when the model issues the same mutating action three times in a
row without a page change.

**Vision → action grounding:** every `snapshot`/`look` returns the visible
interactive elements numbered (`[0] <button> Accept`, `[1] <button> Deny`)
via injected `data-agent-ref` attributes. The model picks a `ref` — no
brittle coordinate guessing. `look` also attaches the screenshot for
vision-capable models, so cookie walls and popups can be seen *and* clicked.

**Reading content:** snapshots use Obscura's `LP.getMarkdown`
(DOM→markdown) with `innerText` fallback — JS-rendered pages come back as
clean text. When a page is visual-only, `look` + vision covers it.

**Context discipline:** the task stays in context the whole run; page text
is truncated and old observations/screenshots are pruned, so the model keeps
the user's goal in view while working through dialogs and navigation.

## Setup

```sh
tools/obscura-browse/install.sh   # vendored Obscura binary
export LLM_BASE_URL=http://127.0.0.1:1234/v1   # default already
export AGENT_MODEL=qwen/qwen3-vl-8b              # default; must be VL for `look`
```

`AGENT_VISION_MODEL` may point at a different model (e.g. agent =
`openai/gpt-oss-20b`, vision = `qwen/qwen3-vl-8b`) — screenshots are then
described by the vision model in a side-call and injected as text.

## Usage

```sh
node tools/web-browser/agent.js \
  --task "Get the 3 main headlines" \
  --start-url https://news.ycombinator.com --trace
```

`--json` wraps the output as `{answer, steps, url, sources, model}` —
`sources` lists every page URL the agent visited.

## E2E tests

The E2E runner only validates the agent's answer — it never solves the
task itself. Validation is **hybrid**: deterministic checks verify
structure, and an optional `judge` expectation sends `{task, rubric,
answer, sources}` to a judge model (`E2E_JUDGE_MODEL`, default the agent
model) which grades semantic correctness — did we truly get 5 articles
about quantum mechanics, or five plausible-looking strings? Grading is
not solving: the judge never produces the answer, only checks adherence
to the request.

```sh
node tests/web-browser/e2e.js                            # all scenarios
node tests/web-browser/e2e.js --only hn-top3             # one scenario
node tests/web-browser/e2e.js --trace                    # live step log on stderr
node tests/web-browser/e2e.js --report-dir out/run-1     # custom report location
```

Every run writes a full-fidelity report to `tests/web-browser/reports/<timestamp>/`
(or `--report-dir`):

```
tests/web-browser/reports/<run>/
├── report.json            # summary: PASSED/FAILED/UNKNOWN counts + verdicts
└── <scenario-id>/
    ├── verdict.json       # status, answer, validation failures, judge
    │                      #   prompt + raw judge responses, duration
    ├── trace.json         # every step: raw model reply, parsed action,
    │                      #   full observation text, screenshot ref, URL
    └── step-NNN.png       # page state after every step
```

Statuses: `PASSED` (all checks + judge), `FAILED` (validation or judge
rejected a produced answer), `UNKNOWN` (agent errored/timed out — no
answer to evaluate). The run exits non-zero unless all scenarios PASS.

`agent.js --trace-dir <dir>` produces the same per-step trace standalone.

Scenarios live in `scenarios.json` (`site`, `task`, `expect`, `maxSteps`).
Deterministic validators: `format:"json"`, `minItems`, `contains`,
`containsAny` (+`containsAnyMin`), `regex`, `minLength`, `notContains`.
Semantic validator: `judge` (rubric string; only runs when the
deterministic checks pass).

| Scenario                  | Site                            | Checks                     |
| ------------------------- | ------------------------------- | -------------------------- |
| `nu-headlines`            | nu.nl (cookie wall)             | JSON ≥ 3 + judge           |
| `bbc-headlines`           | bbc.co.uk (cookie wall)         | JSON ≥ 3 + judge           |
| `github-explore-repo`     | github.com/explore              | `owner/repo` regex         |
| `hn-top3`                 | news.ycombinator.com            | JSON ≥ 3 + judge           |
| `arxiv-first-paper`       | arxiv.org/list/cs.AI/recent     | `\d{4}\.\d{4,5}` regex     |
| `pubmed-quantum-articles` | pubmed.ncbi.nlm.nih.gov         | JSON ≥ 5 + judge           |

Exits non-zero when any scenario fails.

## Limits

- A local LLM cannot solve hard CAPTCHAs (image puzzles, Cloudflare
  turnstile). Obscura's stealth mode avoids many bot walls; when a real
  challenge appears the agent should `fail` honestly.
- Small VL models occasionally need a corrective nudge to emit bare JSON;
  the loop retries a few times before failing.
- Cookie/consent handling depends on the model recognizing the banner —
  `--trace` shows each step when debugging.
