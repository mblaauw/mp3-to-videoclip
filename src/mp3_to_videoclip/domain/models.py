"""Schema 3 models for the GUI rework.

Only ``Project`` changes materially: schema version 3, no legacy workflow flags,
and the production budget moves into the project document. Brief, storyboard,
shot and asset models keep their shape and are re-exported from the engine so
there is one validation path.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from mp3_to_videoclip.models import (  # noqa: F401 - re-exported for the app
    AudioWindow,
    Brief,
    CallToAction,
    CameraKeyframe,
    CameraPath,
    Character,
    CharacterState,
    CreativeProfile,
    Framing,
    ImageSettings,
    Intent,
    Lyrics,
    MusicEvent,
    PostEffects,
    Scene,
    Segment,
    Shot,
    Storyboard,
    VisualBeat,
    VisualReference,
)

SCHEMA_VERSION = 3


class BudgetEntry(BaseModel):
    at: str
    cap_usd: str
    reason: str = ""
    max_corrections: int | None = None


class Project(BaseModel):
    """One production's canonical settings; written once, then edited in place."""

    schema_version: Literal[3] = SCHEMA_VERSION
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str
    source: str = "media/song.mp3"
    source_sha256: str
    duration: float = Field(gt=0)
    aspect: Literal["16:9", "9:16"] = "16:9"
    fps: Literal[24, 30] = 24
    width: int = Field(gt=0, multiple_of=2)
    height: int = Field(gt=0, multiple_of=2)
    music_mode: Literal["vocal", "instrumental"] | None = None
    kind: Literal["music_video", "promo", "advert"] | None = None
    source_duration: float | None = Field(default=None, gt=0)
    audio_window: AudioWindow | None = None
    native_size: list[int] | None = None
    image_model: str | None = None
    image_settings: ImageSettings | None = None
    image_seed: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    style_preset: str | None = None
    signature_required: bool | None = Field(default=None, strict=True)
    budget: list[BudgetEntry] = Field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return math.ceil(self.duration * self.fps)

    @model_validator(mode="after")
    def check_aspect(self):
        a, b = map(int, self.aspect.split(":"))
        if self.width * b != self.height * a:
            raise ValueError("output dimensions must match the selected aspect")
        return self

    @model_validator(mode="after")
    def check_audio_window(self):
        if self.audio_window is None:
            return self
        if self.source_duration is not None and self.audio_window.end > self.source_duration + 1e-6:
            raise ValueError("audio window ends after the source recording")
        if abs(self.duration - self.audio_window.duration) > 1e-6:
            raise ValueError("project duration must equal the selected audio window")
        return self

    @property
    def image_size(self) -> tuple[int, int]:
        if self.native_size is not None:
            return (self.native_size[0], self.native_size[1])
        return (1536, 864) if self.aspect == "16:9" else (864, 1536)

    @property
    def cap_usd(self) -> str | None:
        return self.budget[-1].cap_usd if self.budget else None
