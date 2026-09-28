# gui-screen

Screen capture for KDE Plasma on Wayland. `xdotool`/`scrot` are X11
only — this tool uses `spectacle` (KDE-native), falling back to
`grim` (wlroots) and `gnome-screenshot`.

```sh
gui_screen.py backends
gui_screen.py shot --out /tmp/screen.png
gui_screen.py shot --window --out /tmp/win.png
```

Feed the returned path to `file-media` for MIME/dimensions, or
attach it for a vision-capable model. `--region` pops an interactive
picker — avoid in unattended runs.
