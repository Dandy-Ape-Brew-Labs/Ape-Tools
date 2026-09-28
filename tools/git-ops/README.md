# git-ops

Local git operations with agent-friendly JSON output. Thin `git`
wrapper — use `run-shell` for anything not covered.

```sh
git_ops.py status                 # {branch, files[], clean}
git_ops.py diff --stat
git_ops.py log -n 5               # JSON commits
git_ops.py commit --message "fix" --files src/a.py
git_ops.py checkout -b feature/x
```

Convention: results on stdout (JSON or raw patch), errors on stderr.
For remote operations (PRs, issues, clones) use the `github` tool.
