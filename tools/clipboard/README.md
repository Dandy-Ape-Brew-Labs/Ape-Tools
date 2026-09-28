# clipboard

Give the agent a working clipboard: copy generated text, read what the
user just copied.

```sh
clipboard.py set "$(cat summary.md)"     # or: clipboard.py set --file summary.md
clipboard.py get
clipboard.py clear
clipboard.py backends                    # wl | xclip | xsel status
```

- Wayland (KDE/GNOME): `wl-copy`/`wl-paste` — `sudo dnf install wl-clipboard`
- X11: `xclip` or `xsel`
- `CLIPBOARD_BACKEND=wl|xclip|xsel` forces a backend when several exist.
- `set` with no argument reads stdin.
