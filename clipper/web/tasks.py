"""What each kind of worker task actually does."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from clipper import jobs, pipeline, shell
from clipper.config import AppConfig
from clipper.reframe import plan as plan_mod
from clipper.web import review
from clipper.web.worker import Task, Worker

log = logging.getLogger("clipper.tasks")


def _candidate(data: review.JobData, n: int):
    cand = next((c for c in data.candidates if c.n == n), None)
    if cand is None:
        raise review.ReviewError(404, f"No candidate {n}.")
    return cand


def _fail_if_still_queued(cfg: AppConfig, task: Task, exc: Exception, step: str) -> None:
    """The pipeline records its own failures, but not ones before its first step."""
    paths = jobs.find_job(task.job_id, cfg)
    if paths is not None and jobs.get_status(paths).get("state") == "queued":
        jobs.set_status(paths, "failed", error=str(exc), failed_step=step)


# A job still in one of these states when its run task starts was interrupted there.
REACHED_STEP = {"transcribing": "transcribe", "picking": "pick", "reframing": "reframe"}


def _resume_point(cfg: AppConfig, task: Task) -> str | None:
    """Where a run should start: where it was asked to, or later if it got further
    before the server stopped (no second download or Claude call)."""
    paths = jobs.find_job(task.job_id, cfg)
    reached = REACHED_STEP.get(jobs.get_status(paths).get("state")) if paths else None
    asked = task.start_from
    if reached and (asked is None or pipeline.STEPS.index(reached) > pipeline.STEPS.index(asked)):
        return reached
    return asked


def make_runners(cfg: AppConfig) -> dict[str, Callable[[Task], None]]:
    def run(task: Task) -> None:
        start_from = _resume_point(cfg, task)
        try:
            paths = pipeline.run_job(task.source, task.campaign, cfg, start_from=start_from,
                                     job_id=task.job_id)
        except Exception as exc:
            _fail_if_still_queued(cfg, task, exc, start_from or "fetch")
            raise
        review.clear_errors(paths)                  # new candidates, new framing

    def render(task: Task) -> None:
        if task.n is None:                            # every approved clip (an older queue, Retry)
            try:
                pipeline.render_approved(task.job_id, cfg)
            except Exception as exc:
                _fail_if_still_queued(cfg, task, exc, "render")
                raise
            return
        data = review.load_job(task.job_id, cfg)
        cand = _candidate(data, task.n)
        error = review.render_error_path(data.paths, cand.n)
        error.unlink(missing_ok=True)
        try:
            clip = pipeline.render_one(task.job_id, cand.n, cfg)
        except Exception as exc:                      # this clip's problem, not the job's
            error.parent.mkdir(parents=True, exist_ok=True)
            error.write_text(shell.describe_failure(exc))
            raise
        review.record_render(data.paths, clip, cand)

    def reframe(task: Task) -> None:
        data = review.load_job(task.job_id, cfg)
        cand = _candidate(data, task.n)
        error = review.reframe_error_path(data.paths, cand.n)
        error.unlink(missing_ok=True)
        # Cover everything the old framing did, so the trim limits never shrink.
        old = data.plans.get(cand.n)
        span = None if old is None else (min(old.analyzed_start, cand.start - plan_mod.MARGIN),
                                         max(old.analyzed_end, cand.end + plan_mod.MARGIN))
        try:
            new_plan = plan_mod.build_crop_plan(data.paths.proxy, data.transcript, cand,
                                                data.meta, span=span)
        except Exception as exc:                      # this clip's problem, not the job's
            error.parent.mkdir(parents=True, exist_ok=True)
            error.write_text(str(exc)[-500:])
            raise
        with review.WRITE_LOCK:
            stored = jobs.read_json(data.paths.crop_plan)
            stored["plans"] = [new_plan.to_dict() if p["candidate_n"] == cand.n else p
                               for p in stored["plans"]]
            jobs.write_json(data.paths.crop_plan, stored)
            cands = jobs.read_json(data.paths.candidates)
            for c in cands["candidates"]:
                if c["n"] == cand.n:
                    c["needs_check"] = cand.needs_check
            jobs.write_json(data.paths.candidates, cands)

    return {"run": run, "render": render, "reframe": reframe}


# The step a job was in when its process died, as run_job's failed_step names it.
INTERRUPTED_STEP = {"queued": "fetch", "fetching": "fetch", "transcribing": "transcribe",
                    "picking": "pick", "reframing": "reframe", "rendering": "render"}


def mark_interrupted(cfg: AppConfig, worker: Worker) -> list[str]:
    """Jobs stuck mid-step with no task left to finish them (e.g. Ctrl-C on a CLI
    run) become failed, so Retry appears instead of a card that spins forever."""
    marked = []
    for paths in jobs.existing_jobs(cfg):
        if worker.is_busy(paths.root.name):
            continue
        step = INTERRUPTED_STEP.get(jobs.get_status(paths).get("state"))
        if step:
            jobs.set_status(paths, "failed", failed_step=step,
                            error="Interrupted before this step finished. Retry to resume.")
            marked.append(paths.root.name)
    return marked


def start_daily_cleanup(cfg: AppConfig, interval: float = 86400.0,
                        stop: threading.Event | None = None) -> threading.Thread:
    """Delete expired working files every `interval` seconds."""
    stop = stop or threading.Event()

    def loop() -> None:
        while not stop.wait(interval):
            try:
                pipeline.clean(cfg)
            except Exception:
                log.exception("daily cleanup failed")

    thread = threading.Thread(target=loop, name="clipper-cleanup", daemon=True)
    thread.start()
    return thread
