import os

from clipper import shell


def test_ffmpeg_defaults_to_the_path_binary(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIPPER_FFMPEG", raising=False)
    monkeypatch.delenv("CLIPPER_FFPROBE", raising=False)
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))   # no local build here
    assert shell.ffmpeg() == "ffmpeg"
    assert shell.ffprobe() == "ffprobe"


def test_ffmpeg_honours_the_env_override(monkeypatch):
    monkeypatch.setenv("CLIPPER_FFMPEG", "/opt/tools/bin/ffmpeg")
    monkeypatch.setenv("CLIPPER_FFPROBE", "/opt/tools/bin/ffprobe")
    assert shell.ffmpeg() == "/opt/tools/bin/ffmpeg"
    assert shell.ffprobe() == "/opt/tools/bin/ffprobe"


def test_ffprobe_falls_back_to_the_sibling_of_ffmpeg(monkeypatch):
    monkeypatch.setenv("CLIPPER_FFMPEG", "/opt/tools/bin/ffmpeg")
    monkeypatch.delenv("CLIPPER_FFPROBE", raising=False)
    assert shell.ffprobe() == "/opt/tools/bin/ffprobe"


def test_run_capture_stderr_returns_stderr_on_success(monkeypatch):
    import subprocess

    class Done:
        returncode = 0
        stdout = ""
        stderr = "measurement block"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
    assert shell.run_capture_stderr(["ffmpeg"]) == "measurement block"


def test_the_ffmpeg_clipper_downloaded_is_used_before_the_path_one(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.delenv("CLIPPER_FFMPEG", raising=False)
    monkeypatch.delenv("CLIPPER_FFPROBE", raising=False)
    managed = tmp_path / ".tools" / "bin" / "ffmpeg"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"")
    assert shell.ffmpeg() == str(managed)
    assert shell.ffprobe() == str(managed.with_name("ffprobe"))
    conda = tmp_path / ".conda-tools" / "bin" / "ffmpeg"       # a build you installed still wins
    conda.parent.mkdir(parents=True)
    conda.write_bytes(b"")
    assert shell.ffmpeg() == str(conda)


def test_the_chosen_ffmpeg_goes_first_on_path_for_tools_that_call_it_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_FFMPEG", str(tmp_path / "bin" / "ffmpeg"))
    monkeypatch.setenv("PATH", "/usr/bin")
    shell.tools_on_path()
    shell.tools_on_path()                                       # once is enough
    assert os.environ["PATH"] == f"{tmp_path / 'bin'}{os.pathsep}/usr/bin"
    monkeypatch.delenv("CLIPPER_FFMPEG")
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))           # nothing local: PATH's own ffmpeg
    monkeypatch.setenv("PATH", "/usr/bin")
    shell.tools_on_path()
    assert os.environ["PATH"] == "/usr/bin"


def test_project_local_conda_ffmpeg_is_used_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIPPER_FFMPEG", raising=False)
    local = tmp_path / ".conda-tools" / "bin" / "ffmpeg"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    assert shell.ffmpeg() == str(local)
    assert shell.ffprobe() == str(local.with_name("ffprobe"))


def test_env_override_beats_the_project_local_binary(monkeypatch, tmp_path):
    local = tmp_path / ".conda-tools" / "bin" / "ffmpeg"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.setenv("CLIPPER_FFMPEG", "/elsewhere/ffmpeg")
    assert shell.ffmpeg() == "/elsewhere/ffmpeg"


def test_project_home_prefers_the_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    assert shell.project_home() == tmp_path


def test_project_home_walks_up_from_cwd_to_the_campaigns_marker(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIPPER_HOME", raising=False)
    home = tmp_path / "myproject"
    (home / "campaigns").mkdir(parents=True)
    deep = home / "a" / "b"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert shell.project_home() == home


def test_project_home_falls_back_to_the_package_parent(monkeypatch, tmp_path):
    """An installed package with no project dir in sight still resolves somewhere."""
    monkeypatch.delenv("CLIPPER_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    assert shell.project_home() == shell.PACKAGE_PARENT


def test_describe_failure_reads_like_a_person_wrote_it():
    stopped = shell.CommandError(["ffmpeg"], 255, "frame= 0 fps=0.0\nExiting normally, received signal 15.\n")
    assert shell.describe_failure(stopped) == shell.INTERRUPTED
    assert shell.describe_failure(shell.CommandError(["ffmpeg"], -15, "")) == shell.INTERRUPTED
    broken = shell.CommandError(["ffmpeg"], 1, "banner\n[in] Invalid argument\nframe= 0\nConversion failed!\n")
    assert shell.describe_failure(broken) == "ffmpeg failed: Conversion failed!"
    assert shell.describe_failure(ValueError("no faces")) == "no faces"


ODD_FOLDERS = ["with space", "sam's", "a,b", "br[1]", "semi;x", "col:on", "back\\slash"]
TINY_ASS = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 64\nPlayResY: 64\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,hi\n")


def test_filter_path_leaves_ordinary_paths_alone():
    assert shell.filter_path("/Users/sam/clipper jobs/stories/g-abc/work/part_1.ass") == \
        "/Users/sam/clipper jobs/stories/g-abc/work/part_1.ass"


def test_ffmpeg_reads_captions_from_folders_with_filtergraph_characters(tmp_path):
    import subprocess

    import pytest
    filters = subprocess.run([shell.ffmpeg(), "-hide_banner", "-filters"],
                             capture_output=True, text=True).stdout
    if "ass" not in filters.split():
        pytest.skip("this ffmpeg has no libass")
    for name in ODD_FOLDERS:
        folder = tmp_path / name
        folder.mkdir()
        (folder / "c.ass").write_text(TINY_ASS)
        graph = f"[0:v]ass={shell.filter_path(folder / 'c.ass')}:fontsdir={shell.filter_path(folder)}[v]"
        proc = subprocess.run([shell.ffmpeg(), "-hide_banner", "-f", "lavfi", "-i", "color=s=64x64:d=0.1",
                               "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-f", "null", "-"],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, (name, proc.stderr[-400:])
