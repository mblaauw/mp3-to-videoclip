"""First-run setup: report capabilities and install the pinned local renderer."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from mp3_to_videoclip import setup

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("")
async def get_setup():
    return setup.status()


@router.post("/renderer")
async def install_renderer():
    try:
        return await asyncio.to_thread(setup.install_renderer)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
