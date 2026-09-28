# util-kit

Small deterministic ops agents reach for constantly — kept in one tool
so they don't shell out ad-hoc.

```sh
util_kit.py now --utc
util_kit.py hash dist.tar.gz
echo hello | util_kit.py b64 encode
util_kit.py env --prefix AGENT_    # secrets auto-redacted
util_kit.py json keys data.json
```
