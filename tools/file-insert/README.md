# file-insert

Positional insert when there's no unique anchor string.

```sh
file_insert.py app.py --line 12 --text "import os"
file_insert.py app.py --line 0 --text "#!/usr/bin/env python3"
printf 'x\n' | file_insert.py app.py --line -1    # append at EOF
```

Line numbers shift after every insert — re-locate by content, not number.
