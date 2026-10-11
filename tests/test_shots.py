from pathlib import Path

import pytest

from clipper.reframe import shots

FIXTURE = Path("tests/fixtures/shots.mp4")


@pytest.mark.skipif(not FIXTURE.exists(), reason="run tests/fixtures/make_fixtures.py")
def test_detects_three_shots_at_expected_boundaries():
    found = shots.detect_shots(FIXTURE, 0.0, 6.0)
    assert len(found) == 3
    assert found[0][0] == pytest.approx(0.0, abs=0.1)
    assert found[1][0] == pytest.approx(2.0, abs=0.2)
    assert found[2][1] == pytest.approx(6.0, abs=0.2)


@pytest.mark.skipif(not FIXTURE.exists(), reason="run tests/fixtures/make_fixtures.py")
def test_range_is_clamped_to_requested_window():
    found = shots.detect_shots(FIXTURE, 2.5, 4.0)
    assert found[0][0] >= 2.5 - 1e-6
    assert found[-1][1] <= 4.0 + 1e-6


@pytest.mark.skipif(not FIXTURE.exists(), reason="run tests/fixtures/make_fixtures.py")
def test_single_shot_range_returns_one_span():
    found = shots.detect_shots(FIXTURE, 0.2, 1.8)
    assert found == [(pytest.approx(0.2), pytest.approx(1.8))]


def test_only_the_requested_range_is_scanned(monkeypatch):
    """A 90-minute proxy must not be rescanned in full for every candidate."""
    seen = {}

    def fake_detect(path, detector, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(shots, "detect", fake_detect)
    shots.detect_shots(Path("whatever.mp4"), 600.0, 660.0)
    assert seen["start_time"] == 600.0
    assert seen["end_time"] == 660.0
