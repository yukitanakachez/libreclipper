"""Fetching what a fresh checkout lacks, so nobody has to: an ffmpeg that can draw captions
(with its ffprobe) and the face-detection model.

`clipper serve` starts this in the background, `clipper setup` runs it in the terminal, and a
job that needs a missing piece waits for it. Every download is a fixed version checked against
a SHA-256 written here, then moved into place in one step: a half-finished file is never used.
"""

from __future__ import annotations

import hashlib
import platform
import ssl
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from clipper import shell
from clipper.reframe import faces

AUTO = True          # tests switch this off: no downloads from the suite

FFMPEG_HOST = "https://ffmpeg.martin-riedl.de"
# Static FFmpeg 9.0.2 builds with libass: (system, machine) -> each binary's zip and its SHA-256.
FFMPEG_BUILDS: dict[tuple[str, str], dict[str, tuple[str, str]]] = {
    ("darwin", "arm64"): {
        "ffmpeg": ("/download/macos/arm64/1789931890_9.0.2/ffmpeg.zip",
                   "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"),
        "ffprobe": ("/download/macos/arm64/1789931890_9.0.2/ffprobe.zip",
                    "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"),
    },
    ("darwin", "x86_64"): {
        "ffmpeg": ("/download/macos/amd64/1789931006_9.0.2/ffmpeg.zip",
                   "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4"),
        "ffprobe": ("/download/macos/amd64/1789931006_9.0.2/ffprobe.zip",
                    "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"),
    },
    ("linux", "x86_64"): {
        "ffmpeg": ("/download/linux/amd64/1789931100_9.0.2/ffmpeg.zip",
                   "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f"),
        "ffprobe": ("/download/linux/amd64/1789931100_9.0.2/ffprobe.zip",
                    "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32"),
    },
    ("linux", "aarch64"): {
        "ffmpeg": ("/download/linux/arm64/1789931697_9.0.2/ffmpeg.zip",
                   "93a76ae90db5474eecdf951a729857c64f3de23567228d6a7d5e6e8e3cd1021b"),
        "ffprobe": ("/download/linux/arm64/1789931697_9.0.2/ffprobe.zip",
                    "bcbe80fb741c180083327afaf5434812e006b33cacde2016b9aeaf6936128330"),
    },
}

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
             "float16/1/face_landmarker.task")
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

NEEDED_FILTERS = ("ass", "loudnorm", "sidechaincompress")
MANUAL_FFMPEG = ("Clipper has no ffmpeg download for this system. Install an ffmpeg built with "
                 "libass and put it on your PATH (or point CLIPPER_FFMPEG at it).")


class ProvisionError(Exception):
    pass


def model_path() -> Path:
    return shell.project_home() / "assets" / faces.MODEL_FILE


def _platform() -> tuple[str, str]:
    machine = platform.machine().lower()
    return sys.platform, {"amd64": "x86_64", "arm64": "arm64" if sys.platform == "darwin" else "aarch64"
                          }.get(machine, machine)


def ffmpeg_filters() -> str:
    """The filter list of the ffmpeg Clipper would run; empty when there is none it can run."""
    try:
        return shell.run([shell.ffmpeg(), "-hide_banner", "-filters"], timeout=30)
    except Exception:
        return ""


def ffmpeg_ok(filters: str | None = None) -> bool:
    names = (ffmpeg_filters() if filters is None else filters).split()
    return all(name in names for name in NEEDED_FILTERS)


def _ffprobe_ok() -> bool:
    try:
        shell.run([shell.ffprobe(), "-version"], timeout=30)
        return True
    except Exception:
        return False


# --- progress, as the setup page and `clipper doctor` report it ---------------------------------

_lock = threading.Lock()                 # one download of each thing at a time
_status: dict[str, dict] = {}            # "ffmpeg" | "model" -> {"state", "done", "total", "error"}
_ready: set[str] = set()                 # checked and fine in this process: not checked again


def _set(item: str, **fields) -> None:
    _status[item] = {**_status.get(item, {}), **fields}


def note(item: str, fallback: str) -> str:
    """One line on where `item` stands: downloading (with a percentage), why it failed, or
    `fallback` when nothing has been tried yet."""
    status = _status.get(item) or {}
    if status.get("state") == "working":
        total, done = status.get("total") or 0, status.get("done") or 0
        return f"Downloading now ({done * 100 // total}%)" if total else "Downloading now"
    if status.get("state") == "failed":
        return f"The download failed: {status.get('error')} Run clipper setup to try again."
    return fallback


# --- downloading --------------------------------------------------------------------------------

def _context() -> ssl.SSLContext:
    try:                                  # a bundled Python may not know the system's certificates
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url: str, dest: Path, sha256: str, item: str, share: tuple[float, float] = (0.0, 1.0)) -> None:
    """Fetch `url` to `dest`, checking its SHA-256 first. `share` is the slice of the item's
    progress bar this file fills (ffmpeg is two files)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "clipper"})
    try:
        with urllib.request.urlopen(request, timeout=60, context=_context()) as response, \
                open(partial, "wb") as out:
            size = int(response.headers.get("Content-Length") or 0)
            got = 0
            while chunk := response.read(1 << 16):
                out.write(chunk)
                digest.update(chunk)
                got += len(chunk)
                if size:
                    _set(item, total=1000,
                         done=int(1000 * (share[0] + (share[1] - share[0]) * got / size)))
        if digest.hexdigest() != sha256:
            raise ProvisionError(f"{url} did not match its expected checksum.")
        partial.replace(dest)
    except ProvisionError:
        raise
    except Exception as exc:
        raise ProvisionError(f"Couldn't download {url}: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)


def _install_ffmpeg() -> None:
    build = FFMPEG_BUILDS.get(_platform())
    if build is None:
        raise ProvisionError(MANUAL_FFMPEG)
    folder = shell.managed_tool("ffmpeg").parent
    for at, name in enumerate(("ffmpeg", "ffprobe")):
        path, sha256 = build[name]
        archive = folder / f"{name}.zip"
        _download(FFMPEG_HOST + path, archive, sha256, "ffmpeg", (at / 2, (at + 1) / 2))
        try:
            with zipfile.ZipFile(archive) as bundle:
                staged = Path(bundle.extract(name, folder / "unpacked"))
            staged.chmod(0o755)
            staged.replace(folder / name)
        finally:
            archive.unlink(missing_ok=True)
    (folder / "unpacked").rmdir()


def _ensure_ffmpeg() -> None:
    if not (ffmpeg_ok() and _ffprobe_ok()):
        _fetch_ffmpeg()
    shell.tools_on_path()


def _fetch_ffmpeg() -> None:
    chosen = Path(shell.ffmpeg())
    if chosen.is_absolute() and chosen != shell.managed_tool("ffmpeg"):
        # Something chosen by hand (CLIPPER_FFMPEG, .conda-tools) would stay in front of a download.
        raise ProvisionError(f"{chosen} can't draw captions (it needs libass). Remove it, or "
                             "point CLIPPER_FFMPEG at an ffmpeg that can.")
    _install_ffmpeg()
    if not ffmpeg_ok():
        raise ProvisionError(f"{shell.ffmpeg()} was downloaded but doesn't run on this computer.")


def _ensure_model() -> None:
    if not model_path().exists():
        _download(MODEL_URL, model_path(), MODEL_SHA256, "model")


ITEMS: dict[str, tuple[str, Callable[[], None]]] = {
    "ffmpeg": ("ffmpeg (video tools)", _ensure_ffmpeg),
    "model": ("face detection model", _ensure_model),
}


def ensure(items: tuple[str, ...] = ("ffmpeg", "model"),
           report: Callable[[str], None] | None = None) -> None:
    """Make sure each of `items` is installed, downloading what is missing. Raises
    ProvisionError naming the first one that couldn't be."""
    if not AUTO:
        return
    for item in items:
        if item in _ready:
            continue
        label, install = ITEMS[item]
        with _lock:
            if item in _ready:
                continue
            _set(item, state="working", done=0, total=0, error=None)
            if report:
                report(f"Checking {label}…")
            try:
                install()
            except Exception as exc:
                _set(item, state="failed", error=str(exc))
                raise ProvisionError(str(exc)) from exc
            _set(item, state="ok")
            _ready.add(item)
            if report:
                report(f"{label}: ready")


def start_background() -> threading.Thread:
    """Fetch whatever is missing without holding up the app's start."""
    def run() -> None:
        for item in ITEMS:
            try:
                ensure((item,))
            except ProvisionError:
                pass                      # kept in _status, which the setup page shows

    thread = threading.Thread(target=run, name="clipper-provision", daemon=True)
    thread.start()
    return thread
