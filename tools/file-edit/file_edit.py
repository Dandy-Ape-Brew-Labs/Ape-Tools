"""Exact-string replacement editing — the workhorse.

old_string must match the file content exactly (whitespace included) and be
unique unless --replace-all. Copy old_string from a fresh file-read — never
type it from memory, and strip the 'N\\t' line-number prefixes.

Single edit:
  file_edit.py app.py --old "TIMEOUT = 30" --new "TIMEOUT = 60"
Rename everywhere:
  file_edit.py app.py --old "fetchUser" --new "loadUser" --replace-all
Atomic multi-edit (all-or-nothing, applied in order):
  file_edit.py app.py --edits edits.json   # [{"old": "...", "new": "..."}]
Preview:
  file_edit.py app.py --old X --new Y --dry-run
"""

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def apply_edits(text: str, edits: list[dict]) -> tuple[str, list[dict]]:
    """Apply edits in order; raise on any failure (all-or-nothing)."""
    report = []
    for i, e in enumerate(edits):
        old, new = e["old"], e["new"]
        count = text.count(old)
        replace_all = e.get("replace_all", False)
        if count == 0:
            agentlib.die(
                f"edit {i+1}: old_string not found. Re-read the file — whitespace "
                "or tabs differ, or a previous edit in this batch already changed it.", 1)
        if count > 1 and not replace_all:
            agentlib.die(
                f"edit {i+1}: old_string matches {count} locations. Widen context "
                "with 2-3 surrounding lines, or pass --replace-all.", 1)
        text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        report.append({"edit": i + 1, "replacements": count if replace_all else 1})
    return text, report


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path")
    p.add_argument("--old", help="exact string to find")
    p.add_argument("--new", help="replacement string")
    p.add_argument("--edits", help="JSON file or '-' stdin: [{old,new,replace_all?}]")
    p.add_argument("--replace-all", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="print unified diff without writing")
    args = p.parse_args()

    path = Path(args.path)
    if not path.is_file():
        agentlib.die(f"not a file: {path}", 2)

    if args.edits:
        raw = sys.stdin.read() if args.edits == "-" else Path(args.edits).read_text()
        try:
            edits = json.loads(raw)
        except json.JSONDecodeError as exc:
            agentlib.die(f"invalid --edits JSON: {exc}", 2)
        if not isinstance(edits, list) or not all("old" in e and "new" in e for e in edits):
            agentlib.die("--edits must be a JSON array of {old, new, replace_all?}", 2)
    elif args.old is not None and args.new is not None:
        edits = [{"old": args.old, "new": args.new, "replace_all": args.replace_all}]
    else:
        agentlib.die("provide --old/--new or --edits <json>", 2)

    original = path.read_text(encoding="utf-8")
    updated, report = apply_edits(original, edits)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}",
        )
    )
    if args.dry_run:
        agentlib.emit_text(diff if diff else "(no changes)")
        return 0

    path.write_text(updated, encoding="utf-8")
    agentlib.emit({
        "path": str(path.resolve()),
        "edits_applied": len(report),
        "replacements": sum(r["replacements"] for r in report),
        "diff": diff,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
