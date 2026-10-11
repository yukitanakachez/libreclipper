"""What the review screen shows, and which edits it accepts.

Pure logic over a job's files. The API layer calls these functions and turns
ReviewError into HTTP errors; nothing here knows about HTTP or the worker.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from clipper import jobs, locks, pacing
from clipper.campaigns import (
    Campaign,
    CampaignError,
    for_video,
    load_campaign,
    music_tracks,
)
from clipper.captions import apply_word_fixes
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Candidate, CropPlan, Meta, Transcript
from clipper.pipeline import campaign_root
from clipper.selection import ends_sentence

EDITABLE_STATES = {"ready_for_review", "done"}
# A failed render or reframe leaves the candidates intact, and fixing them (unapprove
# the bad clip, turn music off, change layout back) is how you get past the failure.
EDITABLE_AFTER_FAILURE = {"render", "reframe"}
LAYOUTS = {"auto", "stack", "fit"}
PATCHABLE = {"start", "end", "headline", "post_caption", "layout", "music_on",
             "music_track", "approved"}
EDIT_FIELDS = {"start", "end", "headline", "post_caption", "layout"}
MIN_CLIP = 1.0
HEADLINE_MAX, CAPTION_MAX, WORD_MAX = 200, 2200, 60

# API handlers run in a thread pool and the worker in its own thread; whoever
# reads, changes and rewrites candidates.json or word_fixes.json holds this.
WRITE_LOCK = locks.WRITE_LOCK


class ReviewError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class JobData:
    job_id: str
    paths: JobPaths
    status: dict
    request: dict
    meta: Meta | None
    transcript: Transcript | None
    campaign: Campaign | None
    candidates: list[Candidate]
    plans: dict[int, CropPlan]
    word_fixes: dict[str, str]


def load_job(job_id: str, cfg: AppConfig) -> JobData:
    paths = jobs.find_job(job_id, cfg)
    if paths is None:
        raise ReviewError(404, f"No job called {job_id!r}.")
    read = lambda p: jobs.read_json(p) if p.exists() else None  # noqa: E731
    cand_data = read(paths.candidates) or {}
    request = jobs.read_request(paths)
    slug = cand_data.get("campaign") or request.get("campaign")
    campaign = None
    if slug:
        try:
            campaign = load_campaign(slug, campaign_root())
        except CampaignError:
            campaign = None
    meta, transcript, plans = read(paths.meta), read(paths.transcript), read(paths.crop_plan)
    if campaign is not None and meta:
        campaign = for_video(campaign, Meta.from_dict(meta))
    return JobData(
        job_id=job_id,
        paths=paths,
        status=jobs.get_status(paths),
        request=request,
        meta=Meta.from_dict(meta) if meta else None,
        transcript=Transcript.from_dict(transcript) if transcript else None,
        campaign=campaign,
        candidates=[Candidate.from_dict(c) for c in cand_data.get("candidates", [])],
        plans={p["candidate_n"]: CropPlan.from_dict(p) for p in (plans or {}).get("plans", [])},
        word_fixes=read(paths.word_fixes) or {},
    )


# Names the media route will serve: no spaces (iCloud "01-x 2.mp4" copies), no dot files.
SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(mp4|txt)$")


def clip_files(paths: JobPaths) -> list[Path]:
    """Finished clips the app can play: complete, servable, sorted."""
    if not paths.out.exists():
        return []
    return sorted(p for p in paths.out.glob("*.mp4")
                  if SAFE_FILE.fullmatch(p.name) and not p.name.endswith(".partial.mp4"))


def is_editable(status: dict) -> bool:
    state = status.get("state")
    return state in EDITABLE_STATES or (
        state == "failed" and status.get("failed_step") in EDITABLE_AFTER_FAILURE)


def reframe_error_path(paths: JobPaths, n: int) -> Path:
    return paths.work / f"reframe_{n:02d}.error"


def render_error_path(paths: JobPaths, n: int) -> Path:
    return paths.work / f"render_{n:02d}.error"


def clear_errors(paths: JobPaths) -> None:
    """A new pick renumbers the candidates, so the old ones' framing and render errors go."""
    if not paths.work.exists():
        return
    for pattern in ("reframe_*.error", "render_*.error"):
        for old in paths.work.glob(pattern):
            old.unlink(missing_ok=True)


# --- rendered clips: which candidate each came from, and whether it has been posted ----------

def clip_log_path(paths: JobPaths) -> Path:
    return paths.root / "clips.json"


def clip_log(paths: JobPaths) -> dict[str, dict]:
    """What is known about each rendered clip, by file name. Clips rendered from the command
    line (or before this file existed) have no entry: they count as not posted."""
    path = clip_log_path(paths)
    return jobs.read_json(path) if path.exists() else {}


def record_render(paths: JobPaths, clip: Path, c: Candidate) -> None:
    """A fresh render is a new video: it starts out not posted, whatever its name held before."""
    with WRITE_LOCK:
        log = {name: entry for name, entry in clip_log(paths).items() if entry.get("n") != c.n}
        log[clip.name] = {"n": c.n, "orig_start": c.orig_start, "headline": c.headline,
                          "posted_at": None}
        jobs.write_json(clip_log_path(paths), log)


def set_posted(paths: JobPaths, name: str, posted: bool, now: str) -> dict:
    with WRITE_LOCK:
        log = clip_log(paths)
        entry = log.setdefault(name, {"n": None, "orig_start": None, "headline": None,
                                      "posted_at": None})
        entry["posted_at"] = now if posted else None
        jobs.write_json(clip_log_path(paths), log)
        return entry


def clip_for(c: Candidate, paths: JobPaths, log: dict[str, dict]) -> Path | None:
    """The finished clip of this candidate, if it has one. Clips are numbered like candidates;
    one the log ties to an earlier pick's candidate of the same number is not this one's."""
    for clip in clip_files(paths):
        if not clip.name.startswith(f"{c.n:02d}-"):
            continue
        known = log.get(clip.name, {}).get("orig_start")
        if known is None or abs(known - c.orig_start) < 1e-6:
            return clip
    return None


def clip_view(paths: JobPaths, clip: Path, log: dict[str, dict]) -> dict:
    txt = clip.with_suffix(".txt")
    stat = clip.stat()
    entry = log.get(clip.name, {})
    return {"file": clip.name, "caption": txt.read_text() if txt.exists() else "",
            "headline": entry.get("headline"),
            # changes on re-render, so the page's player reloads the file
            "version": f"{stat.st_mtime_ns}-{stat.st_size}",
            "rendered_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            "posted_at": entry.get("posted_at")}


def _words_in(transcript: Transcript, start: float, end: float):
    return [w for w in transcript.words if w.end > start and w.start < end]


def finished_length(c: Candidate, transcript: Transcript, campaign: Campaign) -> float:
    kept = pacing.keep_intervals(_words_in(transcript, c.start, c.end), c.start, c.end,
                                 campaign.pacing)
    return pacing.finished_duration(kept, campaign.pacing)


def ends_on_sentence(c: Candidate, transcript: Transcript, fixes: dict[str, str]) -> bool:
    inside = [w for w in transcript.words
              if w.start >= c.start - 1e-6 and w.end <= c.end + 1e-6]
    inside = apply_word_fixes(inside, fixes)
    return bool(inside) and ends_sentence(inside[-1])


def _bounds(c: Candidate, data: JobData) -> tuple[float, float]:
    plan = data.plans.get(c.n)
    return (plan.analyzed_start, plan.analyzed_end) if plan else (c.start, c.end)


def candidate_view(c: Candidate, data: JobData, *, render_pending: bool = False,
                   reframe_pending: bool = False) -> dict:
    view = c.to_dict()
    lo, hi = _bounds(c, data)
    view["bounds"] = {"min_start": lo, "max_end": hi}
    view["words"] = []
    view["finished_length"] = None
    view["in_limits"] = None
    view["ends_on_sentence"] = False
    if data.transcript:
        words = apply_word_fixes(_words_in(data.transcript, lo, hi), data.word_fixes)
        view["words"] = [{"i": w.i, "text": w.text, "start": w.start, "end": w.end}
                         for w in words]
        view["ends_on_sentence"] = ends_on_sentence(c, data.transcript, data.word_fixes)
        if data.campaign:
            length = finished_length(c, data.transcript, data.campaign)
            view["finished_length"] = round(length, 2)
            view["in_limits"] = data.campaign.min_len <= length <= data.campaign.max_len
    clip = clip_for(c, data.paths, clip_log(data.paths))
    view["clip"] = clip.name if clip else None
    view["render_pending"] = render_pending
    render_error = render_error_path(data.paths, c.n)
    view["render_error"] = render_error.read_text() if render_error.exists() else None
    view["reframe_pending"] = reframe_pending
    reframe_error = reframe_error_path(data.paths, c.n)
    view["reframe_error"] = reframe_error.read_text() if reframe_error.exists() else None
    return view


def job_summary(paths: JobPaths, busy: bool) -> dict:
    status = jobs.get_status(paths)
    request = jobs.read_request(paths)
    meta = jobs.read_json(paths.meta) if paths.meta.exists() else {}
    cands = (jobs.read_json(paths.candidates).get("candidates", [])
             if paths.candidates.exists() else [])
    clips = clip_files(paths)
    log = clip_log(paths)
    return {
        "id": paths.root.name,
        "title": meta.get("title"),
        "source": request.get("source"),
        "campaign": request.get("campaign"),
        "state": status.get("state"),
        "progress": status.get("progress", 0.0),
        "failed_step": status.get("failed_step"),
        "error": status.get("error"),
        "updated_at": status.get("updated_at"),
        "candidates": len(cands),
        "approved": sum(1 for c in cands if c.get("approved")),
        "clips": len(clips),
        "posted": sum(1 for c in clips if log.get(c.name, {}).get("posted_at")),
        "busy": busy,
    }


def _number(patch: dict, key: str, current: float) -> float:
    value = patch.get(key, current)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReviewError(422, f"{key} must be a number of seconds.")
    return float(value)


def _require_editable(data: JobData) -> None:
    if not is_editable(data.status):
        state = data.status.get("state")
        raise ReviewError(409, f"Candidates can only be edited when the job is ready for "
                               f"review, done, or its render failed; it is {state}.")


def save_candidates(data: JobData) -> None:
    stored = jobs.read_json(data.paths.candidates)
    stored["candidates"] = [c.to_dict() for c in data.candidates]
    jobs.write_json(data.paths.candidates, stored)


def apply_patch(data: JobData, n: int, patch: dict) -> tuple[Candidate, bool]:
    _require_editable(data)
    unknown = sorted(set(patch) - PATCHABLE)
    if unknown:
        raise ReviewError(422, f"Unknown field(s): {', '.join(unknown)}.")
    cand = next((c for c in data.candidates if c.n == n), None)
    if cand is None:
        raise ReviewError(404, f"No candidate {n}.")

    start = _number(patch, "start", cand.start)
    end = _number(patch, "end", cand.end)
    lo, hi = _bounds(cand, data)
    if start < lo - 1e-6 or end > hi + 1e-6:
        raise ReviewError(422, f"Trim must stay within {lo:.1f}-{hi:.1f} s "
                               "(the analyzed range).")
    if end - start < MIN_CLIP:
        raise ReviewError(422, f"A clip must be at least {MIN_CLIP:g} s long.")

    layout = patch.get("layout", cand.layout)
    if layout not in LAYOUTS:
        raise ReviewError(422, f"layout must be one of {sorted(LAYOUTS)}.")
    for key, limit in (("headline", HEADLINE_MAX), ("post_caption", CAPTION_MAX)):
        if key in patch and (not isinstance(patch[key], str) or len(patch[key]) > limit):
            raise ReviewError(422, f"{key} must be text of at most {limit} characters.")
    for key in ("approved", "music_on"):
        if key in patch and not isinstance(patch[key], bool):
            raise ReviewError(422, f"{key} must be true or false.")

    music_on = patch.get("music_on", cand.music_on)
    track = patch.get("music_track", cand.music_track)
    if music_on or "music_track" in patch:
        if not (data.campaign and data.campaign.music_allowed):
            raise ReviewError(422, "This campaign does not allow music.")
        if track is not None and track not in music_tracks(data.campaign):
            raise ReviewError(422, "music_track must be a track from the campaign's music folder.")

    before = {k: getattr(cand, k) for k in EDIT_FIELDS}
    cand.start, cand.end, cand.layout = start, end, layout
    cand.headline = patch.get("headline", cand.headline)
    cand.post_caption = patch.get("post_caption", cand.post_caption)
    cand.music_on, cand.music_track = music_on, track
    cand.approved = patch.get("approved", cand.approved)
    if any(getattr(cand, k) != v for k, v in before.items()):
        cand.edited = True
    save_candidates(data)
    return cand, cand.layout != before["layout"]


def save_word_fixes(data: JobData, fixes: dict[str, str]) -> dict[str, str]:
    _require_editable(data)
    count = len(data.transcript.words) if data.transcript else 0
    for key, text in fixes.items():
        if not key.isdigit() or int(key) >= count:
            raise ReviewError(422, f"No word {key!r} in this transcript.")
        if not isinstance(text, str) or not text.strip() or "\n" in text or len(text) > WORD_MAX:
            raise ReviewError(422, f"Word fixes must be one line of 1-{WORD_MAX} characters.")
    merged = {**data.word_fixes, **{k: v.strip() for k, v in fixes.items()}}
    jobs.write_json(data.paths.word_fixes, merged)
    data.word_fixes = merged
    return merged


def has_edits(data: JobData) -> bool:
    return any(c.approved or c.edited for c in data.candidates)
