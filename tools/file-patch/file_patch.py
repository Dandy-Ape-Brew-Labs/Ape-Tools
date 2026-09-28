"""Apply a Codex-style apply_patch envelope to one or more files.

Patch arrives on stdin or via --file. Grammar:

    *** Begin Patch
    *** Add File: path
    +line
    *** Update File: path
    @@ optional anchor text
    -removed
    context (space prefix or bare)
    +added
    *** Move to: new-path        (only inside Update)
    *** Delete File: path
    *** End Patch

Relative paths resolve against --cwd (default: current dir). Use --dry-run
to preview. Designed for multi-file changes; for a single targeted edit,
file-edit is simpler.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def parse_patch(text: str) -> list[dict]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "*** Begin Patch":
        agentlib.die("patch must start with '*** Begin Patch'", 2)
    ops, i = [], 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "*** End Patch":
            break
        for kw, kind in (("*** Add File:", "add"),
                         ("*** Update File:", "update"),
                         ("*** Delete File:", "delete")):
            if line.startswith(kw):
                op = {"op": kind, "path": line[len(kw):].strip(), "lines": []}
                ops.append(op)
                break
        else:
            if line.startswith("*** Move to:"):
                if not ops or ops[-1]["op"] != "update":
                    agentlib.die("'*** Move to:' must follow '*** Update File:'", 2)
                ops[-1]["move_to"] = line[len("*** Move to:"):].strip()
            elif ops and ops[-1]["op"] in ("add", "update"):
                ops[-1]["lines"].append(line)
            elif line.strip():
                agentlib.die(f"unexpected patch line: {line!r}", 2)
        i += 1
    else:
        agentlib.die("patch missing '*** End Patch'", 2)
    return ops


def find_seq(lines: list[str], seq: list[str], start: int) -> int | None:
    if not seq:
        return start
    for i in range(start, len(lines) - len(seq) + 1):
        if lines[i:i + len(seq)] == seq:
            return i
    return None


def apply_update(original: list[str], hunks: list[tuple[str | None, list]]) -> list[str]:
    out, cursor = list(original), 0
    for anchor, ops in hunks:
        old_seq = [t for tag, t in ops if tag in ("ctx", "del")]
        new_seq = [t for tag, t in ops if tag in ("ctx", "add")]
        search_from = cursor
        if anchor == "EOF":
            search_from = max(0, len(out) - len(old_seq))
        elif anchor:
            hit = next(
                (i for i in range(cursor, len(out)) if anchor in out[i]), None)
            if hit is None:
                agentlib.die(f"anchor not found: {anchor!r}")
            search_from = hit
        pos = find_seq(out, old_seq, search_from)
        if pos is None:
            agentlib.die(
                "hunk does not match file content "
                f"(searched from line {search_from + 1}):\n" +
                "\n".join(f"  {l!r}" for l in old_seq[:5]))
        out[pos:pos + len(old_seq)] = new_seq
        cursor = pos + len(new_seq)
    return out


def split_hunks(raw: list[str]) -> list[tuple[str | None, list]]:
    hunks, anchor, ops = [], None, []
    for line in raw:
        if line.startswith("@@"):
            if ops:
                hunks.append((anchor, ops))
                anchor, ops = None, []
            anchor = line[2:].strip() or None
        elif line.strip() == "*** End of File":
            anchor = "EOF"
        elif line.startswith("+"):
            ops.append(("add", line[1:]))
        elif line.startswith("-"):
            ops.append(("del", line[1:]))
        else:
            ops.append(("ctx", line[1:] if line.startswith(" ") else line))
    if ops or anchor:
        hunks.append((anchor, ops))
    return hunks


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("--file", help="patch file (default: stdin)")
    p.add_argument("--cwd", default=".", help="root for relative paths")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    ops = parse_patch(text)
    root = Path(args.cwd).resolve()
    changes = []

    for op in ops:
        rel = Path(op["path"])
        if rel.is_absolute():
            agentlib.die(f"absolute path not allowed: {rel}", 2)
        path = (root / rel).resolve()
        if not str(path).startswith(str(root) + "/") and path != root:
            agentlib.die(f"path escapes --cwd: {rel}", 2)

        if op["op"] == "add":
            if path.exists() and not args.dry_run:
                agentlib.die(f"Add File target exists: {rel}")
            content = "".join(l[1:] + "\n" for l in op["lines"] if l.startswith("+"))
            changes.append({"op": "add", "path": str(path)})
            if not args.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

        elif op["op"] == "delete":
            if not path.exists():
                agentlib.die(f"Delete File target missing: {rel}")
            changes.append({"op": "delete", "path": str(path)})
            if not args.dry_run:
                path.unlink()

        else:  # update
            if not path.exists():
                agentlib.die(f"Update File target missing: {rel}")
            original = path.read_text(encoding="utf-8").splitlines()
            updated = apply_update(original, split_hunks(op["lines"]))
            changes.append({"op": "update", "path": str(path)})
            if not args.dry_run:
                path.write_text("\n".join(updated) + "\n", encoding="utf-8")
            if "move_to" in op:
                dest = (root / op["move_to"]).resolve()
                changes.append({"op": "move", "path": str(path), "to": str(dest)})
                if not args.dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dest))

    agentlib.emit({"dry_run": args.dry_run, "changes": changes})
    return 0


if __name__ == "__main__":
    sys.exit(main())
