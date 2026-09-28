"""Scan a tree for personal data and secrets that shouldn't be committed —
private/loopback-external IPs, home-directory paths, emails, common token
shapes. Gitignored files are skipped. Hits are reported on stdout as
file:line records; exit 1 when anything is found.

  privacy_scan.py [path]              scan dir (default: repo root)
  privacy_scan.py --patterns FILE     extra patterns (repeatable)

Extra pattern sources, so personal names never need to live in the repo:
  --patterns FILE                     one per line; 'regex:...' for regexes
  $PRIVACY_PATTERNS_FILE              same format (default:
                                      $AGENT_TOOLS_HOME/privacy-patterns.txt)
  $PRIVACY_EXTRA_PATTERNS             newline-separated literals
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")

DOC_RANGES = (
    ipaddress.ip_network("192.0.2.0/24"),    # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("233.252.0.0/24"),  # MCAST-TEST-NET
)

# name, regex — written so this file's own source never matches them.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("home-path", re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\)[\w.-]+")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")),
    ("token", re.compile(
        r"\b(?:sk|ghp|gho|ghu|ghs|ghr|hf|glpat)-[A-Za-z0-9_-]{10,}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{10,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}"
        r"|\bBearer\s+[A-Za-z0-9._~+/=-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("mac", re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")),
]

EMAIL_ALLOW = re.compile(r"@(?:example\.(?:com|org|net)|.*noreply|localhost)\b", re.I)


def is_flagged_ip(text: str) -> bool:
    """True for private/non-public IPv4 that isn't a documentation range."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.is_loopback or str(ip) == "0.0.0.0":
        return False
    if any(ip in net for net in DOC_RANGES):
        return False
    # is_private covers RFC1918, 100.64/10 (CGNAT/Tailscale), 169.254/16.
    return not ip.is_global


def extra_patterns(args) -> list[tuple[str, re.Pattern]]:
    root = Path(os.environ.get("AGENT_TOOLS_HOME", str(agentlib.DEFAULT_STATE)))
    files = [root.expanduser() / "privacy-patterns.txt", *(args.patterns or [])]
    env_file = os.environ.get("PRIVACY_PATTERNS_FILE")
    if env_file:
        files.insert(0, Path(env_file).expanduser())
    out: list[tuple[str, re.Pattern]] = []
    for i, item in enumerate(os.environ.get("PRIVACY_EXTRA_PATTERNS", "").splitlines()):
        if item.strip():
            out.append((f"extra-env:{i}", re.compile(re.escape(item.strip()))))
    for f in files:
        f = Path(f)
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("regex:"):
                out.append((f"extra:{f.name}:{i + 1}", re.compile(line[6:])))
            else:
                out.append((f"extra:{f.name}:{i + 1}", re.compile(re.escape(line))))
    return out


def scan_file(path: Path, patterns) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for m in IPV4_RE.finditer(line):
            if is_flagged_ip(m.group()):
                hits.append({"line": lineno, "kind": "private-ip",
                             "match": m.group(), "text": line.strip()[:160]})
                break
        for kind, rx in patterns:
            m = rx.search(line)
            if not m:
                continue
            if kind == "email" and EMAIL_ALLOW.search(m.group()):
                continue
            hits.append({"line": lineno, "kind": kind,
                         "match": m.group()[:80], "text": line.strip()[:160]})
    return hits


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path", nargs="?", default=str(agentlib.REPO_ROOT),
                   help="directory to scan (default: repo root)")
    p.add_argument("--patterns", action="append", metavar="FILE",
                   help="extra pattern file, one literal or 'regex:...' per line")
    p.add_argument("--include-ignored", action="store_true",
                   help="also scan gitignored files")
    args = p.parse_args()

    root = Path(args.path).expanduser()
    if not root.is_dir():
        agentlib.die(f"not a directory: {root}", 2)

    patterns = PATTERNS + extra_patterns(args)
    files = agentlib.iter_files(
        root, respect_gitignore=not args.include_ignored)

    hits, scanned = [], 0
    for f in files:
        if agentlib.is_binary(f):
            continue
        scanned += 1
        for h in scan_file(f, patterns):
            h["file"] = str(f.relative_to(root))
            hits.append(h)

    agentlib.emit({"ok": not hits, "root": str(root),
                   "scanned": scanned, "hits": hits})
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
