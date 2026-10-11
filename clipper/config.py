"""Application settings, loaded from config.yaml (all keys optional)."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from clipper import shell

ALLOWED_MODELS = {"claude-opus-5", "claude-sonnet-5"}
ALLOWED_BACKENDS = {"mlx", "faster_whisper"}


def default_backend() -> str:
    """mlx-whisper only runs on Apple Silicon; everything else gets faster-whisper."""
    apple_silicon = sys.platform == "darwin" and platform.machine() == "arm64"
    return "mlx" if apple_silicon else "faster_whisper"


@dataclass(frozen=True)
class AppConfig:
    model: str = "claude-opus-5"
    jobs_dir: Path = Path("jobs")
    retention_days: int = 7
    max_height: int = 2160
    cookies_from_browser: str | None = None
    whisper_backend: str = default_backend()
    clips_dir: Path | None = None       # finished clips; None keeps them in each job folder


def _resolve(value: str | Path) -> Path:
    """~ expands to your home folder; relative paths are relative to the project."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else shell.project_home() / path


def load_config(path: Path | None = None) -> AppConfig:
    raw: dict = {}
    if path is not None:
        raw = yaml.safe_load(Path(path).read_text()) or {}

    model = raw.get("model", "claude-opus-5")
    if model not in ALLOWED_MODELS:
        raise ValueError(f"model must be one of {sorted(ALLOWED_MODELS)}, got {model!r}")

    backend = (raw.get("whisper") or {}).get("backend", default_backend())
    if backend not in ALLOWED_BACKENDS:
        raise ValueError(
            f"whisper.backend must be one of {sorted(ALLOWED_BACKENDS)}, got {backend!r}"
        )

    clips = raw.get("clips_dir")
    return AppConfig(
        model=model,
        jobs_dir=_resolve(raw.get("jobs_dir", "jobs")),
        clips_dir=_resolve(clips) if clips else None,
        retention_days=int(raw.get("retention_days", 7)),
        max_height=int(raw.get("max_height", 2160)),
        cookies_from_browser=(raw.get("youtube") or {}).get("cookies_from_browser"),
        whisper_backend=backend,
    )
