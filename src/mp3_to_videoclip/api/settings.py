"""Settings: read and write the user's ~/.config/mp3-to-videoclip/settings.toml."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip.config import (
    FLAT,
    FLAT_ROLES,
    Keys,
    Settings,
    effective_settings,
    merge,
    save_settings,
)
from mp3_to_videoclip.director.routing import route_for

router = APIRouter(prefix="/api/settings", tags=["settings"])

#: Every secret in the nested shape, as a path from ``keys``.
SECRETS = (
    ("runware",),
    ("openai",),
    ("openai_compatible", "key"),
    ("anthropic",),
    ("gemini",),
    ("opencode_go",),
    ("elevenlabs",),
)
#: Honest about what a stored choice does today; the panel shows these words.
NOTES = {
    "direct_path": "Your own endpoint: any address that speaks OpenAI's chat format.",
    "thinking": "Thinking level and the per-turn token budget are stored but not enforced yet.",
    "pictures": "New films still use each look's own model; these choices are stored for later.",
    "narrator": "A story film starts with this voice and can choose another on its Script stage.",
}


def _blank(value: dict, path: tuple[str, ...]) -> None:
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = ""


def _read(value: dict, path: tuple[str, ...]) -> str:
    for part in path:
        value = value[part]
    return value


def _public(settings: Settings) -> dict:
    """Never send a secret back to the browser; expose presence instead."""
    from mp3_to_videoclip import kinds, shotkinds, signature, structures, styles

    value = settings.model_dump()
    has = {}
    for path in SECRETS:
        has[f"has_{path[0]}_key"] = bool(_read(value["keys"], path))
        _blank(value["keys"], path)
    value.update(has)
    # The flat names, which the Studio's readers keep using.
    for name in (*FLAT, *FLAT_ROLES):
        if name != "default_credit_roles":
            value[name] = getattr(settings, name)
    value["llm_api_key"] = ""
    value["runware_api_key"] = ""
    value["has_llm_api_key"] = bool(settings.llm_api_key)
    # A key for whichever provider each role really uses.
    value["role_keys"] = {
        role: bool(route_for(settings, role).key) for role in ("writer", "editor", "critic")
    }
    value["has_runware_api_key"] = bool(settings.runware_api_key)
    value["notes"] = NOTES
    # What a new film of each kind starts with, so the form opens on the same answer.
    value["default_titles"] = {
        kind["id"]: signature.default_package(settings, kind["id"]) for kind in kinds.public_kinds()
    }
    value["style_presets"] = styles.public_presets()
    value["kinds"] = kinds.public_kinds()
    value["shot_kinds"] = shotkinds.public_kinds()
    value["structures"] = structures.public()
    return value


@router.get("")
async def get_settings():
    return _public(effective_settings())


def _test_runware() -> dict:
    from mp3_to_videoclip.providers import ProviderError, RunwareClient

    settings = effective_settings()
    if not settings.runware_api_key:
        return {"ok": False, "kind": "runware", "message": "Add a Runware key first."}
    try:
        with RunwareClient(settings.runware_api_key) as client:
            client.recover(str(uuid.uuid4()))
    except ProviderError as exc:
        if exc.code in ("taskNotFound", "invalidTaskUUID", "mismatched_task"):
            return {"ok": True, "kind": "runware", "message": "Works"}
        if exc.code == "invalidApiKey":
            return {"ok": False, "kind": "runware", "message": "Rejected"}
        return {
            "ok": False,
            "kind": "runware",
            "message": f"Could not verify the key ({exc.code}).",
        }
    except Exception:  # noqa: BLE001 - the settings dialog never shows a traceback
        return {
            "ok": False,
            "kind": "runware",
            "message": "Could not reach Runware. Check the network and the key.",
        }
    return {"ok": True, "kind": "runware", "message": "Works"}


def _test_provider(provider: str) -> dict:
    from mp3_to_videoclip import catalog

    return catalog.test_provider(provider, effective_settings())


def _test_voice(voice_id: str) -> dict:
    """A sample only when it is free: a provider's preview. Nothing is bought here."""
    from mp3_to_videoclip import catalog

    voice = next((item for item in catalog.load().voices if item.id == voice_id), None)
    if voice is None:
        raise ValueError(f"unknown voice {voice_id}")
    if voice.preview_url:
        return {"ok": True, "kind": "voice", "preview_url": voice.preview_url, "message": "Free"}
    return {
        "ok": False,
        "kind": "voice",
        "message": "This voice has no free sample from its provider.",
    }


@router.post("/test")
async def test_settings(payload: dict):
    kind = payload.get("kind")
    if kind == "runware":
        return await asyncio.to_thread(_test_runware)
    if kind == "provider":
        return await asyncio.to_thread(_test_provider, str(payload.get("provider")))
    if kind == "voice":
        return _test_voice(str(payload.get("voice")))
    raise HTTPException(status_code=400, detail="kind must be runware, provider or voice")


@router.get("/catalog")
async def get_catalog():
    from mp3_to_videoclip import catalog, depth, lyric_tools, setup

    view = await asyncio.to_thread(catalog.public_view, effective_settings())
    return {
        **view,
        "computer": setup.status(),
        "lyric_tools": lyric_tools.status(),
        "depth_tools": depth.status(),
        "notes": NOTES,
    }


@router.post("/catalog/refresh")
async def refresh_catalog(payload: dict):
    """Only ever on the owner's click, and only through free listing calls."""
    from mp3_to_videoclip import catalog

    provider = str(payload.get("provider"))
    return await asyncio.to_thread(catalog.refresh, provider, effective_settings())


def _projects_dir(request: Request) -> Path:
    return Path(getattr(request.app.state, "projects_dir", "projects"))


def _costs(budget, projects_dir: Path) -> dict:
    """Pictures from each journal, with the Director's model use beside them."""
    from mp3_to_videoclip.director import usage

    costs = budget.costs_across(projects_dir)
    for film in costs["films"]:
        film["model"] = usage.summary(projects_dir / film["slug"])
    return costs


@router.get("/costs")
async def get_costs(request: Request):
    from mp3_to_videoclip import budget

    return await asyncio.to_thread(_costs, budget, _projects_dir(request))


@router.get("/caches")
async def get_caches(request: Request):
    from mp3_to_videoclip import caches

    return {"caches": await asyncio.to_thread(caches.listing, _projects_dir(request))}


@router.post("/caches/clear")
async def clear_cache(request: Request, payload: dict):
    from mp3_to_videoclip import caches

    name = str(payload.get("name"))
    return await asyncio.to_thread(caches.clear, _projects_dir(request), name)


def _without_empty_secrets(keys: dict) -> dict:
    """An empty secret field means "keep the configured key", not "erase it"."""
    kept = dict(keys)
    for name in Keys.model_fields:
        value = kept.get(name)
        if isinstance(value, dict):
            kept[name] = {k: v for k, v in value.items() if k != "key" or v}
        elif name in kept and not value:
            del kept[name]
    return kept


@router.put("")
async def put_settings(payload: dict):
    current = effective_settings()
    patch = {
        key: value
        for key, value in payload.items()
        if key in Settings.model_fields and key != "schema_version"
    }
    if isinstance(patch.get("keys"), dict):
        patch["keys"] = _without_empty_secrets(patch["keys"])
    # The flat names are still accepted, and lie over the nested shape as they always did.
    flat = {key: value for key, value in payload.items() if key in FLAT or key in FLAT_ROLES}
    for key in ("llm_api_key", "runware_api_key"):
        if not flat.get(key):
            flat.pop(key, None)
    settings = Settings(**{**merge(current.model_dump(), patch), **flat})
    save_settings(settings)
    return _public(settings)
