"""Schema 3 models for the GUI rework.

Only ``Project`` changes materially: schema version 3, no legacy workflow flags,
and the production budget moves into the project document. Brief, storyboard,
shot and asset models keep their shape and are re-exported from the engine so
there is one validation path.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from mp3_to_videoclip.models import (  # noqa: F401 - re-exported for the app
    Brief,
    CameraKeyframe,
    CameraPath,
    Character,
    CharacterState,
    CreativeProfile,
    Framing,
    ImageSettings,
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


class Project(BaseModel):
    """One production's canonical settings; written once, then edited in place."""

    schema_version: Literal[3] = SCHEMA_VERSION
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str
    source: str = "media/song.mp3"
    source_sha256: str
    duration: float = Field(gt=0)
    aspect: Literal["16:9"] = "16:9"
    fps: Literal[24, 30] = 24
    width: int = Field(gt=0, multiple_of=2)
    height: int = Field(gt=0, multiple_of=2)
    music_mode: Literal["vocal", "instrumental"] | None = None
    native_size: list[int] | None = None
    image_model: str | None = None
    image_settings: ImageSettings | None = None
    image_seed: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    style_preset: str | None = None
    budget: list[BudgetEntry] = Field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return math.ceil(self.duration * self.fps)

    @property
    def image_size(self) -> tuple[int, int]:
        if self.native_size is not None:
            return (self.native_size[0], self.native_size[1])
        return (1536, 864)

    @property
    def cap_usd(self) -> str | None:
        return self.budget[-1].cap_usd if self.budget else None
