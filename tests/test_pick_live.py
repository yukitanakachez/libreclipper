"""Opt-in test that calls the real Claude API.

Run with: .venv/bin/python -m pytest -m live       (costs a few cents, needs credentials)

This is the only test that exercises the real request shape: the model id,
structured outputs, and the refusal-fallback parameters. Everything else mocks
the client, so if the SDK ever rejects one of those arguments, this is the test
that catches it.
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.live


def test_live_pick_returns_candidates(tmp_path):
    from clipper import jobs, pick
    from clipper.campaigns import Campaign
    from clipper.config import AppConfig
    from clipper.models import Meta, Transcript

    data = json.loads(Path("tests/fixtures/transcript_short.json").read_text())
    transcript = Transcript.from_dict(data)
    cfg = AppConfig(jobs_dir=tmp_path)
    meta = Meta(job_id="j", source_kind="youtube", source="u", title="Side projects",
                description="", channel="Example Podcast", duration=transcript.duration,
                width=1280, height=720, fps=30.0, max_height=1080)
    campaign = Campaign(name="P", slug="p", min_len=15, max_len=60)

    out = pick.pick(transcript, meta, campaign, cfg, jobs.paths_for("j", cfg))

    assert out, "expected at least one candidate from a transcript with clear moments"
    assert all(c.end > c.start for c in out)
    assert all(15 <= c.end - c.start <= 61 for c in out)
    assert all(c.headline and c.post_caption for c in out)
