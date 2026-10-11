import hashlib
import io
import zipfile

import pytest

from clipper import doctor, provision, shell

ALL_FILTERS = " .. ass V->V\n .. loudnorm A->A\n .. sidechaincompress AA->A\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fresh project folder with downloads switched back on (conftest turns them off)."""
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.delenv("CLIPPER_FFMPEG", raising=False)
    monkeypatch.setattr(provision, "AUTO", True)
    monkeypatch.setattr(provision, "_status", {})
    monkeypatch.setattr(provision, "_ready", set())
    return tmp_path


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serve(monkeypatch, files: dict[str, bytes]) -> list[str]:
    """urlopen answers from `files` (by the URL's last part) and records what was asked for."""
    asked = []

    def urlopen(request, timeout=None, context=None):
        asked.append(request.full_url)
        return FakeResponse(files[request.full_url.rsplit("/", 1)[-1]])

    monkeypatch.setattr(provision.urllib.request, "urlopen", urlopen)
    return asked


def zipped(name: str, body: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(name, body)
    return buffer.getvalue()


def test_the_model_is_downloaded_once_and_checked(home, monkeypatch):
    body = b"model bytes"
    monkeypatch.setattr(provision, "MODEL_SHA256", hashlib.sha256(body).hexdigest())
    asked = serve(monkeypatch, {"face_landmarker.task": body})
    provision.ensure(("model",))
    provision.ensure(("model",))
    assert provision.model_path().read_bytes() == body
    assert asked == [provision.MODEL_URL]


def test_a_download_with_the_wrong_checksum_is_refused_and_leaves_nothing(home, monkeypatch):
    serve(monkeypatch, {"face_landmarker.task": b"tampered"})
    with pytest.raises(provision.ProvisionError, match="checksum"):
        provision.ensure(("model",))
    assert list(provision.model_path().parent.iterdir()) == []
    assert "failed" in provision.note("model", "fallback")
    assert "clipper setup" in provision.note("model", "fallback")


def test_a_working_ffmpeg_is_left_alone(home, monkeypatch):
    monkeypatch.setattr(shell, "run", lambda cmd, **k: ALL_FILTERS)
    asked = serve(monkeypatch, {})
    provision.ensure(("ffmpeg",))
    assert asked == []


def test_ffmpeg_and_ffprobe_are_downloaded_when_the_one_on_path_has_no_libass(home, monkeypatch):
    archives = {"ffmpeg.zip": zipped("ffmpeg", b"#!ffmpeg"), "ffprobe.zip": zipped("ffprobe", b"#!ffprobe")}
    monkeypatch.setattr(provision, "_platform", lambda: ("darwin", "arm64"))
    monkeypatch.setitem(provision.FFMPEG_BUILDS, ("darwin", "arm64"), {
        name: (f"/build/{name}.zip", hashlib.sha256(archives[f"{name}.zip"]).hexdigest())
        for name in ("ffmpeg", "ffprobe")})
    # The PATH ffmpeg lists no caption filter; the downloaded one does.
    monkeypatch.setattr(shell, "run", lambda cmd, **k:
                        ALL_FILTERS if str(cmd[0]).startswith(str(home)) else " .. loudnorm A->A\n")
    asked = serve(monkeypatch, archives)

    provision.ensure(("ffmpeg",))

    assert asked == [provision.FFMPEG_HOST + "/build/ffmpeg.zip", provision.FFMPEG_HOST + "/build/ffprobe.zip"]
    folder = home / ".tools" / "bin"
    assert sorted(p.name for p in folder.iterdir()) == ["ffmpeg", "ffprobe"]      # no zips left
    assert (folder / "ffmpeg").stat().st_mode & 0o111
    assert shell.ffmpeg() == str(folder / "ffmpeg")
    assert shell.ffprobe() == str(folder / "ffprobe")


def test_a_system_with_no_build_says_what_to_install(home, monkeypatch):
    monkeypatch.setattr(provision, "_platform", lambda: ("win32", "x86_64"))
    monkeypatch.setattr(shell, "run", lambda cmd, **k: "")
    with pytest.raises(provision.ProvisionError, match="libass"):
        provision.ensure(("ffmpeg",))


def test_an_ffmpeg_chosen_by_hand_is_never_replaced(home, monkeypatch):
    monkeypatch.setenv("CLIPPER_FFMPEG", "/opt/mine/ffmpeg")
    monkeypatch.setattr(shell, "run", lambda cmd, **k: "")
    asked = serve(monkeypatch, {})
    with pytest.raises(provision.ProvisionError, match="/opt/mine/ffmpeg"):
        provision.ensure(("ffmpeg",))
    assert asked == []


def test_nothing_is_downloaded_when_auto_is_off(home, monkeypatch):
    monkeypatch.setattr(provision, "AUTO", False)
    asked = serve(monkeypatch, {})
    provision.ensure()
    assert asked == []


def test_doctor_shows_download_progress_as_the_fix(home, monkeypatch):
    monkeypatch.setattr(doctor.shell, "run", lambda cmd, **k: "")
    provision._set("ffmpeg", state="working", done=420, total=1000)
    rows = {name: fix for name, ok, fix in doctor.check_all() if not ok}
    assert rows["ffmpeg libass"] == "Downloading now (42%)"
    assert rows["MediaPipe model"].startswith("Clipper downloads this itself")


def test_the_background_run_records_a_failure_instead_of_raising(home, monkeypatch):
    monkeypatch.setattr(provision, "_platform", lambda: ("win32", "x86_64"))
    monkeypatch.setattr(shell, "run", lambda cmd, **k: "")
    body = b"model bytes"
    monkeypatch.setattr(provision, "MODEL_SHA256", hashlib.sha256(body).hexdigest())
    serve(monkeypatch, {"face_landmarker.task": body})
    provision.start_background().join(timeout=10)
    assert provision._status["ffmpeg"]["state"] == "failed"
    assert provision.model_path().exists()                 # one failure doesn't stop the rest
