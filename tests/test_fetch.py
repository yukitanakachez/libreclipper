
import pytest

from clipper import fetch, jobs
from clipper.config import AppConfig
from clipper.models import Meta


def test_youtube_command_requests_720p_and_no_cookies_by_default(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(fetch, "_run_ytdlp_json", lambda *a, **k: {
        "title": "Ep 1", "channel": "Pod", "description": "d",
        "duration": 3600.0, "width": 3840, "height": 2160, "fps": 30.0})
    monkeypatch.setattr(fetch.shell, "run", lambda cmd, **k: seen.append(cmd) or "")
    monkeypatch.setattr(fetch, "_probe_proxy", lambda p: (1280, 720, 30.0))
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("vid", cfg)
    paths.proxy.write_bytes(b"x")
    meta = fetch.fetch("https://youtu.be/vid", paths, cfg)
    cmd = " ".join(seen[0])
    assert "height<=720" in cmd
    assert "--cookies-from-browser" not in cmd
    assert meta.source_kind == "youtube"
    assert meta.max_height == 2160


def test_youtube_command_includes_cookies_when_configured(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(fetch, "_run_ytdlp_json", lambda *a, **k: {
        "title": "t", "channel": "c", "description": "", "duration": 10.0,
        "width": 1920, "height": 1080, "fps": 30.0})
    monkeypatch.setattr(fetch.shell, "run", lambda cmd, **k: seen.append(cmd) or "")
    monkeypatch.setattr(fetch, "_probe_proxy", lambda p: (1280, 720, 30.0))
    cfg = AppConfig(jobs_dir=tmp_path, cookies_from_browser="chrome")
    paths = jobs.paths_for("vid", cfg)
    paths.proxy.write_bytes(b"x")
    fetch.fetch("https://youtu.be/vid", paths, cfg)
    assert "--cookies-from-browser" in " ".join(seen[0])


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


def test_extractor_failure_message_tells_user_to_update_ytdlp(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise fetch.shell.CommandError(["yt-dlp"], 1, "ERROR: Unable to extract player response")
    monkeypatch.setattr(fetch, "_run_ytdlp_json", boom)
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("vid", cfg)
    with pytest.raises(fetch.FetchError, match="uv run yt-dlp -U"):
        fetch.fetch("https://youtu.be/vid", paths, cfg)


def test_download_section_for_local_returns_source_unchanged(tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    meta = Meta(job_id="j", source_kind="local", source=str(src), title="a",
                description="", channel="", duration=100.0, width=1920,
                height=1080, fps=30.0, max_height=1080)
    cfg = AppConfig(jobs_dir=tmp_path)
    assert fetch.download_section(meta, 10, 20, tmp_path / "unused.mp4", cfg) == src


def test_youtube_meta_keeps_the_channel_handle(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "_run_ytdlp_json", lambda *a, **k: {
        "title": "t", "channel": "Just One More Thing", "uploader_id": "@JustOneMoreThing",
        "description": "", "duration": 10.0, "width": 1920, "height": 1080, "fps": 30.0})
    monkeypatch.setattr(fetch.shell, "run", lambda cmd, **k: "")
    monkeypatch.setattr(fetch, "_probe_proxy", lambda p: (1280, 720, 30.0))
    paths = jobs.paths_for("vid", AppConfig(jobs_dir=tmp_path))
    paths.proxy.write_bytes(b"x")
    assert fetch.fetch("https://youtu.be/vid", paths, AppConfig(jobs_dir=tmp_path)).channel_handle == "@JustOneMoreThing"


def test_old_meta_without_a_handle_still_loads():
    old = {"job_id": "v", "source_kind": "youtube", "source": "s", "title": "t", "description": "",
           "channel": "c", "duration": 1.0, "width": 1, "height": 1, "fps": 30.0, "max_height": 720}
    assert Meta.from_dict(old).channel_handle == ""


# --- section downloads survive YouTube's occasional refusals ----------------------------------

FORBIDDEN = ("https://rr15---sn.googlevideo.com/videoplayback?sig=AE0s2&lsig=APaTxx.\n"
             "Error opening input files: Server returned 403 Forbidden (access denied)\n\n"
             "ERROR: ffmpeg exited with code 8\n")


def _yt_meta():
    return Meta(job_id="j", source_kind="youtube", source="https://youtu.be/j", title="a",
                description="", channel="C", duration=100.0, width=1920, height=1080, fps=30.0,
                max_height=1080)


def test_a_refused_section_download_is_tried_again(monkeypatch, tmp_path):
    calls, waits = [], []

    def run(cmd, **k):
        calls.append(cmd)
        if len(calls) < 3:
            raise fetch.shell.CommandError(cmd, 1, FORBIDDEN)
        return ""
    monkeypatch.setattr(fetch.shell, "run", run)
    monkeypatch.setattr(fetch.time, "sleep", waits.append)
    dest = tmp_path / "s" / "a.mp4"
    assert fetch.download_section(_yt_meta(), 10, 20, dest, AppConfig(jobs_dir=tmp_path)) == dest
    assert len(calls) == 3 and len(waits) == 2 and waits[1] > waits[0]


def test_a_section_youtube_keeps_refusing_says_so_plainly(monkeypatch, tmp_path):
    calls = []

    def run(cmd, **k):
        calls.append(cmd)
        raise fetch.shell.CommandError(cmd, 1, FORBIDDEN)
    monkeypatch.setattr(fetch.shell, "run", run)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(fetch.FetchError) as err:
        fetch.download_section(_yt_meta(), 10, 20, tmp_path / "a.mp4", AppConfig(jobs_dir=tmp_path))
    assert len(calls) == fetch.SECTION_TRIES
    text = str(err.value)
    assert "YouTube refused" in text and "Retry" in text and "googlevideo" not in text


def test_other_section_failures_are_not_retried_and_are_translated(monkeypatch, tmp_path):
    calls = []

    def run(cmd, **k):
        calls.append(cmd)
        raise fetch.shell.CommandError(cmd, 1, "ERROR: [youtube] j: Private video. Sign in")
    monkeypatch.setattr(fetch.shell, "run", run)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    with pytest.raises(fetch.FetchError, match="private"):
        fetch.download_section(_yt_meta(), 10, 20, tmp_path / "a.mp4", AppConfig(jobs_dir=tmp_path))
    assert len(calls) == 1
