import pytest

from clipper import pacing
from clipper.models import Word

OFF = pacing.Pacing(cut_pauses=False, speed=1.0)
ON = pacing.Pacing(cut_pauses=True, max_pause=0.3, speed=1.1)


def words(specs):
    return [Word(i, t, s, e, 0.9) for i, (t, s, e) in enumerate(specs)]


def test_nothing_is_cut_when_pause_cutting_is_off():
    w = words([("a", 10.0, 10.4), ("b", 12.0, 12.4)])
    assert pacing.keep_intervals(w, 10.0, 12.7, OFF) == [(0.0, pytest.approx(2.7))]


def test_short_gaps_are_kept_whole():
    w = words([("a", 10.0, 10.4), ("b", 10.6, 11.0)])        # 0.2 s gap
    assert pacing.keep_intervals(w, 10.0, 11.3, ON) == [(0.0, pytest.approx(1.3))]


def test_a_long_pause_is_cut_down_to_a_short_breath():
    w = words([("a", 10.0, 10.4), ("b", 12.0, 12.4)])        # 1.6 s gap
    kept = pacing.keep_intervals(w, 10.0, 12.7, ON)
    assert len(kept) == 2
    (a0, a1), (b0, b1) = kept
    assert a0 == pytest.approx(0.0) and a1 == pytest.approx(0.45)     # 0.4 + 0.05
    assert b0 == pytest.approx(1.95) and b1 == pytest.approx(2.7)     # 2.0 - 0.05
    remaining_pause = (a1 - 0.4) + (2.0 - b0)
    assert remaining_pause == pytest.approx(pacing.KEEP_PAUSE)


def test_cuts_never_fall_inside_a_word():
    w = words([("a", 10.0, 10.4), ("b", 11.5, 12.9), ("c", 14.0, 14.3)])
    kept = pacing.keep_intervals(w, 10.0, 14.6, ON)
    for word in w:
        s, e = word.start - 10.0, word.end - 10.0
        assert any(a <= s and e <= b for a, b in kept), f"{word.text} was split by a cut"


def test_overlapping_word_times_do_not_create_negative_gaps():
    w = words([("a", 10.0, 11.0), ("b", 10.5, 10.8), ("c", 11.1, 11.5)])
    kept = pacing.keep_intervals(w, 10.0, 11.8, ON)
    assert kept == [(0.0, pytest.approx(1.8))]


def test_intervals_snap_to_the_video_frame_grid():
    """Frame-aligned edges keep audio and video the same length after every cut."""
    w = words([("a", 10.0, 10.41), ("b", 12.03, 12.4)])
    kept = pacing.keep_intervals(w, 10.0, 12.7, ON, fps=30.0)
    for a, b in kept:
        assert (a * 30) == pytest.approx(round(a * 30), abs=1e-6)
        assert (b * 30) == pytest.approx(round(b * 30), abs=1e-6)


def test_time_map_moves_later_times_earlier_by_the_cut_amount():
    kept = [(0.0, 0.45), (1.95, 2.7)]
    tm = pacing.TimeMap(kept)
    assert tm(0.2) == pytest.approx(0.2)
    assert tm(2.0) == pytest.approx(0.45 + 0.05)
    assert tm.duration == pytest.approx(0.45 + 0.75)


def test_time_map_sends_times_inside_a_cut_to_the_cut_point():
    tm = pacing.TimeMap([(0.0, 0.45), (1.95, 2.7)])
    assert tm(1.0) == pytest.approx(0.45)


def test_finished_duration_accounts_for_cuts_and_speed():
    kept = [(0.0, 0.45), (1.95, 2.7)]
    assert pacing.finished_duration(kept, ON) == pytest.approx(1.2 / 1.1)
    assert pacing.finished_duration(kept, OFF) == pytest.approx(1.2)
