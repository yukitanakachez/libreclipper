import json
import subprocess
from pathlib import Path

import pytest

from clipper import jobs, preview, shell
from clipper.config import AppConfig
from clipper.models import Candidate, CropPlan, CropSegment, Meta, Rect

FIXTURE = Path("tests/fixtures/shots.mp4")


def _candidate() -> Candidate:
    return Candidate(n=1, start=0.5, end=3.5, orig_start=0.5, orig_end=3.5, headline="h",
                     hook="k", reason="r", score=9, post_caption="c", hashtags=[])


def _plan() -> CropPlan:
    return CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0, 0.28, 1.0)])])


def _meta(source: Path) -> Meta:
    return Meta(job_id="prev", source_kind="local", source=str(source), title="t",
                description="", channel="", duration=6.0, width=1280, height=720,
                fps=30.0, max_height=720)


@pytest.mark.skipif(not FIXTURE.exists(), reason="run tests/fixtures/make_fixtures.py")
def test_preview_is_vertical_and_has_no_captions(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("prev", cfg)
    paths.proxy.write_bytes(FIXTURE.read_bytes())

    out = preview.render_preview(paths, _meta(FIXTURE), _plan(), _candidate())

    probe = json.loads(subprocess.run(
        [shell.ffprobe(), "-v", "error", "-print_format", "json", "-show_streams", str(out)],
        capture_output=True, text=True, check=True).stdout)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (720, 1280)


def test_preview_graph_contains_no_subtitle_filter(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(preview.shell, "run", lambda cmd, **k: seen.setdefault("cmd", cmd) or "")
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("prev", cfg)

    preview.render_preview(paths, _meta(Path("x.mp4")), _plan(), _candidate())

    graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
    assert "ass=" not in graph
    assert "-s" in seen["cmd"]


def test_preview_applies_pacing_when_given_words_and_pacing(monkeypatch, tmp_path):
    from clipper.models import Segment, Transcript, Word
    from clipper.pacing import Pacing

    seen = {}
    monkeypatch.setattr(preview.shell, "run", lambda cmd, **k: seen.setdefault("cmd", cmd) or "")
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("prev", cfg)
    words = [Word(0, "one.", 0.5, 0.9, 0.9), Word(1, "two.", 2.5, 2.9, 0.9)]
    transcript = Transcript(words, [Segment(0.5, 2.9, "w", 0, 1)], 6.0)

    preview.render_preview(paths, _meta(Path("x.mp4")), _plan(), _candidate(),
                           transcript=transcript, pacing=Pacing(True, 0.3, 1.1))

    graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
    assert "select=" in graph and "atempo=1.100" in graph


def test_preview_without_pacing_is_unchanged(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(preview.shell, "run", lambda cmd, **k: seen.setdefault("cmd", cmd) or "")
    paths = jobs.paths_for("prev", AppConfig(jobs_dir=tmp_path))
    preview.render_preview(paths, _meta(Path("x.mp4")), _plan(), _candidate())
    graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
    assert "select=" not in graph and "atempo" not in graph
