# secrets

Two jobs: tell the agent which credentials its tools need but don't
have, and keep a small vault it can inject into processes without the
values ever appearing on stdout or in argv.

```sh
secrets.py check                          # missing creds at a glance
echo "$TOKEN" | secrets.py set MY_API_KEY # value via stdin only
secrets.py run -- curl -H "auth: $MY_API_KEY" ...
```

- `check` unions the `env` declarations across every `tool.json` with
  the vault contents → `{name, declared_by, in_env, in_vault}`.
- `set` reads the value from **stdin** — never argv, so it can't leak
  via `ps` or shell history.
- `run` is the safe consumption path: the child's environment gets
  the vault, stdout stays clean.
- Vault: `$AGENT_TOOLS_HOME/secrets.json`, chmod 600; read warns if
  group/other-readable. It's plaintext-at-rest — for real keyring
  use, prefer system tooling; this covers agent-workflow convenience.
