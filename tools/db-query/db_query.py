"""Query databases: SQLite natively (stdlib), Postgres/MySQL via
psql/mysql CLIs when present. JSON rows on stdout.

  db_query.py --db file.db --sql "SELECT * FROM t LIMIT 5"
  db_query.py --db file.db tables
  db_query.py --db file.db schema [table]
  db_query.py --url postgresql://... --sql "..."   # needs psql
  db_query.py --url mysql://...      --sql "..."   # needs mysql
"""

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def sqlite_query(db: str, sql: str) -> list[dict]:
    if not Path(db).is_file() and db != ":memory:":
        agentlib.die(f"no such database: {db}", 2)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        conn.commit()
        return rows
    except sqlite3.Error as exc:
        agentlib.die(f"sqlite error: {exc}", 1)
    finally:
        conn.close()


def cli_query(url: str, sql: str) -> int:
    scheme = urlparse(url).scheme
    tool = "psql" if scheme.startswith("postgres") else \
           "mysql" if scheme.startswith("mysql") else None
    if tool is None:
        agentlib.die(f"unsupported scheme '{scheme}' "
                     "(sqlite file, postgresql://, mysql://)", 2)
    if not shutil.which(tool):
        agentlib.die(f"'{tool}' CLI not installed", 2)
    r = subprocess.run([tool, url, "-c", sql] if tool == "mysql"
                       else [tool, url, "-c", sql, "--tuples-only",
                             "--no-align"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        agentlib.die(r.stderr.strip(), 1)
    print(r.stdout, end="")
    return 0


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", help="sqlite file path or :memory:")
    src.add_argument("--url", help="postgresql:// or mysql:// DSN")
    p.add_argument("--sql", help="query text, or '-' for stdin")
    p.add_argument("--tables", action="store_true",
                   help="list tables (sqlite)")
    p.add_argument("--schema", nargs="?", const="",
                   help="table DDL (sqlite; all tables if omitted)")
    p.add_argument("--limit", type=int, help="wrap SELECT with LIMIT")
    args = p.parse_args()

    sql = args.sql
    if sql == "-":
        sql = sys.stdin.read()

    if args.url:
        if not sql:
            agentlib.die("--url requires --sql", 2)
        return cli_query(args.url, sql)

    if args.tables:
        sql = ("SELECT name, type FROM sqlite_master "
               "WHERE type IN ('table','view') ORDER BY name")
        agentlib.emit(sqlite_query(args.db, sql))
        return 0

    if args.schema is not None:
        q = ("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
             + (f" AND name = '{args.schema}'" if args.schema else "")
             + " ORDER BY name")
        rows = sqlite_query(args.db, q)
        print("\n\n".join(r["sql"] + ";" for r in rows))
        return 0

    if not sql:
        agentlib.die("need --sql, --tables, or --schema", 2)
    if args.limit and "limit" not in sql.lower():
        sql = f"SELECT * FROM ({sql}) LIMIT {int(args.limit)}"
    agentlib.emit(sqlite_query(args.db, sql))
    return 0


if __name__ == "__main__":
    sys.exit(main())
