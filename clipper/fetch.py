"""Step 1: get a 720p working copy of the source video, plus its metadata.

Two input kinds produce the same two files, so every later step is identical and
unaware of where the video came from:

- youtube: yt-dlp downloads a 720p proxy; render later downloads only the
  approved time ranges at full quality.
- local:   the file stays where it is; ffmpeg makes the proxy from it, and
  render cuts high-quality ranges straight from the original.
"""

from __future__ import annotations

import json
import time
from fractions import Fraction
from pathlib import Path

from clipper import jobs, shell
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Meta


class FetchError(Exception):
    pass



def _handle(info: dict) -> str:
    """The channel's @handle when YouTube gives one (uploader_id), else ""."""
    uploader = str(info.get("uploader_id") or "")
    return uploader if uploader.startswith("@") else ""

def fetch(source: str, paths: JobPaths, cfg: AppConfig) -> Meta:
    if jobs.is_youtube(source):
        return _fetch_youtube(source, paths, cfg)
    return _fetch_local(source, paths, cfg)


def _ytdlp_base(cfg: AppConfig) -> list[str]:
    cmd = [shell.ytdlp()]
    if cfg.cookies_from_browser:
        cmd += ["--cookies-from-browser", cfg.cookies_from_browser]
    return cmd


def _run_ytdlp_json(source: str, cfg: AppConfig) -> dict:
    out = shell.run(_ytdlp_base(cfg) + ["-J", "--no-warnings", source])
    return json.loads(out)


def _fetch_youtube(source: str, paths: JobPaths, cfg: AppConfig) -> Meta:
    try:
        info = _run_ytdlp_json(source, cfg)
    except shell.CommandError as exc:
        raise _translate(exc) from exc
    try:
        shell.run(_ytdlp_base(cfg) + [
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "--merge-output-format", "mp4", "-o", str(paths.proxy), source,
        ])
    except shell.CommandError as exc:
        raise _translate(exc) from exc

    width, height, fps = _probe_proxy(paths.proxy)
    meta = Meta(
        job_id=paths.root.name,
        source_kind="youtube",
        source=source,
        title=info.get("title", ""),
        description=info.get("description", "") or "",
        channel=info.get("channel", "") or "",
        channel_handle=_handle(info),
        duration=float(info.get("duration", 0.0)),
        width=width,
        height=height,
        fps=fps,
        max_height=int(info.get("height") or height),
    )
    jobs.write_json(paths.meta, meta.to_dict())
    return meta


def _fetch_local(source: str, paths: JobPaths, cfg: AppConfig) -> Meta:
    src = Path(source).expanduser()
    if not src.exists():
        raise FetchError(f"Source file not found: {src}")
    src = src.resolve()

    _width, height, _fps, duration = _probe_source(src)
    shell.run([
        shell.ffmpeg(), "-y", "-i", str(src), "-vf", "scale=-2:720",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k", str(paths.proxy),
    ])
    proxy_w, proxy_h, proxy_fps = _probe_proxy(paths.proxy)

    meta = Meta(
        job_id=paths.root.name,
        source_kind="local",
        source=str(src),
        title=src.stem,
        description="",
        channel="",
        duration=duration,
        width=proxy_w,
        height=proxy_h,
        fps=proxy_fps,
        max_height=height,
    )
    jobs.write_json(paths.meta, meta.to_dict())
    return meta


def _stream_dims(path: Path) -> tuple[int, int, float, float]:
    data = shell.probe(path)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    fps = float(Fraction(video.get("avg_frame_rate", "30/1")))
    duration = float(data["format"].get("duration", 0.0))
    return int(video["width"]), int(video["height"]), fps, duration


def _probe_source(path: Path) -> tuple[int, int, float, float]:
    return _stream_dims(path)


def _probe_proxy(path: Path) -> tuple[int, int, float]:
    w, h, fps, _ = _stream_dims(path)
    return w, h, fps


def probe_video(path: Path) -> tuple[int, int, float]:
    """Width, height and frame rate of the file actually being rendered from."""
    w, h, fps, _ = _stream_dims(path)
    return w, h, fps


def _translate(exc: shell.CommandError) -> FetchError:
    text = exc.stderr.lower()
    if "unable to extract" in text or "nsig extraction failed" in text:
        return FetchError(
            "YouTube changed something and yt-dlp needs updating. "
            "Run: uv run yt-dlp -U   (or: uv lock --upgrade-package yt-dlp)"
        )
    if "private video" in text:
        return FetchError("This video is private.")
    if "video unavailable" in text or "removed" in text:
        return FetchError("This video is unavailable or has been removed.")
    if "age" in text and "confirm" in text:
        return FetchError("This video is age-restricted and can't be downloaded anonymously.")
    return FetchError(str(exc))


SECTION_TRIES = 4               # attempts at one clip's high-quality section
SECTION_WAIT = 3.0              # seconds before the second try; grows with each one


def _refused(exc: shell.CommandError) -> bool:
    text = exc.stderr.lower()
    return "403" in text and ("forbidden" in text or "access denied" in text)


def download_section(
    meta: Meta, start: float, end: float, dest: Path, cfg: AppConfig
) -> Path:
    """Local sources need no download: render cuts from the original file."""
    if meta.source_kind == "local":
        return Path(meta.source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fmt = f"bestvideo[height<={cfg.max_height}]+bestaudio/best"
    cmd = _ytdlp_base(cfg) + [
        "-f", fmt, "--merge-output-format", "mp4",
        "--download-sections", f"*{max(0.0, start - 5.0)}-{end + 5.0}",
        "-o", str(dest), meta.source,
    ]
    # YouTube's video servers now and then answer one section with 403 and the next try
    # with the file, so a refusal is tried again before the render gives up.
    for attempt in range(1, SECTION_TRIES + 1):
        try:
            shell.run(cmd)
            return dest
        except shell.CommandError as exc:
            if not _refused(exc):
                raise _translate(exc) from exc
            if attempt == SECTION_TRIES:
                raise FetchError(
                    f"YouTube refused this clip's download {SECTION_TRIES} times (403). "
                    "Wait a minute and press Retry; if it keeps happening, update yt-dlp "
                    "(uv lock --upgrade-package yt-dlp)."
                ) from exc
            time.sleep(SECTION_WAIT * attempt)
    return dest
