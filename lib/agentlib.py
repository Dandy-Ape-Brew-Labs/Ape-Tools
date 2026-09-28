"""Shared helpers for agent-tools scripts.

Every tool inserts the repo's ``lib/`` directory on sys.path and imports this
module::

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
    import agentlib

Contract enforced here: results on stdout (JSON), diagnostics on stderr,
non-interactive, fail fast with actionable errors.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = Path("~/.local/share/agent-tools").expanduser()

MAX_READ_LINES = 2000
MAX_READ_BYTES = 256 * 1024
TRUNC_MARKER = "\n...[truncated, {total} total]"


def emit(obj) -> None:
    """Print a JSON result on stdout."""
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def emit_text(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def die(msg: str, code: int = 1) -> "NoReturn":
    """Print an actionable error on stderr and exit."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def state_dir(*parts: str) -> Path:
    """Resolve the agent-tools state dir (AGENT_TOOLS_HOME or XDG default)."""
    root = Path(os.environ.get("AGENT_TOOLS_HOME", str(DEFAULT_STATE))).expanduser()
    path = root.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_file(*parts: str) -> Path:
    """Like state_dir but treats the last part as a file path."""
    *dirs, name = parts
    return state_dir(*dirs) / name


def truncate_text(text: str, max_bytes: int = MAX_READ_BYTES) -> tuple[str, bool]:
    """Cap text at max_bytes, appending a truncation marker."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text, False
    total = len(data)
    cut = data[:max_bytes].decode("utf-8", errors="ignore")
    return cut + TRUNC_MARKER.format(total=_human(total)), True


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n}B"


def head_tail(text: str, max_bytes: int = MAX_READ_BYTES) -> tuple[str, bool]:
    """Truncate keeping head and tail (shell-output style)."""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text, False
    half = max_bytes // 2
    head = data[:half].decode("utf-8", errors="ignore")
    tail = data[-half:].decode("utf-8", errors="ignore")
    total = len(data)
    marker = f"\n...[truncated middle, {_human(total)} total]...\n"
    return head + marker + tail, True


def is_binary(path: Path, sniff: int = 8192) -> bool:
    """Detect binary files by NUL bytes in the first chunk."""
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(sniff)
    except OSError:
        return False


def guess_mime(path: Path) -> str:
    """Minimal extension/magic mime guess (stdlib-only)."""
    try:
        with path.open("rb") as fh:
            head = fh.read(16)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if head[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if head.startswith(b"%PDF"):
            return "application/pdf"
        if head.startswith(b"PK\x03\x04"):
            return "application/zip"
        if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            return "image/webp"
    except OSError:
        pass
    import mimetypes

    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def run_cmd(
    argv: list[str],
    cwd: str | Path | None = None,
    timeout: float | None = None,
    env: dict | None = None,
    input_text: str | None = None,
) -> dict:
    """Run argv, capture output. Returns {exit, stdout, stderr, duration_ms}."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            timeout=timeout,
            env={**os.environ, **(env or {})},
            input=input_text,
            capture_output=True,
            text=True,
        )
        return {
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit": 124,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": f"timed out after {timeout}s",
            "duration_ms": int((time.monotonic() - start) * 1000),
            "timed_out": True,
        }
    except FileNotFoundError:
        die(f"command not found: {argv[0]}")


DEFAULT_EXCLUDES = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv",
    "__pycache__", "dist", "vendor", ".mypy_cache", ".pytest_cache",
}


def iter_files(
    root: str | Path,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    respect_gitignore: bool = True,
) -> list[Path]:
    """Walk root yielding files matching include/exclude fnmatch globs.

    '*' matches across separators (agent-friendly loose matching). Directory
    traversal prunes DEFAULT_EXCLUDES; when root is a git repo, `git
    check-ignore` filters the result.
    """
    import fnmatch

    root = Path(root).resolve()
    includes = includes or ["*"]
    excludes = excludes or []
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in DEFAULT_EXCLUDES)
        rel_dir = Path(dirpath).relative_to(root)
        for name in filenames:
            rel = str(rel_dir / name) if str(rel_dir) != "." else name
            if not any(
                fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
                for pat in includes
            ):
                continue
            if any(
                fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
                for pat in excludes
            ):
                continue
            collected.append(root / rel)
    if respect_gitignore and collected and (root / ".git").exists() and which("git"):
        rels = [str(p.relative_to(root)) for p in collected]
        res = run_cmd(
            ["git", "-C", str(root), "check-ignore", "--stdin"],
            input_text="\n".join(rels) + "\n",
        )
        ignored = set(res["stdout"].split())
        collected = [p for p, r in zip(collected, rels) if r not in ignored]
    return collected


def which(name: str) -> str | None:
    """Locate a binary on PATH."""
    from shutil import which as _which

    return _which(name)


def require_bin(name: str, hint: str | None = None) -> str:
    """Return binary path or die with an install hint."""
    path = which(name)
    if path is None:
        die(f"required binary '{name}' not found on PATH. {hint or 'Install it and retry.'}")
    return path


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def arg_parser(description: str):
    """Standard argparse.ArgumentParser with our conventions."""
    import argparse

    return argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
