# github

Reference external-service connector — wraps the authenticated `gh`
CLI and passes its JSON through. Requires `gh auth login` beforehand
(fails fast, exit 3, if not).

```sh
github.py auth                          # {login, name}
github.py pr list --state open
github.py pr view 42
github.py issue create --title "bug" --body "details"
github.py search "useState" --type code
github.py api repos/owner/repo/releases/latest
github.py run -- workflow list          # any gh subcommand
```

Everything `gh` supports is reachable via `api`/`run`; the named
subcommands just cover the common agent workflows.
