import threading
import time

import pytest

from clipper import jobs
from clipper.web import review, tasks
from clipper.web.worker import Task, Worker


def test_submit_persists_and_dedupes_pending_tasks(tmp_path):
    w = Worker(tmp_path / "queue.json", runners={})
    first = w.submit(Task("render", "job1"))
    again = w.submit(Task("render", "job1"))
    w.submit(Task("preview", "job1", n=2))
    assert again.id == first.id
    assert [t.kind for t in w.pending()] == ["render", "preview"]
    reloaded = Worker(tmp_path / "queue.json", runners={})
    assert [t.kind for t in reloaded.pending()] == ["render", "preview"]


def test_run_once_processes_in_order_and_clears_running(tmp_path):
    seen = []
    w = Worker(tmp_path / "queue.json",
               runners={"run": lambda t: seen.append(t.job_id), "render": lambda t: seen.append("r")})
    w.submit(Task("run", "a"))
    w.submit(Task("render", "b"))
    assert w.run_once() and w.run_once() and not w.run_once()
    assert seen == ["a", "r"]
    assert w.running() is None and w.pending() == []


def test_a_failing_runner_does_not_stop_the_queue(tmp_path):
    seen = []

    def boom(t):
        raise RuntimeError("nope")

    w = Worker(tmp_path / "queue.json", runners={"run": boom, "render": lambda t: seen.append(t.id)})
    w.submit(Task("run", "a"))
    rendered = w.submit(Task("render", "b"))
    w.run_once()
    w.run_once()
    assert seen == [rendered.id]


def test_task_interrupted_by_a_restart_runs_first_next_time(tmp_path):
    queue = tmp_path / "queue.json"
    interrupted = Task("run", "stuck", source="/videos/stuck.mp4", campaign="pod")
    jobs.write_json(queue, {"pending": [Task("render", "other").to_dict()],
                            "running": interrupted.to_dict()})
    seen = []
    w = Worker(queue, runners={"run": lambda t: seen.append(t.job_id),
                               "render": lambda t: seen.append(t.job_id)})
    w.run_once()
    assert seen == ["stuck"], "the interrupted task resumes before anything else"


def test_is_busy_covers_pending_and_running(tmp_path):
    gate = threading.Event()
    w = Worker(tmp_path / "queue.json", runners={"run": lambda t: gate.wait(2)})
    w.submit(Task("run", "a"))
    w.submit(Task("preview", "b", n=1))
    assert w.is_busy("b", "preview", 1) and not w.is_busy("b", "preview", 2)
    w.start()
    deadline = time.time() + 2
    while w.running() is None and time.time() < deadline:
        time.sleep(0.01)
    assert w.is_busy("a", "run")
    gate.set()
    w.stop()


def test_worker_thread_drains_the_queue(tmp_path):
    done = threading.Event()
    w = Worker(tmp_path / "queue.json", runners={"render": lambda t: done.set()})
    w.start()
    w.submit(Task("render", "j"))
    assert done.wait(3)
    w.stop()




def test_reframe_runner_updates_one_candidates_plan(web_cfg, web_job, monkeypatch):
    web_job()
    from clipper.models import CropPlan, CropSegment, Rect

    def fake_build(video, transcript, cand, meta, margin=10.0, span=None):
        cand.needs_check = False
        return CropPlan(cand.n, 1.0, 13.0, [CropSegment(1.0, 13.0, "fit", [Rect(0, 0, 1, 1)])])

    monkeypatch.setattr(tasks.plan_mod, "build_crop_plan", fake_build)
    tasks.make_runners(web_cfg)["reframe"](Task("reframe", "vid1", n=1))
    data = review.load_job("vid1", web_cfg)
    assert data.plans[1].segments[0].layout == "fit"
    assert data.plans[2].analyzed_start == 10.0, "other candidates keep their plans"


def test_a_run_that_dies_before_the_pipeline_starts_marks_the_job_failed(web_cfg, web_job):
    paths = web_job(state="queued")
    with pytest.raises(Exception):
        tasks.make_runners(web_cfg)["run"](
            Task("run", "vid1", source="/videos/vid1.mp4", campaign="deleted",
                 start_from="pick"))
    status = jobs.get_status(paths)
    assert status["state"] == "failed" and status["failed_step"] == "pick"
    assert "deleted" in status["error"]



def test_daily_cleanup_runs_on_its_interval_until_stopped(web_cfg, monkeypatch):
    ran = threading.Event()
    stop = threading.Event()
    monkeypatch.setattr(tasks.pipeline, "clean", lambda cfg: ran.set() or [])
    thread = tasks.start_daily_cleanup(web_cfg, interval=0.05, stop=stop)
    assert ran.wait(2)
    stop.set()
    thread.join(2)
    assert not thread.is_alive()


def test_jobs_left_mid_step_with_no_task_are_marked_failed_at_start(web_cfg, web_job):
    # e.g. Ctrl-C on a CLI `clipper run`: status says "transcribing" forever.
    stuck = web_job(job_id="stuck", state="transcribing")
    resuming = web_job(job_id="resuming", state="picking")
    fine = web_job(job_id="fine", state="ready_for_review")
    w = Worker(web_cfg.jobs_dir / "queue.json", runners={})
    w.submit(Task("run", "resuming", source="/videos/resuming.mp4", campaign="pod"))

    assert tasks.mark_interrupted(web_cfg, w) == ["stuck"]
    status = jobs.get_status(stuck)
    assert status["state"] == "failed" and status["failed_step"] == "transcribe"
    assert "interrupted" in status["error"].lower()
    assert jobs.get_status(resuming)["state"] == "picking"
    assert jobs.get_status(fine)["state"] == "ready_for_review"


def test_a_failed_reframe_is_reported_on_that_clip_not_the_whole_job(web_cfg, web_job, monkeypatch):
    paths = web_job(state="done")

    def boom(*a, **k):
        raise RuntimeError("no faces decoded")

    monkeypatch.setattr(tasks.plan_mod, "build_crop_plan", boom)
    with pytest.raises(RuntimeError):
        tasks.make_runners(web_cfg)["reframe"](Task("reframe", "vid1", n=1))
    assert jobs.get_status(paths)["state"] == "done"
    data = review.load_job("vid1", web_cfg)
    assert "no faces decoded" in review.candidate_view(data.candidates[0], data)["reframe_error"]
    assert review.candidate_view(data.candidates[1], data)["reframe_error"] is None


def _record_start_from(monkeypatch, paths):
    seen = {}

    def fake_run_job(source, campaign, cfg, start_from=None, job_id=None):
        seen["start_from"] = start_from
        return paths

    monkeypatch.setattr(tasks.pipeline, "run_job", fake_run_job)
    return seen


def test_an_interrupted_run_resumes_from_the_step_it_reached(web_cfg, web_job, monkeypatch):
    # Server died while framing a new job: no second download, no second Claude call.
    paths = web_job(state="reframing")
    seen = _record_start_from(monkeypatch, paths)
    tasks.make_runners(web_cfg)["run"](
        Task("run", "vid1", source="/videos/vid1.mp4", campaign="pod"))
    assert seen["start_from"] == "reframe"


def test_a_queued_run_starts_where_it_was_asked_to(web_cfg, web_job, monkeypatch):
    paths = web_job(state="queued")
    seen = _record_start_from(monkeypatch, paths)
    tasks.make_runners(web_cfg)["run"](
        Task("run", "vid1", source="/videos/vid1.mp4", campaign="pod", start_from="pick"))
    assert seen["start_from"] == "pick"



def test_reframing_after_a_trim_never_narrows_the_trimmable_range(web_cfg, web_job, monkeypatch):
    from clipper.models import CropPlan, CropSegment, Rect
    web_job()                                              # plan 1 analyzed 0.0-14.9
    review.apply_patch(review.load_job("vid1", web_cfg), 1, {"start": 1.0, "end": 3.0,
                                                                 "layout": "fit"})

    def fake_build(video, transcript, cand, meta, margin=10.0, span=None):
        lo, hi = span or (cand.start - margin, cand.end + margin)
        lo = max(0.0, lo)
        return CropPlan(cand.n, lo, hi, [CropSegment(lo, hi, "fit", [Rect(0, 0, 1, 1)])])

    monkeypatch.setattr(tasks.plan_mod, "build_crop_plan", fake_build)
    tasks.make_runners(web_cfg)["reframe"](Task("reframe", "vid1", n=1))
    plan = review.load_job("vid1", web_cfg).plans[1]
    assert (plan.analyzed_start, plan.analyzed_end) == (0.0, pytest.approx(14.9))


def test_rendering_one_clip_records_it_and_finishes_the_job(web_cfg, web_job, monkeypatch):
    paths = web_job()
    def fake(job_id, n, cfg):
        paths.out.mkdir(parents=True, exist_ok=True)
        (paths.out / f"{n:02d}-two.mp4").write_bytes(b"v")
        jobs.set_status(paths, "done")
        return paths.out / f"{n:02d}-two.mp4"
    monkeypatch.setattr(tasks.pipeline, "render_one", fake)
    tasks.make_runners(web_cfg)["render"](Task("render", "vid1", n=2))
    data = review.load_job("vid1", web_cfg)
    assert [review.candidate_view(c, data)["clip"] for c in data.candidates] == [None, "02-two.mp4"]
    assert review.clip_log(paths)["02-two.mp4"]["posted_at"] is None
    assert jobs.get_status(paths)["state"] == "done"


def test_a_failed_clip_render_is_that_clips_problem_not_the_jobs(web_cfg, web_job, monkeypatch):
    paths = web_job()
    def boom(job_id, n, cfg):
        raise RuntimeError("section download failed")
    monkeypatch.setattr(tasks.pipeline, "render_one", boom)
    with pytest.raises(RuntimeError):
        tasks.make_runners(web_cfg)["render"](Task("render", "vid1", n=1))
    data = review.load_job("vid1", web_cfg)
    assert "section download failed" in review.candidate_view(data.candidates[0], data)["render_error"]
    assert jobs.get_status(paths)["state"] == "ready_for_review"
