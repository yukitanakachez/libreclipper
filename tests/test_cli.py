from pathlib import Path

from clipper import cli, jobs
from clipper.config import AppConfig
from clipper.models import Candidate


def _candidates(paths, cfg):
    cands = [
        Candidate(n=1, start=10.0, end=40.0, orig_start=10.0, orig_end=40.0,
                  headline="First", hook="k", reason="why one", score=9,
                  post_caption="c", hashtags=[]),
        Candidate(n=2, start=60.0, end=90.0, orig_start=60.0, orig_end=90.0,
                  headline="Second", hook="k", reason="why two", score=7,
                  post_caption="c", hashtags=[]),
    ]
    jobs.write_json(paths.candidates,
                    {"model": "claude-opus-5", "campaign": "example",
                     "candidates": [c.to_dict() for c in cands]})


def test_approve_marks_only_the_listed_candidates(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    paths = jobs.paths_for("job1", cfg)
    _candidates(paths, cfg)

    assert cli.main(["approve", "job1", "2"]) == 0

    written = jobs.read_json(paths.candidates)["candidates"]
    assert [c["approved"] for c in written] == [False, True]


def test_approve_rejects_an_unknown_candidate_number(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    paths = jobs.paths_for("job1", cfg)
    _candidates(paths, cfg)

    code = cli.main(["approve", "job1", "5"])

    assert code == 1
    assert "5" in capsys.readouterr().out
    assert all(c["approved"] is False for c in jobs.read_json(paths.candidates)["candidates"])


def test_run_prints_each_candidate(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    paths = jobs.paths_for("job1", cfg)
    _candidates(paths, cfg)
    monkeypatch.setattr(cli.pipeline, "run_job", lambda *a, **k: paths)

    assert cli.main(["run", "/videos/x.mp4", "--campaign", "example"]) == 0

    out = capsys.readouterr().out
    assert "First" in out and "Second" in out
    assert "why one" in out


def test_doctor_returns_nonzero_when_a_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli.doctor, "check_all",
                        lambda: [("thing", False, "do this")])
    assert cli.main(["doctor"]) == 1
    assert "do this" in capsys.readouterr().out


def test_doctor_returns_zero_when_everything_passes(monkeypatch, capsys):
    monkeypatch.setattr(cli.doctor, "check_all", lambda: [("thing", True, "")])
    assert cli.main(["doctor"]) == 0


def test_render_prints_each_output(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    monkeypatch.setattr(cli.pipeline, "render_approved",
                        lambda job_id, c: [Path("out/01-a.mp4")])
    assert cli.main(["render", "job1"]) == 0
    assert "01-a.mp4" in capsys.readouterr().out


def test_failure_is_reported_without_a_traceback(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)

    def boom(*a, **k):
        raise RuntimeError("yt-dlp needs updating")

    monkeypatch.setattr(cli.pipeline, "run_job", boom)
    code = cli.main(["run", "/videos/x.mp4", "--campaign", "example"])
    assert code == 1
    assert "yt-dlp needs updating" in capsys.readouterr().err


def test_run_from_passes_the_starting_step(tmp_path, monkeypatch, capsys):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    paths = jobs.paths_for("job1", cfg)
    _candidates(paths, cfg)
    seen = {}
    monkeypatch.setattr(cli.pipeline, "run_job",
                        lambda *a, **k: seen.update(k) or paths)
    assert cli.main(["run", "/videos/x.mp4", "--campaign", "example", "--from", "pick"]) == 0
    assert seen["start_from"] == "pick"


def test_preview_uses_the_campaigns_pacing(tmp_path, monkeypatch):
    from clipper.models import CropPlan, Meta, Segment, Transcript, Word

    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(cli, "_config", lambda: cfg)
    paths = jobs.paths_for("job1", cfg)
    _candidates(paths, cfg)
    jobs.write_json(paths.meta, Meta(job_id="job1", source_kind="local", source="x.mp4",
                                     title="t", description="", channel="", duration=120.0,
                                     width=1280, height=720, fps=30.0, max_height=720).to_dict())
    jobs.write_json(paths.transcript, Transcript([Word(0, "hi.", 10.0, 10.4, 0.9)],
                                                 [Segment(10.0, 10.4, "hi.", 0, 0)], 120.0).to_dict())
    jobs.write_json(paths.crop_plan, {"plans": [CropPlan(n, 0.0, 120.0, []).to_dict()
                                                for n in (1, 2)]})
    seen = []
    monkeypatch.setattr(cli.preview, "render_preview",
                        lambda *a, **k: seen.append(k) or Path("p.mp4"))

    assert cli.main(["preview", "job1"]) == 0
    assert all(k.get("pacing") is not None and k.get("transcript") is not None for k in seen)



def test_config_is_read_from_the_project_folder_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.chdir("/")
    (tmp_path / "config.yaml").write_text("model: claude-sonnet-5\n")
    assert cli._config().model == "claude-sonnet-5"
