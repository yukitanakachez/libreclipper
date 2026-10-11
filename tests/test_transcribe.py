from types import SimpleNamespace

from clipper import jobs, transcribe
from clipper.campaigns import Campaign
from clipper.config import AppConfig
from clipper.models import Meta

CAMPAIGN = Campaign(name="Pod", slug="pod", min_len=20, max_len=60,
                    vocabulary=["Jane Doe", "Acme"])
META = Meta(job_id="j", source_kind="local", source="u", title="Ep 12 with Jane Doe",
            description="d" * 5000, channel="Pod", duration=100.0,
            width=1280, height=720, fps=30.0, max_height=2160)

WHISPER = {"segments": [
    {"start": 0.0, "end": 1.4, "text": " Hello there.",
     "words": [{"word": " Hello", "start": 0.0, "end": 0.5, "probability": 0.99},
               {"word": " there.", "start": 0.6, "end": 1.4, "probability": 0.95}]},
    {"start": 2.0, "end": 2.6, "text": " Welcome.",
     "words": [{"word": " Welcome.", "start": 2.0, "end": 2.6, "probability": 0.9}]}]}


def test_initial_prompt_includes_vocabulary_and_title_and_is_bounded():
    prompt = transcribe.build_initial_prompt(META, CAMPAIGN)
    assert "Jane Doe" in prompt and "Acme" in prompt
    assert "Ep 12 with Jane Doe" in prompt
    assert len(prompt) <= 900


def test_parse_assigns_stable_word_indices_and_strips_spaces():
    t = transcribe.parse_whisper_result(WHISPER, duration=100.0)
    assert [w.text for w in t.words] == ["Hello", "there.", "Welcome."]
    assert [w.i for w in t.words] == [0, 1, 2]
    assert t.duration == 100.0


def test_parse_links_segments_to_word_ranges():
    t = transcribe.parse_whisper_result(WHISPER, duration=100.0)
    assert (t.segments[0].first_word, t.segments[0].last_word) == (0, 1)
    assert (t.segments[1].first_word, t.segments[1].last_word) == (2, 2)


def test_parse_drops_words_with_no_timing():
    broken = {"segments": [{"start": 0.0, "end": 1.0, "text": " a b",
              "words": [{"word": " a", "start": 0.0, "end": 0.3, "probability": 0.9},
                        {"word": " b", "probability": 0.5}]}]}
    t = transcribe.parse_whisper_result(broken, duration=10.0)
    assert [w.text for w in t.words] == ["a"]


def test_parse_skips_segments_with_no_usable_words():
    empty = {"segments": [{"start": 0.0, "end": 1.0, "text": " ", "words": []}]}
    t = transcribe.parse_whisper_result(empty, duration=10.0)
    assert t.words == [] and t.segments == []


def test_transcribe_dispatches_to_the_configured_backend(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(transcribe, "_run_mlx", lambda *a, **k: called.append("mlx") or WHISPER)
    monkeypatch.setattr(transcribe, "_run_faster_whisper",
                        lambda *a, **k: called.append("fw") or WHISPER)
    cfg = AppConfig(jobs_dir=tmp_path, whisper_backend="faster_whisper")
    paths = jobs.paths_for("j", cfg)
    t = transcribe.transcribe(tmp_path / "proxy.mp4", META, CAMPAIGN, paths, cfg)
    assert called == ["fw"]
    assert len(t.words) == 3
    assert paths.transcript.exists()


def test_transcribe_defaults_to_mlx_backend(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(transcribe, "_run_mlx", lambda *a, **k: called.append("mlx") or WHISPER)
    monkeypatch.setattr(transcribe, "_run_faster_whisper",
                        lambda *a, **k: called.append("fw") or WHISPER)
    cfg = AppConfig(jobs_dir=tmp_path)
    transcribe.transcribe(tmp_path / "proxy.mp4", META, CAMPAIGN,
                          jobs.paths_for("j", cfg), cfg)
    assert called == ["mlx"]


def test_faster_whisper_objects_normalize_to_the_shared_shape():
    word = SimpleNamespace(word=" Hi", start=0.0, end=0.4, probability=0.8)
    segment = SimpleNamespace(start=0.0, end=0.4, text=" Hi", words=[word])
    result = transcribe.normalize_faster_whisper([segment])
    t = transcribe.parse_whisper_result(result, duration=5.0)
    assert [w.text for w in t.words] == ["Hi"]
    assert t.words[0].prob == 0.8
