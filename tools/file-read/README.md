# file-read

Read a text file. Output uses `cat -n` style `N\t` prefixes (never part of
the file content). Output is capped (~2000 lines / 256KB); truncation is
reported on stderr — treat a truncated result as incomplete.

## Usage

```sh
file_read.py path/to/file.py                 # whole file (capped)
file_read.py app.py --offset 120 --limit 60  # lines 120-179
file_read.py app.py --start 120 --end 180    # lines 120-180 inclusive
file_read.py app.log --tail 100              # last 100 lines
file_read.py app.py --start 500 --end -1     # line 500 to EOF
```

Prefer a range over a whole-file read for large files — locate with
`code-grep` or `fs-glob` first. Binary files are refused with a hint.
