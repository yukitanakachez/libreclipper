from fastapi.testclient import TestClient

from clipper import cli
from clipper.web.app import create_app
from clipper.web.worker import Worker


def _worker(cfg):
    return Worker(cfg.jobs_dir / "queue.json", {})


def test_built_frontend_is_served_at_the_root(web_cfg, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=root>clipper</div>")
    client = TestClient(create_app(web_cfg, _worker(web_cfg), frontend_dir=dist),
                        base_url="http://127.0.0.1:8765")
    assert "clipper" in client.get("/").text
    assert client.get("/api/campaigns").status_code == 200, "API still wins over the static mount"


def test_unbuilt_frontend_explains_how_to_build(web_cfg, tmp_path):
    client = TestClient(create_app(web_cfg, _worker(web_cfg), frontend_dir=tmp_path / "none"),
                        base_url="http://127.0.0.1:8765")
    assert "npm run build" in client.get("/").text


def test_serve_binds_localhost_cleans_up_and_stops_the_worker(web_cfg, monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "_config", lambda: web_cfg)
    monkeypatch.setattr(cli.pipeline, "clean",
                        lambda cfg, **kw: seen.update(cleaned=kw) or [])
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr("clipper.web.tasks.start_daily_cleanup", lambda cfg: None)
    assert cli.main(["serve", "--no-browser", "--port", "9999"]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 9999
    assert seen["cleaned"] == {"all_partials": True}


def test_serve_marks_orphaned_jobs_before_the_worker_starts(web_cfg, web_job, monkeypatch):
    stuck = web_job(job_id="stuck", state="rendering")
    monkeypatch.setattr(cli, "_config", lambda: web_cfg)
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr("clipper.web.tasks.start_daily_cleanup", lambda cfg: None)
    assert cli.main(["serve", "--no-browser"]) == 0
    from clipper import jobs
    assert jobs.get_status(stuck)["failed_step"] == "render"


def test_a_second_serve_exits_without_touching_the_queue(web_cfg, monkeypatch, capsys):
    import fcntl

    web_cfg.jobs_dir.mkdir(parents=True, exist_ok=True)
    held = open(web_cfg.jobs_dir / "serve.lock", "a+")        # the first server
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    held.write("8765")
    held.flush()
    monkeypatch.setattr(cli, "_config", lambda: web_cfg)
    touched = []
    monkeypatch.setattr(cli.pipeline, "clean", lambda cfg, **kw: touched.append("clean") or [])
    monkeypatch.setattr("clipper.web.worker.Worker.start", lambda self: touched.append("worker"))
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: touched.append("uvicorn"))
    try:
        assert cli.main(["serve", "--no-browser"]) == 1
    finally:
        held.close()
    assert touched == []
    assert "already running" in capsys.readouterr().out
