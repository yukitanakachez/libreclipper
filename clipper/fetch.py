"""Step 1: make a 720p working copy of your video file, plus its metadata.

The file stays where it is: ffmpeg makes the proxy from it, every later step works on the
proxy, and render cuts the finished clip straight from the original at full quality.
Clipper does not download videos: a link is refused before anything else happens.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from clipper import jobs, shell
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Meta


class FetchError(Exception):
    pass


def fetch(source: str, paths: JobPaths, cfg: AppConfig) -> Meta:
    if jobs.is_link(source):
        raise FetchError(jobs.NO_LINKS)
    return _fetch_local(source, paths, cfg)


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


def source_file(meta: Meta, paths: JobPaths) -> Path:
    """The video a clip is cut from: your original file. A job made from a link (by a version
    of Clipper that still downloaded) has no file, so it falls back to its 720p working copy."""
    if meta.source_kind == "local":
        if not Path(meta.source).is_file():
            raise FetchError(f"The video isn't at {meta.source} any more. Put it back, or "
                             "start a new job from the file.")
        return Path(meta.source)
    if paths.proxy.exists():
        return paths.proxy
    raise FetchError("This job came from a link, and its working copy has been cleaned up. "
                     "Start a new job from the video file.")
