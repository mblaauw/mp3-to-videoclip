"""Editable production contracts. All timing is in integer output frames."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

NATIVE_SIZE_STEP = 16
NATIVE_SIZE_MIN = 512
NATIVE_SIZE_MAX = 4096
NATIVE_SIZE_RATIO_TOLERANCE = 0.01

Kind = Literal["music_video", "promo", "advert"]
ShotKind = Literal[
    "scene",
    "product",
    "upload",
    "card",
    "bridge",
    "split",
    "reprise",
    "logo",
    "end_card",
]


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


class AudioWindow(Model):
    """A derived excerpt of the source; seconds are absolute source time."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    fade_in: float = Field(default=0, ge=0)
    fade_out: float = Field(default=0, ge=0)

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 6)

    @model_validator(mode="after")
    def check_interval(self):
        length = self.end - self.start
        if length <= 0:
            raise ValueError("audio window must have positive duration")
        if self.fade_in > length or self.fade_out > length:
            raise ValueError("an audio fade cannot be longer than the excerpt")
        if self.fade_in + self.fade_out > length:
            raise ValueError("audio fades overlap; shorten one fade")
        return self


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
    kind: Kind | None = None
    source_duration: float | None = Field(default=None, gt=0)
    audio_window: AudioWindow | None = None
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
        for key in (
            "prompt_version",
            "signature_required",
            "source_filename",
            "renderer_backend",
            "kind",
            "source_duration",
            "audio_window",
        ):
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
    def check_audio_window(self):
        if self.audio_window is None:
            return self
        window = self.audio_window
        if self.source_duration is not None and window.end > self.source_duration + 1e-6:
            raise ValueError("audio window ends after the source recording")
        if abs(self.duration - window.duration) > 1e-6:
            raise ValueError("project duration must equal the selected audio window")
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
    segments: list[Segment] = Field(default_factory=list)
    # Plain text is a real artifact: the words without invented positions.
    lines: list[str] = Field(default_factory=list)
    words: list[dict] = Field(default_factory=list)
    warning: str = "Sung lyrics and timestamps are unverified until reviewed."

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if not value.get("lines"):
            value.pop("lines", None)
        return value


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
    profile_version: int = Field(default=0, ge=0)

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

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if not value.get("profile_version"):
            value.pop("profile_version", None)
        return value


class CallToAction(Model):
    text: str = ""
    url: str = ""


class Intent(Model):
    """The one-page creative intent, filled from the Story intake form."""

    kind: Kind = "music_video"
    objective: str = ""
    audience: str = ""
    message: str = ""
    reasons: list[str] = Field(default_factory=list, max_length=3)
    tone: list[str] = Field(default_factory=list, max_length=3)
    mandatories: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    cta: CallToAction | None = None
    length_seconds: int | None = Field(default=None, gt=0)
    audio_window: AudioWindow | None = None
    notes: str = ""
    about: str = ""
    performance: bool | None = None
    reference_links: list[str] = Field(default_factory=list)
    assets: str = ""

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        for key in ("notes", "about", "performance", "reference_links", "assets"):
            if value.get(key) in (None, "", []):
                value.pop(key, None)
        if value.get("cta") is None:
            value.pop("cta", None)
        if value.get("length_seconds") is None:
            value.pop("length_seconds", None)
        if value.get("audio_window") is None:
            value.pop("audio_window", None)
        return value


class ScriptBeat(Model):
    """One row of the Writer's beat script; empty cells are omitted from bytes."""

    time_range: str = Field(default="", max_length=40)
    picture: str = Field(default="", max_length=600)
    text: str = Field(default="", max_length=240)
    music: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def useful(self):
        if not any((self.time_range, self.picture, self.text, self.music)):
            raise ValueError("a script beat needs at least one non-empty cell")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value != ""}


class Concept(Model):
    """One genuinely different route for the film, before the treatment is chosen."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    structure: str = Field(min_length=1, max_length=80)
    logline: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=1200)
    world: str = Field(min_length=1, max_length=1200)
    shape: list[str] = Field(min_length=4, max_length=6)
    signature_moment: str = Field(min_length=1, max_length=300)
    risk: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def useful(self):
        if any(not value.strip() for value in self.shape):
            raise ValueError("every concept shape beat needs text")
        return self


class Treatments(Model):
    """Three structurally distinct routes; the Writer may mark one chosen."""

    schema_version: Literal[1] = 1
    concepts: list[Concept] = Field(min_length=3, max_length=3)
    chosen_id: str | None = None

    @model_validator(mode="after")
    def distinct(self):
        ids = [concept.id for concept in self.concepts]
        if len(set(ids)) != len(ids):
            raise ValueError("concept IDs must be unique")
        structures = [concept.structure.strip().casefold() for concept in self.concepts]
        if len(set(structures)) != len(structures):
            raise ValueError("three concepts need three different structures")
        if self.chosen_id is not None and self.chosen_id not in ids:
            raise ValueError("chosen_id must name a concept")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("chosen_id") is None:
            value.pop("chosen_id", None)
        return value


class Brief(Model):
    intent: Intent | None = None
    direction: str = ""
    style: str = ""
    treatment: str = ""
    script: list[ScriptBeat] = Field(default_factory=list, max_length=40)
    visual_rules: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(default_factory=list)
    creative: CreativeProfile | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("intent") is None:
            value.pop("intent", None)
        if not value.get("script"):
            value.pop("script", None)
        return value


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


class BridgeMatch(Model):
    """The explicit alignment a Writer plans and the Editor can execute."""

    type: Literal["shape", "colour", "position"] = "shape"
    anchor: list[float] = Field(default_factory=lambda: [0.5, 0.5], min_length=2, max_length=2)
    note: str = Field(default="", max_length=300)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("note") == "":
            value.pop("note", None)
        return value

    @model_validator(mode="after")
    def anchor_inside_frame(self):
        if any(value < 0 or value > 1 for value in self.anchor):
            raise ValueError("bridge anchor is normalized 0..1")
        return self


class BridgePlan(Model):
    """Designed bridges are local plates; generated bridges are paid stills."""

    mode: Literal["designed", "generated"] = "designed"
    match: BridgeMatch | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("match") is None:
            value.pop("match", None)
        return value


class Pane(Model):
    """One source shot and its crop in a split composition."""

    shot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    crop: Framing = Field(default_factory=Framing)


class Shot(Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    kind: ShotKind = "scene"
    purpose: str = Field(min_length=1)
    message: str = Field(default="", max_length=400)
    lyric_context: str = ""
    music_context: str = ""
    image_prompt: str = ""
    text: list[str] = Field(default_factory=list, max_length=8)
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
    asset: str | None = Field(default=None, min_length=1, max_length=300)
    product_ref: str | None = Field(default=None, min_length=1, max_length=300)
    bridge: BridgePlan | None = None
    panes: list[Pane] = Field(default_factory=list, max_length=3)
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
        # New fields are dropped while default so legacy approval hashes do not move.
        if value.get("kind") == "scene":
            value.pop("kind", None)
        for key, empty in (
            ("message", ""),
            ("text", []),
            ("bridge", None),
            ("product_ref", None),
            ("panes", []),
            ("asset", None),
            ("image_prompt", ""),
        ):
            if value.get(key) == empty:
                value.pop(key, None)
        return value

    @model_validator(mode="after")
    def check_kind(self):
        if self.kind == "reprise" and self.asset_shot_id is None:
            raise ValueError("a reprise shot needs asset_shot_id")
        if self.kind == "upload" and self.asset is None:
            raise ValueError("an upload shot needs a project-relative asset")
        if self.kind == "product" and not (self.product_ref or self.asset):
            raise ValueError("a product shot needs a product_ref or an uploaded asset")
        if self.product_ref is not None and self.kind != "product":
            raise ValueError("product_ref only belongs to a product shot")
        if self.kind == "split":
            if not 2 <= len(self.panes) <= 3:
                raise ValueError("a split shot needs two or three panes")
            ids = [pane.shot_id for pane in self.panes]
            if len(set(ids)) != len(ids):
                raise ValueError("split panes must name different shots")
            if self.id in ids:
                raise ValueError("a split shot cannot include itself as a pane")
        elif self.panes:
            raise ValueError("panes only belong to a split shot")
        if self.kind == "bridge":
            if self.bridge is None:
                raise ValueError("a bridge shot needs a bridge plan")
            if self.bridge.match is None:
                raise ValueError("a bridge shot needs an explicit match")
            if self.bridge.mode == "generated" and not self.image_prompt.strip():
                raise ValueError("a generated bridge needs an image prompt")
            if self.bridge.mode == "designed" and not (self.text or self.message.strip()):
                raise ValueError("a designed bridge needs a message or on-screen text")
        elif self.bridge is not None:
            raise ValueError("bridge plans only belong to a bridge shot")
        if self.text and any(not value.strip() or len(value) > 160 for value in self.text):
            raise ValueError("on-screen text lines must be 1-160 characters")
        if self.kind in ("card", "end_card") and not (self.text or self.message.strip()):
            raise ValueError(f"a {self.kind} shot needs a message or on-screen text")
        generated = self.kind in ("scene", "product", "bridge")
        if self.kind == "product" and self.asset is not None:
            generated = False
        if self.kind == "bridge" and self.bridge is not None:
            generated = self.bridge.mode == "generated"
        if generated and not self.image_prompt.strip():
            raise ValueError("generated shots need an image prompt")
        if self.asset is not None and self.kind not in (
            "upload",
            "product",
            "card",
            "logo",
            "end_card",
        ):
            raise ValueError("an uploaded asset belongs to upload, product, card, logo or end_card")
        return self

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


EditTransitionType = Literal[
    "cut",
    "fade",
    "wipe_left",
    "wipe_right",
    "dip_to_black",
    "dip_to_white",
    "whip_pan",
    "push",
    "slide",
]
EditMotionType = Literal["hold", "push_in", "pull_back", "pan_left", "pan_right"]
EditAccentType = Literal["punch_in", "flash", "light_leak"]
EditTextAnimation = Literal["fade", "type_on", "slide_up", "pop", "kinetic_words"]
EditTextStyle = Literal["super", "title", "lower_third", "lyric", "card"]
GradePreset = Literal["neutral", "warm-night", "clean-day", "monochrome", "vivid", "film-fade"]


class EditTransition(Model):
    """How one edit shot arrives; timing is owned here, not by the storyboard."""

    type: EditTransitionType = "cut"
    frames: int = Field(default=0, ge=0, le=48)
    direction: Literal["left", "right", "up", "down"] | None = None
    reason: str = Field(default="", max_length=240)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("direction") is None:
            value.pop("direction", None)
        if value.get("reason") == "":
            value.pop("reason", None)
        return value


class EditMotion(Model):
    """A bounded camera move for one shot, in normalized crop coordinates."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)

    type: EditMotionType = "hold"
    from_scale: float = Field(
        default=1.0,
        ge=1.0,
        le=1.3,
        validation_alias="from",
        serialization_alias="from",
    )
    to_scale: float = Field(
        default=1.0,
        ge=1.0,
        le=1.3,
        validation_alias="to",
        serialization_alias="to",
    )
    easing: Literal["linear", "smoothstep"] = "smoothstep"
    anchor: list[float] = Field(default_factory=lambda: [0.5, 0.5], min_length=2, max_length=2)
    reason: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def check_motion(self):
        if any(value < 0 or value > 1 for value in self.anchor):
            raise ValueError("motion anchor is normalized 0..1")
        if self.type == "hold" and (self.from_scale != 1.0 or self.to_scale != 1.0):
            raise ValueError("a hold keeps the image at scale 1.00")
        if self.type in ("push_in", "pull_back") and self.from_scale == self.to_scale:
            raise ValueError("push and pull need a scale change")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("reason") == "":
            value.pop("reason", None)
        return value


class EditAccent(Model):
    """A short emphasis hit placed on an absolute film frame."""

    frame: int = Field(ge=0)
    type: EditAccentType
    amount: float = Field(default=1.04, ge=1.0, le=1.2)
    duration_frames: int = Field(default=6, ge=1, le=24)
    reason: str = Field(default="", max_length=240)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("reason") == "":
            value.pop("reason", None)
        return value


class EditText(Model):
    """One timed text layer. Frames are absolute film frames."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    style: EditTextStyle = "super"
    text: str = Field(min_length=1, max_length=160)
    in_frame: int = Field(ge=0)
    out_frame: int = Field(gt=0)
    animation: EditTextAnimation = "fade"
    reason: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def check_window(self):
        if self.out_frame <= self.in_frame:
            raise ValueError("text out_frame must follow in_frame")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("reason") == "":
            value.pop("reason", None)
        return value


class EditShot(Model):
    """One edit decision: order, span, motion, transition, accents and text."""

    shot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    motion: EditMotion = Field(default_factory=EditMotion)
    transition_in: EditTransition = Field(default_factory=EditTransition)
    split_layout: Literal["row", "column", "grid"] | None = None
    accents: list[EditAccent] = Field(default_factory=list, max_length=8)
    text: list[EditText] = Field(default_factory=list, max_length=8)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("split_layout") is None:
            value.pop("split_layout", None)
        return value

    @model_validator(mode="after")
    def check_children(self):
        end = self.start_frame + self.duration_frames
        for accent in self.accents:
            if not self.start_frame <= accent.frame < end:
                raise ValueError(f"accent frame {accent.frame} is outside shot {self.shot_id}")
        ids = {item.id for item in self.text}
        if len(ids) != len(self.text):
            raise ValueError(f"text ids in shot {self.shot_id} must be unique")
        for item in self.text:
            if not self.start_frame <= item.in_frame < item.out_frame <= end:
                raise ValueError(f"text {item.id} is outside shot {self.shot_id}")
        return self


class EditSection(Model):
    """A section intent used by the report and by the Editor's own review."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    start_frame: int = Field(ge=0)
    end_frame: int | None = Field(default=None, gt=0)
    feel: str = Field(min_length=1, max_length=240)
    density_per_10s: float = Field(default=0, ge=0, le=60)
    techniques: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_window(self):
        if self.end_frame is not None and self.end_frame <= self.start_frame:
            raise ValueError("section end_frame must follow start_frame")
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("end_frame") is None:
            value.pop("end_frame", None)
        return value


class Grade(Model):
    """A named look, with the legacy four sliders available as overrides."""

    preset: GradePreset = "neutral"
    strength: float = Field(default=1.0, ge=0, le=1)
    overrides: PostEffects | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        value = handler(self)
        if value.get("overrides") is None:
            value.pop("overrides", None)
        return value


class EditDecisionList(Model):
    """The edit-owned timeline for a storyboard; content stays in Storyboard."""

    schema_version: Literal[1] = 1
    sections: list[EditSection] = Field(default_factory=list)
    shots: list[EditShot] = Field(min_length=1)
    grade: Grade = Field(default_factory=Grade)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def check_order(self):
        shot_ids = [shot.shot_id for shot in self.shots]
        if len(set(shot_ids)) != len(shot_ids):
            raise ValueError("edit shot IDs must be unique")
        starts = [shot.start_frame for shot in self.shots]
        if starts != sorted(starts):
            raise ValueError("edit shots must be ordered by start_frame")
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("edit section IDs must be unique")
        section_starts = [section.start_frame for section in self.sections]
        if section_starts != sorted(section_starts):
            raise ValueError("edit sections must be ordered by start_frame")
        return self

    def check_board(self, board: Storyboard):
        """Require the edit to cover exactly the storyboard's frame range."""
        known = {shot.id for shot in board.shots}
        edit_ids = {shot.shot_id for shot in self.shots}
        if edit_ids != known:
            missing = sorted(known - edit_ids)
            extra = sorted(edit_ids - known)
            raise ValueError(
                f"edit must name every storyboard shot (missing {missing}, extra {extra})"
            )
        cursor = 0
        for index, shot in enumerate(self.shots):
            if shot.start_frame != cursor:
                raise ValueError(
                    f"edit shot {shot.shot_id} starts at {shot.start_frame}; expected {cursor}"
                )
            if shot.transition_in.frames > 0:
                if shot.transition_in.frames >= shot.duration_frames:
                    raise ValueError(f"edit shot {shot.shot_id} transition is longer than the shot")
                if index > 0 and shot.transition_in.frames >= self.shots[index - 1].duration_frames:
                    raise ValueError(
                        f"edit shot {shot.shot_id} transition is longer than the previous shot"
                    )
            cursor += shot.duration_frames
        if cursor != board.total_frames:
            raise ValueError(
                f"edit covers {cursor} frames but the storyboard has {board.total_frames}"
            )
        for section in self.sections:
            end = section.end_frame if section.end_frame is not None else board.total_frames
            if end > board.total_frames:
                raise ValueError(f"edit section {section.id} extends past the film")
        return self

    def effective_board(self, board: Storyboard) -> Storyboard:
        """Apply edit order and spans to the content board, without mutating it."""
        self.check_board(board)
        content = {shot.id: shot for shot in board.shots}
        shots = []
        for decision in self.shots:
            shot = content[decision.shot_id].model_copy(
                update={
                    "start_frame": decision.start_frame,
                    "duration_frames": decision.duration_frames,
                    # Edit timing and motion replace the legacy storyboard controls.
                    "dissolve_frames": 0,
                    "transition": None,
                }
            )
            shots.append(shot)
        return board.model_copy(update={"shots": shots})


class RenderShot(Model):
    """Input to renderer, already resolved and checked against current approvals."""

    shot: Shot
    image: str
    edit: EditShot | None = None
    grade: Grade | None = None


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
