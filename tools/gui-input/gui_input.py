"""Send keyboard/mouse input to the GUI on Wayland via ydotool
(kernel uinput — works on both X11 and Wayland). Fails fast with a
setup hint when ydotool isn't installed or the daemon isn't running.

  gui_input.py backends              # ydotool available? daemon up?
  gui_input.py type "hello world" [--delay-ms 20]
  gui_input.py key ctrl+c | Return | alt+F4
  gui_input.py click <x> <y> [--button left]
  gui_input.py move <x> <y>

ydotool key syntax: 'ctrl+c' maps to '29:1 46:1 46:0 29:0' etc.
Common names are translated; raw ydotool codes pass through.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

# friendly name -> evdev key name (ydotool accepts evdev names too,
# but we validate early for clearer errors)
KEYS = {
    "return": "enter", "enter": "enter", "esc": "esc", "escape": "esc",
    "tab": "tab", "space": "space", "backspace": "backspace",
    "delete": "delete", "home": "home", "end": "end",
    "pageup": "pageup", "pagedown": "pagedown",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "ctrl": "leftctrl", "leftctrl": "leftctrl", "rightctrl": "rightctrl",
    "alt": "leftalt", "leftalt": "leftalt", "rightalt": "rightalt",
    "shift": "leftshift", "leftshift": "leftshift",
    "super": "leftmeta", "meta": "leftmeta", "win": "leftmeta",
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
}

BUTTONS = {"left": "0x110", "right": "0x111", "middle": "0x112"}


def daemon_ok() -> bool:
    return Path("/run/user/" + str(__import__("os").getuid())
                + "/.ydotool_socket").exists() or \
        Path("/tmp/.ydotool_socket").exists()


def yd(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ydotool", *args],
                          capture_output=True, text=True, timeout=15)


def parse_key_combo(spec: str) -> list[str]:
    names = [KEYS.get(part.lower().strip()) for part in spec.split("+")]
    if any(n is None for n in names):
        bad = [p for p, n in zip(spec.split("+"), names) if n is None]
        agentlib.die(f"unknown key name(s): {bad} — "
                     "use evdev names (e.g. leftctrl, f5)", 2)
    return names


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backends")
    t = sub.add_parser("type"); t.add_argument("text")
    t.add_argument("--delay-ms", type=int, default=20)
    k = sub.add_parser("key"); k.add_argument("combo")
    c = sub.add_parser("click"); c.add_argument("x", type=int)
    c.add_argument("y", type=int)
    c.add_argument("--button", default="left", choices=BUTTONS)
    m = sub.add_parser("move"); m.add_argument("x", type=int)
    m.add_argument("y", type=int)
    args = p.parse_args()

    installed = bool(shutil.which("ydotool"))
    running = installed and daemon_ok()
    if args.cmd == "backends":
        agentlib.emit({"ydotool": installed, "daemon": running,
                       "hint": "sudo dnf install ydotool && "
                               "systemctl --user enable --now ydotoold"})
        return 0

    if not installed:
        agentlib.die("ydotool not installed — KDE/Wayland input needs it. "
                     "sudo dnf install ydotool", 3)
    if not running:
        agentlib.die("ydotoold not running — "
                     "systemctl --user enable --now ydotoold", 3)

    if args.cmd == "type":
        r = yd(["type", "--key-delay", str(args.delay_ms), args.text])
    elif args.cmd == "key":
        parse_key_combo(args.combo)
        # ydotool understands combos natively: 'ctrl+c', 'alt+f4'
        r = yd(["key", args.combo.lower()])
    elif args.cmd == "move":
        r = yd(["mousemove", "--absolute", "-x", str(args.x),
                "-y", str(args.y)])
    else:  # click
        r = yd(["mousemove", "--absolute", "-x", str(args.x),
                "-y", str(args.y)])
        if r.returncode == 0:
            time.sleep(0.05)
            r = yd(["click", BUTTONS[args.button]])

    if r.returncode != 0:
        agentlib.die(f"ydotool failed: {r.stderr.strip()}", 1)
    agentlib.emit({"sent": True})
    return 0


if __name__ == "__main__":
    sys.exit(main())
