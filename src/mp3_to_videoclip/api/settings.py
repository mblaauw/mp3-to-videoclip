"""Settings: read and write the user's ~/.config/mp3-to-videoclip/settings.toml."""

from __future__ import annotations

from fastapi import APIRouter

from mp3_to_videoclip.config import effective_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    return effective_settings().model_dump()


@router.put("")
async def put_settings(payload: dict):
    from mp3_to_videoclip.config import Settings

    settings = Settings(**payload)
    save_settings(settings)
    return settings.model_dump()
