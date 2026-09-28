# fs-manage

mkdir / move / copy / delete in one action-enum tool.

```sh
fs_manage.py mkdir a/b/c
fs_manage.py move old.py new.py
fs_manage.py copy src/ bak/ --recursive
fs_manage.py delete tmp.txt              # -> trash (recoverable)
fs_manage.py delete tmp.txt --permanent  # real removal
```

Deletes go to `$AGENT_TOOLS_HOME/trash/<ts>-<name>` by default —
reversible beats irreversible. `move`/`copy` refuse to clobber without
`--force`.
