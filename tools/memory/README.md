# memory

Durable, file-backed memory across sessions — markdown files in
`$AGENT_TOOLS_HOME/memories/`. Mirrors the Anthropic `memory` tool
vocabulary.

```sh
memory.py create prefs.md --text "- prefers uv over pip (2026-09)"
memory.py list
memory.py view prefs.md
memory.py str_replace prefs.md --old "uv over pip" --new "uv for everything"
```

Rules: concise dated facts, not transcripts. Never store secrets or
ephemeral task state. Read `memory.py list` at session start.
