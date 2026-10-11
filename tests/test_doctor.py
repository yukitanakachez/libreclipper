from clipper import doctor, shell

ALL_FILTERS = "ass\nsubtitles\nloudnorm\nsidechaincompress\n"


def test_reports_libass_missing(monkeypatch):
    monkeypatch.setattr(doctor.shell, "run", lambda cmd, **k: "sidechaincompress\n")
    results = {name: ok for name, ok, _ in doctor.check_all()}
    assert results["ffmpeg libass"] is False


def test_passes_when_all_filters_present(monkeypatch):
    monkeypatch.setattr(doctor.shell, "run", lambda cmd, **k: ALL_FILTERS)
    monkeypatch.setattr(doctor, "_font_ok", lambda: True)
    monkeypatch.setattr(doctor, "_model_ok", lambda: True)
    monkeypatch.setattr(doctor, "_provider_row", lambda: ("AI provider (Anthropic)", True, "fix"))
    assert all(ok for _, ok, _ in doctor.check_all())


def test_missing_ffmpeg_does_not_raise(monkeypatch):
    def boom(cmd, **k):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(doctor.shell, "run", boom)
    results = {name: ok for name, ok, _ in doctor.check_all()}
    assert results["ffmpeg libass"] is False


def test_every_failure_carries_a_fix_instruction(monkeypatch):
    monkeypatch.setattr(doctor, "LIVE", True)       # safe: keys unset and shell.run faked below
    monkeypatch.setattr(doctor.shell, "run", lambda cmd, **k: "")
    monkeypatch.setattr(doctor, "_font_ok", lambda: False)
    monkeypatch.setattr(doctor, "_model_ok", lambda: False)
    monkeypatch.setattr(doctor, "_provider_row", lambda: ("AI provider (Anthropic)", False, "fix"))
    monkeypatch.setattr(doctor, "_runs_from_source", lambda: False)
    for name, ok, fix in doctor.check_all():
        assert ok is False
        assert fix.strip(), f"{name} has no remedy text"


def test_asset_checks_use_absolute_paths():
    """doctor must agree with the modules that load these files, from any cwd."""
    assert doctor.font_path().is_absolute()
    assert doctor.model_path().is_absolute()


def test_reports_when_clipper_is_not_running_from_this_source_tree(monkeypatch, tmp_path):
    """A stale installed copy silently ignores code changes."""
    monkeypatch.setattr(doctor.shell, "run", lambda cmd, **k: ALL_FILTERS)
    monkeypatch.setattr(doctor, "_font_ok", lambda: True)
    monkeypatch.setattr(doctor, "_model_ok", lambda: True)
    monkeypatch.setattr(doctor, "_provider_row", lambda: ("AI provider (Anthropic)", True, "fix"))
    monkeypatch.setattr(doctor.shell, "project_home", lambda: tmp_path)
    results = {name: (ok, fix) for name, ok, fix in doctor.check_all()}
    ok, fix = results["runs from source"]
    assert ok is False
    assert "chflags nohidden" in fix


def test_running_from_source_passes_in_this_checkout():
    results = {name: ok for name, ok, _ in doctor.check_all()}
    assert results["runs from source"] is True


def test_ytdlp_check_runs_one_small_search(monkeypatch):
    monkeypatch.setattr(doctor, "LIVE", True)
    calls = []
    ok, _ = doctor.ytdlp_check(run=lambda cmd, timeout=60: calls.append(cmd) or "abc\n")
    assert ok and "--flat-playlist" in calls[0]
    def broken(cmd, timeout=60):
        raise shell.CommandError(cmd, 1, "ERROR: unable to extract")
    ok, fix = doctor.ytdlp_check(run=broken)
    assert not ok and "updating yt-dlp" in fix


