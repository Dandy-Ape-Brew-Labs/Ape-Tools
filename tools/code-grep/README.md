# code-grep

ripgrep-backed content search. Funnel: `fs-glob` (which files) →
`--mode files` (narrow) → `--mode content -C 3` (locate) → `file-read`
a range (understand).

```sh
code_grep.py "def\s+parse_" --type py --mode files
code_grep.py "authenticate" --path src -C 3
code_grep.py "TODO|FIXME" --glob "*.py" --mode count
```

Regex is ripgrep syntax — no look-around; escape literal braces
(`interface\{`). Results cap at 100 (`--max`); paginate with `--offset`.
Requires `rg` on PATH.
