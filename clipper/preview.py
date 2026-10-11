"""Quick, caption-free previews for judging the crop.

Rendered from the 720p proxy at low quality, so you can watch four episodes'
worth of framing decisions in the time one real render would take. This is what
scripts/validate_speaker.md uses.
"""

from __future__ import annotations

from pathlib import Path

from clipper import pacing as pacing_mod
from clipper import shell
from clipper.jobs import JobPaths
from clipper.models import Candidate, CropPlan, Meta, Transcript
from clipper.pacing import Pacing

PREVIEW_W, PREVIEW_H = 720, 1280


def render_preview(
    paths: JobPaths,
    meta: Meta,
    plan: CropPlan,
    candidate: Candidate,
    transcript: Transcript | None = None,
    pacing: Pacing | None = None,
    out: Path | None = None,
) -> Path:
    """With a transcript and pacing, the preview has the finished clip's rhythm."""
    from clipper.render import build_filtergraph

    keep, speed = None, 1.0
    if transcript is not None and pacing is not None:
        words = [w for w in transcript.words
                 if w.end > candidate.start and w.start < candidate.end]
        if pacing.cut_pauses:
            keep = pacing_mod.keep_intervals(words, candidate.start, candidate.end,
                                             pacing, fps=meta.fps)
        speed = pacing.speed

    graph = build_filtergraph(
        plan.segments, candidate.start, candidate.end,
        meta.width, meta.height, None, None, -22.0,
        keep=keep, speed=speed, fps=meta.fps,
    )
    out = out or paths.work / f"preview_{candidate.n:02d}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    shell.run([
        shell.ffmpeg(), "-y", "-i", str(paths.proxy),
        "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
        "-s", f"{PREVIEW_W}x{PREVIEW_H}",
        "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    ])
    return out
