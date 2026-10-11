from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clipper import jobs
from clipper.web import api
from clipper.web.app import create_app
from clipper.web.worker import Worker


@pytest.fixture
def worker(web_cfg):
    return Worker(web_cfg.jobs_dir / "queue.json", runners={})     # never started


@pytest.fixture
def client(web_cfg, worker):
    return TestClient(create_app(web_cfg, worker), base_url="http://127.0.0.1:8765")


def test_a_link_is_refused_clipper_takes_video_files_only(client, worker, web_cfg):
    for link in ("https://youtu.be/abc123", "https://www.youtube.com/watch?v=abc123",
                 "http://example.com/episode.mp4"):
        r = client.post("/api/jobs", json={"source": link, "campaign": "pod"})
        assert r.status_code == 400 and "video files, not links" in r.json()["detail"]
    assert worker.pending() == []
    assert not web_cfg.jobs_dir.exists() or list(web_cfg.jobs_dir.iterdir()) == []


def test_create_job_from_a_local_file(client, worker, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "has_video_stream", lambda path: True)
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"x")
    r = client.post("/api/jobs", json={"source": str(video), "campaign": "pod"})
    assert r.status_code == 201
    assert worker.pending()[0].source == str(video.resolve())


@pytest.mark.parametrize("source,fragment", [
    ("/no/such/file.mp4", "No video file"),
    ("/tmp", "No video file"),
    ("https://vimeo.com/123", "not links"),
])
def test_create_job_rejects_bad_sources_at_submit(client, worker, source, fragment):
    r = client.post("/api/jobs", json={"source": source, "campaign": "pod"})
    assert r.status_code == 400 and fragment in r.json()["detail"]
    assert worker.pending() == []


def test_create_job_rejects_an_invalid_campaign(client, web_home):
    (web_home / "campaigns" / "bad.yaml").write_text("name: B\nclip_length: { min: 9, max: 1 }\n")
    r = client.post("/api/jobs", json={"source": "/videos/x.mp4", "campaign": "bad"})
    assert r.status_code == 400


def test_submitting_an_existing_job_returns_it_without_queuing(client, worker, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "has_video_stream", lambda path: True)
    video = tmp_path / "new1.mp4"
    video.write_bytes(b"x")
    first = client.post("/api/jobs", json={"source": str(video), "campaign": "pod"})
    again = client.post("/api/jobs", json={"source": str(video), "campaign": "pod"})
    assert first.status_code == 201 and first.json()["existing"] is False
    assert again.status_code == 200 and again.json() == {"id": first.json()["id"], "existing": True}
    assert len(worker.pending()) == 1


def test_list_jobs(client, web_job):
    web_job(job_id="vid1")
    rows = client.get("/api/jobs").json()
    assert rows[0]["id"] == "vid1" and rows[0]["candidates"] == 2


def test_job_detail(client, web_job):
    web_job()
    body = client.get("/api/jobs/vid1").json()
    assert body["editable"] is True
    assert body["campaign"]["name"] == "Pod"
    assert [c["n"] for c in body["candidates"]] == [1, 2]
    assert "finished_length" in body["candidates"][0]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_patch_candidate_and_layout_change_queues_reframe(client, worker, web_job):
    web_job()
    r = client.patch("/api/jobs/vid1/candidates/2", json={"layout": "stack", "headline": "New"})
    assert r.status_code == 200
    assert r.json()["headline"] == "New" and r.json()["layout"] == "stack"
    assert [(t.kind, t.n) for t in worker.pending()] == [("reframe", 2)]


def test_patch_out_of_bounds_is_422(client, web_job):
    web_job()
    r = client.patch("/api/jobs/vid1/candidates/1", json={"end": 99.0})
    assert r.status_code == 422 and "analyzed range" in r.json()["detail"]


@pytest.mark.parametrize("state", ["picking", "reframing", "rendering", "queued"])
def test_no_edits_while_the_job_is_being_processed(client, web_job, state):
    paths = web_job(state=state)
    before = paths.candidates.read_text()
    r = client.patch("/api/jobs/vid1/candidates/1", json={"headline": "x"})
    assert r.status_code == 409
    assert paths.candidates.read_text() == before


def test_no_edits_to_a_clip_while_it_renders_but_the_others_stay_editable(client, worker, web_job):
    paths = web_job(state="done")
    assert client.post("/api/jobs/vid1/candidates/1/render").status_code == 202
    before = paths.candidates.read_text()
    assert client.patch("/api/jobs/vid1/candidates/1", json={"headline": "x"}).status_code == 409
    assert paths.candidates.read_text() == before
    assert client.put("/api/jobs/vid1/word-fixes", json={"fixes": {"0": "Hi"}}).status_code == 409
    assert client.patch("/api/jobs/vid1/candidates/2", json={"headline": "x"}).status_code == 200
    detail = client.get("/api/jobs/vid1").json()
    assert detail["editable"] is True and detail["busy"] is True
    assert [c["render_pending"] for c in detail["candidates"]] == [True, False]


def test_each_clip_renders_on_its_own(client, worker, web_job):
    web_job()
    assert client.post("/api/jobs/vid1/candidates/2/render").status_code == 202
    assert client.post("/api/jobs/vid1/candidates/1/render").status_code == 202
    assert [(t.kind, t.n) for t in worker.pending()] == [("render", 2), ("render", 1)]
    assert client.get("/api/jobs/vid1").json()["status"]["state"] == "ready_for_review"
    assert client.post("/api/jobs/vid1/candidates/9/render").status_code == 404


def test_render_needs_a_job_that_is_ready_and_framed(client, worker, web_job):
    paths = web_job(state="reframing")
    assert client.post("/api/jobs/vid1/candidates/1/render").status_code == 409
    jobs.set_status(paths, "ready_for_review")
    client.patch("/api/jobs/vid1/candidates/1", json={"layout": "fit"})      # queues reframe 1
    assert client.post("/api/jobs/vid1/candidates/1/render").status_code == 409
    assert client.post("/api/jobs/vid1/candidates/2/render").status_code == 202


def test_after_a_failed_render_you_can_edit_and_render_again(client, worker, web_job):
    paths = web_job()
    jobs.set_status(paths, "failed", error="section download failed", failed_step="render")
    assert client.get("/api/jobs/vid1").json()["editable"] is True
    assert client.patch("/api/jobs/vid1/candidates/2", json={"headline": "Better"}).status_code == 200
    assert client.post("/api/jobs/vid1/candidates/2/render").status_code == 202
    assert worker.pending()[-1].kind == "render"


def test_rendered_clips_are_listed_across_jobs_and_can_be_marked_posted(client, web_job):
    paths = web_job(state="done")
    paths.out.mkdir(parents=True, exist_ok=True)
    (paths.out / "01-one.mp4").write_bytes(b"v")
    (paths.out / "01-one.txt").write_text("Caption\n\n#tag\n")
    (clip,) = client.get("/api/clips").json()
    assert (clip["job_id"], clip["file"], clip["caption"], clip["posted_at"]) == (
        "vid1", "01-one.mp4", "Caption\n\n#tag\n", None)
    assert clip["job_title"] and clip["rendered_at"]
    r = client.put("/api/jobs/vid1/clips/01-one.mp4/posted", json={"posted": True})
    assert r.status_code == 200 and r.json()["posted_at"]
    assert client.get("/api/clips").json()[0]["posted_at"] == r.json()["posted_at"]
    assert client.get("/api/jobs").json()[0]["posted"] == 1
    assert client.get("/api/jobs/vid1").json()["clips"][0]["posted_at"]
    r = client.put("/api/jobs/vid1/clips/01-one.mp4/posted", json={"posted": False})
    assert r.json()["posted_at"] is None
    assert client.put("/api/jobs/vid1/clips/nope.mp4/posted", json={"posted": True}).status_code == 404
    assert client.put("/api/jobs/vid1/clips/01-one.txt/posted", json={"posted": True}).status_code == 404


def test_no_trims_while_that_candidates_framing_is_being_redone(client, worker, web_job):
    web_job()
    client.patch("/api/jobs/vid1/candidates/1", json={"layout": "fit"})     # queues reframe 1
    assert client.patch("/api/jobs/vid1/candidates/1", json={"start": 4.0}).status_code == 409
    assert client.patch("/api/jobs/vid1/candidates/1", json={"layout": "auto"}).status_code == 409
    assert client.patch("/api/jobs/vid1/candidates/1", json={"approved": True}).status_code == 200
    assert client.patch("/api/jobs/vid1/candidates/2", json={"start": 14.0}).status_code == 200


def test_word_fixes(client, web_job):
    web_job()
    r = client.put("/api/jobs/vid1/word-fixes", json={"fixes": {"12": "twelve"}})
    assert r.status_code == 200 and r.json() == {"fixes": {"12": "twelve"}}




def test_other_folders_in_the_jobs_folder_are_not_listed(client, web_cfg):
    (web_cfg.jobs_dir / "notes").mkdir(parents=True)
    (web_cfg.jobs_dir / "notes" / "todo.txt").write_text("x")
    assert client.get("/api/jobs").json() == []
    assert client.get("/api/jobs/notes").status_code == 404


@pytest.mark.parametrize("failed_step,kind,start_from", [
    ("render", "render", None), ("pick", "run", "pick"), ("fetch", "run", None)])
def test_retry_resumes_from_the_failed_step(client, worker, web_job, failed_step, kind, start_from):
    paths = web_job()
    jobs.set_status(paths, "failed", error="boom", failed_step=failed_step)
    assert client.post("/api/jobs/vid1/retry").status_code == 202
    task = worker.pending()[-1]
    assert (task.kind, task.start_from) == (kind, start_from)
    if kind == "run":
        assert task.source == "/videos/vid1.mp4" and task.campaign == "pod"


def test_retry_only_for_failed_jobs(client, web_job):
    web_job()
    assert client.post("/api/jobs/vid1/retry").status_code == 409


def test_repick_guards_edits_unless_forced(client, worker, web_job):
    web_job()
    client.patch("/api/jobs/vid1/candidates/1", json={"approved": True})
    assert client.post("/api/jobs/vid1/repick", json={"force": False}).status_code == 409
    assert client.post("/api/jobs/vid1/repick", json={"force": True}).status_code == 202
    task = worker.pending()[-1]
    assert (task.kind, task.start_from) == ("run", "pick")


def test_campaign_listing(client):
    slugs = [c["slug"] for c in client.get("/api/campaigns").json()]
    assert slugs == ["musical", "pod"]


def test_reveal_only_reveals_clips(client, web_job, web_cfg, monkeypatch):
    paths = web_job()
    paths.out.mkdir(parents=True)
    (paths.out / "01-one.mp4").write_bytes(b"x")
    revealed = []
    monkeypatch.setattr(api, "reveal_in_finder", lambda p: revealed.append(p))
    assert client.post("/api/jobs/vid1/reveal/01-one.mp4").status_code == 200
    assert client.post("/api/jobs/vid1/reveal/..%2Fjob.json").status_code == 404
    assert client.post("/api/jobs/vid1/reveal/missing.mp4").status_code == 404
    assert revealed == [(paths.out / "01-one.mp4").resolve()]


def test_choose_file_returns_the_picked_path_or_null(client, monkeypatch):
    monkeypatch.setattr(api, "choose_file_dialog", lambda: "/Users/me/episode.mp4")
    assert client.post("/api/choose-file").json() == {"path": "/Users/me/episode.mp4"}
    monkeypatch.setattr(api, "choose_file_dialog", lambda: None)
    assert client.post("/api/choose-file").json() == {"path": None}


def test_clips_still_being_written_are_not_listed(client, web_job):
    paths = web_job(state="rendering")
    paths.out.mkdir(parents=True)
    (paths.out / "01-one.mp4").write_bytes(b"done")
    (paths.out / "02-two.partial.mp4").write_bytes(b"half")
    clips = client.get("/api/jobs/vid1").json()["clips"]
    assert [c["file"] for c in clips] == ["01-one.mp4"]
    assert client.get("/api/jobs").json()[0]["clips"] == 1


def test_a_rerendered_clip_gets_a_new_version_so_players_reload(client, web_job):
    import os
    paths = web_job(state="done")
    paths.out.mkdir(parents=True)
    clip = paths.out / "01-one.mp4"
    clip.write_bytes(b"first render")
    first = client.get("/api/jobs/vid1").json()["clips"][0]["version"]
    clip.write_bytes(b"second render, longer")
    os.utime(clip, ns=(clip.stat().st_atime_ns, clip.stat().st_mtime_ns + 1_000_000))
    assert client.get("/api/jobs/vid1").json()["clips"][0]["version"] != first


def test_other_websites_cannot_trigger_actions(client, worker, web_job):
    web_job()
    r = client.post("/api/jobs/vid1/candidates/1/render", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert worker.pending() == []
    ok = client.post("/api/jobs/vid1/candidates/1/render", headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 202


def test_requests_for_other_host_names_are_refused(client):
    # DNS rebinding: evil.example resolving to 127.0.0.1 must not read the API.
    assert client.get("/api/jobs", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/jobs", headers={"Host": "localhost:8765"}).status_code == 200


def test_files_the_app_cannot_serve_are_not_listed_as_clips(client, web_job):
    paths = web_job(state="done")
    paths.out.mkdir(parents=True)
    (paths.out / "01-one.mp4").write_bytes(b"clip")
    (paths.out / "01-one 2.mp4").write_bytes(b"iCloud conflict copy")
    assert [c["file"] for c in client.get("/api/jobs/vid1").json()["clips"]] == ["01-one.mp4"]
    assert client.get("/api/jobs").json()[0]["clips"] == 1


def test_a_local_file_without_video_is_rejected_at_submit(client, worker, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("not a video")
    r = client.post("/api/jobs", json={"source": str(notes), "campaign": "pod"})
    assert r.status_code == 400 and "no video" in r.json()["detail"]
    assert worker.pending() == []


def test_a_real_video_file_passes_the_submit_check():
    from pathlib import Path
    fixture = Path("tests/fixtures/shots.mp4")
    if not fixture.exists():
        pytest.skip("needs the fixture video")
    assert api.has_video_stream(fixture) is True





def test_config_reveal_shows_config_yaml_in_finder(client, web_home, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "reveal_in_finder", lambda p: seen.append(p))
    assert client.post("/api/config/reveal").status_code == 404
    assert seen == []
    (web_home / "config.yaml").write_text("model: claude-sonnet-5\n")
    r = client.post("/api/config/reveal")
    assert r.status_code == 200 and r.json() == {"revealed": True}
    assert seen == [web_home / "config.yaml"]


def test_the_example_template_cannot_start_a_job(client, web_home):
    (web_home / "campaigns" / "example.yaml").write_text("name: Example\nclip_length: { min: 2, max: 20 }\n")
    r = client.post("/api/jobs", json={"source": "/videos/abc.mp4", "campaign": "example"})
    assert r.status_code == 400 and "template" in r.json()["detail"]


def test_an_unexpected_error_says_what_it_was(web_cfg, worker, web_job, monkeypatch):
    web_job()
    def boom(*args, **kwargs):
        raise KeyError("campaign")
    monkeypatch.setattr(api.review, "job_summary", boom)
    quiet = TestClient(create_app(web_cfg, worker), base_url="http://127.0.0.1:8765",
                       raise_server_exceptions=False)
    r = quiet.get("/api/jobs")
    assert r.status_code == 500
    assert r.json()["detail"].startswith("Clipper hit an unexpected error:") and "campaign" in r.json()["detail"]


def test_a_dropped_video_is_kept_in_the_uploads_folder_and_can_start_a_job(client, worker, web_cfg,
                                                                           monkeypatch):
    r = client.post("/api/uploads", params={"name": "Episode 12.mov"}, content=b"video bytes")
    assert r.status_code == 200
    kept = Path(r.json()["path"])
    assert kept == (web_cfg.jobs_dir / "uploads" / "Episode 12.mov").resolve()
    assert kept.read_bytes() == b"video bytes"
    assert [p.name for p in kept.parent.iterdir()] == ["Episode 12.mov"]       # no .partial left

    monkeypatch.setattr(api, "has_video_stream", lambda path: True)
    made = client.post("/api/jobs", json={"source": str(kept), "campaign": "pod"})
    assert made.status_code == 201 and worker.pending()[0].source == str(kept)
    assert client.get("/api/jobs").json()[0]["id"] == made.json()["id"]         # uploads/ isn't a job


def test_a_dropped_files_name_cannot_leave_the_uploads_folder(client, web_cfg):
    for name in ("../../escape.mp4", "/etc/passwd", "..\\..\\evil.mp4", "a/b/c.mp4"):
        r = client.post("/api/uploads", params={"name": name}, content=b"x")
        assert r.status_code == 200
        assert Path(r.json()["path"]).parent == (web_cfg.jobs_dir / "uploads").resolve()
    assert not (web_cfg.jobs_dir.parent / "escape.mp4").exists()


def test_a_different_video_with_the_same_name_does_not_replace_the_first(client, web_cfg):
    first = client.post("/api/uploads", params={"name": "ep.mp4"}, content=b"one").json()["path"]
    again = client.post("/api/uploads", params={"name": "ep.mp4"}, content=b"one").json()["path"]
    other = client.post("/api/uploads", params={"name": "ep.mp4"}, content=b"another").json()["path"]
    assert again == first and other != first                                   # same size: same video
    assert Path(first).read_bytes() == b"one" and Path(other).read_bytes() == b"another"


def test_an_empty_dropped_file_is_refused(client, web_cfg):
    r = client.post("/api/uploads", params={"name": "empty.mp4"}, content=b"")
    assert r.status_code == 400 and "empty" in r.json()["detail"]
    assert list((web_cfg.jobs_dir / "uploads").iterdir()) == []
