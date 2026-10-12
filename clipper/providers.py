"""Which AI picks the moments: the providers Clipper can talk to, and your choice of one.

Your choice and keys live in settings.json next to config.yaml (written by the app's Settings
page, readable only by you). A key in your shell (ANTHROPIC_API_KEY, OPENAI_API_KEY, …) works
too, so nothing has to be typed into the app. Anthropic goes through its own SDK; every other
provider speaks the OpenAI chat-completions dialect, which is what makes adding one a few lines.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from clipper import jobs, locks, shell
from clipper.config import AppConfig

ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT = 600.0          # one long transcript in, a few clips out: slow models take minutes


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str                    # for "openai"-style providers: the folder /chat/completions is in
    env: tuple[str, ...] = ()        # shell variables that may hold the key
    key_url: str = ""                # where to make a key
    needs_key: bool = True
    style: str = "openai"            # "anthropic" | "openai"


PROVIDERS: dict[str, Provider] = {p.id: p for p in (
    Provider("anthropic", "Anthropic", "https://api.anthropic.com/v1", ("ANTHROPIC_API_KEY",),
             "https://console.anthropic.com/settings/keys", style="anthropic"),
    Provider("openai", "OpenAI", "https://api.openai.com/v1", ("OPENAI_API_KEY",),
             "https://platform.openai.com/api-keys"),
    Provider("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
             ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "https://aistudio.google.com/apikey"),
    Provider("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",),
             "https://openrouter.ai/keys"),
    Provider("mistral", "Mistral", "https://api.mistral.ai/v1", ("MISTRAL_API_KEY",),
             "https://console.mistral.ai/api-keys"),
    Provider("deepseek", "DeepSeek", "https://api.deepseek.com/v1", ("DEEPSEEK_API_KEY",),
             "https://platform.deepseek.com/api_keys"),
    Provider("ollama", "Ollama (on this computer)", "http://localhost:11434/v1", needs_key=False),
)}
DEFAULT = "anthropic"


# --- settings.json ----------------------------------------------------------------------------

def settings_path() -> Path:
    return shell.project_home() / "settings.json"


def load_settings() -> dict:
    """{"provider": id or None, "providers": {id: {"api_key": str, "model": str}}}; missing or
    unreadable means nothing chosen yet."""
    path = settings_path()
    try:
        raw = jobs.read_json(path) if path.exists() else {}
    except (OSError, ValueError):
        raw = {}
    chosen = raw.get("provider") if raw.get("provider") in PROVIDERS else None
    entries = raw.get("providers") if isinstance(raw.get("providers"), dict) else {}
    return {"provider": chosen,
            "providers": {pid: dict(entry) for pid, entry in entries.items()
                          if pid in PROVIDERS and isinstance(entry, dict)}}


def save_settings(settings: dict) -> None:
    path = settings_path()
    jobs.write_json(path, settings)
    try:
        os.chmod(path, 0o600)                      # it holds keys
    except OSError:
        pass


def choose(provider_id: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Make this the one provider in use. api_key None keeps the saved key, "" forgets it."""
    if provider_id not in PROVIDERS:
        raise ProviderError(f"Unknown provider {provider_id!r}.")
    with locks.WRITE_LOCK:
        settings = load_settings()
        entry = settings["providers"].setdefault(provider_id, {})
        if api_key is not None:
            entry["api_key"] = api_key.strip()
        if model is not None:
            entry["model"] = model.strip()
        settings["provider"] = provider_id
        save_settings(settings)
    return settings


def _key(provider: Provider, settings: dict) -> tuple[str, str | None]:
    """The key and where it came from ("saved", the shell variable's name, or None)."""
    saved = settings["providers"].get(provider.id, {}).get("api_key") or ""
    if saved:
        return saved, "saved"
    for name in provider.env:
        if os.environ.get(name):
            return os.environ[name], name
    return "", None


def _signed_in_to_anthropic() -> bool:
    return (Path.home() / ".config" / "anthropic").exists()        # `ant auth login`


def is_ready(provider: Provider, settings: dict) -> bool:
    if not provider.needs_key or _key(provider, settings)[0]:
        return True
    return provider.id == "anthropic" and _signed_in_to_anthropic()


def chosen_provider(settings: dict) -> Provider:
    """The provider in use. Until one is chosen that is Anthropic, as before there was a choice."""
    return PROVIDERS[settings["provider"] or DEFAULT]


def describe(settings: dict | None = None) -> dict:
    """What the Settings page shows. Keys never leave the server: only their last four characters."""
    settings = load_settings() if settings is None else settings
    current = chosen_provider(settings)
    rows = []
    for p in PROVIDERS.values():
        key, source = _key(p, settings)
        rows.append({"id": p.id, "name": p.name, "needs_key": p.needs_key, "key_url": p.key_url,
                     "has_key": bool(key), "key_hint": key[-4:] if len(key) >= 12 else "",
                     "key_source": source, "ready": is_ready(p, settings),
                     "model": settings["providers"].get(p.id, {}).get("model") or ""})
    return {"provider": settings["provider"], "using": current.id,
            "ready": is_ready(current, settings), "providers": rows}


def setup_problem(cfg: AppConfig) -> str | None:
    """Why moments can't be picked yet, or None."""
    settings = load_settings()
    provider = chosen_provider(settings)
    if not is_ready(provider, settings):
        return f"No {provider.name} API key yet. Add one in Settings."
    if provider.style != "anthropic" and not settings["providers"].get(provider.id, {}).get("model"):
        return f"No {provider.name} model chosen yet. Pick one in Settings."
    return None


# --- talking to a provider --------------------------------------------------------------------

def _http(http=None):
    if http is not None:
        return http
    import httpx
    return httpx.Client(timeout=TIMEOUT)


def _headers(provider: Provider, key: str) -> dict:
    if provider.style == "anthropic":
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    return {"Authorization": f"Bearer {key}"} if key else {}


def _explain(provider: Provider, response) -> str:
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else body
        detail = error.get("message") if isinstance(error, dict) else str(error)
    except ValueError:
        detail = response.text[:200]
    if response.status_code in (401, 403):
        return f"{provider.name} didn't accept that API key. ({detail})"
    return f"{provider.name} answered {response.status_code}: {detail}"


def list_models(provider_id: str, api_key: str | None = None, http=None) -> list[str]:
    """The model names this key can use, which also proves the key works."""
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"Unknown provider {provider_id!r}.")
    key = (api_key or "").strip() or _key(provider, load_settings())[0]
    if provider.needs_key and not key:
        raise ProviderError(f"Enter your {provider.name} API key first.")
    try:
        response = _http(http).get(f"{provider.base_url}/models", headers=_headers(provider, key),
                                   params={"limit": 1000} if provider.style == "anthropic" else None)
    except Exception as exc:
        raise ProviderError(f"Couldn't reach {provider.name}: {exc}") from exc
    if response.status_code != 200:
        raise ProviderError(_explain(provider, response))
    body = response.json()
    rows = body.get("data", body.get("models", [])) if isinstance(body, dict) else body
    names = [str(row.get("id") or row.get("name") or "").removeprefix("models/")
             for row in rows if isinstance(row, dict)]
    return sorted(name for name in names if name)


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse(text: str) -> dict:
    text = FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError("No JSON returned by the model.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError(f"The model's answer wasn't valid JSON: {exc}") from exc


# Room for Claude's thinking and its answer together. A two-hour transcript can take well over
# 16,000 tokens of thinking alone, which once left nothing for the answer.
ANTHROPIC_MAX_TOKENS = 64000


def _anthropic_json(client, model: str, system: str, user: str, schema: dict) -> dict:
    # betas/fallbacks live on the beta namespace; client.messages rejects them. Streamed: a long
    # transcript takes minutes, and the SDK refuses a budget this large on a plain request.
    with client.beta.messages.stream(
        model=model,
        max_tokens=ANTHROPIC_MAX_TOKENS,
        thinking={"type": "adaptive"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    ) as stream:
        response = stream.get_final_message()
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise ProviderError("Claude refused to process this transcript.")
    text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
    if stop == "max_tokens":              # cut off mid-thought or mid-answer: nothing usable
        raise ProviderError("Claude ran out of room before finishing its answer. Press Retry; "
                            "if it keeps happening, this video may be too long for one pass.")
    if text is None:
        raise ProviderError("No JSON returned by the model.")
    return _parse(text)


def _openai_json(provider: Provider, key: str, model: str, system: str, user: str, schema: dict,
                 http=None) -> dict:
    """Ask for the schema strictly; a model or provider that doesn't do that is asked for plain
    JSON, then for nothing special. The schema is spelled out in the prompt either way."""
    client = _http(http)
    system = (f"{system}\n\nReply with one JSON object and nothing else. It must match this "
              f"JSON Schema:\n{json.dumps(schema)}")
    body = {"model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    formats = ({"type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": schema}},
               {"type": "json_object"}, None)
    response = None
    for fmt in formats:
        try:
            response = client.post(f"{provider.base_url}/chat/completions",
                                   headers=_headers(provider, key),
                                   json=body if fmt is None else {**body, "response_format": fmt})
        except Exception as exc:
            raise ProviderError(f"Couldn't reach {provider.name}: {exc}") from exc
        if response.status_code not in (400, 422):       # those: this format isn't supported
            break
    if response.status_code != 200:
        raise ProviderError(_explain(provider, response))
    try:
        message = response.json()["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected answer from {provider.name}.") from exc
    if message.get("refusal"):
        raise ProviderError(f"{provider.name} refused to process this transcript.")
    return _parse(message.get("content") or "")


def complete_json(system: str, user: str, schema: dict, cfg: AppConfig, client=None,
                  http=None) -> tuple[dict, str]:
    """One question to the chosen provider, answered as JSON matching `schema`. Returns the
    answer and the model that gave it. `client` is an Anthropic client (tests pass a fake)."""
    if client is not None:
        return _anthropic_json(client, cfg.model, system, user, schema), cfg.model
    problem = setup_problem(cfg)
    if problem:
        raise ProviderError(problem)
    settings = load_settings()
    provider = chosen_provider(settings)
    key = _key(provider, settings)[0]
    model = settings["providers"].get(provider.id, {}).get("model") or cfg.model
    if provider.style == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        return _anthropic_json(client, model, system, user, schema), model
    return _openai_json(provider, key, model, system, user, schema, http), f"{provider.id}/{model}"
