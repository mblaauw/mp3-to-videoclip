"""Editable production contracts. All timing is in integer output frames."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

NATIVE_SIZE_STEP = 16
NATIVE_SIZE_MIN = 512
NATIVE_SIZE_MAX = 4096
NATIVE_SIZE_RATIO_TOLERANCE = 0.01


def native_size_problem(value: list[int], width: int, height: int) -> str | None:
    """Readable error for an unusable declared image size, or None when it fits.

    Shared by the ``Project`` validator and ``clip init``, which checks the
    flag before it creates any production files.
    """
    if len(value) != 2:
        return f"native_size must be exactly [width, height], got {value}"
    for number in value:
        if number % NATIVE_SIZE_STEP:
            return f"native_size {value[0]}x{value[1]} must be multiples of 16"
        if not NATIVE_SIZE_MIN <= number <= NATIVE_SIZE_MAX:
            return (
                f"native_size {value[0]}x{value[1]} must be within "
                f"{NATIVE_SIZE_MIN}..{NATIVE_SIZE_MAX} pixels"
            )
    ratio = value[0] / value[1]
    target = width / height
    if abs(ratio - target) > NATIVE_SIZE_RATIO_TOLERANCE * target:
        return (
            f"native_size {value[0]}x{value[1]} ({ratio:.4f}) is not within 1% of the "
            f"production aspect ratio ({target:.4f})"
        )
    return None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ImageSettings(Model):
    """Supported optional controls; the selected live model schema also validates."""

    thinkingLevel: Literal["minimal", "medium", "high"] | None = None
    imageSearch: bool | None = Field(default=None, strict=True)
    webSearch: bool | None = Field(default=None, strict=True)
    temperature: float | None = Field(default=None, ge=0, le=2, multiple_of=0.01)
    topP: float | None = Field(default=None, ge=0, le=1, multiple_of=0.01)
    systemPrompt: str | None = Field(default=None, min_length=1, max_length=50000)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class Project(Model):
    schema_version: Literal[1, 3] = 1
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    title: str
    source: str = "media/song.mp3"
    source_sha256: str
    duration: float = Field(gt=0)
    aspect: Literal["16:9", "9:16"] = "16:9"
    fps: Literal[24, 30] = 24
    width: int = Field(gt=0, multiple_of=2)
    height: int = Field(gt=0, multiple_of=2)
    music_mode: Literal["vocal", "instrumental", "music-led"] | None = None
    native_size: list[int] | None = None
    workflow_version: Literal[2] | None = None
    image_model: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,100}$")
    image_settings: ImageSettings | None = None
    image_seed: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    style_preset: str | None = None
    prompt_version: Literal[2] | None = None
    signature_required: bool | None = Field(default=None, strict=True)
    source_filename: str | None = None
    renderer_backend: Literal["ffmpeg", "remotion"] | None = None
    budget: list[dict] = Field(default_factory=list)

    @property
    def total_frames(self) -> int:
        return math.ceil(self.duration * self.fps)

    @property
    def uses_remotion(self) -> bool:
        """An explicit backend wins; schema 3 without one is the native Remotion form."""
        if self.renderer_backend is not None:
            return self.renderer_backend == "remotion"
        return self.schema_version == 3

    @property
    def image_size(self) -> tuple[int, int]:
        if self.native_size is not None:
            return (self.native_size[0], self.native_size[1])
        return (1536, 864) if self.aspect == "16:9" else (864, 1536)

    @model_serializer(mode="wrap")
    def serialize(self, handler) -> dict:
        """Legacy projects never serialized ``native_size``; keep their hashes stable."""
        value = handler(self)
        if value.get("native_size") is None:
            value.pop("native_size", None)
        if value.get("workflow_version") is None:
            value.pop("workflow_version", None)
        for key in ("image_model", "image_settings", "image_seed", "style_preset"):
            if value.get(key) is None:
                value.pop(key, None)
        for key in ("prompt_version", "signature_required", "source_filename", "renderer_backend"):
            if value.get(key) is None:
                value.pop(key, None)
        return value

    @model_validator(mode="after")
    def check_aspect(self):
        a, b = map(int, self.aspect.split(":"))
        if self.width * b != self.height * a:
            raise ValueError("output dimensions must match the selected aspect")
        return self

    @model_validator(mode="after")
    def check_native_size(self):
        if self.native_size is not None:
            problem = native_size_problem(self.native_size, self.width, self.height)
            if problem:
                raise ValueError(problem)
        return self


class Segment(Model):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_interval(self):
        if self.end <= self.start:
            raise ValueError("lyric interval must have positive duration")
        return self


class Lyrics(Model):
    language: str | None = None
    provider: str
    model: str
    segments: list[Segment]
    words: list[dict] = Field(default_factory=list)
    warning: str = "Sung lyrics and timestamps are unverified until reviewed."


class CharacterState(Model):
    """Changeable costume/prop state, separate from a character's identity."""

    description: str = Field(min_length=1)
    attributes: dict[str, str] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list, max_length=14)


class Character(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    description: str = ""
    references: list[str] = Field(default_factory=list, max_length=14)
    permission_confirmed: bool = False
    identity: str | None = Field(default=None, min_length=1)
    states: dict[str, CharacterState] = Field(default_factory=dict)
    default_state: str | None = None

    @model_validator(mode="after")
    def check_identity(self):
        if not (self.identity or self.description).strip():
            raise ValueError("a character needs identity or a legacy description")
        if self.default_state is not None and self.default_state not in self.states:
            raise ValueError("character default_state must name a declared state")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        for key, empty in (("identity", None), ("states", {}), ("default_state", None)):
            if value.get(key) == empty:
                value.pop(key, None)
        return value


class VisualReference(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    kind: Literal["style", "location", "prop"]
    description: str = Field(min_length=1)
    path: str = Field(min_length=1)
    permission_confirmed: bool = False


class Scene(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    description: str = Field(min_length=1)
    reference_ids: list[str] = Field(default_factory=list)


class VisualBeat(Model):
    phase: str = Field(min_length=1)
    intention: str = Field(min_length=1)


class CreativeProfile(Model):
    """Global appearance only; story/locations are not repeated into every image."""

    mode: Literal["narrative", "symbolic", "abstract"] = "narrative"
    look: str = ""
    image_rules: list[str] = Field(default_factory=list)
    arc: list[VisualBeat] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    references: list[VisualReference] = Field(default_factory=list)
    global_reference_ids: list[str] = Field(default_factory=list)
    proof_shot_ids: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def unique_ids(self):
        for values in (self.scenes, self.references):
            if len({v.id for v in values}) != len(values):
                raise ValueError("scene/reference IDs must be unique")
        refs = {r.id for r in self.references}
        for ids in [self.global_reference_ids, *(s.reference_ids for s in self.scenes)]:
            if len(set(ids)) != len(ids) or not set(ids) <= refs:
                raise ValueError("reference bindings must be unique and known")
        if len(set(self.proof_shot_ids)) != len(self.proof_shot_ids):
            raise ValueError("proof shot IDs must be unique")
        return self


class Brief(Model):
    direction: str = ""
    style: str = ""
    treatment: str = ""
    visual_rules: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    creative: CreativeProfile | None = None


class Framing(Model):
    zoom: float = Field(default=1, ge=1, le=2)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)


class CameraPath(Model):
    """x/y are normalized position within the available crop, not screen pixels."""

    start: Framing = Field(default_factory=Framing)
    end: Framing = Field(default_factory=Framing)
    easing: Literal["linear", "smoothstep"] = "linear"


class CameraKeyframe(Framing):
    frame: int = Field(ge=0, strict=True)


class PostEffects(Model):
    """Bounded render-side treatment; never part of an image-generation prompt."""

    contrast: float = Field(default=1, ge=1, le=1.2)
    saturation: float = Field(default=1, ge=0.7, le=1.3)
    brightness: float = Field(default=1, ge=0.9, le=1.1)
    vignette: float = Field(default=0, ge=0, le=0.3)


class Shot(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    purpose: str = Field(min_length=1)
    lyric_context: str = ""
    music_context: str = ""
    image_prompt: str = Field(min_length=1)
    motion_prompt: str = ""
    camera: Literal["hold", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "zoom_in"
    dissolve_frames: int = Field(default=0, ge=0)
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list)
    framing: Literal["wide", "medium", "close_up", "detail"] | None = None
    must_show: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    camera_path: CameraPath | None = None
    camera_keyframes: list[CameraKeyframe] | None = Field(default=None, min_length=2, max_length=12)
    post_effects: PostEffects | None = None
    transition: Literal["fade", "wipe_left", "wipe_right"] | None = None
    asset_shot_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    character_states: dict[str, str] = Field(default_factory=dict)
    state_requirements: dict[str, dict[str, str]] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        for key in ("character_states", "state_requirements"):
            if not value.get(key):
                value.pop(key, None)
        for key in ("camera_keyframes", "post_effects", "transition"):
            if value.get(key) is None:
                value.pop(key, None)
        return value

    @model_validator(mode="after")
    def check_render_controls(self):
        if self.transition is not None and not self.dissolve_frames:
            raise ValueError("a transition needs allocated dissolve handle frames")
        if self.camera_keyframes:
            frames = [key.frame for key in self.camera_keyframes]
            if frames[0] != 0 or frames != sorted(set(frames)):
                raise ValueError("camera keyframes must start at zero and be strictly ordered")
            if frames[-1] >= self.duration_frames + self.dissolve_frames:
                raise ValueError("camera keyframe is outside the allocated shot plus handles")
        return self


class Storyboard(Model):
    schema_version: Literal[1, 3] = 1
    aspect: Literal["16:9", "9:16"]
    fps: Literal[24, 30]
    total_frames: int = Field(gt=0)
    shots: list[Shot] = Field(min_length=1)

    @model_validator(mode="after")
    def check_timeline(self):
        cursor = 0
        ids = set()
        for i, shot in enumerate(self.shots):
            if shot.id in ids or shot.start_frame != cursor:
                raise ValueError("unique shot IDs and a contiguous, ordered timeline are required")
            ids.add(shot.id)
            cursor += shot.duration_frames
            if shot.dissolve_frames:
                if i == len(self.shots) - 1:
                    raise ValueError("last shot cannot dissolve into a missing shot")
                if shot.dissolve_frames >= min(
                    shot.duration_frames, self.shots[i + 1].duration_frames
                ):
                    raise ValueError("dissolve must be shorter than both adjacent shots")
        if cursor != self.total_frames:
            raise ValueError("shots must cover the full timeline exactly")
        return self

    def check_project(self, project: Project):
        if (self.aspect, self.fps, self.total_frames) != (
            project.aspect,
            project.fps,
            project.total_frames,
        ):
            raise ValueError("storyboard format/duration does not match project")


class MusicEvent(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    frame: int = Field(ge=0)
    end_frame: int | None = Field(default=None, ge=0)
    kind: Literal[
        "section", "vocal", "instrumental", "build", "release", "motif", "silence", "accent"
    ]
    label: str = Field(min_length=1)
    timing_basis: Literal["manual", "estimated"] = "manual"
    note: str = ""
    level: Literal["section", "phrase", "accent"] | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    source: (
        Literal["local-measurement", "audio-model", "user-listening", "provided-intent"] | None
    ) = None
    evidence: str | None = None

    @model_validator(mode="after")
    def interval(self):
        if self.end_frame is not None and self.end_frame <= self.frame:
            raise ValueError("event end must follow its start")
        return self


class EventMap(Model):
    source_sha256: str
    fps: Literal[24, 30]
    total_frames: int = Field(gt=0)
    pulse: Literal["steady", "variable", "free", "unknown"] = "unknown"
    events: list[MusicEvent] = Field(default_factory=list)
    warning: str = "Editable listening notes; not automatically inferred structure or meter."

    @model_validator(mode="after")
    def events_valid(self):
        if len({e.id for e in self.events}) != len(self.events):
            raise ValueError("musical event IDs must be unique")
        if any(
            e.frame >= self.total_frames
            or (e.end_frame is not None and e.end_frame > self.total_frames)
            for e in self.events
        ):
            raise ValueError("musical events must remain within the song")
        if [e.frame for e in self.events] != sorted(e.frame for e in self.events):
            raise ValueError("musical events must be ordered")
        return self

    def check_project(self, project: Project):
        if (self.source_sha256, self.fps, self.total_frames) != (
            project.source_sha256,
            project.fps,
            project.total_frames,
        ):
            raise ValueError("event map source/format does not match project")


class RenderShot(Model):
    """Input to renderer, already resolved and checked against current approvals."""

    shot: Shot
    image: str


class BrandPackage(Model):
    """Render-time identity, never an image-generation reference or audio pre-roll."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    version: int = Field(default=1, ge=1)
    mark: Literal["open-frame", "cutline", "monogram", "joint", "filmstrip"] = "open-frame"
    name: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=120)
    monogram: str = ""
    duration_seconds: float = Field(default=8, ge=5, le=10)
    foreground: str = Field(default="#F4F1E8", pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(default="#D8FF3E", pattern=r"^#[0-9A-Fa-f]{6}$")
    background: str = Field(default="#0B1015", pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary: str = Field(default="#6E8B99", pattern=r"^#[0-9A-Fa-f]{6}$")
    #: Whether the renderer composites this package as a plate over the opening.
    #: A production whose opening already renders the identity through the
    #: graphics pipeline sets this false so one emblem is never drawn twice.
    plate: bool = True
    safe_margin: float = Field(default=0.08, ge=0.05, le=0.2)

    @model_validator(mode="after")
    def identity(self):
        if self.mark == "monogram" and not 1 <= len(self.monogram.strip()) <= 4:
            raise ValueError("a monogram mark needs 1–4 approved characters")
        return self


class ListeningPassage(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str = Field(min_length=1)
    groove: str
    texture: list[str]
    energy: Literal["low", "medium", "high"]
    tension: Literal["low", "medium", "high"]
    transition: str
    vocal_hook: str | None
    confidence: Literal["low", "medium", "high"]
    evidence: str
    uncertainty: str

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start:
            raise ValueError("listening passage end must follow start")
        return self


class ListeningDraft(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    passages: list[ListeningPassage] = Field(min_length=1)
    overall_observations: list[str]
    limitations: list[str]
