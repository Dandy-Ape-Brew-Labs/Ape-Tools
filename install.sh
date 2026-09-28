#!/usr/bin/env bash
# install.sh — install the Ape Tools toolbox.
#
#   ./install.sh                     in-place setup of this checkout
#   ./install.sh --prefix DIR        lean copy-install into DIR
#   curl -fsSL <raw>/install.sh | bash        fetch + install to the default prefix
#   curl ... | bash -s -- --prefix DIR        fetch + install to DIR
#
# The installed payload is deliberately lean — tools/, lib/, lockfiles and
# docs only. No tests, no .git, no local notes: an agent pointed at the
# prefix sees runnable tools and nothing else.
#
# Env overrides:
#   APE_TOOLS_REPO    git URL to fetch in pipe mode
#                     (default: https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools.git)
#   APE_TOOLS_PREFIX  default install prefix (default: ~/.local/opt/ape-tools)
set -euo pipefail

REPO_URL="${APE_TOOLS_REPO:-https://github.com/Dandy-Ape-Brew-Labs/Ape-Tools.git}"
DEFAULT_PREFIX="${APE_TOOLS_PREFIX:-$HOME/.local/opt/ape-tools}"

# Discovery/dispatcher tools are force-included even in --tools subsets —
# without them the installed copy can't list or dispatch its own tools.
ALWAYS_TOOLS="ape list-tools tool-search"

# Root-level files that belong in an install payload.
PAYLOAD_FILES="pyproject.toml uv.lock package.json package-lock.json README.md AGENTS.md SKILL.md install.sh"

PREFIX="" TOOLS="" UPDATE=0 DEPS=1 NODE=1 OBSCURA=0 TESTS=0 QUIET=0

usage() {
  sed -n '2,16p' "${BASH_SOURCE[0]:-$0}" >&2 || true
  cat >&2 <<'EOF'
Flags:
  --prefix DIR    Install to DIR instead of running in place
  --tools a,b,c   Install a subset (ape/list-tools/tool-search are always included)
  --update        Replace the managed payload at an existing prefix
  --no-deps       Skip uv sync and npm ci entirely
  --no-node       Skip npm ci (keeps uv sync)
  --obscura       Also download the Obscura browser binary into vendor/
  --with-tests    Include tests/ in a copy-install (off by default — keeps
                  the installed tree out of agent context)
  --quiet         Suppress progress output on stderr
  -h, --help      This help
EOF
}

die() { echo "error: $*" >&2; exit 1; }
say() { [ "$QUIET" -eq 0 ] && echo "$*" >&2 || true; }
need() { command -v "$1" >/dev/null 2>&1 || die "required binary '$1' not found on PATH"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix)     [ $# -ge 2 ] || die "--prefix needs a directory"; PREFIX="$2"; shift 2 ;;
    --tools)      [ $# -ge 2 ] || die "--tools needs a list"; TOOLS="$2"; shift 2 ;;
    --update)     UPDATE=1; shift ;;
    --no-deps)    DEPS=0; NODE=0; shift ;;
    --no-node)    NODE=0; shift ;;
    --obscura)    OBSCURA=1; shift ;;
    --with-tests) TESTS=1; shift ;;
    --quiet)      QUIET=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage; die "unknown option: $1" ;;
  esac
done

copy_payload() {
  local src="$1" dst="$2"
  mkdir -p "$dst/tools" "$dst/lib"
  if [ -n "$TOOLS" ]; then
    local t
    for t in $ALWAYS_TOOLS $(printf '%s' "$TOOLS" | tr ',' ' '); do
      if [ -d "$src/tools/$t" ]; then
        cp -R "$src/tools/$t" "$dst/tools/"
      else
        say "warn: no tool dir '$t' — skipped"
      fi
    done
  else
    cp -R "$src/tools/." "$dst/tools/"
  fi
  cp -R "$src/lib/." "$dst/lib/"
  local f
  for f in $PAYLOAD_FILES; do
    [ -f "$src/$f" ] && cp "$src/$f" "$dst/$f" || true
  done
  [ "$TESTS" -eq 1 ] && cp -R "$src/tests" "$dst/tests/"
  find "$dst" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
}

# Remove only paths this installer manages — never the whole prefix.
wipe_managed() {
  local dst="$1" f
  rm -rf "$dst/tools" "$dst/lib" "$dst/tests" "$dst/bin"
  for f in $PAYLOAD_FILES; do rm -f "$dst/$f"; done
}

setup_root() {
  local root="$1"
  if [ "$DEPS" -eq 1 ]; then
    if command -v uv >/dev/null 2>&1; then
      if (cd "$root" && uv sync --frozen >&2); then
        say "python deps: uv sync --frozen ok"
      else
        say "warn: uv sync failed — dependency tools will not run until it succeeds"
      fi
    else
      say "warn: uv not found — skipping python deps (https://docs.astral.sh/uv/)"
    fi
    if [ "$NODE" -eq 1 ] && [ -f "$root/package.json" ]; then
      if command -v npm >/dev/null 2>&1; then
        if (cd "$root" && npm ci --no-audit --no-fund >&2); then
          say "node deps: npm ci ok"
        else
          say "warn: npm ci failed — node tools (obscura-browse, web-browser) need node_modules"
        fi
      else
        say "warn: npm not found — skipping node deps"
      fi
    fi
  fi
  if [ "$OBSCURA" -eq 1 ] && [ -f "$root/tools/obscura-browse/install.sh" ]; then
    bash "$root/tools/obscura-browse/install.sh" || say "warn: obscura install failed"
  fi
  mkdir -p "$root/bin"
  cat > "$root/bin/ape" <<EOF
#!/usr/bin/env bash
exec python3 "$root/tools/ape/ape.py" "\$@"
EOF
  chmod +x "$root/bin/ape"
}

summary() {
  local root="$1" ntools
  ntools=$(find "$root/tools" -mindepth 2 -name tool.json | wc -l | tr -d ' ')
  cat <<EOF
{
  "installed": "$root",
  "tools": $ntools,
  "bin": "$root/bin/ape",
  "state": "\${AGENT_TOOLS_HOME:-~/.local/share/agent-tools}"
}
EOF
  say ""
  say "Run any tool:        $root/bin/ape <tool> [args]"
  say "Tool catalogue:      $root/bin/ape list-tools --format index"
  say "Missing credentials: $root/bin/ape secrets check"
  say "MCP server:          uv run --project $root $root/tools/mcp-serve/mcp_serve.py"
}

# Are we inside a checkout (tools/ + pyproject.toml next to this script)?
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
fi
IN_TREE=0
[ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -d "$SCRIPT_DIR/tools" ] && IN_TREE=1

if [ "$IN_TREE" -eq 1 ] && { [ -z "$PREFIX" ] || [ "$PREFIX" = "$SCRIPT_DIR" ]; }; then
  ROOT="$SCRIPT_DIR"
  say "in-place setup of $ROOT"
  setup_root "$ROOT"
elif [ "$IN_TREE" -eq 1 ]; then
  need python3
  if [ -d "$PREFIX" ]; then
    [ "$UPDATE" -eq 1 ] || die "$PREFIX exists — pass --update to replace the managed payload"
    wipe_managed "$PREFIX"
  fi
  say "copying payload -> $PREFIX"
  copy_payload "$SCRIPT_DIR" "$PREFIX"
  setup_root "$PREFIX"
  summary "$PREFIX"
else
  # Pipe mode: fetch the repo, then copy the lean payload into the prefix.
  need git; need python3
  PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "fetching $REPO_URL"
  git clone --quiet --depth 1 "$REPO_URL" "$TMP/src"
  if [ -d "$PREFIX" ]; then
    [ "$UPDATE" -eq 1 ] || die "$PREFIX exists — pass --update to replace the managed payload"
    wipe_managed "$PREFIX"
  fi
  copy_payload "$TMP/src" "$PREFIX"
  setup_root "$PREFIX"
  summary "$PREFIX"
fi
