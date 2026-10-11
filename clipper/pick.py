"""Step 3: ask the AI you chose (Claude unless you picked another in Settings) which moments
are worth clipping.

One call per episode. The response shape is asked for as structured output, and
everything it returns is re-checked in code (selection.validate_candidates)
before it reaches the review screen.
"""

from __future__ import annotations

from pathlib import Path

from clipper import jobs, providers, selection
from clipper.campaigns import Campaign
from clipper.config import AppConfig
from clipper.jobs import JobPaths
from clipper.models import Candidate, Meta, Transcript

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "pick_system.md").read_text()


MAX_CANDIDATES = 6


class PickError(Exception):
    pass


CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            # No maxItems: the API rejects it for arrays. The cap is enforced in
            # code below and asked for in the system prompt.
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "headline": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                    "score": {"type": "integer",
                              "description": "1-10, clamped in code"},
                    "post_caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start", "end", "headline", "hook", "reason",
                             "score", "post_caption", "hashtags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


def _stamp(seconds: float) -> str:
    return f"[{int(seconds // 60):02d}:{seconds % 60:04.1f}]"


def render_transcript(transcript: Transcript) -> str:
    return "\n".join(f"{_stamp(s.start)} {s.text}" for s in transcript.segments)


def _user_message(transcript: Transcript, meta: Meta, campaign: Campaign) -> str:
    speed = campaign.pacing.speed
    return (
        f"Episode: {meta.title}\nChannel: {meta.channel}\n"
        f"Duration: {meta.duration:.0f}s\n"
        f"Clips must be between {campaign.min_len * speed:.0f} and "
        f"{campaign.max_len * speed:.0f} seconds of the original "
        f"(they are sped up {speed:g}x afterwards).\n\n"
        f"Transcript:\n{render_transcript(transcript)}"
    )


def pick(
    transcript: Transcript,
    meta: Meta,
    campaign: Campaign,
    cfg: AppConfig,
    paths: JobPaths,
    client=None,
) -> list[Candidate]:
    try:
        answer, model = providers.complete_json(
            SYSTEM_PROMPT, _user_message(transcript, meta, campaign), CANDIDATE_SCHEMA, cfg,
            client=client)
        raw = answer["candidates"]
    except providers.ProviderError as exc:
        raise PickError(str(exc)) from exc
    except (KeyError, TypeError) as exc:
        raise PickError(f"Unexpected response shape: {exc}") from exc

    candidates = selection.validate_candidates(raw, transcript, campaign)[:MAX_CANDIDATES]
    jobs.write_json(paths.candidates, {
        "model": model,
        "campaign": campaign.slug,
        "candidates": [c.to_dict() for c in candidates],
    })
    return candidates
