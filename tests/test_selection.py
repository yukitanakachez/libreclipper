import pytest

from clipper import selection
from clipper.campaigns import Campaign
from clipper.models import Segment, Transcript, Word

CAMPAIGN = Campaign(name="P", slug="p", min_len=20, max_len=60,
                    required_hashtags=["#pod"])


def transcript() -> Transcript:
    # words every 0.5s from 0..120s, sentences of 10 words
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(240)]
    segments = [Segment(start=words[s].start, end=words[s + 9].end,
                        text="s", first_word=s, last_word=s + 9)
                for s in range(0, 240, 10)]
    return Transcript(words=words, segments=segments, duration=120.0)


def test_start_snaps_to_nearest_word_start_with_preroll():
    # word 20 starts at 10.0; the 0.1s pre-roll would touch word 19's end (9.9),
    # so the 0.05s guard holds the start at 9.95
    start, _ = selection.snap_bounds(10.2, 40.0, transcript())
    assert start == pytest.approx(9.95, abs=0.001)


def test_start_prefers_a_segment_start_inside_the_window():
    # word 41 starts at 20.5; segment starts at 20.0 (word 40) — within 1.0s
    start, _ = selection.snap_bounds(20.4, 50.0, transcript())
    assert start == pytest.approx(19.95, abs=0.001)


def test_end_snaps_to_segment_final_word_with_tail_pad():
    # segment ending word 49 ends at 24.9; next word starts at 25.0
    _, end = selection.snap_bounds(5.0, 24.6, transcript())
    assert end == pytest.approx(24.95, abs=0.001)          # clamped by next word start


def test_pads_never_overlap_neighbouring_words():
    t = transcript()
    start, end = selection.snap_bounds(10.2, 24.6, t)
    prev_word_end = t.words[19].end
    assert start >= prev_word_end + 0.05 - 1e-9


def test_validate_drops_candidate_past_end_of_video():
    raw = [{"start": 110.0, "end": 200.0, "headline": "h", "hook": "k",
            "reason": "r", "score": 9, "post_caption": "c", "hashtags": []}]
    assert selection.validate_candidates(raw, transcript(), CAMPAIGN) == []


def test_validate_clamps_overlong_candidate_to_campaign_max():
    """The limit applies to the finished clip, after pause cuts and speed-up."""
    raw = [{"start": 10.0, "end": 100.0, "headline": "h", "hook": "k",
            "reason": "r", "score": 9, "post_caption": "c", "hashtags": []}]
    t = transcript()
    out = selection.validate_candidates(raw, t, CAMPAIGN)
    assert selection._finished(out[0].start, out[0].end, t, CAMPAIGN) <= 60.0 + 1e-6


def test_validate_drops_too_short_candidate():
    raw = [{"start": 10.0, "end": 14.0, "headline": "h", "hook": "k",
            "reason": "r", "score": 9, "post_caption": "c", "hashtags": []}]
    assert selection.validate_candidates(raw, transcript(), CAMPAIGN) == []


def test_validate_drops_overlapping_lower_scored_candidate():
    raw = [
        {"start": 10.0, "end": 40.0, "headline": "a", "hook": "k", "reason": "r",
         "score": 9, "post_caption": "c", "hashtags": []},
        {"start": 12.0, "end": 42.0, "headline": "b", "hook": "k", "reason": "r",
         "score": 6, "post_caption": "c", "hashtags": []},
    ]
    out = selection.validate_candidates(raw, transcript(), CAMPAIGN)
    assert [c.headline for c in out] == ["a"]


def test_validate_numbers_sorts_and_appends_required_hashtags():
    raw = [
        {"start": 60.0, "end": 90.0, "headline": "low", "hook": "k", "reason": "r",
         "score": 5, "post_caption": "c", "hashtags": ["#x"]},
        {"start": 10.0, "end": 40.0, "headline": "high", "hook": "k", "reason": "r",
         "score": 9, "post_caption": "c", "hashtags": ["#pod"]},
    ]
    out = selection.validate_candidates(raw, transcript(), CAMPAIGN)
    assert [c.headline for c in out] == ["high", "low"]
    assert [c.n for c in out] == [1, 2]
    assert out[1].hashtags == ["#x", "#pod"]     # appended, not duplicated
    assert out[0].hashtags == ["#pod"]
    assert all(c.orig_start is not None for c in out)


def test_score_outside_one_to_ten_is_clamped():
    raw = [
        {"start": 10.0, "end": 40.0, "headline": "high", "hook": "k", "reason": "r",
         "score": 47, "post_caption": "c", "hashtags": []},
        {"start": 60.0, "end": 90.0, "headline": "low", "hook": "k", "reason": "r",
         "score": -3, "post_caption": "c", "hashtags": []},
    ]
    out = selection.validate_candidates(raw, transcript(), CAMPAIGN)
    assert [c.score for c in out] == [10, 1]


# --- sentence-aware boundaries --------------------------------------------------

from clipper.pacing import Pacing


def spoken(sentences: list[str], word_len=0.4, gap=0.1, sentence_gap=0.6) -> Transcript:
    """A transcript with real punctuation: each sentence ends in . ? or !"""
    words, segments, t = [], [], 0.0
    for sentence in sentences:
        first = len(words)
        for token in sentence.split():
            words.append(Word(len(words), token, round(t, 3), round(t + word_len, 3), 0.9))
            t += word_len + gap
        segments.append(Segment(words[first].start, words[-1].end, sentence, first, len(words) - 1))
        t += sentence_gap - gap
    return Transcript(words, segments, round(t + 2.0, 3))


SENTENCES = [
    "So yeah that was a whole thing.",                      # words 0-6
    "Most people quit in three weeks.",                     # 7-12
    "Um the real reason is the loop is too slow.",          # 13-22
    "You have to see progress every single night.",         # 23-30
]


def _start_word(t: Transcript, clip_start: float) -> str:
    """The first word heard in a clip starting at clip_start."""
    return next(w.text for w in t.words if w.end > clip_start + 1e-6)


def test_start_prefers_a_sentence_start_in_the_window():
    t = spoken(SENTENCES)
    target = t.words[8].start                                # "people", mid-sentence
    start, _ = selection.snap_bounds(target, t.words[12].end, t)
    assert _start_word(t, start) == "Most"


def test_start_skips_filler_lead_ins():
    t = spoken(SENTENCES)
    start, _ = selection.snap_bounds(t.words[13].start, t.words[22].end, t)   # "Um the real..."
    assert _start_word(t, start) == "the"


def test_start_skips_two_word_fillers():
    t = spoken(["That was fun.", "I mean the numbers speak for themselves."])
    start, _ = selection.snap_bounds(t.words[3].start, t.words[-1].end, t)
    assert _start_word(t, start) == "the"


def test_filler_skipping_stops_after_three_words():
    t = spoken(["Done.", "So um like yeah well okay here we go."])
    start, _ = selection.snap_bounds(t.words[1].start, t.words[-1].end, t)
    assert _start_word(t, start) == "yeah", "at most three lead-in words are dropped"


def test_end_prefers_the_sentence_end_before_the_target():
    t = spoken(SENTENCES)
    target = t.words[25].end                                 # mid sentence 4
    _, end = selection.snap_bounds(t.words[7].start, target, t)
    last = max((w for w in t.words if w.end <= end + 1e-6), key=lambda w: w.end)
    assert last.text == "slow."


def test_end_looks_forward_only_when_nothing_ends_before():
    t = spoken(["This is one long sentence that keeps going and going to the end."])
    target = t.words[-3].end                                 # 2 words before the end
    _, end = selection.snap_bounds(t.words[0].start, target, t)
    last = max((w for w in t.words if w.end <= end + 1e-6), key=lambda w: w.end)
    assert last.text == "end."


def test_length_limits_apply_to_the_finished_clip():
    # ~64 s of source with no long pauses plays in ~58 s at 1.1x: within a 60 s max
    t = spoken([f"Sentence number {i} is right here." for i in range(20)])
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=60,
                        pacing=Pacing(cut_pauses=True, max_pause=0.3, speed=1.1))
    raw = [{"start": 0.0, "end": 64.0, "headline": "h", "hook": "k", "reason": "r",
            "score": 9, "post_caption": "c", "hashtags": []}]
    out = selection.validate_candidates(raw, t, campaign)
    assert len(out) == 1
    assert out[0].end - out[0].start > 60.0, "source may run longer than the max"


def test_overlong_clip_is_shortened_to_a_sentence_end_that_fits():
    t = spoken([f"Sentence number {i} is right here." for i in range(30)])
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=40,
                        pacing=Pacing(cut_pauses=False, speed=1.0))
    raw = [{"start": 0.0, "end": 95.0, "headline": "h", "hook": "k", "reason": "r",
            "score": 9, "post_caption": "c", "hashtags": []}]
    out = selection.validate_candidates(raw, t, campaign)
    assert out, "shortened, not dropped"
    assert out[0].end - out[0].start <= 40.0 + 1e-6
    last = max((w for w in t.words if w.end <= out[0].end + 1e-6), key=lambda w: w.end)
    assert last.text.endswith("."), "shortening still ends on a finished sentence"


# --- found in the stopping-point run ---------------------------------------------

def test_start_anchors_on_the_hook_text_when_claudes_time_is_off():
    """Claude only sees one timestamp per segment, so its start can be a word or
    two late. Its hook text says where the clip really opens."""
    t = spoken(["We try to be above the rest.",
                "Anyone can clickbait but you do actually deliver on it."])
    claude_start = t.words[11].start                          # "you", 0.5 s+ late
    start, _ = selection.snap_bounds(claude_start, t.words[-1].end, t,
                                     hook="Anyone can clickbait but you do actually deliver")
    assert _start_word(t, start) == "Anyone"


def test_hook_after_greetings_starts_on_the_hook():
    t = spoken(["Hi.", "Hi.", "Hi.", "Who hurt you?", "Like oh my God."])
    start, _ = selection.snap_bounds(t.words[2].start, t.words[-1].end, t,
                                     hook="Who hurt you? Like oh my God.")
    assert _start_word(t, start) == "Who"


def test_unmatched_hook_falls_back_to_time_based_snapping():
    t = spoken(SENTENCES)
    start, _ = selection.snap_bounds(t.words[8].start, t.words[12].end, t,
                                     hook="words that are nowhere in this transcript")
    assert _start_word(t, start) == "Most"


def test_greetings_are_skipped_as_lead_ins():
    t = spoken(["Done.", "Hey the real story is simple."])
    start, _ = selection.snap_bounds(t.words[1].start, t.words[-1].end, t)
    assert _start_word(t, start) == "the"


def test_pre_roll_guard_never_cuts_into_the_first_word():
    # the previous word ends exactly where the first word starts
    words = [Word(0, "Basically", 43.5, 43.8, 0.9), Word(1, "what", 43.8, 44.0, 0.9),
             Word(2, "I", 44.0, 44.1, 0.9), Word(3, "did.", 44.1, 44.4, 0.9)]
    t = Transcript(words, [Segment(43.5, 44.4, "s", 0, 3)], 60.0)
    start, _ = selection.snap_bounds(43.5, 44.4, t)
    assert start <= 43.8 + 1e-9, "the clip must include the whole first word"


def test_an_ellipsis_is_not_a_finished_sentence():
    t = spoken(["You are saying it's different.", "So what do..."])
    target = t.words[-1].end
    _, end = selection.snap_bounds(t.words[0].start, target, t)
    last = max((w for w in t.words if w.end <= end + 1e-6), key=lambda w: w.end)
    assert last.text == "different."
