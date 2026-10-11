from clipper.models import Rect, Segment, Transcript, Word
from clipper.reframe import speaker
from clipper.reframe.faces import FaceSample, FaceTrack


def track(id_: int, mouths: list[tuple[float, float]]) -> FaceTrack:
    return FaceTrack(id=id_, samples=[FaceSample(t, Rect(0.1 * id_, 0.3, 0.2, 0.3), m)
                                      for t, m in mouths])


def test_speech_mask_is_true_only_while_words_are_spoken():
    t = Transcript(words=[Word(0, "a", 1.0, 1.4, 0.9)],
                   segments=[Segment(1.0, 1.4, "a", 0, 0)], duration=5.0)
    mask = dict(speaker.speech_mask(t, 0.0, 3.0, step=0.5))
    assert mask[0.0] is False and mask[1.0] is True and mask[2.5] is False


def test_talking_score_is_higher_for_a_moving_mouth():
    mask = [(i * 0.1, True) for i in range(20)]
    moving = track(0, [(i * 0.1, 0.02 if i % 2 else 0.12) for i in range(20)])
    still = track(1, [(i * 0.1, 0.03) for i in range(20)])
    moving_score = max(s for _, s in speaker.talking_score(moving, mask))
    still_score = max(s for _, s in speaker.talking_score(still, mask))
    assert moving_score > still_score * 5


def test_single_track_yields_one_span_for_the_whole_range():
    scores = {0: [(i * 0.1, 0.5) for i in range(100)]}
    spans = speaker.speaker_timeline(scores, 0.0, 10.0)
    assert spans == [(0.0, 10.0, 0)]


def test_switch_requires_the_new_speaker_to_lead_for_min_hold():
    # track 1 leads for only 0.5s in the middle — too short to switch
    a = [(i * 0.1, 0.9 if not (30 <= i < 35) else 0.1) for i in range(100)]
    b = [(i * 0.1, 0.1 if not (30 <= i < 35) else 0.9) for i in range(100)]
    spans = speaker.speaker_timeline({0: a, 1: b}, 0.0, 10.0)
    assert spans == [(0.0, 10.0, 0)]


def test_sustained_lead_produces_a_hard_cut_switch():
    a = [(i * 0.1, 0.9 if i < 50 else 0.1) for i in range(100)]
    b = [(i * 0.1, 0.1 if i < 50 else 0.9) for i in range(100)]
    spans = speaker.speaker_timeline({0: a, 1: b}, 0.0, 10.0)
    assert len(spans) == 2
    assert spans[0][2] == 0 and spans[1][2] == 1
    assert spans[0][1] == spans[1][0]          # hard cut, no gap


def test_near_tie_never_switches_and_starts_on_the_stronger_talker():
    a = [(i * 0.1, 0.50) for i in range(100)]
    b = [(i * 0.1, 0.55) for i in range(100)]   # within the 0.15 margin
    spans = speaker.speaker_timeline({0: a, 1: b}, 0.0, 10.0)
    assert len(spans) == 1, "a near tie must not make the crop flip back and forth"
    assert spans[0][2] == 1, "the opening crop goes to the track that talks most"


def test_merge_micro_segments_absorbs_short_spans():
    spans = [(0.0, 3.0, 0), (3.0, 3.2, 1), (3.2, 6.0, 0)]
    assert speaker.merge_micro_segments(spans) == [(0.0, 6.0, 0)]


def test_merge_keeps_spans_at_or_above_the_minimum():
    spans = [(0.0, 3.0, 0), (3.0, 5.0, 1)]
    assert speaker.merge_micro_segments(spans) == spans


def test_merge_absorbs_a_short_first_span():
    """A 0.2s opening span is the 3-frame crop flash the merge exists to stop."""
    spans = [(0.0, 0.2, 0), (0.2, 3.0, 1), (3.0, 6.0, 0)]
    merged = speaker.merge_micro_segments(spans)
    assert merged[0] == (0.0, 3.0, 1)
    assert all(e - s >= 0.4 for s, e, _ in merged)


def test_merge_drops_zero_length_spans():
    spans = [(0.0, 0.0, 0), (0.0, 10.0, 1)]
    assert speaker.merge_micro_segments(spans) == [(0.0, 10.0, 1)]


def test_a_short_opening_lead_does_not_survive_the_timeline():
    quiet_then_loud = [(i * 0.1, 0.0 if i < 30 else 0.9) for i in range(60)]
    loud_early = [(i * 0.1, 0.9 if i < 30 else 0.0) for i in range(60)]
    spans = speaker.speaker_timeline({0: quiet_then_loud, 1: loud_early}, 0.0, 6.0)
    assert all(e - s >= 0.4 for s, e, _ in spans), spans


def test_talking_score_works_when_face_samples_are_off_the_speech_grid():
    """Face samples come from real frame times (e.g. 0.021, 0.121...), not the
    0.1 s grid the speech mask is built on. Matching them by exact timestamp
    silently scored every face as silent."""
    mask = [(round(i * 0.1, 3), True) for i in range(20)]
    moving = track(0, [(i * 0.1 + 0.021, 0.02 if i % 2 else 0.12) for i in range(20)])
    scores = [s for _, s in speaker.talking_score(moving, mask)]
    assert max(scores) > 0.02, "a moving mouth during speech must score as talking"


def test_talking_score_is_zero_during_silence_even_off_grid():
    mask = [(round(i * 0.1, 3), False) for i in range(20)]
    moving = track(0, [(i * 0.1 + 0.021, 0.02 if i % 2 else 0.12) for i in range(20)])
    assert all(s == 0.0 for _, s in speaker.talking_score(moving, mask))
