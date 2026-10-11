
import pytest

from clipper import fetch, jobs
from clipper.config import AppConfig
from clipper.models import Meta


def test_local_file_meta_uses_filename_as_title(monkeypatch, tmp_path):
    src = tmp_path / "Ep 12 Jane.mkv"
    src.write_bytes(b"x")
    monkeypatch.setattr(fetch.shell, "run", lambda cmd, **k: "")
    monkeypatch.setattr(fetch, "_probe_source", lambda p: (3840, 2160, 60.0, 1800.0))
    monkeypatch.setattr(fetch, "_probe_proxy", lambda p: (1280, 720, 60.0))
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("job", cfg)
    paths.proxy.write_bytes(b"x")
    meta = fetch.fetch(str(src), paths, cfg)
    assert meta.source_kind == "local"
    assert meta.title == "Ep 12 Jane"
    assert meta.description == ""
    assert meta.source == str(src.resolve())


def test_missing_local_file_raises_clear_error(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("job", cfg)
    with pytest.raises(fetch.FetchError, match="not found"):
        fetch.fetch(str(tmp_path / "nope.mp4"), paths, cfg)


def _meta(kind, source):
    return Meta(job_id="j", source_kind=kind, source=source, title="a", description="",
                channel="", duration=100.0, width=1920, height=1080, fps=30.0, max_height=1080)


def test_a_link_is_refused_before_anything_is_fetched(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(fetch.shell, "run", lambda cmd, **k: ran.append(cmd) or "")
    cfg = AppConfig(jobs_dir=tmp_path)
    with pytest.raises(fetch.FetchError, match="video files, not links"):
        fetch.fetch("https://youtu.be/abc", jobs.paths_for("job", cfg), cfg)
    assert ran == []
    with pytest.raises(ValueError, match="video files, not links"):
        jobs.job_id_for("https://www.youtube.com/watch?v=abc")


def test_clips_are_cut_from_your_original_file(tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    paths = jobs.paths_for("j", AppConfig(jobs_dir=tmp_path))
    assert fetch.source_file(_meta("local", str(src)), paths) == src


def test_a_job_made_from_a_link_by_an_older_clipper_renders_from_its_working_copy(tmp_path):
    paths = jobs.paths_for("j", AppConfig(jobs_dir=tmp_path))
    old = _meta("youtube", "https://youtu.be/abc")
    with pytest.raises(fetch.FetchError, match="Start a new job from the video file"):
        fetch.source_file(old, paths)                       # working copy already cleaned up
    paths.proxy.write_bytes(b"x")
    assert fetch.source_file(old, paths) == paths.proxy


def test_old_meta_without_a_handle_still_loads():
    old = {"job_id": "v", "source_kind": "youtube", "source": "s", "title": "t", "description": "",
           "channel": "c", "duration": 1.0, "width": 1, "height": 1, "fps": 30.0, "max_height": 720}
    assert Meta.from_dict(old).channel_handle == ""


# --- section downloads survive YouTube's occasional refusals ----------------------------------

FORBIDDEN = ("https://rr15---sn.googlevideo.com/videoplayback?sig=AE0s2&lsig=APaTxx.\n"
             "Error opening input files: Server returned 403 Forbidden (access denied)\n\n"
             "ERROR: ffmpeg exited with code 8\n")


def _yt_meta():
    return Meta(job_id="j", source_kind="local", source="/videos/j.mp4", title="a",
                description="", channel="C", duration=100.0, width=1920, height=1080, fps=30.0,
                max_height=1080)
