"""Scenario runner for TestAgent — the acceptance-test layer for the
toolbox. Mirrors tests/web-browser/e2e.js conventions.

  run.py [--only id,id] [--mode forced|choice|e2e] [--timeout S]
         [--max-rounds N] [--report-dir DIR] [--dry-run]

Each scenario runs agent.py in a fresh workspace; results are graded
deterministically (expected tools, artifacts, answer content) and
optionally by a judge model. Report lands in
tests/test-agent/reports/<timestamp>/report.json with per-scenario
trace.json + verdict.json.

Exit 0 iff no scenario FAILED, STUCK, or UNKNOWN. SKIPPED records
unavailable optional requirements.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib
import lib_test

TEST_DIR = Path(__file__).resolve().parent
AGENT = TEST_DIR / "agent.py"
SCENARIOS = TEST_DIR / "scenarios.json"
REPORTS_ROOT = TEST_DIR / "reports"

DEFAULTS = {"forced": {"max_rounds": 12, "timeout_s": 180},
            "choice": {"max_rounds": 20, "timeout_s": 300},
            "e2e": {"max_rounds": 40, "timeout_s": 900}}

OUTCOME_STATUS = {"done": None, "fail": "FAILED", "stuck": "STUCK",
                  "timeout": "UNKNOWN", "max_rounds": "UNKNOWN",
                  "parse_failure": "UNKNOWN", "error": "UNKNOWN"}


def parse_cli():
    p = agentlib.arg_parser(__doc__)
    p.add_argument("--only")
    p.add_argument("--mode", choices=["forced", "choice", "e2e"])
    p.add_argument("--timeout", type=int)
    p.add_argument("--max-rounds", type=int)
    p.add_argument("--report-dir")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def run_scenario(s: dict, scenario_dir: Path, timeout_s: int) -> dict:
    workspace = scenario_dir / "workspace"
    workspace.mkdir()
    for cmd in s.get("setup", []):
        r = subprocess.run(cmd, shell=True, cwd=workspace, check=False,
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"outcome": "error", "answer": "", "rounds": 0,
                    "invocations": [], "tool_errors": [],
                    "error": f"setup failed: {cmd}: {r.stderr[-200:]}"}
    argv = ["python3", str(AGENT), "--task", s["prompt"],
            "--workspace", str(workspace),
            "--files", json.dumps(s.get("files", {})),
            "--auto-answer", s.get("auto_answer", "yes"),
            "--model", s.get("model") or lib_test.AGENT_MODEL,
            "--max-rounds", str(s["max_rounds"]),
            "--timeout-s", str(timeout_s),
            "--trace-dir", str(scenario_dir)]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          check=False, timeout=timeout_s + 30)
    try:
        result = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {"outcome": "error", "answer": "", "rounds": 0,
                "invocations": [], "tool_errors": [],
                "error": f"agent did not emit JSON: "
                         f"{proc.stderr[-400:]}"}
    return result


def grade(s: dict, result: dict, workspace: Path) -> tuple[str, list, dict | None]:
    """Returns (status, failures, judge_record_or_None)."""
    outcome = result.get("outcome", "error")
    status = OUTCOME_STATUS.get(outcome, "UNKNOWN")
    failures = []
    judge_rec = None
    expect = s.get("expect", {})
    if outcome in ("fail",):
        failures.append(f"agent gave up: {result.get('reason', '?')}")
    if outcome == "done" or s.get("grade_partial"):
        failures += lib_test.validate(result, expect, workspace)
    if status is None:
        status = "FAILED" if failures else "PASSED"
    if not failures and expect.get("judge") and outcome == "done":
        judge_rec = lib_test.judge(s["prompt"], expect["judge"],
                                   str(result.get("answer", "")),
                                   result.get("invocations", []),
                                   result.get("tool_errors", []),
                                   model=s.get("judge_model"))
        judge_rec["rubric"] = expect["judge"]
        judge_rec["model"] = s.get("judge_model") or lib_test.JUDGE_MODEL
        if not judge_rec["pass"]:
            failures.append(f"judge: {judge_rec['reason']}")
            status = "FAILED"
    return status, failures, judge_rec


def suite_failed(tally: dict[str, int]) -> bool:
    return any(tally[key] for key in ("FAILED", "STUCK", "UNKNOWN"))


def main() -> int:
    opts = parse_cli()
    scenarios = json.loads(SCENARIOS.read_text())
    if opts.only:
        wanted = set(opts.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
        if not scenarios:
            agentlib.die(f"no scenarios match --only={opts.only}", 2)
    if opts.mode:
        scenarios = [s for s in scenarios if s["mode"] == opts.mode]

    manifests = lib_test.load_tool_manifests()
    for s in scenarios:
        d = DEFAULTS[s["mode"]]
        s.setdefault("max_rounds", d["max_rounds"])
        s.setdefault("timeout_s", d["timeout_s"])
        s["max_rounds"] = opts.max_rounds or s["max_rounds"]
        s["timeout_s"] = opts.timeout or s["timeout_s"]

    if opts.dry_run:
        for s in scenarios:
            miss = lib_test.check_requires(s.get("requires", []))
            bad = [t for t in s.get("expect", {}).get("tools", [])
                   if t not in manifests]
            print(f"{s['id']:32} [{s['mode']:6}] "
                  f"{'SKIP: ' + miss if miss else 'ok'}"
                  f"{' BAD TOOLS: ' + ','.join(bad) if bad else ''}")
        print(f"{len(scenarios)} scenarios checked")
        return 0

    err = lib_test.preflight()
    if err:
        agentlib.die(err, 2)

    report_dir = (Path(opts.report_dir) if opts.report_dir else
                  REPORTS_ROOT / datetime.now(UTC).strftime(
                      "%Y-%m-%dT%H-%M-%S-%f"))
    report_dir.mkdir(parents=True, exist_ok=False)
    print(f"report dir: {report_dir}", file=sys.stderr)

    tally = {"PASSED": 0, "FAILED": 0, "STUCK": 0, "UNKNOWN": 0,
             "SKIPPED": 0}
    results = []
    exercised: set[str] = set()
    tool_failures: dict[str, int] = {}

    for s in scenarios:
        scenario_dir = report_dir / s["id"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        workspace = scenario_dir / "workspace"
        record = {"id": s["id"], "mode": s["mode"], "prompt": s["prompt"],
                  "expect": s.get("expect", {}),
                  "traceDir": str(scenario_dir.relative_to(lib_test.REPO_ROOT))}

        miss = lib_test.check_requires(s.get("requires", []))
        if miss:
            record.update(status="SKIPPED", reason=miss)
            tally["SKIPPED"] += 1
            print(f"{s['id']} ... SKIPPED ({miss})", file=sys.stderr)
        else:
            t0 = time.time()
            print(f"{s['id']} ... ", end="", file=sys.stderr, flush=True)
            result = run_scenario(s, scenario_dir, s["timeout_s"])
            secs = round(time.time() - t0)
            for inv in result.get("invocations", []):
                exercised.add(inv["name"])
            for e in result.get("tool_errors", []):
                tool_failures[e["tool"]] = tool_failures.get(e["tool"], 0) + 1
            status, failures, judge_rec = grade(s, result, workspace)
            record.update(status=status,
                          model=s.get("model") or lib_test.AGENT_MODEL,
                          rounds=result.get("rounds"),
                          duration_s=secs, outcome=result.get("outcome"),
                          answer=result.get("answer", ""),
                          tools_invoked=[i["name"] for i in
                                         result.get("invocations", [])],
                          tool_errors=result.get("tool_errors", []),
                          validationFailures=failures)
            if judge_rec:
                record["judge"] = judge_rec
            tally[status] += 1
            tag = f" ({secs}s, {result.get('rounds', 0)} rounds)"
            extra = f" — {'; '.join(failures[:2])}" if failures else ""
            print(f"{status}{tag}{extra}", file=sys.stderr)

        results.append(record)
        (scenario_dir / "verdict.json").write_text(
            json.dumps(record, indent=2) + "\n")

    all_expected = {t for s2 in json.loads(SCENARIOS.read_text())
                    for t in s2.get("expect", {}).get("tools", [])}
    report = {
        "at": datetime.now(UTC).isoformat(),
        "llmBaseUrl": lib_test.LLM_BASE_URL,
        "agentModel": lib_test.AGENT_MODEL,
        "judgeModel": lib_test.JUDGE_MODEL,
        "modelsUsed": sorted({r.get("model") for r in results
                              if r.get("model")}),
        "summary": {"total": len(results), **tally},
        "coverage": {
            "tools_expected": sorted(all_expected),
            "tools_exercised": sorted(exercised),
            "tools_untested": sorted(all_expected - exercised),
            "tool_failures": tool_failures,
        },
        "results": results,
    }
    (report_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n{len(results)} scenarios: " +
          ", ".join(f"{k}={v}" for k, v in tally.items()),
          file=sys.stderr)
    print(f"report: {report_dir / 'report.json'}", file=sys.stderr)
    return 1 if suite_failed(tally) else 0


if __name__ == "__main__":
    sys.exit(main())
