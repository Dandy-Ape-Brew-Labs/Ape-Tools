#!/usr/bin/env python3
"""Render a selftest results JSON into a self-contained HTML report.

Reads the JSON emitted by selftest.py (file path or '-' for stdin) and writes
a single-file HTML report — no external assets — plus an optional Markdown
summary suitable for $GITHUB_STEP_SUMMARY.

  render_report.py results.json --out report.html [--lint lint.json]
                  [--md-out summary.md] [--sha SHA] [--ref REF]
                  [--run-url URL] [--title TEXT]
"""

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def badge(status: str) -> str:
    labels = {
        "pass": "PASS", "fail": "FAIL", "skip": "SKIP",
        "none": "NO TEST", "invalid": "INVALID",
    }
    return f'<span class="badge {status}">{labels.get(status, status.upper())}</span>'


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    return f"{seconds:.2f}s"


def normalize_lint(lint: dict) -> list[dict]:
    """Return linter entries [{name, status, total, findings[]}]."""
    linters = lint.get("linters", [])
    for entry in linters:
        entry.setdefault("findings", [])
        entry.setdefault("status", "pass" if not entry["findings"] else "fail")
    return linters


def build_rows(results: dict) -> str:
    """One table row per tool, ordered: invalid, fail, pass, skipped, none."""
    rows: list[str] = []

    def row(name: str, status: str, duration=None, detail: str = "") -> None:
        detail_html = ""
        if detail:
            detail_html = (
                f'<details><summary>details</summary><pre>{esc(detail)}</pre></details>'
            )
        rows.append(
            f'<tr class="r-{status}"><td class="tool">{esc(name)}</td>'
            f"<td>{badge(status)}</td>"
            f'<td class="dur">{fmt_duration(duration)}</td>'
            f"<td>{detail_html}</td></tr>"
        )

    for item in results.get("invalid", []):
        row(item["tool"], "invalid", detail="\n".join(item.get("errors", [])))
    for item in results.get("smoke_fail", []):
        row(item["tool"], "fail", item.get("duration_s"),
            item.get("stderr", "") or f"exit {item.get('exit')}")
    for item in results.get("smoke_pass", []):
        row(item["tool"], "pass", item.get("duration_s"))
    for item in results.get("skipped", []):
        row(item["tool"], "skip", detail=item.get("reason", "skipped"))
    for name in results.get("no_smoke", []):
        row(name, "none")
    return "\n".join(rows)


def build_lint_section(linters: list[dict]) -> str:
    if not linters:
        return ""
    blocks = []
    for entry in linters:
        status = entry["status"]
        label = {"pass": "CLEAN", "fail": "FINDINGS",
                 "skipped": "NOT RUN", "error": "ERROR"}.get(status, status.upper())
        cls = "pass" if status == "pass" else ("skip" if status in ("skipped", "error") else "fail")
        header = (f'<h3>{esc(entry["name"])} '
                  f'<span class="badge {cls}">{label}</span>'
                  f'<span class="count">{entry.get("total", len(entry["findings"]))}</span></h3>')
        if entry.get("error"):
            blocks.append(header + f'<pre class="lint-err">{esc(entry["error"][:2000])}</pre>')
            continue
        if not entry["findings"]:
            blocks.append(header)
            continue
        lines = []
        for f in entry["findings"][:500]:
            loc = esc(f.get("file", "?"))
            if f.get("line"):
                loc += f':{f["line"]}'
            level = esc(f.get("level", "info"))
            code = f' <span class="code">{esc(f["code"])}</span>' if f.get("code") else ""
            lines.append(
                f'<tr><td class="loc">{loc}</td>'
                f'<td class="lvl {level}">{level}</td>'
                f'<td>{esc(f.get("message", ""))}{code}</td></tr>'
            )
        extra = ""
        if len(entry["findings"]) > 500:
            extra = f'<p class="muted">…and {len(entry["findings"]) - 500} more</p>'
        blocks.append(
            header + '<table class="lint"><thead><tr><th>location</th>'
            "<th>level</th><th>message</th></tr></thead><tbody>"
            + "\n".join(lines) + "</tbody></table>" + extra
        )
    return ('<section><h2>Lint <span class="muted">(non-blocking)</span></h2>'
            + "\n".join(blocks) + "</section>")


def render_html(results: dict, lint: dict | None, meta: dict) -> str:
    ok = bool(results.get("ok"))
    n_pass = len(results.get("smoke_pass", []))
    n_fail = len(results.get("smoke_fail", []))
    n_invalid = len(results.get("invalid", []))
    n_skip = len(results.get("skipped", []))
    n_none = len(results.get("no_smoke", []))
    n_valid = len(results.get("valid", []))
    duration = sum(i.get("duration_s", 0) for i in results.get("smoke_pass", [])) \
        + sum(i.get("duration_s", 0) for i in results.get("smoke_fail", []))

    linters = normalize_lint(lint) if lint else []
    lint_findings = sum(e.get("total", len(e["findings"])) for e in linters)

    verdict_cls = "good" if ok else "bad"
    verdict = "READY TO MERGE" if ok else "BLOCKED — FIX REQUIRED"
    sub = ("All manifests valid, all smoke tests passed." if ok else
           f"{n_fail} smoke test(s) failed, {n_invalid} invalid manifest(s).")

    chips = []
    for key, label in (("sha", "commit"), ("ref", "ref"), ("run_url", "run")):
        val = meta.get(key)
        if not val:
            continue
        if key == "run_url":
            chips.append(f'<a class="chip" href="{esc(val)}">view run ↗</a>')
        elif key == "sha":
            chips.append(f'<span class="chip mono">{esc(val[:10])}</span>')
        else:
            chips.append(f'<span class="chip">{esc(val)}</span>')

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta.get("title", "Agent Tools — CI Report"))}</title>
<style>
:root {{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c2330; --border:#2d333d;
  --text:#e6edf3; --muted:#8b949e;
  --green:#2ea043; --green-bg:#12261e; --red:#f85149; --red-bg:#2d1215;
  --amber:#d29922; --amber-bg:#271e10; --blue:#58a6ff;
}}
* {{ box-sizing:border-box; margin:0; padding:0 }}
body {{ background:var(--bg); color:var(--text);
  font:15px/1.55 -apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  padding:2.5rem 1rem }}
.wrap {{ max-width:1060px; margin:0 auto }}
header {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:.75rem;
  margin-bottom:1.4rem }}
h1 {{ font-size:1.5rem; font-weight:700; letter-spacing:-.01em }}
.chips {{ display:flex; gap:.5rem; flex-wrap:wrap }}
.chip {{ background:var(--panel2); border:1px solid var(--border);
  border-radius:999px; padding:.15rem .7rem; font-size:.78rem; color:var(--muted);
  text-decoration:none }}
a.chip {{ color:var(--blue) }}
.mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace }}
.verdict {{ border-radius:14px; padding:1.3rem 1.6rem; margin-bottom:1.4rem;
  border:1px solid }}
.verdict.good {{ background:var(--green-bg); border-color:#1f6b34 }}
.verdict.bad  {{ background:var(--red-bg);   border-color:#8e2f2f }}
.verdict h2 {{ font-size:1.25rem; letter-spacing:.02em }}
.verdict.good h2 {{ color:#56d364 }} .verdict.bad h2 {{ color:#ff7b72 }}
.verdict p {{ color:var(--muted); margin-top:.25rem }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:.8rem; margin-bottom:1.6rem }}
.card {{ background:var(--panel); border:1px solid var(--border);
  border-radius:12px; padding:.9rem 1rem }}
.card .num {{ font-size:1.7rem; font-weight:700 }}
.card .lbl {{ font-size:.75rem; color:var(--muted); text-transform:uppercase;
  letter-spacing:.06em }}
.num.green {{ color:#56d364 }} .num.red {{ color:#ff7b72 }}
.num.amber {{ color:#e3b341 }} .num.blue {{ color:var(--blue) }}
.num {{ color:var(--text) }}
section {{ background:var(--panel); border:1px solid var(--border);
  border-radius:12px; padding:1.2rem 1.4rem; margin-bottom:1.4rem }}
section h2 {{ font-size:1.05rem; margin-bottom:.9rem }}
section h3 {{ font-size:.95rem; margin:1rem 0 .5rem }}
table {{ width:100%; border-collapse:collapse; font-size:.88rem }}
th {{ text-align:left; color:var(--muted); font-weight:600; font-size:.72rem;
  text-transform:uppercase; letter-spacing:.06em;
  border-bottom:1px solid var(--border); padding:.35rem .5rem }}
td {{ padding:.42rem .5rem; border-bottom:1px solid #21262d;
  vertical-align:top }}
td.tool {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace }}
td.dur {{ color:var(--muted); white-space:nowrap }}
td.loc {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  white-space:nowrap; color:var(--muted) }}
.badge {{ display:inline-block; border-radius:6px; padding:.08rem .55rem;
  font-size:.72rem; font-weight:700; letter-spacing:.05em }}
.badge.pass {{ background:var(--green-bg); color:#56d364 }}
.badge.fail,.badge.invalid {{ background:var(--red-bg); color:#ff7b72 }}
.badge.skip,.badge.none {{ background:var(--panel2); color:var(--muted);
  border:1px solid var(--border) }}
.count {{ color:var(--muted); font-weight:400; font-size:.85rem;
  margin-left:.4rem }}
.lvl.error {{ color:#ff7b72 }} .lvl.warning {{ color:#e3b341 }}
.lvl.note,.lvl.info,.lvl.style {{ color:var(--muted) }}
.code {{ color:var(--blue); font-family:ui-monospace,monospace; font-size:.8em }}
details summary {{ cursor:pointer; color:var(--blue); font-size:.82rem }}
pre {{ background:var(--bg); border:1px solid var(--border); border-radius:8px;
  padding:.7rem .9rem; margin-top:.5rem; overflow:auto; font-size:.78rem;
  color:#c9d1d9; white-space:pre-wrap }}
.muted {{ color:var(--muted); font-weight:400 }}
footer {{ color:var(--muted); font-size:.78rem; text-align:center;
  margin-top:2rem }}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(meta.get("title", "Agent Tools — CI Report"))}</h1>
  <div class="chips">{"".join(chips)}</div>
</header>
<div class="verdict {verdict_cls}"><h2>{verdict}</h2><p>{esc(sub)}</p></div>
<div class="cards">
  <div class="card"><div class="num green">{n_pass}</div><div class="lbl">smoke passed</div></div>
  <div class="card"><div class="num red">{n_fail}</div><div class="lbl">smoke failed</div></div>
  <div class="card"><div class="num red">{n_invalid}</div><div class="lbl">invalid manifests</div></div>
  <div class="card"><div class="num amber">{n_skip}</div><div class="lbl">skipped</div></div>
  <div class="card"><div class="num">{n_none}</div><div class="lbl">no smoke</div></div>
  <div class="card"><div class="num blue">{lint_findings}</div><div class="lbl">lint findings</div></div>
</div>
<section>
<h2>Smoke tests <span class="count">{n_valid} tools · {duration:.1f}s total</span></h2>
<table><thead><tr><th>tool</th><th>status</th><th>duration</th><th></th></tr></thead>
<tbody>
{build_rows(results)}
</tbody></table>
</section>
{build_lint_section(linters)}
<footer>generated {esc(generated)} · selftest render_report.py</footer>
</div></body></html>
"""


def render_markdown(results: dict, lint: dict | None) -> str:
    ok = bool(results.get("ok"))
    lines = ["## CI — Tool Smoke Tests", ""]
    lines.append("### ✅ READY TO MERGE" if ok else "### ❌ BLOCKED — failures present")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| Smoke passed | {len(results.get('smoke_pass', []))} |")
    lines.append(f"| Smoke failed | {len(results.get('smoke_fail', []))} |")
    lines.append(f"| Invalid manifests | {len(results.get('invalid', []))} |")
    lines.append(f"| Skipped | {len(results.get('skipped', []))} |")
    lines.append(f"| No smoke test | {len(results.get('no_smoke', []))} |")
    fails = results.get("smoke_fail", []) + [
        {"tool": i["tool"], "stderr": "; ".join(i.get("errors", []))}
        for i in results.get("invalid", [])
    ]
    if fails:
        lines += ["", "**Failures:**", ""]
        for f in fails:
            lines.append(f"- `{f['tool']}`")
    if lint:
        total = sum(e.get("total", 0) for e in lint.get("linters", []))
        lines += ["", f"_Lint: {total} finding(s) (non-blocking)._"]
    lines += ["", "📄 Full HTML report: download the **`ci-report`** artifact."]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("results", help="selftest JSON output path, or '-' for stdin")
    p.add_argument("--lint", metavar="PATH", help="lint JSON from run_lint.py")
    p.add_argument("--out", metavar="PATH", default="report.html")
    p.add_argument("--md-out", metavar="PATH", help="also write a Markdown summary")
    p.add_argument("--sha", help="commit SHA shown in the report header")
    p.add_argument("--ref", help="git ref shown in the report header")
    p.add_argument("--run-url", help="link to the CI run")
    p.add_argument("--title", help="report title")
    args = p.parse_args()
    meta = {k: v for k, v in
            vars(args).items() if k in ("sha", "ref", "run_url", "title") and v}

    raw = sys.stdin.read() if args.results == "-" else Path(args.results).read_text()
    results = json.loads(raw)
    lint = json.loads(Path(args.lint).read_text()) if args.lint and Path(args.lint).exists() else None

    Path(args.out).write_text(render_html(results, lint, meta), encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(render_markdown(results, lint), encoding="utf-8")
    print(json.dumps({"report": str(Path(args.out).resolve()),
                      "ok": bool(results.get("ok"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
