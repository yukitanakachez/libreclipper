"""Job folders: one directory per source video, JSON files as the only state.

Every write is atomic (temp file + rename) so a crash never leaves a half-written
file, and any step can be re-run without redoing the ones before it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from clipper.config import AppConfig

YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VALID_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def is_youtube(source: str) -> bool:
    return urlparse(source).netloc.lower() in YT_HOSTS


PATH_PREFIXES = ("shorts", "live", "embed", "v")


def job_id_for(source: str) -> str:
    if is_youtube(source):
        parsed = urlparse(source)
        if parsed.netloc.lower() == "youtu.be":
            return parsed.path.lstrip("/").split("/")[0]
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return video_id
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in PATH_PREFIXES:
            return parts[1]
        raise ValueError(
            f"No video id in this YouTube URL: {source}. "
            "Use a link to a single video (watch, youtu.be, shorts or live)."
        )
    path = Path(source).expanduser().resolve()
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")[:40] or "video"
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:8]
    return f"{slug}-{digest}"


class JobPaths:
    def __init__(self, root: Path, out: Path | None = None) -> None:
        self.root = root
        self._out = out

    @property
    def request(self) -> Path:
        return self.root / "job.json"

    @property
    def status(self) -> Path:
        return self.root / "status.json"

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def proxy(self) -> Path:
        return self.root / "proxy.mp4"

    @property
    def transcript(self) -> Path:
        return self.root / "transcript.json"

    @property
    def candidates(self) -> Path:
        return self.root / "candidates.json"

    @property
    def crop_plan(self) -> Path:
        return self.root / "crop_plan.json"

    @property
    def word_fixes(self) -> Path:
        return self.root / "word_fixes.json"

    @property
    def sections(self) -> Path:
        return self.root / "sections"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def out(self) -> Path:
        return self._out if self._out is not None else self.root / "out"


def paths_for(job_id: str, cfg: AppConfig) -> JobPaths:
    root = Path(cfg.jobs_dir) / job_id
    root.mkdir(parents=True, exist_ok=True)
    out = Path(cfg.clips_dir) / job_id if cfg.clips_dir else None
    return JobPaths(root, out)


def find_job(job_id: str, cfg: AppConfig) -> JobPaths | None:
    """An existing job's paths, or None. Never creates anything (safe for web input)."""
    if not VALID_JOB_ID.fullmatch(job_id or ""):
        return None
    root = Path(cfg.jobs_dir) / job_id
    if not root.is_dir():
        return None
    out = Path(cfg.clips_dir) / job_id if cfg.clips_dir else None
    return JobPaths(root, out)


def existing_jobs(cfg: AppConfig) -> list[JobPaths]:
    """Every job in the jobs folder. A folder without status.json is something else."""
    root = Path(cfg.jobs_dir)
    found = (find_job(folder.name, cfg) for folder in sorted(root.iterdir())) if root.exists() else ()
    return [paths for paths in found if paths is not None and paths.status.exists()]


def read_request(paths: JobPaths) -> dict:
    """What the job was created from; older jobs predate job.json."""
    if paths.request.exists():
        return read_json(paths.request)
    found: dict = {}
    if paths.meta.exists():
        found["source"] = read_json(paths.meta).get("source")
    if paths.candidates.exists():
        found["campaign"] = read_json(paths.candidates).get("campaign")
    return found


def write_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)      # raises before the rename on bad data
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def set_status(
    paths: JobPaths,
    state: str,
    progress: float = 0.0,
    error: str | None = None,
    failed_step: str | None = None,
) -> None:
    write_json(
        paths.status,
        {
            "state": state,
            "progress": progress,
            "updated_at": datetime.now(UTC).isoformat(),
            "error": error,
            "failed_step": failed_step,
        },
    )


def get_status(paths: JobPaths) -> dict:
    if not paths.status.exists():
        return {"state": "queued", "progress": 0.0, "error": None, "failed_step": None}
    return read_json(paths.status)
