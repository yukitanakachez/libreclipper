import json
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

from clipper import providers
from clipper.config import AppConfig
from clipper.web.app import create_app
from clipper.web.worker import Worker

SCHEMA = {"type": "object", "properties": {"candidates": {"type": "array"}}}
KEY_VARS = [name for p in providers.PROVIDERS.values() for name in p.env]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Each test gets its own settings.json, no keys from the developer's shell, and no
    `ant auth login` on the machine."""
    monkeypatch.setenv("CLIPPER_HOME", str(tmp_path))
    for name in KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(providers, "_signed_in_to_anthropic", lambda: False)
    return tmp_path


def _http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_nothing_chosen_means_anthropic_and_not_ready():
    d = providers.describe()
    assert d["provider"] is None and d["using"] == "anthropic" and d["ready"] is False
    assert [p["id"] for p in d["providers"]][:3] == ["anthropic", "openai", "gemini"]
    assert "API key" in providers.setup_problem(AppConfig())


def test_a_key_in_the_shell_is_enough_for_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-0123456789abcd")
    row = providers.describe()["providers"][0]
    assert (row["has_key"], row["key_source"], row["key_hint"]) == (True, "ANTHROPIC_API_KEY", "abcd")
    assert providers.setup_problem(AppConfig()) is None


def test_choosing_saves_one_provider_and_keeps_the_others_keys(home):
    providers.choose("openai", "sk-openai-0123456789", "gpt-x")
    providers.choose("gemini", "g-key-0123456789ab", "gemini-x")
    saved = json.loads((home / "settings.json").read_text())
    assert saved["provider"] == "gemini"                      # only ever one in use
    assert saved["providers"]["openai"] == {"api_key": "sk-openai-0123456789", "model": "gpt-x"}
    assert stat.S_IMODE((home / "settings.json").stat().st_mode) == 0o600
    providers.choose("openai")                                # switching back needs no retyping
    d = providers.describe()
    assert d["using"] == "openai" and d["ready"] is True
    assert "sk-openai" not in json.dumps(d), "keys never leave the server"
    providers.choose("openai", "")                            # "" forgets the key
    assert providers.describe()["ready"] is False
    with pytest.raises(providers.ProviderError):
        providers.choose("skynet")


def test_another_provider_needs_a_model_too():
    providers.choose("openai", "sk-openai-0123456789")
    assert "model" in providers.setup_problem(AppConfig())
    providers.choose("openai", model="gpt-x")
    assert providers.setup_problem(AppConfig()) is None


def test_ollama_needs_no_key():
    providers.choose("ollama", model="llama")
    assert providers.describe()["ready"] is True and providers.setup_problem(AppConfig()) is None


def test_list_models_checks_the_key_the_way_each_provider_expects():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "b"}, {"id": "models/a"}]})
    assert providers.list_models("anthropic", "sk-ant", _http(handler)) == ["a", "b"]
    assert seen[0].headers["x-api-key"] == "sk-ant" and "anthropic-version" in seen[0].headers
    assert str(seen[0].url).startswith("https://api.anthropic.com/v1/models")
    providers.list_models("gemini", "g-key", _http(handler))
    assert seen[1].headers["authorization"] == "Bearer g-key"
    assert str(seen[1].url) == "https://generativelanguage.googleapis.com/v1beta/openai/models"


def test_list_models_says_plainly_when_the_key_is_wrong_or_missing():
    bad = _http(lambda r: httpx.Response(401, json={"error": {"message": "Incorrect API key"}}))
    with pytest.raises(providers.ProviderError, match="didn't accept that API key"):
        providers.list_models("openai", "nope", bad)
    with pytest.raises(providers.ProviderError, match="Enter your OpenAI API key"):
        providers.list_models("openai", "", bad)
    def down(request):
        raise httpx.ConnectError("refused")
    with pytest.raises(providers.ProviderError, match="Couldn't reach Ollama"):
        providers.list_models("ollama", None, _http(down))


def _answer(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_an_openai_style_provider_is_asked_for_the_schema():
    providers.choose("openai", "sk-openai-0123456789", "gpt-x")
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return _answer('{"candidates": []}')
    answer, model = providers.complete_json("sys", "user", SCHEMA, AppConfig(), http=_http(handler))
    assert answer == {"candidates": []} and model == "openai/gpt-x"
    (body,) = seen
    assert body["model"] == "gpt-x" and body["response_format"]["type"] == "json_schema"
    assert body["messages"][0]["content"].startswith("sys") and "JSON Schema" in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "user"}


def test_a_provider_without_structured_output_is_asked_more_simply():
    providers.choose("deepseek", "sk-deepseek-0123456789", "chat")
    formats = []
    def handler(request):
        fmt = json.loads(request.content).get("response_format")
        formats.append(fmt and fmt["type"])
        if fmt and fmt["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "json_schema is not supported"}})
        return _answer('```json\n{"candidates": [1]}\n```')
    answer, _ = providers.complete_json("sys", "user", SCHEMA, AppConfig(), http=_http(handler))
    assert answer == {"candidates": [1]} and formats == ["json_schema", "json_object"]


def test_provider_failures_become_readable_errors():
    providers.choose("openai", "sk-openai-0123456789", "gpt-x")
    cfg = AppConfig()
    with pytest.raises(providers.ProviderError, match="answered 429: slow down"):
        providers.complete_json("s", "u", SCHEMA, cfg, http=_http(
            lambda r: httpx.Response(429, json={"error": {"message": "slow down"}})))
    with pytest.raises(providers.ProviderError, match="No JSON"):
        providers.complete_json("s", "u", SCHEMA, cfg, http=_http(lambda r: _answer("Sorry, no.")))
    providers.choose("openai", "")
    with pytest.raises(providers.ProviderError, match="Add one in Settings"):
        providers.complete_json("s", "u", SCHEMA, cfg, http=_http(lambda r: _answer("{}")))


@pytest.fixture
def client(home):
    cfg = AppConfig(jobs_dir=home / "jobs")
    worker = Worker(cfg.jobs_dir / "queue.json", runners={})
    return TestClient(create_app(cfg, worker), base_url="http://127.0.0.1:8765")


def test_the_settings_api_chooses_a_provider_without_echoing_the_key(client, monkeypatch):
    assert client.get("/api/settings").json()["ready"] is False
    r = client.put("/api/settings", json={"provider": "openai", "api_key": "sk-openai-0123456789",
                                          "model": "gpt-x"})
    assert r.status_code == 200 and r.json()["using"] == "openai" and r.json()["ready"] is True
    assert "sk-openai" not in r.text
    row = next(p for p in client.get("/api/settings").json()["providers"] if p["id"] == "openai")
    assert (row["has_key"], row["key_hint"], row["key_source"], row["model"]) == (True, "6789", "saved", "gpt-x")
    assert client.put("/api/settings", json={"provider": "skynet"}).status_code == 400
    monkeypatch.setattr(providers, "list_models", lambda provider, key=None: ["m1", "m2"])
    assert client.post("/api/settings/models", json={"provider": "openai"}).json() == {"models": ["m1", "m2"]}
    def refuse(provider, key=None):
        raise providers.ProviderError("OpenAI didn't accept that API key.")
    monkeypatch.setattr(providers, "list_models", refuse)
    r = client.post("/api/settings/models", json={"provider": "openai", "api_key": "x"})
    assert r.status_code == 400 and "didn't accept" in r.json()["detail"]


def test_setup_checks_list_the_install_but_not_the_provider(client):
    rows = client.get("/api/setup/checks").json()
    assert rows and all(set(row) == {"name", "ok", "fix"} for row in rows)
    assert not any(row["name"].startswith("AI provider") for row in rows)
