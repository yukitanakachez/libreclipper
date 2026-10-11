"""JSON API for the review app. Rules live in review.py; this layer maps them to HTTP."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from clipper import jobs, shell
from clipper.campaigns import (
    TEMPLATES,
    CampaignError,
    list_campaigns,
    load_campaign,
    music_tracks,
)
from clipper.pipeline import campaign_root
from clipper.web import review
from clipper.web.media import safe_clip_path
from clipper.web.worker import Task, Worker

router = APIRouter(prefix="/api")


class NewJob(BaseModel):
    source: str
    campaign: str


class Repick(BaseModel):
    force: bool = False


class WordFixes(BaseModel):
    fixes: dict[str, str]


class Posted(BaseModel):
    posted: bool


TRIM_FIELDS = {"start", "end", "layout"}
CHOOSE_VIDEO = 'POSIX path of (choose file with prompt "Choose a video" of type {"public.movie"})'


def reveal_in_finder(path: Path) -> None:
    subprocess.run(["open", "-R", str(path)], check=False)


def has_video_stream(path: Path) -> bool:
    """ffprobe finds a video stream: rejects text files, audio-only files and the like
    at submit, rather than as a failed download minutes later."""
    try:
        out = shell.run([shell.ffprobe(), "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
                        timeout=30)
    except Exception:
        return False
    return "video" in out


def choose_file_dialog() -> str | None:
    """The Mac's own file chooser. The server runs on the same Mac as the browser."""
    if sys.platform != "darwin":
        raise HTTPException(501, "Paste the video's file path instead.")
    result = subprocess.run(["osascript", "-e", "activate", "-e", CHOOSE_VIDEO],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:                    # cancelled
        return None
    return result.stdout.strip() or None


def _ctx(request: Request) -> tuple:
    return request.app.state.cfg, request.app.state.worker


def _load(job_id: str, cfg) -> review.JobData:
    try:
        data = review.load_job(job_id, cfg)
    except review.ReviewError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    if not data.paths.status.exists():                  # some other folder, not a job
        raise HTTPException(404, f"No job called {job_id!r}.")
    return data


def _running(worker: Worker, job_id: str) -> bool:
    """The job is being fetched, transcribed, picked or framed: nothing in it can change."""
    return worker.is_busy(job_id, "run")


def _clips(paths: jobs.JobPaths) -> list[dict]:
    log = review.clip_log(paths)
    return [review.clip_view(paths, mp4, log) for mp4 in review.clip_files(paths)]


@router.post("/jobs")
def create_job(body: NewJob, request: Request):
    cfg, worker = _ctx(request)
    source = body.source.strip()
    if body.campaign in TEMPLATES:
        raise HTTPException(400, f"'{body.campaign}' is a template: copy it to campaigns/<creator>.yaml, "
                                 "or use Any creator (auto).")
    try:
        load_campaign(body.campaign, campaign_root())
    except CampaignError as exc:
        raise HTTPException(400, str(exc)) from exc
    if source.lower().startswith(("http://", "https://")) and not jobs.is_youtube(source):
        raise HTTPException(400, "Only YouTube links or local video files are supported.")
    if not jobs.is_youtube(source):
        path = Path(source).expanduser()
        if not path.is_file():
            raise HTTPException(400, f"No video file at {path}.")
        if not has_video_stream(path):
            raise HTTPException(400, f"That file has no video: {path.name}")
        source = str(path.resolve())
    try:
        job_id = jobs.job_id_for(source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not jobs.VALID_JOB_ID.fullmatch(job_id):          # it becomes a folder name
        raise HTTPException(400, f"That link has no usable video id: {source}")

    existing = jobs.find_job(job_id, cfg)
    if existing is not None and (existing.status.exists() or worker.is_busy(job_id)):
        return JSONResponse({"id": job_id, "existing": True}, status_code=200)

    paths = jobs.paths_for(job_id, cfg)
    jobs.write_json(paths.request, {"source": source, "campaign": body.campaign,
                                    "created_at": datetime.now(UTC).isoformat()})
    jobs.set_status(paths, "queued")
    worker.submit(Task("run", job_id, source=source, campaign=body.campaign))
    return JSONResponse({"id": job_id, "existing": False}, status_code=201)


@router.get("/jobs")
def list_jobs(request: Request):
    cfg, worker = _ctx(request)
    rows = [review.job_summary(paths, busy=worker.is_busy(paths.root.name))
            for paths in jobs.existing_jobs(cfg)]
    rows.sort(key=lambda r: r["updated_at"] or "", reverse=True)
    return rows


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, request: Request):
    cfg, worker = _ctx(request)
    data = _load(job_id, cfg)
    campaign = None
    if data.campaign:
        campaign = {"slug": data.campaign.slug, "name": data.campaign.name,
                    "min_len": data.campaign.min_len, "max_len": data.campaign.max_len,
                    "music_allowed": data.campaign.music_allowed,
                    "tracks": music_tracks(data.campaign)}
    views = [review.candidate_view(
        c, data,
        render_pending=worker.is_busy(job_id, "render", c.n),
        reframe_pending=worker.is_busy(job_id, "reframe", c.n)) for c in data.candidates]
    return {
        "id": job_id,
        "status": data.status,
        "request": data.request,
        "meta": data.meta.to_dict() if data.meta else None,
        "campaign": campaign,
        "candidates": views,
        "clips": _clips(data.paths),
        "busy": worker.is_busy(job_id),
        "editable": review.is_editable(data.status) and not _running(worker, job_id),
    }


@router.patch("/jobs/{job_id}/candidates/{n}")
def patch_candidate(job_id: str, n: int, request: Request, patch: dict = Body(...)):
    cfg, worker = _ctx(request)
    if _running(worker, job_id):
        raise HTTPException(409, "This job is being processed; wait for it to finish.")
    if worker.is_busy(job_id, "render", n):
        raise HTTPException(409, "This clip is rendering; wait for it to finish.")
    if TRIM_FIELDS & set(patch) and worker.is_busy(job_id, "reframe", n):
        raise HTTPException(409, "This clip's framing is being updated; try again in a moment.")
    with review.WRITE_LOCK:
        data = _load(job_id, cfg)
        try:
            cand, layout_changed = review.apply_patch(data, n, patch)
        except review.ReviewError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
    if layout_changed:
        worker.submit(Task("reframe", job_id, n=n))
    fresh = _load(job_id, cfg)
    cand = next(c for c in fresh.candidates if c.n == n)
    return review.candidate_view(cand, fresh, render_pending=worker.is_busy(job_id, "render", n),
                                 reframe_pending=worker.is_busy(job_id, "reframe", n))


@router.put("/jobs/{job_id}/word-fixes")
def put_word_fixes(job_id: str, body: WordFixes, request: Request):
    cfg, worker = _ctx(request)
    if _running(worker, job_id) or worker.is_busy(job_id, "render"):
        raise HTTPException(409, "This job is being processed; wait for it to finish.")
    with review.WRITE_LOCK:
        try:
            return {"fixes": review.save_word_fixes(_load(job_id, cfg), body.fixes)}
        except review.ReviewError as exc:
            raise HTTPException(exc.status, str(exc)) from exc


@router.post("/jobs/{job_id}/candidates/{n}/render", status_code=202)
def render(job_id: str, n: int, request: Request):
    """Render this one clip. Clips render one at a time, in the order they were asked for."""
    cfg, worker = _ctx(request)
    data = _load(job_id, cfg)
    if not review.is_editable(data.status) or _running(worker, job_id):
        raise HTTPException(409, "This job can't render right now.")
    if not any(c.n == n for c in data.candidates):
        raise HTTPException(404, f"No candidate {n}.")
    if n not in data.plans or worker.is_busy(job_id, "reframe", n):
        raise HTTPException(409, "This clip's framing isn't ready yet; try again in a moment.")
    worker.submit(Task("render", job_id, n=n))
    return {"queued": True}


@router.get("/clips")
def all_clips(request: Request):
    """Every rendered clip of every job, newest first."""
    cfg, _ = _ctx(request)
    rows = []
    for paths in jobs.existing_jobs(cfg):
        meta = jobs.read_json(paths.meta) if paths.meta.exists() else {}
        rows += [dict(clip, job_id=paths.root.name, job_title=meta.get("title"))
                 for clip in _clips(paths)]
    rows.sort(key=lambda r: r["rendered_at"], reverse=True)
    return rows


@router.put("/jobs/{job_id}/clips/{name}/posted")
def mark_posted(job_id: str, name: str, body: Posted, request: Request):
    cfg, _ = _ctx(request)
    paths = jobs.find_job(job_id, cfg)
    path = safe_clip_path(paths, name) if paths else None
    if path is None or path.suffix != ".mp4":
        raise HTTPException(404, "No such clip.")
    review.set_posted(paths, name, body.posted, datetime.now(UTC).isoformat())
    return review.clip_view(paths, path, review.clip_log(paths))


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str, request: Request):
    cfg, worker = _ctx(request)
    data = _load(job_id, cfg)
    if data.status.get("state") != "failed":
        raise HTTPException(409, "Only failed jobs can be retried.")
    step = data.status.get("failed_step")
    jobs.set_status(data.paths, "queued")
    if step == "render":
        worker.submit(Task("render", job_id))
    else:
        worker.submit(Task("run", job_id, source=data.request.get("source"),
                           campaign=data.request.get("campaign"),
                           start_from=None if step in (None, "fetch") else step))
    return {"queued": True}


@router.post("/jobs/{job_id}/repick", status_code=202)
def repick(job_id: str, request: Request, body: Repick = Body(default=Repick())):
    cfg, worker = _ctx(request)
    data = _load(job_id, cfg)
    if worker.is_busy(job_id):
        raise HTTPException(409, "This job is busy; wait for it to finish.")
    if data.transcript is None:
        raise HTTPException(409, "This job has no transcript yet.")
    if review.has_edits(data) and not body.force:
        raise HTTPException(409, "Candidates have been approved or edited; picking again replaces them.")
    jobs.set_status(data.paths, "queued")
    worker.submit(Task("run", job_id, source=data.request.get("source"),
                       campaign=data.request.get("campaign"), start_from="pick"))
    return {"queued": True}


@router.get("/campaigns")
def campaigns():
    return list_campaigns(campaign_root())


@router.post("/jobs/{job_id}/reveal/{name}")
def reveal(job_id: str, name: str, request: Request):
    cfg, _ = _ctx(request)
    paths = jobs.find_job(job_id, cfg)
    path = safe_clip_path(paths, name) if paths else None
    if path is None:
        raise HTTPException(404, "No such clip.")
    reveal_in_finder(path)
    return {"revealed": True}


@router.post("/config/reveal")
def reveal_config():
    path = shell.project_home() / "config.yaml"
    if not path.is_file():
        raise HTTPException(404, "There's no config.yaml yet. Copy config.yaml.example to make one.")
    reveal_in_finder(path)
    return {"revealed": True}


@router.post("/choose-file")
def choose_file():
    return {"path": choose_file_dialog()}
