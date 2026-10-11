"""Renders a real clip with real ffmpeg, from the fixture video.

Everything except the Claude call is genuine here: crop, captions burned in by
libass, loudness normalization and the encode.
"""

import json
import subprocess
from pathlib import Path

import pytest

from clipper import jobs, render, shell
from clipper.campaigns import Campaign
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

FIXTURE = Path("tests/fixtures/shots.mp4")

from clipper.pacing import Pacing

# Duration checks that predate pacing: render the clip at its natural length.
NO_PACING = Campaign(name="P", slug="p", min_len=1, max_len=60,
                     pacing=Pacing(cut_pauses=False, speed=1.0))
FONT = Path("assets/fonts/Montserrat-Black.ttf")


def _has_libass() -> bool:
    try:
        filters = shell.run([shell.ffmpeg(), "-hide_banner", "-filters"])
    except Exception:
        return False
    return "\n .. ass " in filters or " ass " in filters


requires_render = pytest.mark.skipif(
    not (FIXTURE.exists() and FONT.exists() and _has_libass()),
    reason="needs the fixture video, the font, and an ffmpeg with libass",
)


def _probe(path: Path) -> dict:
    return json.loads(subprocess.run(
        [shell.ffprobe(), "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True).stdout)


@requires_render
def test_renders_a_playable_vertical_clip(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("e2e", cfg)
    meta = Meta(job_id="e2e", source_kind="local", source=str(FIXTURE.resolve()),
                title="fixture", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(8)]
    transcript = Transcript(words, [Segment(0.0, 4.0, "w", 0, 7)], 6.0)
    cand = Candidate(n=1, start=0.5, end=4.5, orig_start=0.5, orig_end=4.5,
                     headline="Fixture clip", hook="w0", reason="r", score=9,
                     post_caption="c", hashtags=["#a"])
    plan = CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)])])

    out = render.render_clip(paths, meta, NO_PACING, cand, plan, transcript, cfg)

    assert out.exists()
    probe = _probe(out)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert float(probe["format"]["duration"]) == pytest.approx(4.0, abs=0.2)
    assert out.with_suffix(".txt").exists()


@requires_render
def test_a_clip_appears_in_the_clips_folder_only_once_complete(tmp_path, monkeypatch):
    # The Output page and iCloud both pick up whatever is in the clips folder.
    cfg = AppConfig(jobs_dir=tmp_path, clips_dir=tmp_path / "clips")
    paths = jobs.paths_for("e2e", cfg)
    meta = Meta(job_id="e2e", source_kind="local", source=str(FIXTURE.resolve()),
                title="fixture", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(8)]
    transcript = Transcript(words, [Segment(0.0, 4.0, "w", 0, 7)], 6.0)
    cand = Candidate(n=1, start=0.5, end=4.5, orig_start=0.5, orig_end=4.5,
                     headline="Fixture clip", hook="w0", reason="r", score=9,
                     post_caption="c", hashtags=["#a"])
    plan = CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)])])
    real_run = shell.run
    visible_after_each_encode = []

    def spy(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        visible_after_each_encode.append(
            [p.name for p in paths.out.glob("*.mp4") if not p.name.endswith(".partial.mp4")]
            if paths.out.exists() else [])
        return result

    monkeypatch.setattr(render.shell, "run", spy)
    out = render.render_clip(paths, meta, NO_PACING, cand, plan, transcript, cfg)

    assert all(names == [] for names in visible_after_each_encode)
    assert sorted(p.name for p in paths.out.iterdir()) == [out.name, out.with_suffix(".txt").name]



@requires_render
def test_a_re_render_with_a_new_headline_keeps_only_the_new_clip_in_view(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, clips_dir=tmp_path / "clips")
    paths = jobs.paths_for("e2e", cfg)
    meta = Meta(job_id="e2e", source_kind="local", source=str(FIXTURE.resolve()),
                title="fixture", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(8)]
    transcript = Transcript(words, [Segment(0.0, 4.0, "w", 0, 7)], 6.0)
    plan = CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)])])

    def render_with(headline):
        cand = Candidate(n=1, start=0.5, end=2.5, orig_start=0.5, orig_end=2.5,
                         headline=headline, hook="w0", reason="r", score=9,
                         post_caption="c", hashtags=[])
        return render.render_clip(paths, meta, NO_PACING, cand, plan, transcript, cfg)

    first = render_with("First take")
    second = render_with("Second take")
    in_view = sorted(p.name for p in paths.out.glob("*.*"))
    assert in_view == [second.name, second.with_suffix(".txt").name]
    assert (paths.out / "previous" / first.name).exists()

@requires_render
def test_rendered_audio_is_normalized_to_minus_14_lufs(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("e2e-loud", cfg)
    # a quiet tone: loudnorm must bring it up to about -14 LUFS
    source = tmp_path / "tone.mp4"
    subprocess.run([shell.ffmpeg(), "-y", "-f", "lavfi", "-i",
                    "color=c=gray:s=1280x720:d=6:r=30", "-f", "lavfi", "-i",
                    "sine=frequency=220:duration=6:sample_rate=48000",
                    "-filter:a", "volume=-30dB", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)],
                   capture_output=True, check=True)

    meta = Meta(job_id="e2e-loud", source_kind="local", source=str(source),
                title="tone", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    transcript = Transcript([Word(0, "w", 0.0, 0.4, 0.9)],
                            [Segment(0.0, 0.4, "w", 0, 0)], 6.0)
    cand = Candidate(n=1, start=0.5, end=4.5, orig_start=0.5, orig_end=4.5,
                     headline="Tone", hook="w", reason="r", score=9,
                     post_caption="c", hashtags=[])
    plan = CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)])])

    out = render.render_clip(paths, meta, Campaign(name="P", slug="p", min_len=1, max_len=60),
                             cand, plan, transcript, cfg)

    measured = subprocess.run(
        [shell.ffmpeg(), "-hide_banner", "-i", str(out), "-af", "ebur128=peak=true",
         "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    integrated = float(measured.rsplit("I:", 1)[1].split("LUFS")[0].strip())
    assert integrated == pytest.approx(-14.0, abs=1.5)


@requires_render
def test_renders_a_clip_whose_plan_mixes_layouts(tmp_path):
    """Every earlier render test used one segment; concat is where plans break."""
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("mixed", cfg)
    meta = Meta(job_id="mixed", source_kind="local", source=str(FIXTURE.resolve()),
                title="fixture", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(10)]
    transcript = Transcript(words, [Segment(0.0, 5.0, "w", 0, 9)], 6.0)
    cand = Candidate(n=1, start=0.5, end=5.0, orig_start=0.5, orig_end=5.0,
                     headline="Mixed layouts", hook="w0", reason="r", score=9,
                     post_caption="c", hashtags=[])
    plan = CropPlan(1, 0.0, 6.0, [
        CropSegment(0.0, 2.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)]),
        CropSegment(2.0, 3.5, "fit", [Rect(0.0, 0.0, 1.0, 1.0)]),
        CropSegment(3.5, 4.5, "stack", [Rect(0.0, 0.1, 0.5, 0.5),
                                        Rect(0.5, 0.1, 0.5, 0.5)]),
        CropSegment(4.5, 6.0, "single", [Rect(0.5, 0.0, 0.28, 1.0)]),
    ])

    out = render.render_clip(paths, meta, NO_PACING, cand, plan, transcript, cfg)

    probe = _probe(out)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert float(probe["format"]["duration"]) == pytest.approx(4.5, abs=0.3)


@requires_render
def test_pacing_cuts_the_pause_and_speeds_up_without_drifting_out_of_sync(tmp_path):
    from clipper.pacing import Pacing

    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("paced", cfg)
    meta = Meta(job_id="paced", source_kind="local", source=str(FIXTURE.resolve()),
                title="fixture", description="", channel="", duration=6.0,
                width=1280, height=720, fps=30.0, max_height=720)
    words = [Word(0, "one", 0.5, 0.9, 0.9), Word(1, "two.", 1.0, 1.4, 0.9),
             Word(2, "three", 3.0, 3.4, 0.9), Word(3, "four.", 3.5, 3.9, 0.9)]
    transcript = Transcript(words, [Segment(0.5, 3.9, "w", 0, 3)], 6.0)
    cand = Candidate(n=1, start=0.5, end=4.2, orig_start=0.5, orig_end=4.2,
                     headline="Paced", hook="one", reason="r", score=9,
                     post_caption="c", hashtags=[])
    plan = CropPlan(1, 0.0, 6.0, [CropSegment(0.0, 6.0, "single", [Rect(0.2, 0.0, 0.28, 1.0)])])
    campaign = Campaign(name="P", slug="p", min_len=1, max_len=60,
                        pacing=Pacing(cut_pauses=True, max_pause=0.3, speed=1.1))

    out = render.render_clip(paths, meta, campaign, cand, plan, transcript, cfg)

    probe = _probe(out)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    # 3.7 s of source, 1.6 s pause cut to 0.1 s -> ~2.2 s kept -> ~2.0 s at 1.1x
    assert float(video["duration"]) == pytest.approx(2.2 / 1.1, abs=0.12)
    assert float(audio["duration"]) == pytest.approx(float(video["duration"]), abs=0.06), \
        "audio and video must stay the same length through cuts and speed-up"
