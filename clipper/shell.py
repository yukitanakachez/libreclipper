"""Thin wrapper around external commands (ffmpeg, ffprobe)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PACKAGE_PARENT = Path(__file__).resolve().parent.parent
MARKER = "campaigns"


def project_home() -> Path:
    """Where this installation's data lives: campaigns, assets, the ffmpeg build.

    Not the package directory — an installed clipper lives in site-packages while
    its campaigns and fonts stay in the project folder. CLIPPER_HOME wins; else
    walk up from the working directory looking for a campaigns/ folder; else fall
    back to the package's parent, which is right for a source checkout.
    """
    override = os.environ.get("CLIPPER_HOME")
    if override:
        return Path(override)
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / MARKER).is_dir():
            return candidate
    return PACKAGE_PARENT


def _local(name: str) -> Path:
    """The project-local conda build (see README Setup)."""
    return project_home() / ".conda-tools" / "bin" / name


def managed_tool(name: str) -> Path:
    """Where Clipper keeps a tool it downloaded itself (see provision.py)."""
    return project_home() / ".tools" / "bin" / name


def filter_path(path) -> str:
    """A path as an ffmpeg filter option value inside a -filter_complex graph.

    Two escaping levels: the option value (\\ ' :), then the filtergraph (\\ ' [ ] , ;).
    Unescaped, a folder like "Sam's clips" breaks every caption burn-in.
    """
    value = re.sub(r"([\\':])", r"\\\1", str(path))
    return re.sub(r"([\\'\[\],;])", r"\\\1", value)


def ffmpeg() -> str:
    """The ffmpeg to run.

    A system ffmpeg may be the wrong architecture or built without libass, so
    CLIPPER_FFMPEG wins, then the project-local conda build, then the build Clipper
    downloaded for itself, then PATH.
    """
    override = os.environ.get("CLIPPER_FFMPEG")
    if override:
        return override
    for local in (_local("ffmpeg"), managed_tool("ffmpeg")):
        if local.exists():
            return str(local)
    return "ffmpeg"


def tools_on_path() -> None:
    """Put the chosen ffmpeg's folder first on PATH, for the programs that run "ffmpeg" by
    name themselves (mlx-whisper loading audio)."""
    binary = Path(ffmpeg())
    if binary.is_absolute():
        folders = os.environ.get("PATH", "").split(os.pathsep)
        if folders[0] != str(binary.parent):
            os.environ["PATH"] = os.pathsep.join([str(binary.parent), *folders])


def ffprobe() -> str:
    override = os.environ.get("CLIPPER_FFPROBE")
    if override:
        return override
    binary = os.environ.get("CLIPPER_FFMPEG")
    if binary:
        return str(Path(binary).with_name("ffprobe"))
    for local in (_local("ffmpeg"), managed_tool("ffmpeg")):
        if local.exists():
            return str(local.with_name("ffprobe"))      # stay with the build we chose
    return "ffprobe"


class CommandError(Exception):
    def __init__(self, cmd: list[str], returncode: int, stderr: str) -> None:
        super().__init__(f"{cmd[0]} failed ({returncode}): {stderr.strip()[-500:]}")
        self.cmd, self.returncode, self.stderr = cmd, returncode, stderr


INTERRUPTED = "Rendering was interrupted — press Render again."
_NOISE = ("frame=", "size=", "video:", "Exiting normally", "[out#", "Press [q]")


def describe_failure(exc: Exception) -> str:
    """One readable line for the page: never ffmpeg's banner or progress lines."""
    if isinstance(exc, CommandError):
        if exc.returncode in (-15, -2) or "received signal" in exc.stderr:
            return INTERRUPTED
        lines = [l.strip() for l in exc.stderr.splitlines() if l.strip()]
        useful = [l for l in lines if not l.startswith(_NOISE)]
        tail = (useful or lines or ["no details"])[-1]
        return f"{Path(str(exc.cmd[0])).name} failed: {tail[:300]}"
    return str(exc)[-500:]


def run(cmd: list[str], timeout: int = 3600) -> str:
    proc = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr)
    return proc.stdout


def probe(path: Path) -> dict:
    return json.loads(
        run([
            ffprobe(), "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(path),
        ])
    )


def run_capture_stderr(cmd: list[str], timeout: int = 3600) -> str:
    """ffmpeg writes its analysis (e.g. loudnorm's JSON) to stderr, not stdout."""
    proc = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr)
    return proc.stderr


def run_binary(cmd: list[str], timeout: int = 3600) -> bytes:
    """Like run(), for commands whose stdout is binary (raw audio samples)."""
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr.decode("utf-8", "replace"))
    return proc.stdout
