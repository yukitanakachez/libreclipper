"""Step 2: transcribe the proxy locally, with per-word timings.

Two backends produce the same shape:

- mlx:            Apple Silicon (this Mac), via mlx-whisper.
- faster_whisper: Windows/Linux with an NVIDIA GPU (uv sync --extra pc).

Everything downstream reads transcript.json, so the backend is invisible past
this module.
"""

from __future__ import annotations

from pathlib import Path

from clipper import jobs
from clipper.campaigns import Campaign
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Meta, Segment, Transcript, Word

MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_WHISPER_MODEL = "large-v3"
PROMPT_LIMIT = 900


def build_initial_prompt(meta: Meta, campaign: Campaign) -> str:
    """Spelling hints for names Whisper would otherwise mangle."""
    parts = []
    if campaign.vocabulary:
        parts.append("Names and terms: " + ", ".join(campaign.vocabulary) + ".")
    if meta.title:
        parts.append(f"Episode: {meta.title}.")
    if meta.description:
        parts.append(meta.description)
    return " ".join(parts)[:PROMPT_LIMIT]


def parse_whisper_result(result: dict, duration: float) -> Transcript:
    words: list[Word] = []
    segments: list[Segment] = []
    for seg in result.get("segments", []):
        first = len(words)
        for raw in seg.get("words", []):
            if raw.get("start") is None or raw.get("end") is None:
                continue
            text = str(raw.get("word", "")).strip()
            if not text:
                continue
            words.append(Word(
                i=len(words),
                text=text,
                start=float(raw["start"]),
                end=float(raw["end"]),
                prob=float(raw.get("probability", 1.0)),
            ))
        if len(words) > first:
            segments.append(Segment(
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=str(seg.get("text", "")).strip(),
                first_word=first,
                last_word=len(words) - 1,
            ))
    return Transcript(words=words, segments=segments, duration=duration)


def normalize_faster_whisper(segments) -> dict:
    """faster-whisper yields objects; convert them to the mlx-whisper dict shape."""
    return {"segments": [
        {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": [
                {"word": w.word, "start": w.start, "end": w.end,
                 "probability": getattr(w, "probability", 1.0)}
                for w in (seg.words or [])
            ],
        }
        for seg in segments
    ]}


def _run_mlx(proxy: Path, prompt: str) -> dict:
    import mlx_whisper

    return mlx_whisper.transcribe(
        str(proxy),
        path_or_hf_repo=MLX_MODEL,
        language="en",
        word_timestamps=True,
        initial_prompt=prompt,
    )


def _run_faster_whisper(proxy: Path, prompt: str) -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(FASTER_WHISPER_MODEL, device="auto", compute_type="auto")
    segments, _info = model.transcribe(
        str(proxy), language="en", word_timestamps=True, initial_prompt=prompt
    )
    return normalize_faster_whisper(segments)


def transcribe(
    proxy: Path, meta: Meta, campaign: Campaign, paths: JobPaths, cfg: AppConfig
) -> Transcript:
    prompt = build_initial_prompt(meta, campaign)
    runner = _run_faster_whisper if cfg.whisper_backend == "faster_whisper" else _run_mlx
    result = runner(proxy, prompt)
    transcript = parse_whisper_result(result, duration=meta.duration)
    jobs.write_json(paths.transcript, transcript.to_dict())
    return transcript
