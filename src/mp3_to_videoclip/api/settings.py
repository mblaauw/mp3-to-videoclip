"""Settings: read and write the user's ~/.config/mp3-to-videoclip/settings.toml."""

from __future__ import annotations

import asyncio
import subprocess
import uuid

from fastapi import APIRouter, HTTPException

from mp3_to_videoclip.config import Settings, effective_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _public(settings: Settings) -> dict:
    """Never send a secret back to the browser; expose presence instead."""
    from mp3_to_videoclip import kinds, shotkinds, styles

    value = settings.model_dump()
    value["llm_api_key"] = ""
    value["runware_api_key"] = ""
    value["has_llm_api_key"] = bool(settings.llm_api_key)
    value["has_runware_api_key"] = bool(settings.runware_api_key)
    value["style_presets"] = styles.public_presets()
    value["kinds"] = kinds.public_kinds()
    value["shot_kinds"] = shotkinds.public_kinds()
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


def _test_opencode() -> dict:
    from mp3_to_videoclip.director.opencode import discover_binary

    settings = effective_settings()
    binary = discover_binary(settings.opencode_bin)
    try:
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
        auth = subprocess.run([binary, "auth", "list"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return {
            "ok": False,
            "kind": "opencode",
            "message": "OpenCode was not found on this computer.",
        }
    label = (version.stdout or version.stderr).strip().splitlines()
    name = label[0] if label else "OpenCode"
    if version.returncode != 0:
        return {"ok": False, "kind": "opencode", "message": "OpenCode could not start."}
    if auth.returncode != 0 or not (auth.stdout or "").strip():
        return {
            "ok": False,
            "kind": "opencode",
            "message": "OpenCode is installed but not signed in.",
            "version": name,
        }
    return {
        "ok": True,
        "kind": "opencode",
        "message": f"{name} · signed in",
        "version": name,
    }


@router.post("/test")
async def test_settings(payload: dict):
    kind = payload.get("kind")
    if kind == "runware":
        return await asyncio.to_thread(_test_runware)
    if kind == "opencode":
        return await asyncio.to_thread(_test_opencode)
    raise HTTPException(status_code=400, detail="kind must be runware or opencode")


@router.put("")
async def put_settings(payload: dict):
    current = effective_settings()
    updates = {key: value for key, value in payload.items() if key in Settings.model_fields}
    # An empty secret field means "keep the configured key", not "erase it".
    for key in ("llm_api_key", "runware_api_key"):
        if not updates.get(key):
            updates[key] = getattr(current, key)
    try:
        settings = Settings(**{**current.model_dump(), **updates})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_settings(settings)
    from mp3_to_videoclip.api.director import close_gateways

    close_gateways()
    return _public(settings)
