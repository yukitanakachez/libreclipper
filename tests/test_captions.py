from pathlib import Path

import pytest

from clipper import captions
from clipper.campaigns import Campaign
from clipper.models import Word

CAMPAIGN = Campaign(name="P", slug="p", min_len=20, max_len=60, accent_color="#FFE500")


def words(specs: list[tuple[str, float, float]]) -> list[Word]:
    return [Word(i, t, s, e, 0.9) for i, (t, s, e) in enumerate(specs)]


def test_chunks_cap_at_three_words():
    w = words([(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)])
    chunks = captions.chunk_words(w)
    assert all(len(c.words) <= 3 for c in chunks)
    assert len(chunks) == 3


def test_chunk_breaks_on_a_pause():
    w = words([("one", 0.0, 0.2), ("two", 0.25, 0.45), ("three", 1.5, 1.7)])
    chunks = captions.chunk_words(w)
    assert [c.text for c in chunks] == ["one two", "three"]


def test_chunk_breaks_after_sentence_punctuation():
    w = words([("Stop.", 0.0, 0.2), ("Next", 0.25, 0.45)])
    assert [c.text for c in captions.chunk_words(w)] == ["Stop.", "Next"]


def test_chunk_breaks_on_character_budget():
    w = words([("internationalization", 0.0, 0.4), ("is", 0.45, 0.5)])
    assert [c.text for c in captions.chunk_words(w)] == ["internationalization", "is"]


def test_filler_words_are_dropped():
    w = words([("um", 0.0, 0.1), ("really", 0.2, 0.5), ("uh", 0.6, 0.7)])
    assert [c.text for c in captions.chunk_words(w)] == ["really"]


def test_zero_length_words_get_a_minimum_duration():
    w = words([("hi", 1.0, 1.0)])
    chunk = captions.chunk_words(w)[0]
    assert chunk.end > chunk.start


def test_out_of_order_word_is_repaired_not_crashing():
    w = [Word(0, "a", 2.0, 1.0, 0.9), Word(1, "b", 2.1, 2.4, 0.9)]
    chunks = captions.chunk_words(w)
    assert all(c.end > c.start for c in chunks)


def test_apply_word_fixes_replaces_text_but_keeps_timings():
    w = words([("Jane", 0.0, 0.3), ("Dough", 0.35, 0.8)])
    fixed = captions.apply_word_fixes(w, {"1": "Doe"})
    assert [x.text for x in fixed] == ["Jane", "Doe"]
    assert fixed[1].start == 0.35 and fixed[1].end == 0.8


def test_apply_word_fixes_ignores_unknown_indices():
    w = words([("Jane", 0.0, 0.3)])
    assert [x.text for x in captions.apply_word_fixes(w, {"99": "Nope"})] == ["Jane"]


def test_escape_ass_protects_braces_and_backslashes():
    assert captions.escape_ass("{cue}") == r"\{cue\}"
    assert captions.escape_ass("a\\b") == r"a\\b"


def test_build_ass_escapes_dialogue_text():
    chunks = captions.chunk_words(words([("{hi}", 0.0, 0.4)]))
    out = captions.build_ass(chunks, CAMPAIGN, "single", 0.0, None, None)
    assert r"\{hi\}" in out
    assert "\nDialogue:" in out


def test_build_ass_positions_captions_at_68_percent_for_single():
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             CAMPAIGN, "single", 0.0, None, None)
    assert "\\pos(540,1305" in out or "\\pos(540,1306" in out   # 0.68 * 1920


def test_build_ass_positions_captions_at_seam_for_stack():
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             CAMPAIGN, "stack", 0.0, None, None)
    assert "\\pos(540,960)" in out


def test_uppercase_campaign_uppercases_caption_text():
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=60, uppercase=True)
    out = captions.build_ass(captions.chunk_words(words([("hey", 0.0, 0.4)])),
                             campaign, "single", 0.0, None, None)
    assert "HEY" in out


def test_headline_and_credit_render_as_their_own_events():
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=60,
                        credit_enabled=True, credit_handle="@pod")
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             campaign, "single", 0.0, "Big Claim", "@pod")
    assert "Big Claim" in out and "@pod" in out


def test_times_are_relative_to_clip_start():
    out = captions.build_ass(captions.chunk_words(words([("hi", 30.0, 30.4)])),
                             CAMPAIGN, "single", 30.0, None, None)
    assert "Dialogue: 0,0:00:00.00" in out


def test_golden_ass_output():
    w = words([("This", 0.0, 0.3), ("changed", 0.35, 0.8), ("everything.", 0.85, 1.5)])
    out = captions.build_ass(captions.chunk_words(w), CAMPAIGN, "single", 0.0, "Big Claim", "@pod")
    golden = Path("tests/fixtures/golden_caption.ass")
    if not golden.exists():
        golden.write_text(out)          # first run records it; review the diff in git
    assert out == golden.read_text()


def _events(ass: str) -> list[tuple[float, float, str]]:
    out = []
    for line in ass.splitlines():
        if not line.startswith("Dialogue:") or ",Caption," not in line:
            continue
        fields = line.split(",", 9)
        def secs(stamp: str) -> float:
            h, m, s = stamp.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        out.append((secs(fields[1]), secs(fields[2]), fields[9]))
    return out


def test_captions_stay_on_screen_between_words_in_a_chunk():
    w = words([("This", 0.0, 0.30), ("changed", 0.45, 0.80), ("it.", 0.95, 1.50)])
    events = _events(captions.build_ass(captions.chunk_words(w), CAMPAIGN,
                                        "single", 0.0, None, None))
    for (_, end, _), (next_start, _, _) in zip(events, events[1:]):
        assert next_start <= end + 1e-6, "captions must not blink off between words"


def test_last_word_of_a_chunk_holds_until_the_chunk_ends():
    w = words([("Hold", 0.0, 0.20), ("this.", 0.30, 0.60)])
    events = _events(captions.build_ass(captions.chunk_words(w), CAMPAIGN,
                                        "single", 0.0, None, None))
    assert events[-1][1] == pytest.approx(0.60, abs=0.01)


def test_long_headline_wraps_to_two_lines():
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             CAMPAIGN, "single", 0.0,
                             "Why Most People Quit Their Side Projects Early", None)
    headline = [line for line in out.splitlines() if ",Headline," in line][0]
    assert "\\N" in headline, "a long headline must wrap instead of running off frame"
    assert headline.count("\\N") == 1, "at most two lines"


def test_very_long_headline_also_shrinks_the_font():
    long_out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                                  CAMPAIGN, "single", 0.0,
                                  "Why Almost Everybody Quits Their Ambitious Side Projects", None)
    headline = [line for line in long_out.splitlines() if ",Headline," in line][0]
    assert "\\fs" in headline, "an over-long headline must shrink to fit"


def test_short_headline_is_left_alone():
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             CAMPAIGN, "single", 0.0, "Big Claim", None)
    headline = [line for line in out.splitlines() if ",Headline," in line][0]
    assert "\\N" not in headline and "\\fs" not in headline


def test_small_gap_between_chunks_does_not_blink():
    # "This changed" then "everything." — split by the character budget, not a pause
    w = words([("This", 0.0, 0.30), ("changed", 0.35, 0.80), ("everything.", 0.85, 1.50)])
    events = _events(captions.build_ass(captions.chunk_words(w), CAMPAIGN,
                                        "single", 0.0, None, None))
    for (_, end, _), (next_start, _, _) in zip(events, events[1:]):
        assert next_start <= end + 1e-6


def test_a_real_pause_still_clears_the_caption():
    w = words([("Done.", 0.0, 0.30), ("Later", 3.0, 3.40)])
    events = _events(captions.build_ass(captions.chunk_words(w), CAMPAIGN,
                                        "single", 0.0, None, None))
    assert events[0][1] < events[1][0], "a long silence should leave the screen clear"
    assert events[0][1] == pytest.approx(0.30, abs=0.01)


def test_credit_clears_a_two_line_headline():
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=60,
                        credit_enabled=True, credit_handle="@pod")
    chunks = captions.chunk_words(words([("hi", 0.0, 0.4)]))
    one_line = captions.build_ass(chunks, campaign, "single", 0.0, "Big Claim", "@pod")
    two_line = captions.build_ass(chunks, campaign, "single", 0.0,
                                  "Why Most People Quit Their Side Projects Early", "@pod")

    def credit_y(ass: str) -> int:
        line = [x for x in ass.splitlines() if ",Credit," in x][0]
        return int(line.split("\\pos(540,")[1].split(")")[0])

    assert credit_y(two_line) > credit_y(one_line), (
        "a wrapped headline is taller; the credit must move down to clear it"
    )


# --- retiming onto the cut timeline ---------------------------------------------

from clipper import pacing


def test_retime_moves_words_after_a_cut_earlier():
    w = words([("before", 10.0, 10.4), ("after", 12.0, 12.4)])
    chunks = captions.chunk_words(w)
    tm = pacing.TimeMap([(0.0, 0.45), (1.95, 2.7)])       # clip starts at 10.0
    retimed = captions.retime_chunks(chunks, tm, clip_start=10.0)
    starts = [wd.start for c in retimed for wd in c.words]
    assert starts[0] == pytest.approx(0.0)
    assert starts[1] == pytest.approx(0.45 + 0.05)          # 12.0 -> after the cut


def test_retimed_chunks_keep_their_original_grouping():
    w = words([("one", 0.0, 0.2), ("two", 0.25, 0.45), ("three", 1.5, 1.7)])
    chunks = captions.chunk_words(w)
    tm = pacing.TimeMap([(0.0, 0.5), (1.45, 2.0)])
    retimed = captions.retime_chunks(chunks, tm, clip_start=0.0)
    assert [c.text for c in retimed] == ["one two", "three"]
    assert all(c.end > c.start for c in retimed)


def test_headline_lasts_the_whole_clip_when_duration_is_given():
    out = captions.build_ass(captions.chunk_words(words([("hi", 0.0, 0.4)])),
                             CAMPAIGN, "single", 0.0, "Big Claim", None, duration=12.5)
    headline = [line for line in out.splitlines() if ",Headline," in line][0]
    assert ",0:00:12.50," in headline


def test_hook_scale_grows_short_lines_and_never_overflows():
    assert captions.hook_scale("SHE LIED") == 140
    assert captions.hook_scale("A" * 30) == 100          # already full width: no growth


def test_hook_caption_makes_the_first_chunk_bigger_and_holds_it():
    words = [Word(0, "She", 0.0, 0.2), Word(1, "lied.", 0.25, 0.5),
             Word(2, "Then", 1.5, 1.7), Word(3, "what?", 1.75, 2.0)]
    chunks = captions.chunk_words(words)
    camp = Campaign(name="x", slug="x", min_len=1, max_len=60, headline_enabled=False)
    ass = captions.build_ass(chunks, camp, "single", 0.0, None, None, duration=3.0, hook=True)
    first = [l for l in ass.splitlines() if l.startswith("Dialogue") and "SHE" in l.upper()]
    assert all("\\fscx140" in l for l in first)
    assert "0:00:01.50" in first[-1]                     # held until the next chunk starts
    later = [l for l in ass.splitlines() if l.startswith("Dialogue") and "THEN" in l.upper()]
    assert not any("\\fscx140" in l for l in later)
    assert "\\fscx140" not in captions.build_ass(chunks, camp, "single", 0.0, None, None, 3.0)


@pytest.mark.skipif(not captions.CAPTION_FONT.exists(), reason="needs the caption font")
def test_hook_scale_measures_the_real_font_so_typical_hooks_grow():
    # Measured in a real render: "THEN THE LANDLORD" spans 730 px with its 7 px outline.
    assert abs(captions._text_width("THEN THE LANDLORD") - 716) < 30
    for text in ("THEN THE LANDLORD", "SHE LIED TO ME", "I SAID NO"):
        scale = captions.hook_scale(text)
        assert scale > 100, text                         # a normal first line gets bigger
        assert captions._text_width(text) * scale / 100 <= captions.HOOK_MAX_WIDTH


def test_the_hook_is_measured_as_displayed_and_clears_the_side_buttons():
    words = [Word(0, "Then", 0.0, 0.2), Word(1, "the", 0.25, 0.4), Word(2, "landlord", 0.45, 0.8),
             Word(3, "called.", 1.5, 1.9)]
    camp = Campaign(name="x", slug="x", min_len=1, max_len=60, headline_enabled=False, uppercase=True)
    ass = captions.build_ass(captions.chunk_words(words), camp, "single", 0.0, None, None,
                             duration=3.0, hook=True)
    expected = captions.hook_scale("THEN THE LANDLORD")
    assert f"\\fscx{expected}\\fscy{expected}" in ass and expected < 140
    # The right 12% of the frame is covered by the app's buttons: a centred line stays inside.
    assert 1080 - 2 * int(1080 * 0.12) >= captions.HOOK_MAX_WIDTH
