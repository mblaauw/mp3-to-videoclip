"""Transcription: only used when the user has no lyrics to paste."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip.transcription import (
    quote_runware as quote_transcription,
)
from mp3_to_videoclip.transcription import (
    recover_runware,
    transcribe_runware,
)


def quote(root: Path, language: str | None = None) -> dict:
    return quote_transcription(root, language=language)


def run(root: Path, quote_id: str, client=None) -> dict:
    return transcribe_runware(root, quote_id, client)


def recover(root: Path, task_uuid: str, client=None) -> dict:
    return recover_runware(root, task_uuid, client)
