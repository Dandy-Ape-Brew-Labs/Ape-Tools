# privacy-scan

Scan a directory tree for personal data and secrets that shouldn't be
committed — private IPv4 addresses, home-directory paths, emails, common
API-token shapes, private keys, MAC addresses. Gitignored files are
skipped; RFC 5737 documentation ranges and loopback are allowed.

```sh
python3 tools/privacy-scan/privacy_scan.py            # scan repo root
python3 tools/privacy-scan/privacy_scan.py ~/src/proj # any directory
python3 tools/privacy-scan/privacy_scan.py --include-ignored
```

Exit `0` = clean, `1` = hits (JSON list of `file`, `line`, `kind`,
`match` on stdout), `2` = usage error.

## Extra patterns

Personal names, hostnames, or tokens you want guarded belong in a local
file — never in the repo itself. Sources, all optional:

- `--patterns FILE` (repeatable)
- `$PRIVACY_PATTERNS_FILE`
- default: `$AGENT_TOOLS_HOME/privacy-patterns.txt`

Format: one pattern per line; literal substring by default, prefix with
`regex:` for a regular expression. `#` starts a comment.
`$PRIVACY_EXTRA_PATTERNS` takes newline-separated literals inline.

## Run the smoke test

```sh
python3 tools/selftest/selftest.py --only privacy-scan
```
