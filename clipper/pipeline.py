"""Driving the steps in order, and cleaning up after them.

The web app calls these same functions; the CLI is just one caller.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from clipper import fetch, jobs, provision, render, shell
from clipper import pick as pick_mod
from clipper import transcribe as transcribe_mod
from clipper.campaigns import Campaign, for_video, load_campaign
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Candidate, CropPlan, Meta, Transcript
from clipper.reframe import plan as plan_mod

STEPS = ["fetch", "transcribe", "pick", "reframe"]


class PipelineError(Exception):
    pass


def campaign_root() -> Path:
    return shell.project_home() / "campaigns"


def _fetch(source, paths, cfg):
    return fetch.fetch(source, paths, cfg)


def _transcribe(paths, meta, campaign, cfg):
    return transcribe_mod.transcribe(paths.proxy, meta, campaign, paths, cfg)


def _pick(transcript, meta, campaign, cfg, paths):
    return pick_mod.pick(transcript, meta, campaign, cfg, paths)


def _reframe(paths, transcript, meta, candidates):
    return plan_mod.reframe_candidates(paths, transcript, meta, candidates)


def _record_request(paths: JobPaths, source: str, campaign_slug: str) -> None:
    data = jobs.read_json(paths.request) if paths.request.exists() else {
        "created_at": datetime.now(UTC).isoformat()}
    data.update(source=source, campaign=campaign_slug)
    jobs.write_json(paths.request, data)


def _load(path: Path, step: str) -> dict:
    if not path.exists():
        raise PipelineError(
            f"Cannot start from '{step}': {path.name} is missing. Run earlier steps first."
        )
    return jobs.read_json(path)


def run_job(
    source: str,
    campaign_slug: str,
    cfg: AppConfig,
    stop_after: str | None = None,
    start_from: str | None = None,
) -> JobPaths:
    """Run the steps in order. start_from reuses saved output of the steps before it."""
    campaign = load_campaign(campaign_slug, campaign_root())   # before any download
    provision.ensure()                 # a first run may still be fetching ffmpeg: wait for it
    paths = jobs.paths_for(jobs.job_id_for(source), cfg)
    _record_request(paths, source, campaign_slug)
    first = STEPS.index(start_from) if start_from else 0
    step = "fetch"
    try:
        if first <= STEPS.index("fetch"):
            jobs.set_status(paths, "fetching")
            meta = _fetch(source, paths, cfg)
        else:
            meta = Meta.from_dict(_load(paths.meta, start_from))
        campaign = for_video(campaign, meta)       # "auto" credit/tags from this video's creator
        if stop_after == "fetch":
            jobs.set_status(paths, "ready_for_review")
            return paths

        step = "transcribe"
        if first <= STEPS.index("transcribe"):
            jobs.set_status(paths, "transcribing")
            transcript = _transcribe(paths, meta, campaign, cfg)
        else:
            transcript = Transcript.from_dict(_load(paths.transcript, start_from))
        if stop_after == "transcribe":
            jobs.set_status(paths, "ready_for_review")
            return paths

        step = "pick"
        if first <= STEPS.index("pick"):
            jobs.set_status(paths, "picking")
            candidates = _pick(transcript, meta, campaign, cfg, paths)
        else:
            candidates = [Candidate.from_dict(c) for c in
                          _load(paths.candidates, start_from)["candidates"]]
        if stop_after == "pick":
            jobs.set_status(paths, "ready_for_review")
            return paths

        step = "reframe"
        jobs.set_status(paths, "reframing")
        _reframe(paths, transcript, meta, candidates)
        jobs.set_status(paths, "ready_for_review")
        return paths
    except Exception as exc:
        jobs.set_status(paths, "failed", error=str(exc), failed_step=step)
        raise


@dataclass
class RenderInputs:
    """Everything a job's files say about how to render its candidates."""
    paths: JobPaths
    meta: Meta
    transcript: Transcript
    campaign: Campaign
    candidates: list[Candidate]
    plans: dict[int, CropPlan]


def load_render_inputs(job_id: str, cfg: AppConfig) -> RenderInputs:
    paths = jobs.paths_for(job_id, cfg)
    meta = Meta.from_dict(jobs.read_json(paths.meta))
    data = jobs.read_json(paths.candidates)
    return RenderInputs(
        paths=paths,
        meta=meta,
        transcript=Transcript.from_dict(jobs.read_json(paths.transcript)),
        campaign=for_video(load_campaign(data["campaign"], campaign_root()), meta),
        candidates=[Candidate.from_dict(c) for c in data["candidates"]],
        plans={p["candidate_n"]: CropPlan.from_dict(p)
               for p in jobs.read_json(paths.crop_plan)["plans"]},
    )


def _render(job: RenderInputs, cand: Candidate, cfg: AppConfig) -> Path:
    return render.render_clip(job.paths, job.meta, job.campaign, cand, job.plans[cand.n],
                              job.transcript, cfg)


def render_approved(job_id: str, cfg: AppConfig) -> list[Path]:
    provision.ensure()
    job = load_render_inputs(job_id, cfg)
    jobs.set_status(job.paths, "rendering")
    try:
        outputs = [_render(job, cand, cfg) for cand in job.candidates if cand.approved]
    except Exception as exc:
        jobs.set_status(job.paths, "failed", error=str(exc), failed_step="render")
        raise
    jobs.set_status(job.paths, "done")
    return outputs


def render_one(job_id: str, n: int, cfg: AppConfig) -> Path:
    """Render a single candidate, approved or not. Unlike render_approved it leaves the
    job's status alone until the clip exists: a failure is that clip's, not the job's."""
    provision.ensure()
    job = load_render_inputs(job_id, cfg)
    cand = next((c for c in job.candidates if c.n == n), None)
    if cand is None:
        raise ValueError(f"No candidate {n}.")
    out = _render(job, cand, cfg)
    jobs.set_status(job.paths, "done")
    return out


def _last_activity(paths: JobPaths) -> float:
    """Newest write to the job's state, so review edits count as activity."""
    files = (paths.status, paths.request, paths.candidates, paths.word_fixes, paths.crop_plan)
    return max(f.stat().st_mtime for f in files if f.exists())


PARTIAL_MAX_AGE = 3600.0     # a running encode writes to its file constantly


def _leftover_partials(paths: JobPaths, now: float, everything: bool) -> list[Path]:
    """Half-written clips from a crash. Unless nothing can be rendering
    (server start), only those untouched for an hour: never a render in progress."""
    found = []
    for folder in (paths.work, paths.out):
        if folder.exists():
            found += [p for p in folder.glob("*.partial.mp4")
                      if everything or now - p.stat().st_mtime > PARTIAL_MAX_AGE]
    return found


def clean(cfg: AppConfig, now: float | None = None, all_partials: bool = False) -> list[Path]:
    """Delete working files once a job has aged out, and leftover partial files.
    Finished clips are kept. all_partials is only safe when nothing is rendering."""
    now = now or time.time()
    cutoff = now - cfg.retention_days * 86400
    removed: list[Path] = []
    root = Path(cfg.jobs_dir)
    if not root.exists():
        return removed

    for job_dir in sorted(root.iterdir()):
        located = jobs.find_job(job_dir.name, cfg)          # knows where clips_dir is
        for partial in _leftover_partials(located, now, all_partials) if located else []:
            partial.unlink(missing_ok=True)
            removed.append(partial)
        paths = JobPaths(job_dir)
        if not paths.status.exists() or _last_activity(paths) > cutoff:
            continue
        if paths.proxy.exists():
            paths.proxy.unlink()
            removed.append(paths.proxy)
        for folder in (paths.sections, paths.work):
            if folder.exists():
                shutil.rmtree(folder)
                removed.append(folder)
    return removed
