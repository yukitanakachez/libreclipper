"""Tightening a clip's rhythm: cutting long pauses, then a mild speed-up.

Everything here works in clip-relative time (0 = the clip's first frame).
Cuts only ever fall inside the silence between words, and each cut leaves a
short breath behind so speech never sounds spliced. When a frame rate is
given, interval edges land on the video frame grid, which keeps audio and
video exactly the same length through any number of cuts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from clipper.models import Word

KEEP_PAUSE = 0.1          # seconds of silence left behind where a pause is cut


@dataclass(frozen=True)
class Pacing:
    cut_pauses: bool = True
    max_pause: float = 0.3
    speed: float = 1.1


def _removals(words: list[Word], clip_start: float, clip_end: float,
              max_pause: float) -> list[tuple[float, float]]:
    """Clip-relative spans of silence to drop."""
    spans = sorted((max(w.start, clip_start) - clip_start, min(w.end, clip_end) - clip_start)
                   for w in words if w.end > clip_start and w.start < clip_end)
    half = KEEP_PAUSE / 2
    removals: list[tuple[float, float]] = []
    speech_end = None
    for start, end in spans:
        if speech_end is None:
            if start > max_pause:                       # long silence before the first word
                removals.append((0.0, start - half))
        elif start - speech_end > max_pause:
            removals.append((speech_end + half, start - half))
        speech_end = end if speech_end is None else max(speech_end, end)
    return removals


def keep_intervals(words: list[Word], clip_start: float, clip_end: float,
                   pacing: Pacing, fps: float | None = None) -> list[tuple[float, float]]:
    """Clip-relative [a, b) spans to keep, in order."""
    length = clip_end - clip_start
    if not pacing.cut_pauses:
        return [(0.0, length)]

    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for cut_start, cut_end in _removals(words, clip_start, clip_end, pacing.max_pause):
        if cut_start > cursor:
            kept.append((cursor, cut_start))
        cursor = cut_end
    if cursor < length:
        kept.append((cursor, length))

    if fps:
        # Kept speech stays whole: edges only ever move outward into silence.
        aligned = []
        for a, b in kept:
            a2 = math.floor(a * fps + 1e-9) / fps
            b2 = min(math.ceil(b * fps - 1e-9) / fps, math.floor(length * fps + 1e-9) / fps)
            if b2 > a2:
                if aligned and a2 <= aligned[-1][1]:
                    aligned[-1] = (aligned[-1][0], b2)
                else:
                    aligned.append((a2, b2))
        kept = aligned
    return kept


class TimeMap:
    """Maps clip-relative source time to time in the cut clip (before speed-up)."""

    def __init__(self, intervals: list[tuple[float, float]]) -> None:
        self.intervals = intervals
        self.duration = sum(b - a for a, b in intervals)

    def __call__(self, t: float) -> float:
        elapsed = 0.0
        for a, b in self.intervals:
            if t < a:
                return elapsed                      # inside a cut: land on the cut point
            if t < b:
                return elapsed + (t - a)
            elapsed += b - a
        return elapsed


def finished_duration(intervals: list[tuple[float, float]], pacing: Pacing) -> float:
    """How long the clip plays once pauses are cut and the speed-up applied."""
    return sum(b - a for a, b in intervals) / pacing.speed
