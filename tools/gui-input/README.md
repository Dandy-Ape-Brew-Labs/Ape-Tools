# gui-input

Keyboard and pointer injection for KDE/Wayland (and X11) via
`ydotool`, which writes to kernel uinput — compositor-independent.

```sh
gui_input.py backends            # installed? daemon running?
gui_input.py type "hello, world"
gui_input.py key ctrl+shift+p
gui_input.py move 640 480
gui_input.py click 640 480 --button right
```

Setup (one-time):

```sh
sudo dnf install ydotool
systemctl --user enable --now ydotoold
```

Without the daemon every action exits 3 with the hint — check
`backends` first in an automation loop.
