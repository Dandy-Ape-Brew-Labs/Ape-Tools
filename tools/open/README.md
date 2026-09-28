# open

Hand the user a finished artifact in the right app: generated report in
the viewer, docs page in the browser, output folder in the file manager.

```sh
open.py open dist/report.pdf
open.py open https://docs.python.org/3/
open.py open --reveal build/output.bin
open.py mime report.pdf        # what's the default handler?
```

Exits 3 on headless sessions — combine with `send-file` for a
notification the user can click later instead.
