# speak

Audible agent signals — "task done" reaches you even when you're across
the room.

```sh
speak.py say "Tests finished, all green"
speak.py say --file short-summary.txt --rate 200
speak.py backends
```

Engines tried in order: `espeak-ng` → `espeak` → `flite` → `festival` →
`pico2wave`+`aplay`. `SPEAK_ENGINE` forces a choice. `say` with no
argument reads stdin.
