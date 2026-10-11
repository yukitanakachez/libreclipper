"""Range-enabled media routes: the proxy and finished clips.

Starlette's FileResponse answers Range requests with 206, which the browser's
video element needs for seeking. Nothing outside a job's own files is served.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from clipper import jobs
from clipper.jobs import JobPaths
from clipper.web import review

router = APIRouter(prefix="/media")
SAFE_FILE = review.SAFE_FILE


def safe_clip_path(paths: JobPaths, name: str) -> Path | None:
    """A file directly inside the job's clip folder, or None. Blocks traversal."""
    if not SAFE_FILE.match(name) or ".." in name:
        return None
    base = paths.out.resolve()
    path = (paths.out / name).resolve()
    if path.parent != base or not path.is_file():
        return None
    return path


def _paths(request: Request, job_id: str) -> JobPaths:
    paths = jobs.find_job(job_id, request.app.state.cfg)
    if paths is None:
        raise HTTPException(404, "No such job.")
    return paths


@router.get("/{job_id}/proxy.mp4")
def proxy(job_id: str, request: Request):
    paths = _paths(request, job_id)
    if not paths.proxy.is_file():
        raise HTTPException(404, "No proxy for this job.")
    return FileResponse(paths.proxy, media_type="video/mp4")


@router.get("/{job_id}/clips/{name}")
def clip(job_id: str, name: str, request: Request):
    path = safe_clip_path(_paths(request, job_id), name)
    if path is None:
        raise HTTPException(404, "No such clip.")
    media_type = "video/mp4" if path.suffix == ".mp4" else "text/plain"
    return FileResponse(path, media_type=media_type)
