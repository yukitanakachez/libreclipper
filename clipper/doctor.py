"""Setup checks, so a missing piece is a clear message instead of a crash mid-render."""

from __future__ import annotations

from pathlib import Path

from clipper import provision, shell
from clipper.reframe import faces


def font_path() -> Path:
    return shell.project_home() / "assets" / "fonts" / "Montserrat-Black.ttf"


def model_path() -> Path:
    return shell.project_home() / "assets" / faces.MODEL_FILE


def _filters() -> str:
    try:
        return shell.run([shell.ffmpeg(), "-hide_banner", "-filters"])
    except Exception:
        return ""


def _font_ok() -> bool:
    return font_path().exists()


def _model_ok() -> bool:
    return model_path().exists()


def _runs_from_source() -> bool:
    """False when an installed copy of clipper shadows this checkout."""
    import clipper
    return Path(clipper.__file__).resolve().parent.parent == shell.project_home().resolve()


def _provider_row() -> tuple[str, bool, str]:
    from clipper import providers
    settings = providers.load_settings()
    provider = providers.chosen_provider(settings)
    fix = (f"Add your {provider.name} API key in the app's Settings (clipper serve)"
           + (f", or set {provider.env[0]} in your shell" if provider.env else "")
           + (", or run: ant auth login" if provider.id == "anthropic" else ""))
    return f"AI provider ({provider.name})", providers.is_ready(provider, settings), fix


LIVE = True          # tests switch this off: no network calls from the suite


def ytdlp_check(run=None) -> tuple[bool, str]:
    fix = "YouTube search failed — try updating yt-dlp: uv sync --upgrade-package yt-dlp (./start keeps its uv at .tools/uv/uv)"
    if not LIVE:
        return True, fix
    run = run or shell.run
    try:
        out = run([shell.ytdlp(), "--flat-playlist", "--playlist-end", "1", "--print", "id",
                   "ytsearch1:podcast"], timeout=60)
        return bool(out.strip()), fix
    except Exception:
        return False, fix


def check_all() -> list[tuple[str, bool, str]]:
    filters = _filters()
    # Clipper fetches these two itself (provision.py): while it does, the fix is the progress.
    ffmpeg_fix = provision.note("ffmpeg", "Clipper downloads its own ffmpeg: run clipper setup, "
                                          "or start the app and wait a minute.")
    model_fix = provision.note("model", "Clipper downloads this itself: run clipper setup, "
                                        "or start the app and wait a minute.")
    return [
        ("ffmpeg libass", "ass" in filters.split(), ffmpeg_fix),
        ("ffmpeg loudnorm", "loudnorm" in filters, ffmpeg_fix),
        ("ffmpeg sidechaincompress", "sidechaincompress" in filters, ffmpeg_fix),
        ("Montserrat font", _font_ok(),
         f"Missing {font_path()}. It ships with Clipper: restore it with "
         "git checkout -- assets/fonts"),
        ("MediaPipe model", _model_ok(), model_fix),
        _provider_row(),
        ("runs from source", _runs_from_source(),
         "clipper is running an installed copy, so code changes are ignored. Reinstall "
         "editable (.venv/bin/uv pip install --python .venv/bin/python -e .), then run: "
         "chflags nohidden .venv/lib/python3.13/site-packages/*.pth  (Python 3.13 skips "
         ".pth files carrying macOS's hidden flag)"),
        ("YouTube search (yt-dlp)", *ytdlp_check()),
    ]
