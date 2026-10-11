import os
import time
from pathlib import Path

import pytest

from clipper import jobs, pipeline
from clipper.config import AppConfig
from clipper.models import Meta, Segment, Transcript, Word


def _fake_meta(tmp_path: Path) -> Meta:
    return Meta(job_id="abc", source_kind="local", source="/videos/abc.mp4",
                title="T", description="", channel="C", duration=120.0,
                width=1280, height=720, fps=30.0, max_height=2160)


def _fake_transcript() -> Transcript:
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(40)]
    segments = [Segment(words[s].start, words[s + 9].end, "s", s, s + 9)
                for s in range(0, 40, 10)]
    return Transcript(words, segments, 120.0)


def _stub_all(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: _fake_meta(tmp_path))
    monkeypatch.setattr(pipeline, "_transcribe", lambda *a, **k: _fake_transcript())
    monkeypatch.setattr(pipeline, "_pick", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "_reframe", lambda *a, **k: [])


def test_run_job_sets_status_through_each_step(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    seen = []
    real_set_status = jobs.set_status
    monkeypatch.setattr(jobs, "set_status",
                        lambda paths, state, **kw: seen.append(state) or
                        real_set_status(paths, state, **kw))
    _stub_all(monkeypatch, tmp_path)
    pipeline.run_job("/videos/abc.mp4", "example", cfg, job_id="abc")
    assert seen[:4] == ["fetching", "transcribing", "picking", "reframing"]
    assert seen[-1] == "ready_for_review"


def test_run_job_records_failure_with_step(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)

    def boom(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(pipeline, "_fetch", boom)
    with pytest.raises(RuntimeError):
        pipeline.run_job("/videos/abc.mp4", "example", cfg, job_id="abc")
    status = jobs.get_status(jobs.paths_for("abc", cfg))
    assert status["state"] == "failed"
    assert status["failed_step"] == "fetch"
    assert "no network" in status["error"]


def test_stop_after_halts_the_pipeline(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: _fake_meta(tmp_path))
    called = []
    monkeypatch.setattr(pipeline, "_transcribe",
                        lambda *a, **k: called.append("t") or _fake_transcript())
    pipeline.run_job("/videos/abc.mp4", "example", cfg, stop_after="fetch", job_id="abc")
    assert called == []


def test_unknown_campaign_fails_before_any_download(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    called = []
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: called.append("f"))
    from clipper.campaigns import CampaignError
    with pytest.raises(CampaignError):
        pipeline.run_job("/videos/abc.mp4", "no-such-campaign", cfg, job_id="abc")
    assert called == []


def test_clean_removes_proxy_after_retention_but_keeps_json(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, retention_days=7)
    paths = jobs.paths_for("old", cfg)
    paths.proxy.write_bytes(b"x")
    jobs.write_json(paths.candidates, {"candidates": []})
    jobs.set_status(paths, "done")
    old = time.time() - 8 * 86400
    for f in (paths.status, paths.candidates):          # nothing touched for 8 days
        os.utime(f, (old, old))

    removed = pipeline.clean(cfg)

    assert paths.proxy in removed
    assert not paths.proxy.exists()
    assert paths.candidates.exists()


def test_clean_removes_a_dropped_video_with_its_old_job_but_never_one_still_in_use(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, retention_days=7)
    uploads = jobs.uploads_dir(cfg)
    uploads.mkdir(parents=True)
    old = time.time() - 8 * 86400

    def dropped(name, age=old):
        video = uploads / name
        video.write_bytes(b"x")
        os.utime(video, (age, age))
        return video

    def job(job_id, source, touched):
        paths = jobs.paths_for(job_id, cfg)
        jobs.write_json(paths.request, {"source": str(source), "campaign": "pod"})
        jobs.set_status(paths, "done")
        for f in (paths.status, paths.request):
            os.utime(f, (touched, touched))

    stale, live, orphan, fresh = dropped("stale.mp4"), dropped("live.mp4"), dropped("orphan.mp4"), \
        dropped("fresh.mp4", age=time.time())
    half = dropped("half.mp4.partial", age=time.time())
    mine = tmp_path.parent / "mine.mp4"                # a file chosen from disk: not Clipper's
    mine.write_bytes(b"x")
    os.utime(mine, (old, old))
    job("old-job", stale, old)
    job("live-job", live, time.time())                 # an old copy, but its job was touched today
    job("my-job", mine, old)

    removed = pipeline.clean(cfg)

    assert stale in removed and orphan in removed
    assert not stale.exists() and not orphan.exists()
    assert live.exists() and fresh.exists() and mine.exists()
    assert half.exists()                               # a copy may be arriving right now
    pipeline.clean(cfg, all_partials=True)             # at server start nothing can be
    assert not half.exists()


def test_clean_keeps_recent_jobs(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, retention_days=7)
    paths = jobs.paths_for("new", cfg)
    paths.proxy.write_bytes(b"x")
    jobs.set_status(paths, "done")
    assert pipeline.clean(cfg) == []
    assert paths.proxy.exists()


def test_clean_also_clears_sections_and_work_dirs(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, retention_days=7)
    paths = jobs.paths_for("old", cfg)
    paths.sections.mkdir()
    (paths.sections / "01.mp4").write_bytes(b"x")
    paths.work.mkdir()
    (paths.work / "clip_01.ass").write_text("x")
    paths.out.mkdir()
    (paths.out / "01-a.mp4").write_bytes(b"x")
    jobs.set_status(paths, "done")
    old = time.time() - 8 * 86400
    os.utime(paths.status, (old, old))

    pipeline.clean(cfg)

    assert not paths.sections.exists()
    assert not paths.work.exists()
    assert (paths.out / "01-a.mp4").exists()      # finished clips are never deleted


def test_campaign_root_is_absolute(tmp_path, monkeypatch):
    """An installed `clipper` runs from any cwd; campaigns/ must still resolve."""
    assert pipeline.campaign_root().is_absolute()
    assert pipeline.campaign_root().name == "campaigns"


def _saved_job(tmp_path) -> AppConfig:
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("abc", cfg)
    jobs.write_json(paths.meta, _fake_meta(tmp_path).to_dict())
    jobs.write_json(paths.transcript, _fake_transcript().to_dict())
    return cfg


def test_start_from_pick_reuses_the_saved_download_and_transcript(tmp_path, monkeypatch):
    cfg = _saved_job(tmp_path)
    called = []
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: called.append("fetch"))
    monkeypatch.setattr(pipeline, "_transcribe", lambda *a, **k: called.append("transcribe"))
    monkeypatch.setattr(pipeline, "_pick",
                        lambda transcript, *a, **k: called.append(("pick", len(transcript.words))) or [])
    monkeypatch.setattr(pipeline, "_reframe", lambda *a, **k: called.append("reframe"))

    pipeline.run_job("/videos/abc.mp4", "example", cfg, start_from="pick", job_id="abc")

    assert called == [("pick", 40), "reframe"]


def test_start_from_pick_without_a_transcript_says_what_is_missing(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    jobs.write_json(jobs.paths_for("abc", cfg).meta, _fake_meta(tmp_path).to_dict())
    with pytest.raises(pipeline.PipelineError, match="transcript.json"):
        pipeline.run_job("/videos/abc.mp4", "example", cfg, start_from="pick", job_id="abc")


def test_start_from_fetch_is_a_normal_run(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    _stub_all(monkeypatch, tmp_path)
    called = []
    monkeypatch.setattr(pipeline, "_fetch",
                        lambda *a, **k: called.append("fetch") or _fake_meta(tmp_path))
    pipeline.run_job("/videos/abc.mp4", "example", cfg, start_from="fetch", job_id="abc")
    assert called == ["fetch"]


def test_run_job_records_what_was_asked_for(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    _stub_all(monkeypatch, tmp_path)
    pipeline.run_job("/videos/abc.mp4", "example", cfg, job_id="abc")
    request = jobs.read_json(jobs.paths_for("abc", cfg).request)
    assert request["source"] == "/videos/abc.mp4"
    assert request["campaign"] == "example"
    assert "created_at" in request


def test_clean_counts_review_edits_as_activity(tmp_path):
    # Reviewing over more than retention_days must not delete the proxy mid-review.
    cfg = AppConfig(jobs_dir=tmp_path, retention_days=7)
    paths = jobs.paths_for("reviewing", cfg)
    paths.proxy.write_bytes(b"x")
    jobs.set_status(paths, "ready_for_review")
    old = time.time() - 8 * 86400
    os.utime(paths.status, (old, old))
    jobs.write_json(paths.candidates, {"candidates": []})     # edited just now

    assert pipeline.clean(cfg) == []
    assert paths.proxy.exists()


def _partials(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path / "jobs", clips_dir=tmp_path / "clips")
    paths = jobs.paths_for("crashed", cfg)
    jobs.set_status(paths, "rendering")
    paths.out.mkdir(parents=True)
    paths.work.mkdir()
    stale = paths.out / "01-a.partial.mp4"
    stale.write_bytes(b"x")
    two_hours_ago = time.time() - 7200
    os.utime(stale, (two_hours_ago, two_hours_ago))
    fresh = paths.work / "preview_01_1.00-2.00.partial.mp4"
    fresh.write_bytes(b"x")
    return cfg, stale, fresh


def test_clean_removes_leftover_partial_files_but_not_a_render_in_progress(tmp_path):
    cfg, stale, fresh = _partials(tmp_path)
    removed = pipeline.clean(cfg)
    assert stale in removed and not stale.exists()
    assert fresh.exists(), "a running encode keeps its file fresh; never pull it away"


def test_clean_at_server_start_removes_every_partial_file(tmp_path):
    cfg, stale, fresh = _partials(tmp_path)
    pipeline.clean(cfg, all_partials=True)
    assert not stale.exists() and not fresh.exists()



def test_picking_uses_the_campaign_as_it_applies_to_this_video(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    seen = []
    _stub_all(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "_pick", lambda t, m, campaign, *a, **k: seen.append(campaign) or [])
    pipeline.run_job("/videos/abc.mp4", "auto", cfg, job_id="abc")
    assert seen[0].credit_handle == "@C" and seen[0].required_hashtags == ["#c"]


def test_the_creator_you_name_is_credited_and_tagged_by_the_auto_campaign(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    seen = []
    _stub_all(monkeypatch, tmp_path)
    file_meta = Meta(job_id="abc", source_kind="local", source="/videos/abc.mp4", title="abc",
                     description="", channel="", duration=600.0, width=1280, height=720,
                     fps=30.0, max_height=2160)                       # a file: no channel of its own
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: file_meta)
    monkeypatch.setattr(pipeline, "_pick", lambda t, m, campaign, *a, **k: seen.append(campaign) or [])

    pipeline.run_job("/videos/abc.mp4", "auto", cfg, job_id="abc", creator=" jane.doe ")

    assert seen[0].credit_enabled and seen[0].credit_handle == "@jane.doe"
    assert seen[0].required_hashtags == ["#janedoe"]
    paths = jobs.paths_for("abc", cfg)
    assert jobs.read_json(paths.request)["creator"] == "@jane.doe"
    assert jobs.read_json(paths.meta)["channel_handle"] == "@jane.doe"     # kept for later renders


def test_with_no_creator_named_a_file_gets_no_credit(tmp_path, monkeypatch):
    cfg = AppConfig(jobs_dir=tmp_path)
    seen = []
    _stub_all(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "_fetch", lambda *a, **k: Meta(
        job_id="abc", source_kind="local", source="/videos/abc.mp4", title="abc", description="",
        channel="", duration=600.0, width=1280, height=720, fps=30.0, max_height=2160))
    monkeypatch.setattr(pipeline, "_pick", lambda t, m, campaign, *a, **k: seen.append(campaign) or [])
    pipeline.run_job("/videos/abc.mp4", "auto", cfg, job_id="abc")
    assert not seen[0].credit_enabled and seen[0].required_hashtags == []
