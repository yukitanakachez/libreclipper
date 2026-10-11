from pathlib import Path

import pytest

from clipper import render
from clipper.models import Candidate, CropSegment, Rect


def seg(start, end, layout="single", crops=None):
    return CropSegment(start, end, layout, crops or [Rect(0.2, 0.0, 0.28, 1.0)])


def test_single_segment_produces_one_crop_and_scale():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     Path("x.ass"), None, -22.0)
    assert graph.count("crop=") == 1
    assert "scale=1080:1920" in graph
    assert "ass=" in graph


def test_two_segments_are_concatenated_in_order():
    graph = render.build_filtergraph([seg(10.0, 20.0), seg(20.0, 30.0)],
                                     10.0, 30.0, 1920, 1080, Path("x.ass"), None, -22.0)
    assert graph.count("crop=") == 2
    assert "concat=n=2:v=1:a=0" in graph


def test_stack_segment_stacks_two_crops():
    graph = render.build_filtergraph(
        [seg(10.0, 20.0, "stack", [Rect(0.05, 0.1, 0.5, 0.45), Rect(0.5, 0.1, 0.5, 0.45)])],
        10.0, 20.0, 1920, 1080, Path("x.ass"), None, -22.0)
    assert "vstack=inputs=2" in graph
    assert graph.count("scale=1080:960") == 2


def test_fit_segment_uses_a_blurred_background():
    graph = render.build_filtergraph([seg(10.0, 20.0, "fit", [Rect(0, 0, 1, 1)])],
                                     10.0, 20.0, 1920, 1080, Path("x.ass"), None, -22.0)
    assert "gblur" in graph
    assert "overlay" in graph


def test_crop_pixels_are_even_numbers():
    graph = render.build_filtergraph([seg(10.0, 40.0, "single", [Rect(0.211, 0.0, 0.281, 1.0)])],
                                     10.0, 40.0, 1920, 1080, Path("x.ass"), None, -22.0)
    crop = [p for p in graph.split(";") if p.strip().startswith("[0:v]")][0]
    numbers = [int(n) for n in crop.split("crop=")[1].split("[")[0].split(",")[0].split(":")]
    assert all(n % 2 == 0 for n in numbers)


def test_music_adds_sidechain_ducking_and_fades():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     Path("x.ass"), Path("bed.mp3"), -22.0)
    assert "sidechaincompress" in graph
    assert "volume=-22" in graph
    assert "afade=t=in" in graph and "afade=t=out" in graph


def test_no_music_leaves_audio_untouched():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     Path("x.ass"), None, -22.0)
    assert "sidechaincompress" not in graph


def test_no_ass_path_skips_the_caption_filter():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     None, None, -22.0)
    assert "ass=" not in graph
    assert "[vout]" in graph


def test_segments_outside_the_clip_are_dropped():
    graph = render.build_filtergraph([seg(0.0, 9.0), seg(10.0, 40.0)], 10.0, 40.0,
                                     1920, 1080, None, None, -22.0)
    assert graph.count("crop=") == 1
    assert "concat=n=1:v=1:a=0" in graph


def test_sidecar_contains_caption_and_hashtags(tmp_path):
    cand = Candidate(n=1, start=0, end=30, orig_start=0, orig_end=30, headline="h",
                     hook="k", reason="r", score=9, post_caption="Watch this",
                     hashtags=["#a", "#b"])
    path = render.write_sidecar(tmp_path / "01-h.txt", cand)
    text = path.read_text()
    assert "Watch this" in text and "#a #b" in text


LOUDNORM_STDERR = """\
[Parsed_loudnorm_0 @ 0x600001] 
{
	"input_i" : "-31.50",
	"input_tp" : "-16.99",
	"input_lra" : "0.00",
	"input_thresh" : "-41.53",
	"output_i" : "-13.99",
	"output_tp" : "-1.00",
	"output_lra" : "0.00",
	"output_thresh" : "-24.02",
	"normalization_type" : "dynamic",
	"target_offset" : "-0.01"
}
"""


def test_parse_loudnorm_json_reads_the_measured_values():
    measured = render.parse_loudnorm_json(LOUDNORM_STDERR)
    assert measured["input_i"] == "-31.50"
    assert measured["input_tp"] == "-16.99"
    assert measured["target_offset"] == "-0.01"


def test_parse_loudnorm_json_returns_empty_when_absent():
    assert render.parse_loudnorm_json("no json here") == {}


def test_loudnorm_filter_is_inside_the_complex_graph_not_a_simple_filter():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     None, None, -22.0)
    assert "loudnorm=I=-14:TP=-1:LRA=11" in graph
    assert graph.rstrip().endswith("[aout]")


def test_second_pass_graph_carries_the_measured_values():
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     None, None, -22.0,
                                     measured=render.parse_loudnorm_json(LOUDNORM_STDERR))
    assert "measured_I=-31.50" in graph
    assert "measured_TP=-16.99" in graph
    assert "measured_thresh=-41.53" in graph
    assert "offset=-0.01" in graph
    assert "linear=true" in graph


def test_measurement_pass_requests_json_output():
    graph = render.build_audio_graph(10.0, 40.0, None, -22.0, measure=True)
    assert "print_format=json" in graph
    assert graph.endswith("[aout]")


def test_non_finite_measurements_fall_back_to_single_pass():
    """A -inf value is rejected as a loudnorm parameter. (Fully silent audio skips
    loudnorm altogether; see test_silent_audio_skips_loudnorm_entirely.)"""
    partial = {"input_i": "-31.50", "input_tp": "-inf", "input_lra": "0.00",
               "input_thresh": "-41.53", "target_offset": "0.00"}
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     None, None, -22.0, measured=partial)
    assert "measured_I" not in graph
    assert "loudnorm=I=-14:TP=-1:LRA=11" in graph


def test_caption_layout_comes_from_a_segment_the_clip_actually_shows():
    """The crop plan spans candidate +/-10s; the margin's layout must not decide."""
    plan_segments = [
        seg(0.0, 10.0, "stack", [Rect(0.0, 0.1, 0.5, 0.45), Rect(0.5, 0.1, 0.5, 0.45)]),
        seg(10.0, 40.0, "single"),
    ]
    assert render.caption_layout(plan_segments, 10.0, 40.0) == "single"


def test_caption_layout_uses_stack_when_the_clip_starts_in_a_stack_shot():
    plan_segments = [
        seg(0.0, 10.0, "single"),
        seg(10.0, 40.0, "stack", [Rect(0.0, 0.1, 0.5, 0.45), Rect(0.5, 0.1, 0.5, 0.45)]),
    ]
    assert render.caption_layout(plan_segments, 10.0, 40.0) == "stack"


def test_caption_layout_falls_back_to_single_when_nothing_overlaps():
    assert render.caption_layout([seg(0.0, 5.0, "stack")], 10.0, 40.0) == "single"


def test_empty_segment_list_raises_a_clear_error_not_an_ffmpeg_one():
    with pytest.raises(render.RenderError, match="no crop"):
        render.build_filtergraph([seg(0.0, 5.0)], 10.0, 40.0, 1920, 1080,
                                 None, None, -22.0)


def test_fontsdir_is_absolute_so_it_works_outside_the_repo(monkeypatch, tmp_path):
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080,
                                     Path("x.ass"), None, -22.0)
    fontsdir = graph.split("fontsdir=")[1].split("[")[0]
    assert Path(fontsdir).is_absolute(), (
        "a relative fontsdir makes libass silently substitute a font when the CLI "
        "runs outside the repo root"
    )
    assert Path(fontsdir).name == "fonts"


def test_audio_graph_resamples_after_loudnorm():
    """loudnorm outputs 192kHz, which the AAC encoder rejects with EINVAL."""
    graph = render.build_audio_graph(10.0, 40.0, None, -22.0)
    assert "aresample=48000" in graph
    assert graph.index("loudnorm") < graph.index("aresample"), "resample must come after"


def test_measurement_pass_also_ends_at_48k():
    graph = render.build_audio_graph(10.0, 40.0, None, -22.0, measure=True)
    assert "aresample=48000" in graph


def test_every_segment_ends_with_a_normalized_sample_aspect_ratio():
    """concat refuses inputs whose SAR differs; the fit branch drifts to 10240:10239."""
    segments = [
        seg(10.0, 20.0, "single"),
        seg(20.0, 30.0, "fit", [Rect(0, 0, 1, 1)]),
        seg(30.0, 40.0, "stack", [Rect(0.0, 0.1, 0.5, 0.45), Rect(0.5, 0.1, 0.5, 0.45)]),
    ]
    graph = render.build_filtergraph(segments, 10.0, 40.0, 1920, 1080, None, None, -22.0)
    concat_inputs = graph.split("concat=")[0].split(";")
    for label in ("[v0]", "[v1]", "[v2]"):
        producer = [p for p in concat_inputs if p.rstrip().endswith(label)][0]
        assert "setsar=1" in producer, f"{label} can reach concat with a foreign SAR"


# --- pacing in the graph -------------------------------------------------------

KEEP = [(0.0, 1.0), (2.0, 3.5)]


def test_audio_is_cut_into_pieces_and_rejoined_sample_accurately():
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0, keep=KEEP, speed=1.0)
    assert "asplit=2" in graph
    assert "atrim=start=0.0000:end=1.0000" in graph
    assert "atrim=start=2.0000:end=3.5000" in graph
    assert "concat=n=2:v=0:a=1" in graph
    assert "atempo" not in graph


def test_each_audio_piece_gets_a_tiny_fade_so_cuts_never_click():
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0, keep=KEEP)
    assert graph.count("afade=t=in") == 2 and graph.count("afade=t=out") == 2


def test_speed_up_uses_atempo_so_pitch_is_preserved():
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0, keep=KEEP, speed=1.1)
    assert "atempo=1.100" in graph


def test_no_pacing_leaves_the_audio_graph_as_before():
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0)
    assert "asplit" not in graph and "atempo" not in graph and "concat" not in graph


def test_music_fades_out_at_the_end_of_the_finished_clip():
    graph = render.build_audio_graph(10.0, 14.0, Path("bed.mp3"), -22.0, keep=KEEP, speed=1.25)
    finished = (1.0 + 1.5) / 1.25                              # 2.0 s
    assert f"afade=t=out:st={finished - 1.0:.3f}:d=1.0" in graph


def test_measure_pass_hears_the_same_paced_audio_as_the_render():
    measure = render.build_audio_graph(10.0, 14.0, None, -22.0, measure=True,
                                       keep=KEEP, speed=1.1)
    final = render.build_audio_graph(10.0, 14.0, None, -22.0, keep=KEEP, speed=1.1)
    assert measure.split("loudnorm")[0] == final.split("loudnorm")[0]


def test_video_drops_the_cut_frames_then_renumbers_them():
    graph = render.build_filtergraph([seg(10.0, 14.0)], 10.0, 14.0, 1920, 1080,
                                     None, None, -22.0, keep=KEEP, speed=1.0, fps=30.0)
    assert "select='gte(t\\,-0.0167)*lt(t\\,0.9833)+gte(t\\,1.9833)*lt(t\\,3.4833)'" in graph
    assert "setpts=N/(30.0*TB)" in graph


def test_captions_burn_in_before_the_speed_up_so_they_stay_in_sync():
    graph = render.build_filtergraph([seg(10.0, 14.0)], 10.0, 14.0, 1920, 1080,
                                     Path("x.ass"), None, -22.0, keep=KEEP, speed=1.1, fps=30.0)
    video = graph.split("[vout]")[0]
    assert video.index("select=") < video.index("ass=") < video.index("setpts=PTS/1.100")


def test_no_pacing_leaves_the_video_graph_as_before():
    graph = render.build_filtergraph([seg(10.0, 14.0)], 10.0, 14.0, 1920, 1080,
                                     None, None, -22.0)
    assert "select=" not in graph and "setpts=PTS/" not in graph


def test_silent_audio_skips_loudnorm_entirely():
    """loudnorm on digital silence emits NaN samples after the cut chain, which the
    AAC encoder rejects. There is nothing to normalize, so leave it out."""
    silent = {"input_i": "-inf", "input_tp": "-inf", "input_lra": "0.00",
              "input_thresh": "-70.00", "target_offset": "0.00"}
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0, measured=silent,
                                     keep=KEEP, speed=1.1)
    assert "loudnorm" not in graph
    assert graph.endswith("aresample=48000[aout]")


def test_measure_pass_always_keeps_loudnorm():
    graph = render.build_audio_graph(10.0, 14.0, None, -22.0, measure=True, keep=KEEP)
    assert "loudnorm" in graph


def test_speed_up_converts_frame_rate_inside_the_graph():
    """Converting 33 fps back to 30 with the output -r flag kept extra frames and
    left video ~0.07 s longer than audio; the fps filter drops them evenly."""
    graph = render.build_filtergraph([seg(10.0, 14.0)], 10.0, 14.0, 1920, 1080,
                                     None, None, -22.0, keep=KEEP, speed=1.1, fps=30.0)
    assert "setpts=PTS/1.100,fps=30" in graph


def test_output_frame_rate_is_capped_at_60():
    graph = render.build_filtergraph([seg(10.0, 14.0)], 10.0, 14.0, 1920, 1080,
                                     None, None, -22.0, keep=KEEP, speed=1.1, fps=120.0)
    assert "fps=60" in graph


def test_section_files_are_keyed_by_time_range_not_candidate_number(tmp_path):
    """Re-picking renumbers candidates; a file named 03.mp4 from the old clip 3 was
    reused for the new clip 3 and covered a different moment entirely."""
    from clipper import jobs
    from clipper.config import AppConfig

    paths = jobs.paths_for("j", AppConfig(jobs_dir=tmp_path))
    old = Candidate(n=3, start=188.4, end=212.6, orig_start=188.4, orig_end=212.6,
                    headline="h", hook="k", reason="r", score=9, post_caption="c")
    new = Candidate(n=3, start=131.1, end=159.3, orig_start=131.1, orig_end=159.3,
                    headline="h", hook="k", reason="r", score=9, post_caption="c")
    same_range = Candidate(n=5, start=131.1, end=159.3, orig_start=131.1, orig_end=159.3,
                           headline="h", hook="k", reason="r", score=9, post_caption="c")

    assert render.section_path(paths, old) != render.section_path(paths, new)
    assert render.section_path(paths, new) == render.section_path(paths, same_range), \
        "an identical range can reuse its download (a retry after a failed render)"


def test_default_music_track_is_found_relative_to_the_project(tmp_path, monkeypatch):
    from pathlib import Path

    from clipper.campaigns import Campaign
    from clipper.models import Candidate
    from clipper.render import _pick_music

    home = tmp_path / "project"
    (home / "music").mkdir(parents=True)
    (home / "music" / "b.mp3").write_bytes(b"x")
    (home / "music" / "a.mp3").write_bytes(b"x")
    monkeypatch.setenv("CLIPPER_HOME", str(home))
    monkeypatch.chdir(tmp_path)                      # the server can start anywhere
    campaign = Campaign(name="C", slug="c", min_len=5, max_len=60,
                        music_allowed=True, music_folder=Path("music"))
    cand = Candidate(n=1, start=0, end=5, orig_start=0, orig_end=5, headline="h",
                     hook="k", reason="r", score=9, post_caption="c", music_on=True)
    assert _pick_music(cand, campaign) == (home / "music" / "a.mp3").resolve()


def test_older_renders_of_a_clip_move_to_previous_and_others_stay(tmp_path):
    from clipper.render import retire_older_renders

    for name in ("01-old-headline.mp4", "01-old-headline.txt", "02-other.mp4", "02-other.txt"):
        (tmp_path / name).write_text(name)
    retire_older_renders(tmp_path, 1)
    assert sorted(p.name for p in tmp_path.glob("*.*")) == ["02-other.mp4", "02-other.txt"]
    assert sorted(p.name for p in (tmp_path / "previous").iterdir()) == [
        "01-old-headline.mp4", "01-old-headline.txt"]


def test_retiring_never_overwrites_an_earlier_previous_version(tmp_path):
    from clipper.render import retire_older_renders

    (tmp_path / "previous").mkdir()
    (tmp_path / "previous" / "01-same.mp4").write_text("first render")
    (tmp_path / "01-same.mp4").write_text("second render")
    retire_older_renders(tmp_path, 1)
    kept = sorted(p.read_text() for p in (tmp_path / "previous").iterdir())
    assert kept == ["first render", "second render"]


def test_caption_paths_are_escaped_for_the_filtergraph(monkeypatch, tmp_path):
    from clipper import shell
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path / "Sam's clipper, v[2]"))
    ass = tmp_path / "jobs; odd:name" / "x.ass"
    graph = render.build_filtergraph([seg(10.0, 40.0)], 10.0, 40.0, 1920, 1080, ass, None, -22.0)
    fonts = tmp_path / "Sam's clipper, v[2]" / "assets" / "fonts"
    assert f"ass={shell.filter_path(ass)}:fontsdir={shell.filter_path(fonts)}" in graph
