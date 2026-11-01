"""Who can read a story film, and how to ask each of them.

``Voice`` is the one interface. MiniMax through Runware is what a film can buy today. ElevenLabs
is scaffolded behind the same interface and proved only against a fake: it is listed when a key
exists, and a quote refuses it plainly until a client is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

#: Words a second until a film's own takes have measured one.
DEFAULT_READING_RATE = 2.3
DEFAULT_MODEL = "minimax-speech-2-8"


class Voice(Protocol):
    id: str
    provider: str
    label: str
    language: str
    reading_rate_wps: float

    def build_request(self, text: str, task_uuid: str, air_id: str) -> dict: ...

    def parse_result(self, result: dict) -> dict: ...


@dataclass(frozen=True)
class RunwareMiniMaxVoice:
    id: str
    label: str = ""
    language: str = "en"
    provider: str = "runware"
    reading_rate_wps: float = DEFAULT_READING_RATE

    def build_request(self, text: str, task_uuid: str, air_id: str) -> dict:
        return {
            "taskType": "audioInference",
            "taskUUID": task_uuid,
            "model": air_id,
            "speech": {"text": text, "voice": self.id},
            "settings": {"turbo": False},
            "outputType": "URL",
            "outputFormat": "WAV",
            "deliveryMethod": "sync",
            "numberResults": 1,
            "includeCost": True,
        }

    def parse_result(self, result: dict) -> dict:
        return {"url": result["audioURL"], "cost": result["cost"], "words": None}


@dataclass(frozen=True)
class ElevenLabsVoice:
    id: str
    label: str = ""
    language: str = "en"
    provider: str = "elevenlabs"
    reading_rate_wps: float = DEFAULT_READING_RATE
    settings: dict[str, Any] = field(default_factory=dict)

    def build_request(self, text: str, task_uuid: str, air_id: str) -> dict:
        return {
            "path": f"/v1/text-to-speech/{self.id}/with-timestamps",
            "taskUUID": task_uuid,
            "body": {"text": text, "model_id": air_id, "voice_settings": self.settings},
        }

    def parse_result(self, result: dict) -> dict:
        """Words from the provider's per-character times."""
        alignment = result.get("alignment") or {}
        characters = alignment.get("characters") or []
        starts = alignment.get("character_start_times_seconds") or []
        ends = alignment.get("character_end_times_seconds") or []
        words: list[dict] = []
        current: dict | None = None
        for character, start, end in zip(characters, starts, ends, strict=False):
            if character.isspace():
                current = None
            elif current is None:
                current = {"text": character, "start": start, "end": end}
                words.append(current)
            else:
                current["text"] += character
                current["end"] = end
        return {"url": result.get("audio_url"), "cost": result.get("cost"), "words": words}


def default_voice() -> str:
    from .config import load_settings

    return load_settings().voices.default_voice


def get(voice_id: str) -> Voice:
    """A voice by id. A provider's own schema decides whether an unknown id is really offered."""
    for row in catalogue(with_all=True):
        if row["id"] == voice_id and row["provider"] == "elevenlabs":
            return ElevenLabsVoice(id=voice_id, label=row["label"])
    return RunwareMiniMaxVoice(id=voice_id)


def catalogue(*, with_all: bool = False) -> list[dict]:
    """The voices to offer, the default first. ElevenLabs only when it has a key."""
    from . import catalog
    from .config import effective_settings

    settings = effective_settings()
    chosen = settings.voices.default_voice
    rows = [
        {
            "id": voice.id,
            "provider": voice.provider,
            "label": voice.label,
            "language": voice.language,
            "recommended": voice.id == chosen,
        }
        for voice in catalog.load().voices
        if with_all or voice.provider != "elevenlabs" or settings.keys.elevenlabs
    ]
    return sorted(rows, key=lambda row: not row["recommended"])
