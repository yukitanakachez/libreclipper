"""Step 4: turn faces and speech into a crop plan for each candidate.

Only each candidate's range (plus 10s of margin, so trimming in review stays
inside analyzed footage) is examined. Shots where the framing is a guess are
flagged needs_check so review can show a "check framing" badge.
"""

from __future__ import annotations

from pathlib import Path

from clipper import jobs
from clipper.jobs import JobPaths
from clipper.models import Candidate, CropPlan, CropSegment, Meta, Transcript
from clipper.reframe import faces as faces_mod
from clipper.reframe import layout, shots, speaker

MARGIN = 10.0
MIN_TRACK_SAMPLES = 5
CONFIDENT_SCORE = 0.004


def build_crop_plan(
    video: Path,
    transcript: Transcript,
    candidate: Candidate,
    meta: Meta,
    margin: float = MARGIN,
    span: tuple[float, float] | None = None,
) -> CropPlan:
    """span, when given, is the range to analyze instead of the candidate ± margin."""
    lo, hi = span if span is not None else (candidate.start - margin, candidate.end + margin)
    start = max(0.0, lo)
    end = min(transcript.duration, hi)
    segments: list[CropSegment] = []
    needs_check = False

    # Read the whole analyzed range once, then decide shot by shot.
    detections = faces_mod.detect_faces(video, start, end)

    for shot_start, shot_end in shots.detect_shots(video, start, end):
        tracks = [
            t for t in faces_mod.tracks_in(detections, shot_start, shot_end)
            if len(t.samples) >= MIN_TRACK_SAMPLES
        ]
        mask = speaker.speech_mask(transcript, shot_start, shot_end)
        scores = {t.id: speaker.talking_score(t, mask) for t in tracks}
        loudest_mouth = max(
            (max((s for _, s in series), default=0.0) for series in scores.values()),
            default=0.0,
        )
        confident = bool(scores) and loudest_mouth >= CONFIDENT_SCORE
        forced = candidate.layout if candidate.layout in {"stack", "fit"} else None
        kind = forced or layout.choose_layout(len(tracks), confident)
        if kind == "stack" and len(tracks) < 2:
            kind = "fit"          # nothing to stack

        if kind == "single":
            crop = layout.single_crop(tracks[0].median_box(), meta.width, meta.height)
            segments.append(CropSegment(shot_start, shot_end, "single", [crop]))
        elif kind == "speaker":
            for span_start, span_end, track_id in speaker.speaker_timeline(
                scores, shot_start, shot_end
            ):
                track = next(t for t in tracks if t.id == track_id)
                crop = layout.single_crop(track.median_box(), meta.width, meta.height)
                segments.append(CropSegment(span_start, span_end, "single", [crop]))
        elif kind == "stack":
            crops = layout.stack_crops(
                [t.median_box() for t in tracks], meta.width, meta.height
            )
            segments.append(CropSegment(shot_start, shot_end, "stack", crops))
        else:
            segments.append(CropSegment(shot_start, shot_end, "fit", [layout.fit_rect()]))

        # A layout you chose is not a fallback, so it does not raise the flag.
        needs_check = needs_check or (forced is None and kind in {"stack", "fit"})

    candidate.needs_check = needs_check
    return CropPlan(
        candidate_n=candidate.n,
        analyzed_start=start,
        analyzed_end=end,
        segments=segments,
    )


def reframe_candidates(
    paths: JobPaths, transcript: Transcript, meta: Meta, candidates: list[Candidate]
) -> list[CropPlan]:
    plans = [build_crop_plan(paths.proxy, transcript, c, meta) for c in candidates]
    jobs.write_json(paths.crop_plan, {"plans": [p.to_dict() for p in plans]})
    data = jobs.read_json(paths.candidates)          # keep model + campaign
    data["candidates"] = [c.to_dict() for c in candidates]
    jobs.write_json(paths.candidates, data)
    return plans
