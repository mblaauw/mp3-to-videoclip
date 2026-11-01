"""What can be chosen: providers, models and voices, with what is known about each.

The static ``catalog.toml`` is the truth for prices. A refresh runs only on the
owner's click, uses free calls only, and adds what a provider lists in a cache file
beside it; a listed entry never overwrites a static price.
"""

from __future__ import annotations

import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .providers import ProviderError, RunwareClient
from .storage import write_json

STATIC = Path(__file__).with_name("catalog.toml")
CACHE_ENV = "MP3_TO_VIDEOCLIP_CATALOG_CACHE"
OPENCODE_GO_URL = "https://opencode.ai/inference/go/openai/v1"
ANTHROPIC_URL = "https://api.anthropic.com/v1/models"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
ELEVENLABS_URL = "https://api.elevenlabs.io"
_TIMEOUT = 15.0

Capability = Literal["text", "vision", "image", "video", "speech", "music", "upscale"]
ProviderKind = Literal["openai-compatible", "anthropic", "gemini", "opencode-go", "runware", "elevenlabs"]  # fmt: skip


class Provider(BaseModel):
    id: str
    label: str
    kind: ProviderKind
    key_setting: str
    env_var: str = ""
    lists_models: bool = False
    only_with_key: bool = False
    unlocks: list[str] = []


class Price(BaseModel):
    amount: str
    unit: Literal["1k_tokens_in", "1k_tokens_out", "image", "second", "1k_chars"]


class Model(BaseModel):
    id: str
    provider: str
    label: str = ""
    capabilities: list[Capability] = []
    price: Price | None = None
    price_note: str = ""
    price_source: str = ""
    price_checked: str = ""
    context: int | None = None
    max_output: int | None = None
    recommended: list[str] = []
    source: Literal["static", "listed"] = "static"
    status: str = ""
    published_price: str = ""


class Voice(BaseModel):
    id: str
    provider: str
    model: str = ""
    label: str = ""
    language: str = ""
    preview_url: str = ""
    recommended: bool = False
    source: Literal["static", "listed"] = "static"


class Catalog(BaseModel):
    providers: list[Provider] = []
    models: list[Model] = []
    voices: list[Voice] = []

    def provider(self, provider_id: str) -> Provider:
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        raise ValueError(f"unknown provider {provider_id}")


def cache_dir() -> Path:
    override = os.environ.get(CACHE_ENV)
    return Path(override) if override else Path.home() / ".cache/mp3-to-videoclip/catalog"


def _read_cache(name: str) -> dict:
    """A damaged cache only loses what a refresh added; the static file still loads."""
    try:
        value = json.loads((cache_dir() / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _static() -> Catalog:
    with STATIC.open("rb") as handle:
        return Catalog.model_validate(tomllib.load(handle))


def load() -> Catalog:
    """The static file plus whatever the last refresh of each provider listed."""
    catalog = _static()
    known = {(model.provider, model.id): model for model in catalog.models}
    voices = {(voice.provider, voice.id) for voice in catalog.voices}
    for provider in catalog.providers:
        for entry in _cached(provider.id, "models"):
            mine = known.get((provider.id, entry.get("id")))
            if mine is not None:
                mine.status = str(entry.get("status") or "")
                mine.published_price = str(entry.get("published_price") or "")
                continue
            try:
                model = Model.model_validate({**entry, "provider": provider.id, "source": "listed"})
            except ValidationError:
                continue
            # A list is not a price list: only the static file may state a price.
            model.price = None
            catalog.models.append(model)
            known[(provider.id, model.id)] = model
        for entry in _cached(provider.id, "voices"):
            if (provider.id, entry.get("id")) in voices:
                continue
            try:
                voice = Voice.model_validate({**entry, "provider": provider.id, "source": "listed"})
            except ValidationError:
                continue
            catalog.voices.append(voice)
            voices.add((provider.id, voice.id))
    return catalog


def provider_key(settings: Settings, provider: Provider) -> str:
    value = settings
    for part in provider.key_setting.split("."):
        value = getattr(value, part)
    return value


def _get_json(client: httpx.Client, url: str, **kwargs) -> dict:
    """One free GET. A failure carries a public code and never the request or the key."""
    try:
        response = client.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise ProviderError("network_error") from exc
    if response.status_code in (401, 403):
        raise ProviderError("invalidApiKey", status=response.status_code)
    if response.status_code >= 400:
        raise ProviderError("http_error", status=response.status_code)
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError("invalid_response") from exc
    if not isinstance(data, dict):
        raise ProviderError("invalid_response")
    return data


def _require_key(settings: Settings, provider: Provider) -> str:
    key = provider_key(settings, provider)
    if not key:
        raise ProviderError("no_key")
    return key


def _text_models(ids: list) -> list[dict]:
    return [
        {"id": item, "label": item, "capabilities": ["text"]}
        for item in ids
        if isinstance(item, str) and item
    ]


def _bearer_models(url: str, key: str, client: httpx.Client) -> list[dict]:
    data = _get_json(
        client, f"{url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}
    )
    return _text_models([item.get("id") for item in data.get("data", []) if isinstance(item, dict)])


def _anthropic_models(key: str, client: httpx.Client) -> list[dict]:
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    data = _get_json(client, ANTHROPIC_URL, headers=headers)
    return _text_models([item.get("id") for item in data.get("data", []) if isinstance(item, dict)])


def _gemini_models(key: str, client: httpx.Client) -> list[dict]:
    data = _get_json(client, GEMINI_URL, headers={"x-goog-api-key": key})
    names = [item.get("name", "") for item in data.get("models", []) if isinstance(item, dict)]
    return _text_models([name.removeprefix("models/") for name in names])


def _published_price(info: dict) -> str:
    rates = (info.get("x-pricing") or {}).get("rates") or []
    return "; ".join(str(rate["display"]) for rate in rates if rate.get("display"))


def _runware_models(catalog: Catalog, client: httpx.Client) -> list[dict]:
    """Re-read the public schema of each known model: free, and it needs no key.

    Runware's model search is not used, because its documentation does not say
    that a search is free.
    """
    runware = RunwareClient("public-schema-only", client=client)
    found = []
    for model in catalog.models:
        if model.provider == "runware" and model.source == "static":
            info = runware.schema(model.id).get("info") or {}
            found.append(
                {
                    "id": model.id,
                    "status": str(info.get("x-status") or ""),
                    "published_price": _published_price(info),
                }
            )
    return found


def _elevenlabs_voices(key: str, client: httpx.Client) -> list[dict]:
    data = _get_json(client, f"{ELEVENLABS_URL}/v2/voices", headers={"xi-api-key": key})
    return [
        {
            "id": item["voice_id"],
            "label": str(item.get("name") or item["voice_id"]),
            "preview_url": str(item.get("preview_url") or ""),
        }
        for item in data.get("voices", [])
        if isinstance(item, dict) and item.get("voice_id")
    ]


def _listing(
    catalog: Catalog, provider: Provider, settings: Settings, client: httpx.Client
) -> dict:
    if provider.kind == "runware":
        return {"models": _runware_models(catalog, client)}
    key = _require_key(settings, provider)
    if provider.kind == "openai-compatible":
        url = settings.keys.openai_compatible.base_url
        return {"models": _bearer_models(url, key, client)}
    if provider.kind == "opencode-go":
        return {"models": _bearer_models(OPENCODE_GO_URL, key, client)}
    if provider.kind == "anthropic":
        return {"models": _anthropic_models(key, client)}
    if provider.kind == "gemini":
        return {"models": _gemini_models(key, client)}
    return {"voices": _elevenlabs_voices(key, client)}


def refresh(provider_id: str, settings: Settings, client: httpx.Client | None = None) -> dict:
    """List one provider into its cache file and report what is new. Costs nothing."""
    catalog = _static()
    provider = catalog.provider(provider_id)
    before = {entry.get("id") for field in ("models", "voices") for entry in _cached(provider.id, field)}  # fmt: skip
    own = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        listing = _listing(catalog, provider, settings, client)
    finally:
        if own:
            client.close()
    fetched_at = datetime.now(UTC).isoformat()
    write_json(
        _ensure_cache_dir() / f"{provider.id}.json",
        {**listing, "fetched_at": fetched_at, "tested": _read_cache(provider.id).get("tested")},
    )
    listed = [entry["id"] for field in ("models", "voices") for entry in listing.get(field, [])]
    static = {model.id for model in catalog.models} | {voice.id for voice in catalog.voices}
    return {
        "provider": provider.id,
        "fetched_at": fetched_at,
        "listed": len(listed),
        "added": sorted(set(listed) - before - static),
    }


def _cached(name: str, field: str) -> list[dict]:
    entries = _read_cache(name).get(field)
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []  # fmt: skip


def _ensure_cache_dir() -> Path:
    path = cache_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_provider(provider_id: str, settings: Settings, client: httpx.Client | None = None) -> dict:
    """A free call that proves a key works; the result stays beside the catalogue."""
    catalog = _static()
    provider = catalog.provider(provider_id)
    if not provider_key(settings, provider):
        return _tested(provider, False, f"Add a {provider.label} key first.")
    own = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        if provider.kind == "runware":
            ok, message = _test_runware(provider_key(settings, provider), client)
        elif provider.kind == "elevenlabs":
            _get_json(
                client,
                f"{ELEVENLABS_URL}/v1/user",
                headers={"xi-api-key": provider_key(settings, provider)},
            )
            ok, message = True, "Works"
        else:
            _listing(catalog, provider, settings, client)
            ok, message = True, "Works"
    except ProviderError as exc:
        ok, message = False, _test_failure(exc)
    finally:
        if own:
            client.close()
    return _tested(provider, ok, message)


def _test_runware(key: str, client: httpx.Client) -> tuple[bool, str]:
    from uuid import uuid4

    with RunwareClient(key, client=client) as runware:
        try:
            runware.recover(str(uuid4()))
        except ProviderError as exc:
            if exc.code not in ("taskNotFound", "invalidTaskUUID", "mismatched_task"):
                raise
    return True, "Works"


def _test_failure(exc: ProviderError) -> str:
    if exc.code == "invalidApiKey":
        return "Rejected"
    if exc.code == "network_error":
        return "Could not reach the provider. Check the network."
    return f"Could not verify the key ({exc.code})."


def _tested(provider: Provider, ok: bool, message: str) -> dict:
    at = datetime.now(UTC).isoformat()
    tested = {"ok": ok, "message": message, "at": at}
    cached = _read_cache(provider.id)
    write_json(_ensure_cache_dir() / f"{provider.id}.json", {**cached, "tested": tested})
    return {"provider": provider.id, "kind": "provider", **tested}


def public_view(settings: Settings) -> dict:
    """The catalogue with what each entry needs. Never holds a key's value."""
    catalog = load()
    providers = []
    hidden = set()
    for provider in catalog.providers:
        has_key = bool(provider_key(settings, provider))
        if provider.only_with_key and not has_key:
            hidden.add(provider.id)
            continue
        tested = _read_cache(provider.id).get("tested")
        providers.append(
            {
                **provider.model_dump(exclude={"key_setting", "env_var"}),
                "fetched_at": _read_cache(provider.id).get("fetched_at"),
                "ready": {
                    "key": has_key,
                    "reachable": tested if isinstance(tested, dict) else None,
                    "unlocks": provider.unlocks,
                },
            }
        )
    return {
        "providers": providers,
        "models": [m.model_dump() for m in catalog.models if m.provider not in hidden],
        "voices": [v.model_dump() for v in catalog.voices if v.provider not in hidden],
    }
