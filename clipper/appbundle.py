"""A double-clickable Clipper.app for the Mac: opening it starts the server if it isn't
already running, then shows Clipper in its own window. No Electron: the bundle is one small
shell script, and the window is Chrome's app mode (any other browser gets a normal tab)."""

from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path

from clipper import shell

NAME = "Clipper"

LAUNCHER = """#!/bin/zsh
# Made by `clipper app`. Run that again after moving the project folder.
source ~/.zshrc 2>/dev/null          # API keys are exported there
{exports}
PROJECT={project}
PYTHON={python}
PORT={port}
URL="http://127.0.0.1:$PORT"
LOG="$HOME/Library/Logs/Clipper.log"

up() {{ curl -s -o /dev/null -m 2 "$URL/api/jobs"; }}

if ! up; then
  mkdir -p "$HOME/Library/Logs"
  cd "$PROJECT" || {{ osascript -e 'display alert "Clipper" message "The project folder has moved. Run clipper app again from its new place."'; exit 1; }}
  nohup "$PYTHON" -m clipper.cli serve --port "$PORT" --no-browser >> "$LOG" 2>&1 &
  disown
  for i in {{1..60}}; do up && break; sleep 0.5; done
fi

if ! up; then
  osascript -e "display alert \\"Clipper couldn't start\\" message \\"$(tail -n 5 "$LOG" | tr '\\"' "'")\\""
  exit 1
fi

if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="$URL"
else
  open "$URL"
fi
"""


def launcher(project: Path, python: str, port: int, env: dict[str, str]) -> str:
    exports = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in sorted(env.items()))
    return LAUNCHER.format(exports=exports, project=shlex.quote(str(project)),
                           python=shlex.quote(python), port=int(port))


def install(dest: Path | None = None, port: int = 8765) -> Path:
    """Write Clipper.app into `dest` (~/Applications by default) for this project folder."""
    if sys.platform != "darwin":
        raise RuntimeError("clipper app makes a Mac app; on other systems, run clipper serve.")
    app = Path(dest or Path.home() / "Applications") / f"{NAME}.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    # Tool locations set for this shell (e.g. a shared ffmpeg build) are kept for the app.
    env = {k: os.environ[k] for k in ("CLIPPER_FFMPEG", "CLIPPER_FFPROBE")
           if os.environ.get(k)}
    script = macos / NAME
    script.write_text(launcher(shell.project_home().resolve(), sys.executable, port, env))
    script.chmod(0o755)
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleName": NAME, "CFBundleDisplayName": NAME,
                       "CFBundleIdentifier": "local.clipper.app", "CFBundleExecutable": NAME,
                       "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.0",
                       "LSUIElement": True}, fh)       # no Dock icon of its own: the window is Chrome's
    return app
