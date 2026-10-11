from clipper.models import Rect
from clipper.reframe.faces import group_into_tracks


def box(x: float) -> Rect:
    return Rect(x=x, y=0.3, w=0.2, h=0.3)


def test_groups_detections_at_the_same_position_into_one_track():
    dets = [(0.0, box(0.1), 0.02), (0.1, box(0.11), 0.05), (0.2, box(0.1), 0.01)]
    tracks = group_into_tracks(dets)
    assert len(tracks) == 1
    assert len(tracks[0].samples) == 3


def test_separates_two_people_into_two_tracks():
    dets = [(0.0, box(0.1), 0.02), (0.0, box(0.7), 0.01),
            (0.1, box(0.1), 0.03), (0.1, box(0.7), 0.02)]
    tracks = group_into_tracks(dets)
    assert len(tracks) == 2
    assert {len(t.samples) for t in tracks} == {2}


def test_median_box_ignores_a_single_outlier_detection():
    dets = [(0.0, box(0.1), 0.0), (0.1, box(0.1), 0.0),
            (0.2, Rect(0.12, 0.3, 0.2, 0.3), 0.0), (0.3, box(0.1), 0.0)]
    track = group_into_tracks(dets)[0]
    assert track.median_box().x == 0.1


def test_mouth_series_is_time_ordered():
    dets = [(0.2, box(0.1), 0.05), (0.0, box(0.1), 0.01)]
    track = group_into_tracks(dets)[0]
    assert [t for t, _ in track.mouth_series()] == [0.0, 0.2]


def test_mediapipe_is_pinned_below_1_0():
    """1.x aborts natively on macOS: DrishtiMetalHelper in TensorsToDetectionsCalculator.

    It is not catchable from Python — the process dies — so the version is the guard.
    """
    import mediapipe

    major = int(mediapipe.__version__.split(".")[0])
    assert major < 1, (
        f"mediapipe {mediapipe.__version__} crashes in Metal on macOS; "
        "pin >=0.10.35,<1.0"
    )


# --- sequential sampling -------------------------------------------------------

from pathlib import Path

import pytest

from clipper.reframe import faces

FIXTURE = Path("tests/fixtures/shots.mp4")


def _frames(fps: float, start: float, end: float) -> list[float]:
    n = int((end - start) * fps)
    return [start + i / fps for i in range(n)]


def test_sampler_keeps_about_ten_frames_per_second_from_a_30fps_source():
    sampler = faces.Sampler(10.0, 12.0, fps=10.0)
    kept = [t for t in _frames(29.97, 10.0, 12.0) if sampler.take(t)]
    assert 19 <= len(kept) <= 21
    gaps = [b - a for a, b in zip(kept, kept[1:])]
    assert all(0.09 <= g <= 0.14 for g in gaps), gaps


def test_sampler_handles_a_60fps_source_the_same_way():
    sampler = faces.Sampler(0.0, 1.0, fps=10.0)
    kept = [t for t in _frames(60.0, 0.0, 1.0) if sampler.take(t)]
    assert len(kept) == 10


def test_sampler_ignores_frames_outside_the_range():
    sampler = faces.Sampler(5.0, 6.0, fps=10.0)
    assert sampler.take(4.9) is False
    assert sampler.take(5.0) is True
    assert sampler.take(6.0) is False


@pytest.mark.skipif(not FIXTURE.exists(), reason="run tests/fixtures/make_fixtures.py")
def test_sampled_frames_come_from_one_seek_then_sequential_reads(monkeypatch):
    seeks = []
    real_open = faces._open_video

    def counting_open(path):
        cap = real_open(path)
        real_set = cap.set

        class Wrapped:
            def __getattr__(self, name):
                return getattr(cap, name)

            def set(self, prop, value):
                seeks.append(value)
                return real_set(prop, value)

        return Wrapped()

    monkeypatch.setattr(faces, "_open_video", counting_open)
    frames = list(faces.iter_sampled_frames(FIXTURE, 0.5, 3.5, fps=10.0))

    assert len(seeks) == 1, "one seek to the start, then read forward"
    times = [t for t, _ in frames]
    assert 28 <= len(times) <= 31
    assert times[0] >= 0.5 - 0.05 and times[-1] < 3.5
    assert all(b > a for a, b in zip(times, times[1:]))
    assert frames[0][1].shape[2] == 3, "frames are RGB"


def test_detect_faces_builds_one_landmarker_for_the_whole_range(monkeypatch):
    import numpy as np

    made, stamps = [], []

    class FakeLandmarker:
        def detect_for_video(self, image, ms):
            stamps.append(ms)

            class Result:
                face_landmarks = []
            return Result()

        def close(self):
            pass

    monkeypatch.setattr(faces, "_make_landmarker", lambda: made.append(1) or FakeLandmarker())
    frame = np.zeros((72, 128, 3), dtype=np.uint8)
    monkeypatch.setattr(faces, "iter_sampled_frames",
                        lambda *a, **k: ((10.0 + i * 0.1, frame) for i in range(25)))

    assert faces.detect_faces(Path("x.mp4"), 10.0, 12.5) == []
    assert len(made) == 1
    assert len(stamps) == 25
    assert all(b > a for a, b in zip(stamps, stamps[1:])), "MediaPipe needs rising timestamps"


def test_tracks_in_keeps_only_detections_inside_the_shot():
    from clipper.models import Rect
    box = Rect(0.4, 0.3, 0.2, 0.3)
    detections = [(t / 10, box, 0.05) for t in range(60)]      # 0.0 .. 5.9 s
    tracks = faces.tracks_in(detections, 2.0, 4.0)
    assert len(tracks) == 1
    assert all(2.0 <= s.t < 4.0 for s in tracks[0].samples)
    assert len(tracks[0].samples) == 20
