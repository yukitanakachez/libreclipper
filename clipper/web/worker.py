"""One background worker, one task at a time, with a queue that survives restarts.

The queue lives in <jobs_dir>/queue.json. The task being run is recorded there
too, so if the process dies mid-task it runs again first on the next start.
Runners record their own outcome in the job's files; the worker only logs
anything they let escape, so one bad task never stops the queue.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from clipper import jobs

log = logging.getLogger("clipper.worker")

@dataclass
class Task:
    kind: str                      # "run" | "render" | "reframe"
    job_id: str
    source: str | None = None
    campaign: str | None = None
    start_from: str | None = None
    n: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def key(self) -> tuple:
        return (self.kind, self.job_id, self.n)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        return cls(**d)


class Worker:
    def __init__(self, queue_file: Path, runners: dict[str, Callable[[Task], None]]) -> None:
        self.queue_file = Path(queue_file)
        self.runners = runners
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running: Task | None = None
        self._pending: list[Task] = self._load()

    def _load(self) -> list[Task]:
        if not self.queue_file.exists():
            return []
        data = jobs.read_json(self.queue_file)
        tasks = [Task.from_dict(t) for t in data.get("pending", [])]
        if data.get("running"):
            tasks.insert(0, Task.from_dict(data["running"]))   # interrupted: resume first
        return tasks

    def _save(self) -> None:
        jobs.write_json(self.queue_file, {
            "pending": [t.to_dict() for t in self._pending],
            "running": self._running.to_dict() if self._running else None,
        })

    def submit(self, task: Task) -> Task:
        with self._lock:
            for queued in self._pending:
                if queued.key() == task.key():
                    return queued
            self._pending.append(task)
            self._save()
        self._wake.set()
        return task

    def pending(self) -> list[Task]:
        with self._lock:
            return list(self._pending)

    def running(self) -> Task | None:
        with self._lock:
            return self._running

    def is_busy(self, job_id: str, kind: str | None = None, n: int | None = None) -> bool:
        with self._lock:
            tasks = self._pending + ([self._running] if self._running else [])
        return any(t.job_id == job_id and (kind is None or t.kind == kind)
                   and (n is None or t.n == n) for t in tasks)

    def run_once(self) -> bool:
        with self._lock:
            if not self._pending:
                return False
            task = self._pending.pop(0)
            self._running = task
            self._save()
        try:
            self.runners[task.kind](task)
        except Exception:
            log.exception("task %s (%s for %s) failed", task.id, task.kind, task.job_id)
        finally:
            with self._lock:
                self._running = None
                self._save()
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._wake.wait(0.5)
                self._wake.clear()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="clipper-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)
