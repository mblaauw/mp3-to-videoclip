"""Settings: read and write the user's ~/.config/mp3-to-videoclip/settings.toml."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from mp3_to_videoclip.config import Settings, effective_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _public(settings: Settings) -> dict:
    """Never send a secret back to the browser; expose presence instead."""
    from mp3_to_videoclip import kinds, styles

    value = settings.model_dump()
    value["llm_api_key"] = ""
    value["runware_api_key"] = ""
    value["has_llm_api_key"] = bool(settings.llm_api_key)
    value["has_runware_api_key"] = bool(settings.runware_api_key)
    value["style_presets"] = styles.public_presets()
    value["kinds"] = kinds.public_kinds()
    return value


@router.get("")
async def get_settings():
    return _public(effective_settings())


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
