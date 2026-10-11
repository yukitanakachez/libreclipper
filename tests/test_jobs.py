import json

import pytest

from clipper import jobs
from clipper.config import AppConfig
from clipper.models import Segment, Transcript, Word


def test_job_id_from_local_file_is_slug_plus_hash(tmp_path):
    f = tmp_path / "Ep 12 — Jane Doe.mp4"
    f.write_bytes(b"x")
    job_id = jobs.job_id_for(str(f))
    assert job_id.startswith("ep-12-jane-doe-")
    assert jobs.job_id_for(str(f)) == job_id          # stable
    assert len(job_id.split("-")[-1]) == 8


def test_write_json_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "a.json"
    jobs.write_json(target, {"hello": "world"})
    assert json.loads(target.read_text()) == {"hello": "world"}
    assert list(tmp_path.iterdir()) == [target]


def test_write_json_does_not_clobber_on_serialization_error(tmp_path):
    target = tmp_path / "a.json"
    jobs.write_json(target, {"ok": 1})
    with pytest.raises(TypeError):
        jobs.write_json(target, {"bad": object()})
    assert json.loads(target.read_text()) == {"ok": 1}


def test_status_roundtrip(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("abc", cfg)
    jobs.set_status(paths, "transcribing", progress=0.43)
    s = jobs.get_status(paths)
    assert s["state"] == "transcribing"
    assert s["progress"] == 0.43
    assert s["error"] is None
    jobs.set_status(paths, "failed", error="boom", failed_step="fetch")
    s = jobs.get_status(paths)
    assert (s["state"], s["error"], s["failed_step"]) == ("failed", "boom", "fetch")


def test_transcript_roundtrip():
    t = Transcript(
        words=[Word(0, "hi", 0.0, 0.2, 0.9)],
        segments=[Segment(0.0, 0.2, "hi", 0, 0)],
        duration=1.0,
    )
    assert Transcript.from_dict(t.to_dict()) == t


def test_finished_clips_go_to_clips_dir_when_set(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path / "work", clips_dir=tmp_path / "clips")
    paths = jobs.paths_for("abc", cfg)
    assert paths.out == tmp_path / "clips" / "abc"
    assert paths.proxy == tmp_path / "work" / "abc" / "proxy.mp4"


def test_finished_clips_stay_in_the_job_folder_by_default(tmp_path):
    paths = jobs.paths_for("abc", AppConfig(jobs_dir=tmp_path))
    assert paths.out == tmp_path / "abc" / "out"


def test_find_job_rejects_unsafe_ids_and_never_creates_folders(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    assert jobs.find_job("../etc", cfg) is None
    assert jobs.find_job("a/b", cfg) is None
    assert jobs.find_job("missing", cfg) is None
    assert not (tmp_path / "missing").exists()
    jobs.paths_for("real_1", cfg)
    assert jobs.find_job("real_1", cfg).root == tmp_path / "real_1"


def test_read_request_falls_back_for_jobs_made_before_job_json(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("old", cfg)
    jobs.write_json(paths.meta, {"source": "/videos/old.mp4"})
    jobs.write_json(paths.candidates, {"campaign": "pod", "candidates": []})
    assert jobs.read_request(paths) == {"source": "/videos/old.mp4", "campaign": "pod"}


def test_candidate_without_edited_field_loads_with_false():
    from clipper.models import Candidate
    old = {"n": 1, "start": 0.0, "end": 1.0, "orig_start": 0.0, "orig_end": 1.0,
           "headline": "h", "hook": "k", "reason": "r", "score": 9, "post_caption": "c",
           "hashtags": [], "layout": "auto", "music_on": False, "music_track": None,
           "approved": False, "needs_check": False}
    assert Candidate.from_dict(old).edited is False
