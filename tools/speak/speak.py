"""Text-to-speech alerts — hear the agent instead of watching it.

  speak.py say "build finished" [--rate 175] [--voice en-us]
  speak.py say --file report.txt
  speak.py backends            # which TTS engines exist

Engine order: espeak-ng -> espeak -> flite -> festival -> pico2wave+aplay.
Override with $SPEAK_ENGINE.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib

ENGINES = ["espeak-ng", "espeak", "flite", "festival", "pico2wave"]
HINT = "sudo dnf install espeak-ng   # or espeak / flite / festival"


def available() -> dict:
    return {e: bool(shutil.which(e)) for e in ENGINES}


def pick() -> str | None:
    forced = os.environ.get("SPEAK_ENGINE")
    for name, ok in available().items():
        if forced:
            if name == forced and ok:
                return name
        elif ok:
            return name
    return None


def say(engine: str, text: str, rate: int, voice: str | None) -> subprocess.CompletedProcess:
    if engine in ("espeak-ng", "espeak"):
        argv = [engine, "-s", str(rate)]
        if voice:
            argv += ["-v", voice]
        argv.append(text)
    elif engine == "flite":
        argv = ["flite", "-t", text]
    elif engine == "festival":
        return subprocess.run(["festival", "--tts"],
                              input=text, capture_output=True, text=True,
                              timeout=60)
    else:  # pico2wave — synthesize to wav then play
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        r = subprocess.run(["pico2wave", "-w", wav, text],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and shutil.which("aplay"):
            r = subprocess.run(["aplay", "-q", wav],
                               capture_output=True, text=True, timeout=60)
        Path(wav).unlink(missing_ok=True)
        return r
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("say")
    s.add_argument("text", nargs="?")
    s.add_argument("--file")
    s.add_argument("--rate", type=int, default=175)
    s.add_argument("--voice")
    sub.add_parser("backends")
    args = p.parse_args()

    if args.cmd == "backends":
        agentlib.emit({"available": available(), "selected": pick(),
                       "hint": HINT})
        return 0

    engine = pick()
    if engine is None:
        agentlib.die("no TTS engine found on PATH.\n" + HINT, 3)
    if args.file:
        text = Path(args.file).read_text(errors="replace")
    elif args.text is not None:
        text = args.text
    else:
        text = sys.stdin.read()
    if not text.strip():
        agentlib.die("nothing to say (empty text)", 2)
    r = say(engine, text, args.rate, args.voice)
    if r.returncode != 0:
        agentlib.die(f"{engine} failed: {r.stderr.strip()}", 1)
    agentlib.emit({"spoken": True, "engine": engine, "chars": len(text)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
