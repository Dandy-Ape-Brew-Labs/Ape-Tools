"""Structural Python code search via stdlib ast — finds defs, classes,
imports, calls, and attribute uses by name pattern, not text.

  ast_search.py defs <path> [--name REGEX]       # functions+classes
  ast_search.py imports <path> [--name REGEX]
  ast_search.py calls <path> --name REGEX        # call sites
  ast_search.py symbols <path>                   # top-level outline
  ast_search.py refs <path> --name REGEX         # all Name/attr refs

<path> may be a file or directory (walks *.py). Emits JSON matches
{file, line, col, kind, name, context}.
"""

import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def py_files(path: str) -> list[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.is_dir():
        agentlib.die(f"no such path: {path}", 2)
    return sorted(agentlib.iter_files(p, ["*.py"]))


def parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        agentlib.warn(f"skipping {path}: {exc}")
        return None


def call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = []
        while isinstance(f, ast.Attribute):
            parts.append(f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.append(f.id)
        return ".".join(reversed(parts))
    return None


def collect(path: Path, tree: ast.AST, mode: str,
            pat: re.Pattern | None) -> list[dict]:
    out = []
    src = path.read_text(encoding="utf-8", errors="replace").splitlines()

    def ctx(line: int) -> str:
        return src[line - 1].strip() if 0 < line <= len(src) else ""

    for node in ast.walk(tree):
        rec = None
        if mode == "defs" and isinstance(node, (ast.FunctionDef,
                                                ast.AsyncFunctionDef,
                                                ast.ClassDef)):
            kind = ("class" if isinstance(node, ast.ClassDef)
                    else "async def" if isinstance(node, ast.AsyncFunctionDef)
                    else "def")
            rec = (kind, node.name)
        elif mode == "imports" and isinstance(node, (ast.Import,
                                                     ast.ImportFrom)):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [(node.module or "") + ":" + a.name
                           for a in node.names])
            for n in names:
                if not pat or pat.search(n):
                    rec = ("import", n)
                    out.append({"file": str(path), "line": node.lineno,
                                "col": node.col_offset, "kind": rec[0],
                                "name": rec[1], "context": ctx(node.lineno)})
            continue
        elif mode == "calls" and isinstance(node, ast.Call):
            name = call_name(node)
            if name:
                rec = ("call", name)
        elif mode == "refs" and isinstance(node, (ast.Name,
                                                  ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            rec = ("ref", name)
        elif mode == "symbols" and node is tree:
            continue
        if rec and (not pat or pat.search(rec[1])):
            out.append({"file": str(path), "line": node.lineno,
                        "col": node.col_offset, "kind": rec[0],
                        "name": rec[1], "context": ctx(node.lineno)})

    if mode == "symbols":
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "def"
                end = getattr(node, "end_lineno", node.lineno)
                out.append({"file": str(path), "line": node.lineno,
                            "end": end, "kind": kind, "name": node.name,
                            "lines": end - node.lineno + 1})
    return out


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    s = p.add_subparsers(dest="cmd", required=True)
    for mode in ("defs", "imports", "calls", "symbols", "refs"):
        sp = s.add_parser(mode)
        sp.add_argument("path")
        if mode != "symbols":
            sp.add_argument("--name", help="regex filter")
    args = p.parse_args()

    pat = re.compile(args.name) if getattr(args, "name", None) else None
    if args.cmd in ("calls", "refs") and pat is None:
        agentlib.die(f"{args.cmd} requires --name", 2)

    results = []
    for f in py_files(args.path):
        tree = parse(f)
        if tree is not None:
            results += collect(f, tree, args.cmd, pat)
    agentlib.emit(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
