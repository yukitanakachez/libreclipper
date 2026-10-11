"""The Settings page: which AI provider picks the moments, its key and model, and whether the
rest of the install is complete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clipper import doctor, providers

router = APIRouter(prefix="/api")


class Choice(BaseModel):
    provider: str
    api_key: str | None = None        # None keeps the saved key; "" forgets it
    model: str | None = None


class KeyCheck(BaseModel):
    provider: str
    api_key: str | None = None        # None or "": check the key already saved or in the shell


@router.get("/settings")
def get_settings():
    return providers.describe()


@router.put("/settings")
def put_settings(body: Choice):
    try:
        return providers.describe(providers.choose(body.provider, body.api_key, body.model))
    except providers.ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/settings/models")
def models(body: KeyCheck):
    """The models a key can use. Asking is also how the page checks a key before saving it."""
    try:
        return {"models": providers.list_models(body.provider, body.api_key)}
    except providers.ProviderError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/setup/checks")
def checks():
    """Everything `clipper doctor` checks except the AI provider, which the page shows itself."""
    return [{"name": name, "ok": ok, "fix": fix} for name, ok, fix in doctor.check_all()
            if not name.startswith("AI provider")]
