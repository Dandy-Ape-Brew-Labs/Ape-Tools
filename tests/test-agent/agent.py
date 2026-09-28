"""TestAgent — drives one scenario through an LLM that may only *use*
the toolbox, never fix it.

The model gets two functions: tool_call(name, argv) and
finish(answer). Legacy args strings also work. The tool index lives in
its system prompt; full schemas
come from calling tool-search/list-tools through tool_call — the §13
tiered discovery flow is what we exercise.

  agent.py --task "..." --workspace DIR [--files JSON] [--auto-answer T]
           [--max-rounds N] [--timeout-s S] [--model M] [--trace-dir DIR]

Emits one JSON result on stdout: {outcome, answer, rounds, invocations,
tool_errors, duration_s}. Diagnostics on stderr. Exit codes: 0 done,
1 fail/stuck/timeout/max-rounds/parse-failure/error.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib
import lib_test

REPO_ROOT = lib_test.REPO_ROOT
PROTECTED = [REPO_ROOT / "tools", REPO_ROOT / "lib",
             Path(__file__).resolve().parent]

MUTATING = {"file-write", "file-edit", "file-insert", "file-patch",
            "fs-manage", "nb-tool", "memory"}

OUT_RESULT_CAP = 16_000
TODO_EXAMPLE = json.dumps({"name": "plan-todo", "argv": [
    "set", "--todos", json.dumps([
        {"content": "write tests", "status": "in_progress"},
        {"content": "run tests", "status": "pending"}])]}, separators=(",", ":"))
WARN_AT, ABORT_AT = 2, 4          # identical call or identical error
POLL_WARN_AT, POLL_ABORT_AT = 5, 8  # identical successful call (polling slack)
MAX_PARSE_FAILS = 3
# Thinking models spend most of the budget on reasoning_content before the
# tool_call token; 2048 truncates them into reasoning-only replies that
# count as parse failures. Requires a server context of 32k+.
AGENT_MAX_TOKENS = 8192
RUN_SHELL_FLAGS = {"--cwd", "--timeout-ms", "--max-bytes"}

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "tool_call",
        "description": "Invoke one toolbox tool by name. Prefer argv (CLI tokens); "
                       "legacy args string is also accepted.",
        "parameters": {"type": "object",
                       "properties": {
                           "name": {"type": "string",
                                    "description": "tool name from the index"},
                           "argv": {"type": "array", "items": {"type": "string"},
                                    "description": "Preferred: CLI tokens, e.g. ['set','--todos','[{\"content\":\"x\"}]']. Each array item is exactly one argument."},
                           "args": {"type": "string",
                                    "description": "Legacy CLI arguments split with shlex; quote individual values containing spaces, never the entire args string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "End the task and return the final answer.",
        "parameters": {"type": "object",
                       "properties": {"answer": {"type": "string"}},
                       "required": ["answer"]}}},
]

SYSTEM = """You are TestAgent. You complete tasks USING a toolbox of CLI tools.
You never modify, fix, or debug the tools themselves — if a tool fails,
report the failure and move on or try a different tool.

WORKSPACE (your working directory): {workspace}
All relative paths resolve there. Write only here. run-shell is NOT an OS sandbox.

STATE DIR (AGENT_TOOLS_HOME): {state}
Stateful tools (memory, notify, plan-todo, ask-user, proc, schedule)
keep their data under this directory — use it to verify side effects,
or prefer the tool's own inspection subcommands (e.g. notify outbox).

REPOSITORY (toolbox source): {repo}
When a task says "the repo"/"the repository"/"the tools", it means THIS
path, not your workspace. Your workspace is a SEPARATE empty directory:
searching "." will NOT find repo files — always pass the repo path
explicitly. NOTE: this path CONTAINS SPACES — quote only that value,
e.g. code-grep args: PATTERN --path "{repo}".

HOW TO INVOKE A TOOL:
- Preferred: emit a tool_call function call with name and argv (CLI token array).
  The dispatcher runs the named tool itself. Do NOT invoke a toolbox script via
  run-shell or include 'python3 tools/<name>/...' in argv.
  Example: {{"name":"file-read","argv":["note.txt"]}}.
  For plan-todo: {todo_example}.
  For run-shell: {{"name":"run-shell","argv":["sha256sum payload.bin"]}}.
- Legacy args string remains accepted; do not wrap the entire args string in quotes.
- Fallback: reply with ONLY a JSON object {{"tool": "<name>", "argv": ["<CLI token>"]}}.
- To finish: call finish, or reply {{"action": "done", "answer": "<answer>"}}.
- To give up: reply {{"action": "fail", "reason": "..."}}.
- If function calling stops working, always use the JSON reply format.

DISCOVERY (do this when unsure of a tool's exact args):
- tool-search args: --select <name> → full manifest incl. args/exit codes
- tool-search args: <what you want to do> → best-matching tools
- list-tools args: --format json --full → every manifest (large; avoid unless needed)

TOOL INDEX (name — when to use):
{index}

RULES:
1. Prefer the dedicated tool over run-shell: fs-list/fs-glob to list or
   find files, file-read/file-write for file contents, code-grep/code-map
   for source, git-ops for git state, selftest/list-tools for tool stats.
   run-shell is for real shell commands (pipes, finds, builds), not a
   substitute for a listed tool.
2. One tool_call per reply is ideal; batch independent calls if needed.
3. Copy arg syntax exactly from the manifest (required flags, quoting).
   Prefer argv: split flags and values into separate array entries. Do NOT include
   shell quotes around entries; a file path with spaces is still ONE entry.
   Use relative workspace paths for fixtures. Do not invent --path for positional paths.
   For run-shell, prefer the entire shell command as ONE argv entry;
   plain command tokens before --cwd are joined safely if you split them.
   Legacy args strings are split with shlex: set --todos '[{{"content":"x"}}]'.
4. A nonzero exit or error output means the TOOL call failed — record it,
   adjust args once or twice, then try another tool or finish with a
   partial answer. Never repeatedly retry identical calls.
5. Never attempt to edit files under tools/, lib/, or the test harness —
   such calls are refused by the dispatcher anyway.
6. When done, summarize what you did AND which tool calls failed (if any).
   Never invent a result: if a tool returned no value or failed, say so.
   Return the actual result in your final answer, not just "Done".
"""


def parse_args():
    p = agentlib.arg_parser(__doc__)
    p.add_argument("--task", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--files", help="JSON {relpath: content} fixtures")
    p.add_argument("--auto-answer", default="yes")
    p.add_argument("--max-rounds", type=int, default=15)
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--model", default=lib_test.AGENT_MODEL)
    p.add_argument("--trace-dir")
    return p.parse_args()


def guard_args(tool: str, args: str | list[str], workspace: Path) -> str | None:
    """Refuse writes that target protected dirs. Returns reason or None."""
    if tool not in MUTATING:
        return None
    try:
        tokens = shlex.split(args) if isinstance(args, str) else args
    except ValueError:
        tokens = args.split()
    candidates = list(tokens)
    if tool == "file-patch":
        candidates += re_paths_in_patch(args if isinstance(args, str) else " ".join(args))
    for tok in candidates:
        if tok.startswith("-") or "\n" in tok:
            continue
        p = (workspace / tok).resolve() if not os.path.isabs(tok) \
            else Path(tok).resolve()
        if str(p).startswith(str(workspace) + os.sep) or p == workspace:
            continue  # workspace writes are always allowed
        for prot in PROTECTED:
            if str(p).startswith(str(prot) + os.sep):
                return (f"refused: '{tok}' targets {prot.name}/ — tools are "
                        "not fixable in this test")
    return None


def re_paths_in_patch(args: str) -> list[str]:
    import re
    return re.findall(r"\*\*\* (?:Add|Update|Delete|Move to) File: (\S+)", args)


def run_tool(manifests: dict, name: str, args: str | list[str],
             workspace: Path) -> dict:
    """Execute one tool_call. Returns {name,args,exit,stdout,stderr,ms}
    or an error dict that is still fed to the model."""
    if name not in manifests:
        close = [n for n in manifests if n.startswith(name[:3])][:5]
        return {"name": name, "args": args, "exit": 127, "stdout": "",
                "stderr": f"unknown tool '{name}'. Similar: {close}. "
                          "Use the index or tool-search for names.",
                "refused": True}
    if name == "run-shell":
        command = " ".join(args) if isinstance(args, list) else args
        for tool_name, manifest in manifests.items():
            path = f"tools/{manifest['dir']}/{manifest['entrypoint']}"
            if tool_name not in ("run-shell", "mcp-serve") and path in command:
                return {"name": name, "args": args, "exit": 2, "stdout": "",
                        "stderr": f"The dispatcher runs {tool_name} directly. "
                                  f"Call tool_call with name='{tool_name}' and "
                                  "argv containing only that tool's CLI tokens."}
        if isinstance(args, list):
            flag_index = next((i for i, token in enumerate(args)
                               if token in RUN_SHELL_FLAGS), len(args))
            if flag_index > 1:
                args = [shlex.join(args[:flag_index]), *args[flag_index:]]
    refusal = guard_args(name, args, workspace)
    if refusal:
        return {"name": name, "args": args, "exit": 126, "stdout": "",
                "stderr": refusal, "refused": True}
    m = manifests[name]
    venv_python = REPO_ROOT / ".venv/bin/python"
    if m.get("dependencies") and not venv_python.is_file() and m.get("language") == "python":
        return {"name": name, "args": args, "exit": 2, "stdout": "",
                "stderr": "project virtual environment missing; run uv sync"}
    exe = ("node" if m.get("language") in ("node", "javascript") else
           str(venv_python) if venv_python.is_file() else "python3")
    script = REPO_ROOT / "tools" / m["dir"] / m["entrypoint"]
    try:
        argv = [exe, str(script), *(shlex.split(args) if isinstance(args, str) else args)]
    except ValueError as exc:
        return {"name": name, "args": args, "exit": 2, "stdout": "",
                "stderr": f"unparseable args: {exc}"}
    env = {**os.environ,
           "AGENT_TOOLS_HOME": str(workspace / "state"),
           "LLM_BASE_URL": lib_test.LLM_BASE_URL}
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, cwd=workspace, env=env,
                              stdin=subprocess.DEVNULL, check=False,
                              capture_output=True, text=True, timeout=60)
        out, err = proc.stdout, proc.stderr
        code = proc.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", "tool_call timed out after 60s", 124
    if name == "run-shell" and code == 0:
        try:
            command_result = json.loads(out)
            code = command_result["exit"]
            if not isinstance(code, int) or isinstance(code, bool):
                raise TypeError("invalid command exit code")
            if code:
                err = command_result.get("stderr") or f"shell command exited {code}"
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            code, err = 2, f"invalid run-shell output: {exc}"
    stdout, _ = agentlib.head_tail(out, OUT_RESULT_CAP)
    stderr, _ = agentlib.head_tail(err, 4_000)
    return {"name": name, "args": args, "exit": code, "stdout": stdout,
            "stderr": stderr, "ms": int((time.monotonic() - start) * 1000)}


def sanitize_history(messages: list[dict]) -> list[dict]:
    """Flatten tool_calls/tool-role turns into plain text so a model
    whose function-calling channel broke mid-run can continue on the
    JSON reply protocol with an equivalent transcript."""
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append({"role": "user",
                        "content": f"TOOL RESULT:\n{m.get('content', '')}"})
        elif m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    payload = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    payload = {}
                action = {"tool": payload.get("name") or fn.get("name")}
                if isinstance(payload.get("argv"), list):
                    action["argv"] = payload["argv"]
                else:
                    action["args"] = payload.get("args", "")
                calls.append(action)
            body = (m.get("content") or "")
            body += ("\n" if body else "") + json.dumps(
                calls[0] if len(calls) == 1 else calls)
            out.append({"role": "assistant", "content": body})
        else:
            out.append({"role": m["role"],
                        "content": m.get("content") or ""})
    return out


def can_fallback_to_json(exc: BaseException) -> bool:
    return isinstance(exc, lib_test.LLMHTTPError) and exc.status in (400, 422)


def record_tool_turn(messages: list[dict], msg: dict, name: str,
                     args: str, observation: str) -> None:
    calls = msg.get("tool_calls") or []
    if calls:
        assistant = {"role": "assistant", "content": msg.get("content") or "",
                     "tool_calls": calls}
        for key in ("reasoning", "reasoning_content"):
            if msg.get(key):
                assistant[key] = msg[key]
        messages.append(assistant)
        messages.append({"role": "tool", "tool_call_id": calls[0]["id"],
                         "content": observation})
    else:
        messages.append({"role": "assistant", "content": msg.get("content") or
                         json.dumps({"tool": name, "args": args})})
        messages.append({"role": "user", "content":
                         f"TOOL RESULT ({name}):\n{observation}"})


def answer_pending_questions(workspace: Path, text: str) -> list[str]:
    """File-handoff for ask-user: answer any pending question file."""
    qdir = workspace / "state" / "questions"
    adir = workspace / "state" / "answers"
    if not qdir.is_dir():
        return []
    answered = []
    adir.mkdir(parents=True, exist_ok=True)
    for qf in sorted(qdir.glob("*.json")):
        aid = qf.stem
        af = adir / f"{aid}.json"
        if af.exists():
            continue
        try:
            q = json.loads(qf.read_text())
            if q.get("options"):
                af.write_text(json.dumps(
                    {"id": aid, "answer": q["options"][0],
                     "ts": time.time()}))
            else:
                af.write_text(json.dumps(
                    {"id": aid, "answer": text, "ts": time.time()}))
            answered.append(aid)
        except (json.JSONDecodeError, OSError):
            continue
    return answered


def main() -> int:
    opts = parse_args()
    workspace = Path(opts.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "state").mkdir(exist_ok=True)

    if opts.files:
        for rel, content in json.loads(opts.files).items():
            fp = workspace / rel
            if not str(fp.resolve()).startswith(str(workspace)):
                agentlib.die(f"fixture escapes workspace: {rel}", 2)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)

    manifests = lib_test.load_tool_manifests()
    index = "\n".join(
        f"{m['name']} — {m.get('use_when') or m['description'][:80]}"
        for m in manifests.values())

    trace_dir = Path(opts.trace_dir) if opts.trace_dir else None
    if trace_dir:
        trace_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    def emit_result(outcome: str, answer: str = "", extra: dict | None = None):
        result = {"outcome": outcome, "answer": answer,
                  "rounds": rounds, "invocations": invocations,
                  "tool_errors": tool_errors,
                  "duration_s": round(time.monotonic() - t0, 1)}
        if extra:
            result.update(extra)
        if trace_dir:
            (trace_dir / "trace.json").write_text(
                json.dumps({"task": opts.task, "model": opts.model,
                            "steps": steps, "result": result}, indent=2))
        agentlib.emit(result)
        return 0 if outcome == "done" else 1

    sys_prompt = SYSTEM.format(workspace=workspace,
                               state=workspace / "state", todo_example=TODO_EXAMPLE,
                               repo=REPO_ROOT, index=index)
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"TASK: {opts.task}"}]

    t0 = time.monotonic()
    deadline = t0 + opts.timeout_s
    rounds = 0
    parse_fails = 0
    native_tools = True
    last_sig = last_err_sig = None
    repeats = err_repeats = 0
    invocations: list[dict] = []
    tool_errors: list[dict] = []

    while rounds < opts.max_rounds and time.monotonic() < deadline:
        rounds += 1
        step = {"round": rounds}
        try:
            msg = lib_test.chat(messages,
                                tools=TOOLS_SCHEMA if native_tools else None,
                                model=opts.model,
                                max_tokens=AGENT_MAX_TOKENS)
        except (lib_test.LLMHTTPError, OSError, ValueError, KeyError) as exc:
            step["error"] = f"llm request failed: {exc}"
            steps.append(step)
            if native_tools and can_fallback_to_json(exc):
                # A protocol-specific bad request may be recovered without
                # changing tools or the task: flatten prior tool turns and
                # switch to the JSON reply protocol for subsequent rounds.
                # Preserve the original server error in the trace.
                native_tools = False
                step["recovered"] = "json-fallback"
                messages = sanitize_history(messages)
                messages.append({"role": "user", "content":
                                 "Function calling is unavailable. Reply "
                                 "with ONLY JSON: {\"tool\": \"<name>\", "
                                 "\"argv\": [\"<CLI token>\"]} or "
                                 "{\"action\": \"done\", \"answer\": \"...\"} "
                                 "or {\"action\": \"fail\", \"reason\": \"...\"}."})
                continue
            return emit_result("error", extra={"error": str(exc)})

        step["raw_reply"] = msg
        parsed = lib_test.parse_reply(msg)
        if parsed is None:
            parse_fails += 1
            step["error"] = "unparseable reply"
            steps.append(step)
            messages.append({"role": "assistant",
                             "content": msg.get("content") or ""})
            messages.append({"role": "user", "content":
                             "Reply with a tool_call or JSON "
                             "{\"tool\":...}/{\"action\":\"done\"} only."})
            if parse_fails > MAX_PARSE_FAILS:
                return emit_result("parse_failure")
            continue
        parse_fails = 0
        step["parsed"] = parsed
        calls = msg.get("tool_calls") or []
        if len(calls) > 1:
            step["error"] = "multiple simultaneous tool calls; retry one at a time"
            steps.append(step)
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": calls})
            for call in calls:
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": "Not executed: call one tool at a time."})
            continue

        if parsed["kind"] == "finish":
            steps.append(step)
            return emit_result("done", parsed["answer"])
        if parsed["kind"] == "fail":
            steps.append(step)
            return emit_result("fail", extra={"reason": parsed["reason"]})

        # tool call
        name = parsed.get("name") or ""
        args = parsed["argv"] if parsed.get("argv") is not None else parsed.get("args") or ""
        display_args = shlex.join(args) if isinstance(args, list) else args
        result = run_tool(manifests, name, args, workspace)
        step["call"] = {"name": name, "args": display_args, "exit": result["exit"]}
        steps.append(step)
        invocations.append({"name": name, "args": display_args[:400],
                            "exit": result["exit"]})
        if result["exit"] != 0:
            tool_errors.append({"tool": name, "args": display_args[:400],
                                "exit": result["exit"],
                                "stderr": result["stderr"][:300]})

        # stuck detection — identical errors abort fast; identical
        # *successful* calls get polling slack (proc read, ask-user list...)
        sig = sha1(f"{name}|{display_args}".encode()).hexdigest()[:12]
        err_sig = (sha1(f"{name}|{result['stderr'][:120]}".encode())
                   .hexdigest()[:12] if result["exit"] != 0 else None)
        repeats = repeats + 1 if sig == last_sig else 0
        last_sig = sig
        err_repeats = (err_repeats + 1 if err_sig and err_sig == last_err_sig
                       else 0)
        last_err_sig = err_sig
        warn_at = WARN_AT if result["exit"] != 0 else POLL_WARN_AT
        abort_at = ABORT_AT if result["exit"] != 0 else POLL_ABORT_AT

        obs = result["stdout"]
        if result["exit"] != 0:
            obs += (f"\n[tool exited {result['exit']}]\n{result['stderr']}"
                    .rstrip())
            obs += (f"\nHINT: wrong args? Use tool-search with args "
                    f"--select {name} (no outer quotes) to see the full "
                    f"manifest (args, flags, exit codes).")
        if not obs.strip():
            obs = "(no output)"
        if repeats >= warn_at - 1 or err_repeats >= WARN_AT - 1:
            obs += ("\n\nWARNING: you are repeating identical calls/errors "
                    "without progress. Change approach, use another tool, "
                    "or finish/fail.")
        if repeats >= abort_at - 1 or err_repeats >= ABORT_AT - 1:
            return emit_result("stuck", extra={"loop": name})

        # Feed native tool_calls/tool-role turns back to the model;
        # flatten only when the backend rejects the native protocol.
        # This preserves the tool_call_id for the next model turn.
        # The fallback JSON-text transcript remains available if needed.
        record_tool_turn(messages, msg, name, display_args, obs)

        answered = answer_pending_questions(workspace, opts.auto_answer)
        if answered:
            messages.append({"role": "user", "content":
                             f"(harness auto-answered questions: "
                             f"{', '.join(answered)} with "
                             f"'{opts.auto_answer}')"})

    outcome = "timeout" if time.monotonic() >= deadline else "max_rounds"
    return emit_result(outcome)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(main())
