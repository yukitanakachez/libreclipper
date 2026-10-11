from pathlib import Path

import pytest

from clipper.config import load_config


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    cfg = load_config(None)
    assert cfg.model == "claude-opus-5"
    assert cfg.retention_days == 7
    assert cfg.jobs_dir == tmp_path / "jobs"


def test_file_values_override_defaults(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "model: claude-sonnet-5\nretention_days: 3\n"
        "jobs_dir: /tmp/clipjobs\n"
        "max_height: 1080\nyoutube: { cookies_from_browser: chrome }\n"   # from older versions: ignored
    )
    cfg = load_config(p)
    assert cfg.model == "claude-sonnet-5"
    assert cfg.retention_days == 3
    assert cfg.jobs_dir == Path("/tmp/clipjobs")


def test_rejects_unknown_model(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("model: gpt-4\n")
    try:
        load_config(p)
    except ValueError as exc:
        assert "claude-opus-5" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_whisper_backend_defaults_to_what_this_computer_can_run(tmp_path, monkeypatch):
    from clipper import config
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.platform, "machine", lambda: "arm64")
    assert load_config(None).whisper_backend == "mlx"
    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert load_config(None).whisper_backend == "faster_whisper"


def test_whisper_backend_can_be_faster_whisper(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("whisper: { backend: faster_whisper }\n")
    assert load_config(p).whisper_backend == "faster_whisper"


def test_rejects_unknown_whisper_backend(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("whisper: { backend: vosk }\n")
    with pytest.raises(ValueError, match="faster_whisper"):
        load_config(p)



def test_relative_paths_resolve_against_the_project_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.chdir("/")
    p = tmp_path / "config.yaml"
    p.write_text("jobs_dir: work\nclips_dir: clips\n")
    cfg = load_config(p)
    assert cfg.jobs_dir == tmp_path / "work"
    assert cfg.clips_dir == tmp_path / "clips"


def test_home_directory_paths_are_expanded(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("jobs_dir: ~/clipper-jobs\n")
    assert load_config(p).jobs_dir == Path.home() / "clipper-jobs"


def test_clips_dir_is_unset_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    assert load_config(None).clips_dir is None
