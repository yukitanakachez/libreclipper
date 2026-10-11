import json

import pytest

from clipper import jobs, pick
from clipper.campaigns import Campaign
from clipper.config import AppConfig
from clipper.models import Meta, Segment, Transcript, Word

CAMPAIGN = Campaign(name="P", slug="p", min_len=20, max_len=60)
META = Meta(job_id="j", source_kind="local", source="u", title="T", description="",
            channel="C", duration=120.0, width=1280, height=720, fps=30.0, max_height=2160)


def transcript() -> Transcript:
    words = [Word(i, f"w{i}", i * 0.5, i * 0.5 + 0.4, 0.9) for i in range(240)]
    segments = [Segment(words[s].start, words[s + 9].end,
                        " ".join(f"w{j}" for j in range(s, s + 10)), s, s + 9)
                for s in range(0, 240, 10)]
    return Transcript(words, segments, 120.0)


def test_render_transcript_has_timestamps_per_segment():
    text = pick.render_transcript(transcript())
    assert text.splitlines()[0].startswith("[00:00.0]")
    assert "w0 w1" in text


class FakeClient:
    def __init__(self, payload, stop_reason="end_turn"):
        self.payload, self.stop_reason, self.kwargs = payload, stop_reason, None
        self.messages = self
        self.beta = self          # pick() calls client.beta.messages.create

    def create(self, **kwargs):
        self.kwargs = kwargs
        payload = self.payload

        class Block:
            type = "text"
            text = json.dumps(payload)

        class Resp:
            pass

        r = Resp()
        r.content = [Block()]
        r.stop_reason = self.stop_reason
        return r


def payload(n=2):
    return {"candidates": [
        {"start": 10.0 + i * 30, "end": 40.0 + i * 30, "headline": f"h{i}", "hook": "k",
         "reason": "r", "score": 9 - i, "post_caption": "c", "hashtags": ["#a"]}
        for i in range(n)]}


def test_pick_returns_validated_candidates(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    out = pick.pick(transcript(), META, CAMPAIGN, cfg, paths, client=FakeClient(payload()))
    assert [c.n for c in out] == [1, 2]
    assert jobs.read_json(paths.candidates)["campaign"] == "p"


def test_pick_uses_configured_model_and_schema(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path, model="claude-sonnet-5")
    paths = jobs.paths_for("j", cfg)
    client = FakeClient(payload())
    pick.pick(transcript(), META, CAMPAIGN, cfg, paths, client=client)
    assert client.kwargs["model"] == "claude-sonnet-5"
    assert client.kwargs["output_config"]["format"]["schema"] == pick.CANDIDATE_SCHEMA


def test_pick_raises_on_refusal(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    with pytest.raises(pick.PickError, match="refus"):
        pick.pick(transcript(), META, CAMPAIGN, cfg, paths,
                  client=FakeClient(payload(), stop_reason="refusal"))


def test_pick_writes_empty_list_when_nothing_survives(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    bad = {"candidates": [{"start": 10.0, "end": 12.0, "headline": "h", "hook": "k",
                           "reason": "r", "score": 9, "post_caption": "c", "hashtags": []}]}
    out = pick.pick(transcript(), META, CAMPAIGN, cfg, paths, client=FakeClient(bad))
    assert out == []
    assert jobs.read_json(paths.candidates)["candidates"] == []


class StrictClient:
    """Mirrors the real SDK: messages.create rejects betas/fallbacks, beta.messages accepts them."""

    def __init__(self, payload):
        self.payload = payload
        self.used_beta = False
        outer = self

        class Messages:
            def create(self, **kwargs):
                if "betas" in kwargs or "fallbacks" in kwargs:
                    raise TypeError(
                        "Messages.create() got an unexpected keyword argument 'betas'")
                return outer._response()

        class BetaMessages:
            def create(self, **kwargs):
                outer.used_beta = True
                outer.kwargs = kwargs
                return outer._response()

        class Beta:
            messages = BetaMessages()

        self.messages = Messages()
        self.beta = Beta()

    def _response(self):
        payload = self.payload

        class Block:
            type = "text"
            text = json.dumps(payload)

        class Resp:
            pass

        r = Resp()
        r.content = [Block()]
        r.stop_reason = "end_turn"
        return r


def test_pick_uses_the_beta_namespace_so_fallbacks_are_accepted(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    client = StrictClient(payload())
    out = pick.pick(transcript(), META, CAMPAIGN, cfg, paths, client=client)
    assert client.used_beta, "must call client.beta.messages.create, not client.messages.create"
    assert client.kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert client.kwargs["fallbacks"] == "default"
    assert len(out) == 2


def test_schema_uses_only_keywords_the_api_accepts():
    """Structured outputs take a small subset of JSON Schema.

    Two 400s in a row (maxItems on arrays, then minimum/maximum on integers)
    say an allowlist is the only safe rule here. Constraints the API will not
    take are enforced in code instead.
    """
    allowed = {"type", "properties", "required", "additionalProperties", "items",
               "description"}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("properties",):
                    for sub in value.values():
                        walk(sub)
                    continue
                assert key in allowed, f"schema uses unsupported keyword {key!r}"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(pick.CANDIDATE_SCHEMA)


def test_pick_keeps_at_most_six_candidates(tmp_path):
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    many = {"candidates": [
        {"start": 5.0 + i * 20, "end": 30.0 + i * 20, "headline": f"h{i}", "hook": "k",
         "reason": "r", "score": 9, "post_caption": "c", "hashtags": []}
        for i in range(9)]}
    out = pick.pick(transcript(), META, CAMPAIGN, cfg, paths, client=FakeClient(many))
    assert len(out) <= 6
    assert [c.n for c in out] == list(range(1, len(out) + 1))


def test_system_prompt_asks_for_cold_opens_and_finished_endings():
    prompt = pick.SYSTEM_PROMPT.lower()
    assert "first words" in prompt, "the hook must be the clip's first words"
    assert "finished sentence" in prompt, "clips must end on a finished sentence"
    assert "slightly wide" not in prompt, "wide ranges produced run-on endings"


def test_user_message_gives_length_in_original_seconds():
    from clipper.pacing import Pacing
    campaign = Campaign(name="P", slug="p", min_len=20, max_len=40,
                        pacing=Pacing(cut_pauses=True, max_pause=0.3, speed=1.1))
    message = pick._user_message(transcript(), META, campaign)
    assert "22 and 44 seconds of the original" in message


def test_pick_uses_the_provider_chosen_in_settings(tmp_path, monkeypatch):
    import httpx

    from clipper import providers
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    providers.choose("openai", "sk-openai-0123456789", "gpt-x")
    answer = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload())}}]})
    http = httpx.Client(transport=httpx.MockTransport(lambda request: answer))
    monkeypatch.setattr(providers, "_http", lambda given=None: http)
    cfg = AppConfig(jobs_dir=tmp_path)
    paths = jobs.paths_for("j", cfg)
    got = pick.pick(transcript(), META, CAMPAIGN, cfg, paths)
    assert len(got) == 2
    assert jobs.read_json(paths.candidates)["model"] == "openai/gpt-x"


def test_pick_without_a_key_says_where_to_add_one(tmp_path, monkeypatch):
    from clipper import providers
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(providers, "_signed_in_to_anthropic", lambda: False)
    cfg = AppConfig(jobs_dir=tmp_path)
    with pytest.raises(pick.PickError, match="Settings"):
        pick.pick(transcript(), META, CAMPAIGN, cfg, jobs.paths_for("j", cfg))
