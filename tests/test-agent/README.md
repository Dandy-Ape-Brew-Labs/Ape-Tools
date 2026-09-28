# test-agent

Acceptance layer: an LLM drives the real toolbox end-to-end. It
*uses* tools — direct write-tool calls to `tools/`, `lib/`, and this
harness are refused by the dispatcher. `run-shell` is not an OS sandbox:
only run trusted scenarios, and inspect traces for indirect writes.
Failures are recorded, not repaired.

The model gets two functions — `tool_call(name, argv)` and
`finish(answer)` — plus the tool index in its system prompt. `argv` is
an array of exact CLI tokens; legacy `args` strings remain accepted.
The dispatcher invokes the named tool itself, so `run-shell` is not
needed to launch other toolbox scripts. For `run-shell`, plain command
tokens in `argv` are joined before flags such as `--cwd`; a single argv
entry remains the preferred way to pass a shell command with operators.
Discovery of schemas happens
through `tool-search`/`list-tools` calls, exercising the tiered flow from
`Agent Tool Reference.md` §13. Native tool calls and matching tool-role
results are replayed to the model. A JSON-reply fallback covers
backends that reject tool calling with HTTP 400/422.

## Scenarios

- **forced/** — prompt names (or unmistakably describes) the tool;
  `expect.tools` verifies it was invoked. One per tool.
- **choice/** — task without tool names; `tools_any` lists acceptable
  picks — measures selection accuracy.
- **e2e/** — broad multi-tool assignments (research → build TODO app
  with sqlite; repo health report) graded by a judge model.

Fields per scenario: `prompt`, optional `files` (fixtures), `setup`
(shell commands run in the workspace first), `requires` (preflight
gates → SKIPPED), `auto_answer` (ask-user reply), `expect`,
`model`/`judge_model` (per-scenario overrides — different models per
scenario are supported), and `max_rounds`/`timeout_s` overrides.
`expect.absent` asserts a workspace path was removed. Each
scenario gets a fresh workspace inside its report directory; existing
workspaces are never removed.

## Running

```sh
python3 tests/test-agent/run.py                    # everything
python3 tests/test-agent/run.py --mode forced      # one class
python3 tests/test-agent/run.py --only file-read,file-edit
python3 tests/test-agent/run.py --dry-run          # validate the set, no LLM
```

Env: `LLM_BASE_URL`, `TEST_AGENT_MODEL`, `E2E_JUDGE_MODEL`
(defaults: `qwen/qwen3.5-9b`). Load a single model on the endpoint and
check the server's model state before running. GPT-OSS-20B can
return intermittent LM Studio/llama.cpp `peg-native` parser errors in
multi-turn sessions; Qwen3.5-9B is a more stable transport default,
though its instruction-following still needs the acceptance suite.

Reasoning models need headroom: the harness sends `max_tokens=8192`
per turn (reasoning precedes the tool call), so load the model with a
context of at least 32k (`lms load <model> --context-length 32768`).
Per-model sampling overrides live in `lib_test.MODEL_SAMPLING` —
Qwen3.5 thinking mode gets its model-card values (temp 0.6, top_p 0.95,
top_k 20) because greedy decoding degenerates into repetition loops;
other models default to `temperature=0`. `finish_reason`/`usage` are
recorded per step in `trace.json` as `_finish_reason`/`_usage`.

## Report

`reports/<timestamp>/report.json` — statuses
PASSED/FAILED/STUCK/UNKNOWN/SKIPPED, a `coverage` block (exercised /
untested / per-tool failure counts), and per-scenario `trace.json` +
`verdict.json`. Exit code is 0 only if nothing FAILED, STUCK, or UNKNOWN;
SKIPPED scenarios do not fail the suite.

## Stuck detection

Same call signature 3× → warning injected, 5× → STUCK. Identical tool
error 3×/5× likewise (triage-cycle detector). >3 unparseable replies →
parse_failure. Every tool call has a 60s cap; the scenario has a
wall-clock timeout.

## ask-user

The harness auto-answers pending questions between rounds by writing
`state/answers/<id>.json` (first option, or `auto_answer`). Timeouts
still surface as exit 3 — the agent should `list`/`read` to retrieve
late answers.
