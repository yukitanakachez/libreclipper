"""Who is talking, and when the crop is allowed to cut to them.

Mouth movement decides the speaker, but only while Whisper says someone is
speaking. A new speaker has to hold the lead for 1.5s before the crop cuts, and
switches are hard cuts, the way a human editor would do it.
"""

from __future__ import annotations

import bisect
import statistics

from clipper.models import Transcript
from clipper.reframe.faces import FaceTrack

MIN_HOLD = 1.5
MARGIN = 0.15
MIN_SPAN = 0.4


def speech_mask(
    transcript: Transcript, start: float, end: float, step: float = 0.1
) -> list[tuple[float, bool]]:
    spans = [(w.start, w.end) for w in transcript.words if w.end > start and w.start < end]
    out: list[tuple[float, bool]] = []
    t = start
    while t < end:
        out.append((round(t, 3), any(s <= t <= e for s, e in spans)))
        t += step
    return out


def _speaking_at(mask: list[tuple[float, bool]]):
    """Whether speech is on at any time, from the mask entry nearest to it.

    Face samples land on real frame times, not the mask's 0.1 s grid, so an
    exact-timestamp match would call every face silent.
    """
    times = [t for t, _ in mask]
    flags = [on for _, on in mask]

    def lookup(t: float) -> bool:
        if not times:
            return False
        i = bisect.bisect_left(times, t)
        if i == 0:
            return flags[0]
        if i == len(times):
            return flags[-1]
        return flags[i] if times[i] - t < t - times[i - 1] else flags[i - 1]

    return lookup


def talking_score(
    track: FaceTrack, mask: list[tuple[float, bool]], window: float = 0.5
) -> list[tuple[float, float]]:
    speaking_at = _speaking_at(mask)
    series = track.mouth_series()
    out: list[tuple[float, float]] = []
    for t, _ in series:
        window_vals = [m for u, m in series if t - window / 2 <= u <= t + window / 2]
        if len(window_vals) < 2 or not speaking_at(t):
            out.append((t, 0.0))
            continue
        out.append((t, statistics.pstdev(window_vals)))
    return out


def speaker_timeline(
    scores: dict[int, list[tuple[float, float]]],
    start: float,
    end: float,
    min_hold: float = MIN_HOLD,
    margin: float = MARGIN,
) -> list[tuple[float, float, int]]:
    if not scores:
        return []
    if len(scores) == 1:
        only = next(iter(scores))
        return [(start, end, only)]

    times = sorted({t for series in scores.values() for t, _ in series})
    lookup = {tid: dict(series) for tid, series in scores.items()}
    current = max(scores, key=lambda tid: sum(s for _, s in scores[tid]))
    spans: list[tuple[float, float, int]] = []
    span_start = start
    challenger, challenger_since = None, None

    for t in times:
        ranked = sorted(scores, key=lambda tid: lookup[tid].get(t, 0.0), reverse=True)
        leader = ranked[0]
        lead_value = lookup[leader].get(t, 0.0)
        current_value = lookup[current].get(t, 0.0)
        if leader == current or lead_value - current_value <= margin:
            challenger, challenger_since = None, None
            continue
        if challenger != leader:
            challenger, challenger_since = leader, t
        elif t - challenger_since >= min_hold:
            spans.append((span_start, challenger_since, current))
            span_start, current = challenger_since, leader
            challenger, challenger_since = None, None

    spans.append((span_start, end, current))
    return merge_micro_segments(spans)


def merge_micro_segments(
    spans: list[tuple[float, float, int]], min_len: float = MIN_SPAN
) -> list[tuple[float, float, int]]:
    """A 3-frame crop flash reads as a glitch; fold short spans into a neighbour."""
    kept = [(s, e, tid) for s, e, tid in spans if e > s]
    if not kept:
        return []

    out: list[list] = []
    for start, end, tid in kept:
        if out and (end - start < min_len or out[-1][2] == tid):
            out[-1][1] = end              # absorb into the span before it
        else:
            out.append([start, end, tid])

    # The first span has nothing before it, so fold it forward instead.
    while len(out) > 1 and out[0][1] - out[0][0] < min_len:
        out[1][0] = out[0][0]
        del out[0]

    merged = [(s, e, tid) for s, e, tid in out]
    if len(merged) > 1 and merged[-1][1] - merged[-1][0] < min_len:
        s, _, tid = merged[-2]
        merged = merged[:-2] + [(s, merged[-1][1], tid)]
    return merged
