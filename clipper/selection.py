"""Turning the model's approximate times into clip boundaries that survive posting.

Claude proposes roughly-right ranges; this module snaps them to real sentence
boundaries so a clip opens on its hook and ends on a finished thought, then
throws out anything that breaks the campaign's rules.

Starts anchor on the hook text Claude quotes (its timestamps are only
segment-accurate), else prefer the first word of a sentence, then skip filler
lead-ins ("so", "um", "I mean", "hi"...). Ends prefer the last word of a sentence, looking back
first so a clip gets shorter rather than longer. Transcripts without
punctuation fall back to Whisper's segment boundaries.
"""

from __future__ import annotations

from clipper import pacing as pacing_mod
from clipper.campaigns import Campaign
from clipper.models import Candidate, Transcript, Word

START_WINDOW = 1.0
HOOK_WINDOW, HOOK_WORDS = 8.0, 4
END_BACK, END_FORWARD, END_SLACK = 4.0, 2.0, 0.25
SEGMENT_END_WINDOW = 1.5
PREROLL, TAIL, GUARD = 0.1, 0.3, 0.05

SENTENCE_END = (".", "?", "!")
FILLER_LEADS = {
    "so", "and", "but", "um", "uh", "uhh", "erm", "like", "yeah", "yes", "well",
    "okay", "ok", "right", "anyway", "basically", "honestly", "look", "alright", "now",
    "hi", "hey", "hello",
}
TWO_WORD_LEADS = {("i", "mean"), ("you", "know")}
MAX_LEAD_SKIP = 3


def _norm(text: str) -> str:
    return text.strip(".,!?;:\"'").lower()


def _ends_sentence(word: Word) -> bool:
    text = word.text.rstrip("\"')")
    if text.endswith(("...", "\u2026")):          # trailing off, not finishing
        return False
    return text.endswith(SENTENCE_END)


ends_sentence = _ends_sentence       # public name, used by the review screen


def _skip_lead_in(words: list[Word], i: int) -> int:
    """Index of the first word after up to three filler words."""
    skipped = 0
    while i < len(words) - 1:
        pair = (_norm(words[i].text), _norm(words[i + 1].text))
        if pair in TWO_WORD_LEADS and skipped + 2 <= MAX_LEAD_SKIP:
            i, skipped = i + 2, skipped + 2
        elif pair[0] in FILLER_LEADS and skipped + 1 <= MAX_LEAD_SKIP:
            i, skipped = i + 1, skipped + 1
        else:
            break
    return i


def find_hook(hook: str, transcript: Transcript, near: float) -> int | None:
    """Index of the word where the hook text begins, closest to `near`.

    Claude sees one timestamp per transcript segment, so its start time can be
    off by a word or several; the hook it quotes pins the real opening line.
    Matches the first few words, allowing one mismatch for transcription noise.
    """
    wanted = [w for w in (_norm(x) for x in hook.split()) if w][:HOOK_WORDS]
    if not wanted:
        return None
    words = transcript.words
    best = None
    for w in words:
        if abs(w.start - near) > HOOK_WINDOW:
            continue
        window = [_norm(x.text) for x in words[w.i:w.i + len(wanted)]]
        hits = sum(a == b for a, b in zip(window, wanted))
        if hits >= max(1, len(wanted) - 1) and window[:1] == wanted[:1]:
            if best is None or abs(w.start - near) < abs(words[best].start - near):
                best = w.i
    return best


def snap_start(start: float, transcript: Transcript, hook: str | None = None) -> float:
    words = transcript.words
    if not words:
        return start
    anchored = find_hook(hook, transcript, start) if hook else None
    if anchored is not None:
        chosen = words[anchored]
    else:
        sentence_starts = {0} | {i for i in range(1, len(words)) if _ends_sentence(words[i - 1])}
        segment_starts = {s.first_word for s in transcript.segments}
        in_window = [w for w in words if abs(w.start - start) <= START_WINDOW]
        pool = ([w for w in in_window if w.i in sentence_starts]
                or [w for w in in_window if w.i in segment_starts]
                or in_window)
        chosen = min(pool or words, key=lambda w: abs(w.start - start))
    first = words[_skip_lead_in(words, chosen.i)]

    new_start = first.start - PREROLL
    if first.i > 0:
        new_start = max(new_start, words[first.i - 1].end + GUARD)
    # The guard keeps the previous word out, but never at the cost of the first one.
    return max(0.0, min(new_start, first.start))


def _end_word(end: float, transcript: Transcript, after: float) -> Word:
    words = [w for w in transcript.words if w.start > after]
    if not words:
        return transcript.words[-1]
    endings = [w for w in words if _ends_sentence(w)]
    before = [w for w in endings if end - END_BACK <= w.end <= end + END_SLACK]
    if before:
        return max(before, key=lambda w: w.end)
    ahead = [w for w in endings if end < w.end <= end + END_FORWARD]
    if ahead:
        return min(ahead, key=lambda w: w.end)

    segment_ends = {s.last_word for s in transcript.segments}
    nearby = [w for w in words if abs(w.end - end) <= SEGMENT_END_WINDOW]
    pool = [w for w in nearby if w.i in segment_ends] or nearby
    return min(pool or words, key=lambda w: abs(w.end - end))


def snap_end(end: float, transcript: Transcript, after: float = 0.0) -> float:
    words = transcript.words
    if not words:
        return end
    last = _end_word(end, transcript, after)
    new_end = last.end + TAIL
    if last.i + 1 < len(words):
        new_end = min(new_end, words[last.i + 1].start - GUARD)
    return min(new_end, transcript.duration)


def snap_bounds(start: float, end: float, transcript: Transcript,
                hook: str | None = None) -> tuple[float, float]:
    new_start = snap_start(start, transcript, hook)
    return new_start, snap_end(end, transcript, after=new_start)


def _finished(start: float, end: float, transcript: Transcript, campaign: Campaign) -> float:
    words = [w for w in transcript.words if w.end > start and w.start < end]
    kept = pacing_mod.keep_intervals(words, start, end, campaign.pacing)
    return pacing_mod.finished_duration(kept, campaign.pacing)


def _fit_to_max(start: float, end: float, transcript: Transcript,
                campaign: Campaign) -> tuple[float, float]:
    """Pull the end back, sentence by sentence, until the finished clip fits."""
    duration = _finished(start, end, transcript, campaign)
    target = end
    for _ in range(12):
        if duration <= campaign.max_len:
            break
        target = min(target, end) - (duration - campaign.max_len) * campaign.pacing.speed - 0.5
        new_end = snap_end(target, transcript, after=start)
        if new_end >= end - 1e-6:
            target -= 1.0
            continue
        end = new_end
        duration = _finished(start, end, transcript, campaign)
    return end, duration


def _overlap(a: Candidate, b: Candidate) -> float:
    span = min(a.end, b.end) - max(a.start, b.start)
    if span <= 0:
        return 0.0
    return span / min(a.end - a.start, b.end - b.start)


def validate_candidates(
    raw: list[dict], transcript: Transcript, campaign: Campaign
) -> list[Candidate]:
    built: list[Candidate] = []
    for item in raw:
        start, end = float(item["start"]), float(item["end"])
        if start < 0 or end > transcript.duration or end <= start:
            continue
        start, end = snap_bounds(start, end, transcript, hook=item.get("hook"))
        if end <= start:
            continue
        end, duration = _fit_to_max(start, end, transcript, campaign)
        if duration < campaign.min_len or duration > campaign.max_len + 1.0:
            continue

        hashtags = list(item.get("hashtags") or [])
        for tag in campaign.required_hashtags:
            if tag not in hashtags:
                hashtags.append(tag)

        built.append(Candidate(
            n=0,
            start=start,
            end=end,
            orig_start=float(item["start"]),
            orig_end=float(item["end"]),
            headline=str(item["headline"]),
            hook=str(item["hook"]),
            reason=str(item["reason"]),
            score=max(1, min(10, int(item["score"]))),
            post_caption=str(item["post_caption"]),
            hashtags=hashtags,
        ))

    built.sort(key=lambda c: (-c.score, c.start))
    kept: list[Candidate] = []
    for cand in built:
        if any(_overlap(cand, k) > 0.5 for k in kept):
            continue
        kept.append(cand)
    for n, cand in enumerate(kept, start=1):
        cand.n = n
    return kept
