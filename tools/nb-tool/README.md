# nb-tool

`.ipynb` editing without Jupyter — the file is JSON, so this tool
treats it as a document: list cells, read sources, inspect outputs,
edit/add/delete cells, clear outputs.

```sh
nb_tool.py list analysis.ipynb
nb_tool.py read analysis.ipynb --cell 3
nb_tool.py outputs analysis.ipynb
nb_tool.py set analysis.ipynb --cell 0 --text "import pandas as pd"
nb_tool.py add analysis.ipynb --type markdown --text "## Notes" --at 0
nb_tool.py clear-outputs analysis.ipynb
```

No kernel involved — for execution, pair with `py-run` or jupyter
CLI (`jupyter execute`) via `run-shell`.
