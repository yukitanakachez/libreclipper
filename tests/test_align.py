import numpy as np
import pytest

from clipper import align


def signal(seconds: float = 20.0, rate: int = 8000, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(seconds * rate)).astype(np.float32)


def test_measures_a_known_shift():
    full = signal()
    rate = 8000
    # section actually begins 1.5s before the requested start
    offset, confidence = align.measure_offset_arrays(
        section=full[int(8.5 * rate):int(16.5 * rate)],
        proxy=full[int(10.0 * rate):int(18.0 * rate)], rate=rate)
    assert offset == pytest.approx(1.5, abs=0.02)
    assert confidence > 0.8


def test_zero_shift_is_detected():
    full = signal()
    rate = 8000
    offset, confidence = align.measure_offset_arrays(
        section=full[:8 * rate], proxy=full[:8 * rate], rate=rate)
    assert offset == pytest.approx(0.0, abs=0.01)
    assert confidence > 0.9


def test_unrelated_audio_gives_low_confidence():
    rate = 8000
    a = signal(8.0, seed=0)
    b = signal(8.0, seed=1)
    _, confidence = align.measure_offset_arrays(section=a, proxy=b, rate=rate)
    assert confidence < 0.4


def test_measure_offset_raises_on_low_confidence(monkeypatch, tmp_path):
    rng = np.random.default_rng(2)
    monkeypatch.setattr(align, "load_audio",
                        lambda path, start, duration, rate=8000:
                        rng.standard_normal(int(duration * 8000)).astype(np.float32))
    with pytest.raises(align.AlignmentError, match="align"):
        align.measure_offset(tmp_path / "s.mp4", tmp_path / "p.mp4", expected_start=10.0)


def test_measure_offset_returns_proxy_time_of_section_start(monkeypatch, tmp_path):
    full = signal(60.0)
    rate = 8000

    def fake_load(path, start, duration, rate=rate):
        # The section file has its own time base starting at 18.5s of the source,
        # i.e. 1.5s earlier than the 20.0s that was requested from yt-dlp.
        begin = (18.5 + start) if "section" in str(path) else start
        first = int(begin * rate)
        return full[first:first + int(duration * rate)]

    monkeypatch.setattr(align, "load_audio", fake_load)
    offset, confidence = align.measure_offset(
        tmp_path / "section.mp4", tmp_path / "proxy.mp4", expected_start=20.0)
    assert offset == pytest.approx(18.5, abs=0.05)   # proxy time at section t=0
    assert confidence > 0.8


@pytest.mark.parametrize("lead", [0.5, 2.0, 5.0, 6.0, 9.0])
def test_large_keyframe_offsets_are_measured_and_trusted(monkeypatch, tmp_path, lead):
    """yt-dlp cuts at keyframes; a 5-10s GOP is normal and must not fail the clip."""
    full = signal(120.0)
    rate = 8000

    def fake_load(path, start, duration, rate=rate):
        begin = (20.0 - lead + start) if "section" in str(path) else start
        first = int(begin * rate)
        return full[first:first + int(duration * rate)]

    monkeypatch.setattr(align, "load_audio", fake_load)
    offset, confidence = align.measure_offset(
        tmp_path / "section.mp4", tmp_path / "proxy.mp4", expected_start=20.0)
    assert offset == pytest.approx(20.0 - lead, abs=0.05)
    assert confidence > 0.7, f"a correct {lead}s offset was measured but distrusted"


def test_unrelated_audio_is_still_rejected_with_the_wider_window(monkeypatch, tmp_path):
    counter = {"n": 0}

    def fake_load(path, start, duration, rate=8000):
        counter["n"] += 1
        return signal(duration, seed=counter["n"])

    monkeypatch.setattr(align, "load_audio", fake_load)
    with pytest.raises(align.AlignmentError):
        align.measure_offset(tmp_path / "section.mp4", tmp_path / "proxy.mp4",
                             expected_start=20.0)
