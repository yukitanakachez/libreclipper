"""Step 5: word-by-word captions as an ASS subtitle file.

The look is the standard podcast-clip one: two or three words on screen, the
word being spoken highlighted, a small pop as each group appears. Positions
avoid the areas TikTok and Shorts cover with their own UI.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

from clipper import shell
from clipper.campaigns import Campaign
from clipper.models import Word

FILLERS = {"um", "uh", "uhh", "erm", "hmm"}
MIN_EVENT = 0.08
W, H = 1080, 1920
SENTENCE_END = tuple(".!?")
PAUSE = 0.35          # gap that counts as a real pause, not a flicker

# Safe zones: TikTok/Shorts cover the top 10%, bottom 20% and right 12%.
CAPTION_Y = 0.68
STACK_SEAM_Y = 0.5
HEADLINE_Y = 0.13


@dataclass
class Chunk:
    words: list[Word]
    start: float
    end: float
    text: str


def escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def apply_word_fixes(words: list[Word], fixes: dict[str, str]) -> list[Word]:
    """Spelling corrections made in review, keyed by word index."""
    if not fixes:
        return list(words)
    return [Word(w.i, fixes.get(str(w.i), w.text), w.start, w.end, w.prob) for w in words]


def _clean(words: list[Word]) -> list[Word]:
    out: list[Word] = []
    for w in words:
        if w.text.strip(".,!?").lower() in FILLERS:
            continue
        start = w.start
        end = w.end if w.end > w.start else w.start + MIN_EVENT
        out.append(Word(w.i, w.text, start, end, w.prob))
    return out


def chunk_words(
    words: list[Word], max_words: int = 3, max_chars: int = 18, pause: float = PAUSE
) -> list[Chunk]:
    cleaned = _clean(words)
    chunks: list[Chunk] = []
    current: list[Word] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(w.text for w in current)
        start = current[0].start
        end = max(current[-1].end, start + MIN_EVENT)
        chunks.append(Chunk(list(current), start, end, text))
        current.clear()

    for word in cleaned:
        if current:
            gap = word.start - current[-1].end
            candidate_len = len(" ".join(w.text for w in current)) + 1 + len(word.text)
            if (
                gap > pause
                or len(current) >= max_words
                or candidate_len > max_chars
                or current[-1].text.endswith(SENTENCE_END)
            ):
                flush()
        current.append(word)
    flush()
    return chunks


def retime_chunks(chunks: list[Chunk], time_map, clip_start: float) -> list[Chunk]:
    """Move chunks onto the cut clip's timeline (0 = first frame, pauses removed).

    Grouping is decided on the original timing, where real pauses still exist;
    only the times move. Words never straddle a cut, so each maps whole.
    """
    out: list[Chunk] = []
    for chunk in chunks:
        moved = [Word(w.i, w.text, time_map(w.start - clip_start),
                      max(time_map(w.end - clip_start), time_map(w.start - clip_start) + MIN_EVENT),
                      w.prob)
                 for w in chunk.words]
        start = moved[0].start
        out.append(Chunk(moved, start, max(moved[-1].end, start + MIN_EVENT), chunk.text))
    return out


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


HEADLINE_SIZE = 64
MIN_HEADLINE_SIZE = 40
HEADLINE_MAX_WIDTH = 0.8 * W
# Montserrat Black is wide; this is the average advance per character as a
# fraction of the font size, measured from rendered samples.
CHAR_WIDTH_RATIO = 0.62


def _fits(text: str, size: int) -> bool:
    return len(text) * size * CHAR_WIDTH_RATIO <= HEADLINE_MAX_WIDTH


def _wrap_two_lines(headline: str, size: int) -> str | None:
    """Split on the word boundary closest to the middle; None if it still won't fit."""
    words_in = headline.split()
    if len(words_in) < 2:
        return None
    best, best_gap = None, None
    for i in range(1, len(words_in)):
        first, second = " ".join(words_in[:i]), " ".join(words_in[i:])
        if not (_fits(first, size) and _fits(second, size)):
            continue
        gap = abs(len(first) - len(second))
        if best_gap is None or gap < best_gap:
            best, best_gap = f"{first}\\N{second}", gap
    return best


def _fit_headline(headline: str) -> tuple[str, int]:
    """Returns the (escaped, possibly wrapped) text and the font size to use."""
    escaped = escape_ass(headline)
    if _fits(escaped, HEADLINE_SIZE):
        return escaped, HEADLINE_SIZE
    wrapped = _wrap_two_lines(escaped, HEADLINE_SIZE)
    if wrapped:
        return wrapped, HEADLINE_SIZE
    for size in range(HEADLINE_SIZE - 4, MIN_HEADLINE_SIZE - 1, -4):
        wrapped = _wrap_two_lines(escaped, size)
        if wrapped:
            return wrapped, size
        if _fits(escaped, size):
            return escaped, size
    return _wrap_two_lines(escaped, MIN_HEADLINE_SIZE) or escaped, MIN_HEADLINE_SIZE


def _bgr(hex_colour: str) -> str:
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    return f"&H00{b}{g}{r}".upper()


CAPTION_SIZE = 96
CAPTION_FONT = shell.project_home() / "assets" / "fonts" / "Montserrat-Black.ttf"
HOOK_MAX_WIDTH = 820     # centred, it stays clear of the app buttons over the right 12%


@functools.lru_cache(maxsize=1)
def _caption_font():
    from PIL import ImageFont
    return ImageFont.truetype(str(CAPTION_FONT), CAPTION_SIZE)


# libass sizes a font by usWinAscent + usWinDescent, not by its em: Montserrat Black's are
# 1109 + 453 per 1000 em, so letters render at 1000 / 1562 of the style's font size.
LIBASS_EM = 1000 / (1109 + 453)


def _text_width(text: str) -> float:
    """Rendered width of a caption line at 100%, in frame pixels."""
    try:
        return _caption_font().getlength(text) * LIBASS_EM
    except OSError:                                   # font missing: a safe overestimate
        return max(1, len(text)) * 0.62 * CAPTION_SIZE


def hook_scale(text: str) -> int:
    """How much bigger the hook line can be (percent) without leaving the frame."""
    return int(max(100, min(140, HOOK_MAX_WIDTH / max(1.0, _text_width(text)) * 100)))


def build_ass(
    chunks: list[Chunk],
    campaign: Campaign,
    layout: str,
    clip_start: float,
    headline: str | None,
    credit: str | None,
    duration: float | None = None,
    hook: bool = False,
) -> str:
    caption_y = int(H * (STACK_SEAM_Y if layout == "stack" else CAPTION_Y))
    headline_y = int(H * HEADLINE_Y)

    headline_text, headline_size = _fit_headline(headline) if headline else ("", HEADLINE_SIZE)
    headline_lines = headline_text.count("\\N") + 1 if headline_text else 0
    if campaign.credit_position == "below_headline":
        # Clear the whole headline box, however many lines it turned out to need.
        credit_y = headline_y + int(headline_size * 1.25 * headline_lines) + 20
    else:
        credit_y = headline_y
    accent = _bgr(campaign.accent_color)
    clip_end = (duration if duration is not None
                else max((c.end for c in chunks), default=clip_start) - clip_start)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Montserrat Black,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1
Style: Headline,Montserrat Black,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC8000000,0,0,0,0,100,100,0,0,3,14,0,5,120,120,0,1
Style: Credit,Montserrat Black,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,4,2,5,120,120,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines: list[str] = []
    if headline and campaign.headline_enabled:
        override = f"\\fs{headline_size}" if headline_size != HEADLINE_SIZE else ""
        lines.append(
            f"Dialogue: 0,{_ass_time(0)},{_ass_time(clip_end)},Headline,,0,0,0,,"
            f"{{\\pos({W // 2},{headline_y}){override}}}{headline_text}"
        )
    if credit and campaign.credit_enabled:
        lines.append(
            f"Dialogue: 0,{_ass_time(0)},{_ass_time(clip_end)},Credit,,0,0,0,,"
            f"{{\\pos({W // 2},{credit_y})\\alpha&H33&}}{escape_ass(credit)}"
        )

    for chunk_index, chunk in enumerate(chunks):
        start = chunk.start - clip_start
        # Hold the last word until the next chunk appears, unless the gap is a real
        # pause — a 50ms blank between chunks reads as a flicker, a silence does not.
        chunk_end = chunk.end - clip_start
        if chunk_index + 1 < len(chunks):
            next_chunk_start = chunks[chunk_index + 1].start - clip_start
            if next_chunk_start - chunk_end <= PAUSE:
                chunk_end = next_chunk_start
        shown = chunk.text.upper() if campaign.uppercase else chunk.text
        size = hook_scale(shown) if hook and chunk_index == 0 else 100
        if size != 100 and chunk_index + 1 < len(chunks):
            chunk_end = chunks[1].start - clip_start           # the hook holds until line two
        for index, word in enumerate(chunk.words):
            w_start = max(start, word.start - clip_start)
            # Hold each word until the next one takes over, so the group stays on
            # screen instead of blinking off in the gaps between words.
            if index + 1 < len(chunk.words):
                hand_over = chunk.words[index + 1].start - clip_start
            else:
                hand_over = chunk_end
            w_end = max(w_start + MIN_EVENT, hand_over)
            parts = []
            for other in chunk.words:
                text = escape_ass(other.text.upper() if campaign.uppercase else other.text)
                parts.append(
                    f"{{\\c{accent}}}{text}{{\\c&H00FFFFFF&}}" if other.i == word.i else text
                )
            body = " ".join(parts)
            if word.i == chunk.words[0].i:
                pop = (f"\\fscx{size + 8}\\fscy{size + 8}"
                       f"\\t(0,80,\\fscx{size}\\fscy{size})")
            else:
                pop = f"\\fscx{size}\\fscy{size}" if size != 100 else ""
            lines.append(
                f"Dialogue: 0,{_ass_time(w_start)},{_ass_time(w_end)},Caption,,0,0,0,,"
                f"{{\\pos({W // 2},{caption_y}){pop}}}{body}"
            )

    return header + "\n".join(lines) + "\n"


def write_ass(
    path: Path,
    chunks: list[Chunk],
    campaign: Campaign,
    layout: str,
    clip_start: float,
    headline: str | None,
    credit: str | None,
    duration: float | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(chunks, campaign, layout, clip_start, headline, credit, duration))
    return path
