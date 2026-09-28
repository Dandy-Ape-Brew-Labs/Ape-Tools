"""Jupyter notebook (.ipynb) manipulation without a running kernel —
read/edit cells, inspect outputs, list structure. JSON document ops.

  nb_tool.py list <nb>                     # cell index/type/preview
  nb_tool.py read <nb> [--cell N]          # source (all or one)
  nb_tool.py outputs <nb> [--cell N]       # rendered outputs
  nb_tool.py set <nb> --cell N --text ...  # replace source
  nb_tool.py add <nb> --type code|markdown --text ... [--at N]
  nb_tool.py delete <nb> --cell N
  nb_tool.py clear-outputs <nb>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def load(path: str) -> tuple[Path, dict]:
    p = Path(path)
    if not p.is_file() or p.suffix != ".ipynb":
        agentlib.die(f"not a notebook: {path}", 2)
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        agentlib.die(f"corrupt notebook JSON: {exc}", 2)


def save(path: Path, nb: dict) -> None:
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")


def source_text(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def get_cell(nb: dict, n: int) -> dict:
    cells = nb.get("cells", [])
    if not 0 <= n < len(cells):
        agentlib.die(f"cell {n} out of range (0..{len(cells)-1})", 2)
    return cells[n]


def text_arg(args) -> str:
    if args.text is not None:
        return args.text
    return sys.stdin.read()


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("list", "read", "outputs"):
        s = sub.add_parser(name); s.add_argument("nb")
        s.add_argument("--cell", type=int)
    s = sub.add_parser("set"); s.add_argument("nb")
    s.add_argument("--cell", type=int, required=True)
    s.add_argument("--text")
    s = sub.add_parser("add"); s.add_argument("nb")
    s.add_argument("--type", choices=["code", "markdown", "raw"],
                   required=True)
    s.add_argument("--text"); s.add_argument("--at", type=int)
    s = sub.add_parser("delete"); s.add_argument("nb")
    s.add_argument("--cell", type=int, required=True)
    s = sub.add_parser("clear-outputs"); s.add_argument("nb")
    args = p.parse_args()

    path, nb = load(args.nb)
    cells = nb.get("cells", [])

    if args.cmd == "list":
        agentlib.emit([
            {"index": i, "type": c.get("cell_type"),
             "lines": source_text(c).count("\n") + 1,
             "preview": source_text(c).strip().splitlines()[0][:80]
                        if source_text(c).strip() else ""}
            for i, c in enumerate(cells)])
        return 0

    if args.cmd == "read":
        if args.cell is not None:
            print(source_text(get_cell(nb, args.cell)), end="")
        else:
            for i, c in enumerate(cells):
                print(f"# %% [{i}] {c.get('cell_type')}")
                print(source_text(c))
        return 0

    if args.cmd == "outputs":
        def render(c):
            out = []
            for o in c.get("outputs", []):
                if "text" in o:
                    t = o["text"]
                elif "data" in o and "text/plain" in o["data"]:
                    t = o["data"]["text/plain"]
                elif "ename" in o:
                    t = f"{o['ename']}: {o.get('evalue','')}"
                else:
                    t = f"<{o.get('output_type','?')}>"
                out.append("".join(t) if isinstance(t, list) else t)
            return out
        if args.cell is not None:
            c = get_cell(nb, args.cell)
            agentlib.emit({"cell": args.cell,
                           "execution_count": c.get("execution_count"),
                           "outputs": render(c)})
        else:
            agentlib.emit([{"cell": i,
                            "execution_count": c.get("execution_count"),
                            "outputs": render(c)}
                           for i, c in enumerate(cells)
                           if c.get("outputs")])
        return 0

    if args.cmd == "set":
        c = get_cell(nb, args.cell)
        c["source"] = text_arg(args).splitlines(keepends=True)
        save(path, nb)
        agentlib.emit({"updated": args.cell})
        return 0

    if args.cmd == "add":
        new = {"cell_type": args.type, "metadata": {},
               "source": text_arg(args).splitlines(keepends=True)}
        if args.type == "code":
            new.update({"execution_count": None, "outputs": []})
        at = args.at if args.at is not None else len(cells)
        cells.insert(max(0, min(at, len(cells))), new)
        nb["cells"] = cells
        save(path, nb)
        agentlib.emit({"added_at": at})
        return 0

    if args.cmd == "delete":
        cells.pop(args.cell) if 0 <= args.cell < len(cells) else \
            agentlib.die(f"cell {args.cell} out of range", 2)
        nb["cells"] = cells
        save(path, nb)
        agentlib.emit({"deleted": args.cell})
        return 0

    if args.cmd == "clear-outputs":
        n = 0
        for c in cells:
            if c.get("cell_type") == "code" and c.get("outputs"):
                c["outputs"] = []
                c["execution_count"] = None
                n += 1
        save(path, nb)
        agentlib.emit({"cleared": n})
        return 0


if __name__ == "__main__":
    sys.exit(main())
