import plistlib
import subprocess
import sys

import pytest

from clipper import appbundle, cli
from clipper.config import AppConfig


def test_launcher_starts_the_server_only_when_it_is_down_and_quotes_paths():
    text = appbundle.launcher(__import__("pathlib").Path("/Users/me/My Clips/clipper"), "/x/.venv/bin/python",
                              8770, {"CLIPPER_FFMPEG": "/opt/ff mpeg"})
    assert "PROJECT='/Users/me/My Clips/clipper'" in text and "PORT=8770" in text
    assert "export CLIPPER_FFMPEG='/opt/ff mpeg'" in text
    assert text.index("if ! up; then") < text.index("clipper.cli serve") < text.index('--app="$URL"')
    assert "--no-browser" in text and "source ~/.zshrc" in text
    assert subprocess.run(["/bin/sh", "-n"], input=text, text=True).returncode == 0 or sys.platform != "darwin"


@pytest.mark.skipif(sys.platform != "darwin", reason="a Mac app")
def test_install_writes_a_runnable_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path / "project"))
    monkeypatch.setenv("CLIPPER_FFMPEG", "/opt/ffmpeg")
    monkeypatch.setattr(cli, "_config", lambda: AppConfig())
    assert cli.main(["app", "--dest", str(tmp_path / "Apps"), "--port", "8770"]) == 0
    app = tmp_path / "Apps" / "Clipper.app"
    script = app / "Contents" / "MacOS" / "Clipper"
    assert script.stat().st_mode & 0o111 and "PORT=8770" in script.read_text()
    assert f"PYTHON={sys.executable}" in script.read_text() and "/opt/ffmpeg" in script.read_text()
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "Clipper" and info["CFBundlePackageType"] == "APPL"
    assert subprocess.run(["/bin/zsh", "-n", str(script)]).returncode == 0
