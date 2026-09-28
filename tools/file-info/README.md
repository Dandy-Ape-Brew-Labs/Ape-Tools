# file-info

Metadata for files and directories — check size/type before reading an
unknown file (logs, dumps, minified bundles).

```sh
file_info.py big.log
file_info.py src/ package.json
```

Returns JSON: `size_bytes`, `mtime` (UTC ISO), `mode`, `type`, `mime`,
`binary`, `lines` (text files) or `entries` (directories).
