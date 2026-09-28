# ape

One entry point for the whole toolbox:

```sh
ape <tool> [args...]
ape --list                    # tool index (list-tools --format index)
```

`ape` reads `tools/<name>/tool.json`, picks the interpreter from the
manifest (`node` for node tools, `uv run --project <root>` for Python
tools with dependencies, `python3` for stdlib-only tools, `bash` for
shell tools) and `exec`s the entrypoint. Arguments pass through
verbatim; the process is replaced, so the tool's stdout/stderr/exit code
is what you get.

All paths resolve against the install root (the script's own location),
so `ape` works from any working directory — the manifest `run` fields
are repo-relative and would otherwise need a `cd` first.

## In an installed prefix

`install.sh` generates `<prefix>/bin/ape` — a two-line shim that execs
this script. Put `<prefix>/bin` on PATH and the whole toolbox is one
word away:

```sh
ape file-read /etc/hosts --head 5
ape secrets check
```
