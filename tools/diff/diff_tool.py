"""File/directory diffs — unified output, exit code signals change.

  diff_tool.py old.txt new.txt            # two files
  diff_tool.py dir_a/ dir_b/ --recursive  # two trees
  diff_tool.py a b --context 5 --stat     # summary only

No external dependency on git; uses `diff` for trees and a stdlib
difflib path when only files are compared and `diff` is missing.
Exit 0 = identical, 1 = differences, 2 = error — same as `diff(1)`.
"""

import difflib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def file_diff(a: Path, b: Path, context: int) -> str:
    try:
        ta = a.read_text(errors="replace").splitlines(keepends=True)
        tb = b.read_text(errors="replace").splitlines(keepends=True)
    except OSError as exc:
        agentlib.die(str(exc), 2)
    return "".join(difflib.unified_diff(
        ta, tb, fromfile=str(a), tofile=str(b), n=context))


def run_diff(a: Path, b: Path, context: int, recursive: bool,
             stat: bool) -> tuple[int, str]:
    diff_bin = agentlib.which("diff")
    if diff_bin and (a.is_dir() or b.is_dir()):
        cmd = [diff_bin, "-ru", f"-U{context}", str(a), str(b)]
        if not recursive:
            cmd.remove("-r")
    elif diff_bin:
        cmd = [diff_bin, "-u", f"-U{context}", str(a), str(b)]
    elif a.is_dir() or b.is_dir():
        agentlib.die("directory diffs need the 'diff' binary", 2)
    else:
        out = file_diff(a, b, context)
        return (1 if out else 0), out
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 2:
        agentlib.die(r.stderr.strip() or "diff failed", 2)
    return r.returncode, r.stdout


def summarize(diff_text: str) -> dict:
    files = []
    cur = None
    for line in diff_text.splitlines():
        if line.startswith(("--- ", "diff -")):
            if line.startswith("diff -"):
                parts = line.split()
                cur = {"file": parts[-1], "added": 0, "removed": 0}
                files.append(cur)
            else:
                cur = {"file": line[4:].split("\t")[0],
                       "added": 0, "removed": 0}
                files.append(cur)
        elif cur is not None:
            if line.startswith("+") and not line.startswith("+++"):
                cur["added"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                cur["removed"] += 1
    return {"changed_files": len(files), "files": files}


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("a"); p.add_argument("b")
    p.add_argument("--context", type=int, default=3)
    p.add_argument("--recursive", action="store_true",
                   help="recurse into subdirs (dir compare)")
    p.add_argument("--stat", action="store_true",
                   help="emit JSON change summary instead of the diff")
    args = p.parse_args()
    a, b = Path(args.a), Path(args.b)
    for f in (a, b):
        if not f.exists():
            agentlib.die(f"no such path: {f}", 2)

    code, text = run_diff(a, b, args.context, args.recursive, args.stat)
    if args.stat:
        agentlib.emit(summarize(text))
    else:
        sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
