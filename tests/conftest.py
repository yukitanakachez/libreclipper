"""Fixtures for the web tests: a project home, a config, and a reviewable job."""

import pytest

from clipper import jobs
from clipper.config import AppConfig
from clipper.models import (
    Candidate,
    CropPlan,
    CropSegment,
    Meta,
    Rect,
    Segment,
    Transcript,
    Word,
)


@pytest.fixture
def web_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    (tmp_path / "campaigns").mkdir()
    (tmp_path / "campaigns" / "pod.yaml").write_text(
        "name: Pod\nclip_length: { min: 2, max: 20 }\n")
    (tmp_path / "music" / "pod").mkdir(parents=True)
    (tmp_path / "music" / "pod" / "bed.mp3").write_bytes(b"x")
    (tmp_path / "campaigns" / "musical.yaml").write_text(
        "name: Musical\nclip_length: { min: 2, max: 20 }\n"
        "music: { allowed: true, folder: music/pod }\n")
    return tmp_path


@pytest.fixture
def web_cfg(web_home):
    return AppConfig(jobs_dir=web_home / "jobs", clips_dir=web_home / "clips")


def _transcript() -> Transcript:
    # w0..w59 every 0.5 s; every fifth word ends a sentence ("w4.", "w9." ...)
    words = [Word(i, f"w{i}." if i % 5 == 4 else f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9)
             for i in range(60)]
    segments = [Segment(words[s].start, words[s + 4].end, "s", s, s + 4)
                for s in range(0, 60, 5)]
    return Transcript(words, segments, 30.0)


@pytest.fixture
def web_job(web_cfg):
    """A job ready for review: two candidates, crop plans with ±5 s analyzed ranges."""
    def make(job_id="vid1", state="ready_for_review", campaign="pod"):
        paths = jobs.paths_for(job_id, web_cfg)
        jobs.write_json(paths.request, {"source": f"https://youtu.be/{job_id}",
                                        "campaign": campaign})
        jobs.write_json(paths.meta, Meta(
            job_id=job_id, source_kind="youtube", source=f"https://youtu.be/{job_id}",
            title="Episode", description="", channel="Pod", duration=30.0,
            width=1280, height=720, fps=30.0, max_height=1080).to_dict())
        jobs.write_json(paths.transcript, _transcript().to_dict())
        cands = [Candidate(n=1, start=5.0, end=9.9, orig_start=5.0, orig_end=9.9,
                           headline="One", hook="w10", reason="r", score=9,
                           post_caption="c1", hashtags=[]),
                 Candidate(n=2, start=15.0, end=19.9, orig_start=15.0, orig_end=19.9,
                           headline="Two", hook="w30", reason="r", score=8,
                           post_caption="c2", hashtags=[])]
        jobs.write_json(paths.candidates, {"model": "claude-opus-5", "campaign": campaign,
                                           "candidates": [c.to_dict() for c in cands]})
        seg = [CropSegment(0.0, 30.0, "single", [Rect(0.3, 0.0, 0.3, 1.0)])]
        jobs.write_json(paths.crop_plan, {"plans": [
            CropPlan(1, 0.0, 14.9, seg).to_dict(), CropPlan(2, 10.0, 24.9, seg).to_dict()]})
        jobs.set_status(paths, state)
        return paths
    return make


@pytest.fixture(autouse=True)
def _no_live_doctor(monkeypatch):
    monkeypatch.setattr("clipper.doctor.LIVE", False)
    monkeypatch.setattr("clipper.provision.AUTO", False)
