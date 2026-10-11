"""Crop-plan assembly, with shot detection and face tracking stubbed out.

The real detectors are exercised in test_shots.py / test_faces.py; here we pin
the decisions the plan makes from their output.
"""


from clipper import jobs
from clipper.config import AppConfig
from clipper.models import Candidate, Meta, Rect, Segment, Transcript, Word
from clipper.reframe import plan as plan_mod
from clipper.reframe.faces import FaceSample, FaceTrack

META = Meta(job_id="j", source_kind="local", source="u", title="t", description="",
            channel="c", duration=300.0, width=1280, height=720, fps=30.0, max_height=2160)


def transcript() -> Transcript:
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(600)]
    segments = [Segment(words[s].start, words[s + 9].end, "s", s, s + 9)
                for s in range(0, 600, 10)]
    return Transcript(words, segments, 300.0)


def candidate(n: int = 1, start: float = 100.0, end: float = 130.0) -> Candidate:
    return Candidate(n=n, start=start, end=end, orig_start=start, orig_end=end,
                     headline="h", hook="k", reason="r", score=9,
                     post_caption="c", hashtags=[])


def track(id_: int, x: float, mouths: list[float], t0: float = 100.0) -> FaceTrack:
    return FaceTrack(id=id_, samples=[
        FaceSample(t0 + i * 0.1, Rect(x, 0.3, 0.15, 0.25), m) for i, m in enumerate(mouths)
    ])


def _flatten(tracks):
    return [(s.t, s.box, s.mouth) for tr in tracks for s in tr.samples]


def stub(monkeypatch, shots_list, tracks):
    monkeypatch.setattr(plan_mod.shots, "detect_shots", lambda *a, **k: shots_list)
    monkeypatch.setattr(plan_mod.faces_mod, "detect_faces", lambda *a, **k: _flatten(tracks))


def test_analyzes_ten_seconds_either_side_of_the_candidate(monkeypatch):
    seen = {}

    def fake_shots(video, start, end, **kwargs):
        seen["range"] = (start, end)
        return [(start, end)]

    monkeypatch.setattr(plan_mod.shots, "detect_shots", fake_shots)
    monkeypatch.setattr(plan_mod.faces_mod, "detect_faces",
                        lambda *a, **k: _flatten([track(0, 0.4, [0.05] * 20)]))
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), candidate(), META)
    assert seen["range"] == (90.0, 140.0)
    assert (p.analyzed_start, p.analyzed_end) == (90.0, 140.0)



def test_an_explicit_span_is_analyzed_instead_of_the_margin(monkeypatch):
    seen = {}

    def fake_shots(video, start, end, **kwargs):
        seen["range"] = (start, end)
        return [(start, end)]

    monkeypatch.setattr(plan_mod.shots, "detect_shots", fake_shots)
    monkeypatch.setattr(plan_mod.faces_mod, "detect_faces",
                        lambda *a, **k: _flatten([track(0, 0.4, [0.05] * 20)]))
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), candidate(), META,
                                 span=(80.0, 150.0))
    assert seen["range"] == (80.0, 150.0)
    assert (p.analyzed_start, p.analyzed_end) == (80.0, 150.0)

def test_margin_is_clamped_at_the_start_of_the_video(monkeypatch):
    stub(monkeypatch, [(0.0, 15.0)], [track(0, 0.4, [0.05] * 20, t0=0.0)])
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), candidate(start=5.0, end=30.0), META)
    assert p.analyzed_start == 0.0


def test_one_face_gives_a_single_layout_and_no_check_flag(monkeypatch):
    stub(monkeypatch, [(100.0, 130.0)], [track(0, 0.4, [0.05] * 20)])
    cand = candidate()
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["single"]
    assert cand.needs_check is False


def test_two_faces_with_clear_talking_produce_speaker_spans(monkeypatch):
    talking = [0.02 if i % 2 else 0.20 for i in range(120)]
    quiet = [0.05] * 120
    stub(monkeypatch, [(100.0, 112.0)], [track(0, 0.15, talking), track(1, 0.7, quiet)])
    cand = candidate()
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["single"]
    assert cand.needs_check is False


def test_two_faces_with_no_mouth_movement_fall_back_to_stack_and_flag(monkeypatch):
    still = [0.05] * 60
    stub(monkeypatch, [(100.0, 106.0)], [track(0, 0.15, still), track(1, 0.7, still)])
    cand = candidate()
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["stack"]
    assert len(p.segments[0].crops) == 2
    assert cand.needs_check is True


def test_no_faces_falls_back_to_fit_and_flags(monkeypatch):
    stub(monkeypatch, [(100.0, 130.0)], [])
    cand = candidate()
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["fit"]
    assert p.segments[0].crops == [Rect(0.0, 0.0, 1.0, 1.0)]
    assert cand.needs_check is True


def test_short_lived_detections_are_ignored(monkeypatch):
    # a two-sample blob is noise, not a face track
    stub(monkeypatch, [(100.0, 130.0)],
         [track(0, 0.4, [0.05] * 20), track(1, 0.8, [0.05, 0.05])])
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), candidate(), META)
    assert [s.layout for s in p.segments] == ["single"]


def test_reframe_candidates_writes_both_files_and_keeps_campaign(tmp_path, monkeypatch):
    stub(monkeypatch, [(100.0, 130.0)], [track(0, 0.4, [0.05] * 20)])
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    cand = candidate()
    jobs.write_json(paths.candidates,
                    {"model": "claude-opus-5", "campaign": "example",
                     "candidates": [cand.to_dict()]})

    plans = plan_mod.reframe_candidates(paths, transcript(), META, [cand])

    assert len(plans) == 1
    written = jobs.read_json(paths.candidates)
    assert written["campaign"] == "example"
    assert written["model"] == "claude-opus-5"
    assert jobs.read_json(paths.crop_plan)["plans"][0]["candidate_n"] == 1


def test_candidate_layout_stack_overrides_speaker_detection(monkeypatch):
    talking = [0.02 if i % 2 else 0.20 for i in range(120)]
    quiet = [0.05] * 120
    stub(monkeypatch, [(100.0, 112.0)], [track(0, 0.15, talking), track(1, 0.7, quiet)])
    cand = candidate()
    cand.layout = "stack"
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["stack"]
    assert len(p.segments[0].crops) == 2


def test_candidate_layout_fit_overrides_everything(monkeypatch):
    stub(monkeypatch, [(100.0, 130.0)], [track(0, 0.4, [0.05] * 20)])
    cand = candidate()
    cand.layout = "fit"
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert [s.layout for s in p.segments] == ["fit"]


def test_forced_layout_does_not_raise_the_check_framing_flag(monkeypatch):
    stub(monkeypatch, [(100.0, 130.0)], [track(0, 0.4, [0.05] * 20)])
    cand = candidate()
    cand.layout = "fit"
    plan_mod.build_crop_plan("proxy.mp4", transcript(), cand, META)
    assert cand.needs_check is False, "you chose this layout; it is not a fallback"



def test_faces_are_detected_once_per_candidate_not_once_per_shot(monkeypatch):
    """Per-shot detection re-created the landmarker and re-read video 95 times."""
    calls = []
    many_shots = [(90.0 + i * 5, 95.0 + i * 5) for i in range(10)]
    monkeypatch.setattr(plan_mod.shots, "detect_shots", lambda *a, **k: many_shots)

    def fake_detect(video, start, end, **kwargs):
        calls.append((start, end))
        return _flatten([track(0, 0.4, [0.05] * 500, t0=90.0)])

    monkeypatch.setattr(plan_mod.faces_mod, "detect_faces", fake_detect)
    p = plan_mod.build_crop_plan("proxy.mp4", transcript(), candidate(), META)

    assert calls == [(90.0, 140.0)], "one pass over the whole analyzed range"
    assert len(p.segments) == 10, "still one decision per shot"
