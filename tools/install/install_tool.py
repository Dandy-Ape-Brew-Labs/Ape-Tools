#!/usr/bin/env python3
"""install — install this toolbox to a prefix (thin wrapper over install.sh).

All arguments forward to the repo-root install.sh unchanged:

  install_tool.py --prefix ~/.local/opt/ape-tools          # copy install
  install_tool.py --prefix DIR --tools file-read,web-fetch # subset
  install_tool.py --prefix DIR --update                    # re-copy payload
  install_tool.py                                        # in-place setup

install.sh prints a JSON summary on stdout; progress on stderr.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "install.sh"


def main() -> int:
    if not INSTALLER.is_file():
        print(f"error: {INSTALLER} not found", file=sys.stderr)
        return 1
    proc = subprocess.run(["bash", str(INSTALLER), *sys.argv[1:]])
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
