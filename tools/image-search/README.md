# image-search

Visual references for an agent — pinout diagrams, wiring schematics,
UI mockups — returned as direct `image_url`s you can hand to
`file-media`-style pipelines or embed in docs.

```sh
image_search.py "raspberry pi pico pinout" --max 5
image_search.py "kanban layout" --backend brave
```

- `auto` picks Brave when `BRAVE_API_KEY` is set, else DuckDuckGo.
- DDG uses the unofficial `vqd` token flow — if it starts failing,
  `--backend brave` is the stable path.
