"""Shot boundaries inside a candidate's range.

A crop is fixed per shot, so cuts in the source are where the framing is allowed
to change without looking like a mistake.

Only the requested range is scanned: a 90-minute proxy would otherwise be decoded
in full once per candidate.
"""

from __future__ import annotations

from pathlib import Path

from scenedetect import ContentDetector, detect


def detect_shots(
    video: Path, start: float, end: float, threshold: float = 27.0
) -> list[tuple[float, float]]:
    scenes = detect(
        str(video),
        ContentDetector(threshold=threshold),
        start_time=start,
        end_time=end,
        show_progress=False,
    )
    cuts = [s.seconds for s, _ in scenes]
    bounds = sorted({start, end, *[c for c in cuts if start < c < end]})
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
