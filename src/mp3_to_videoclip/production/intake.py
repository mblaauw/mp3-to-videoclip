"""Starting a film and applying intake answers to it."""

import shutil
from pathlib import Path

from .. import flow, kinds, profiles, styles
from ..models import (
    AudioWindow,
    Brief,
    CreativeProfile,
    Intent,
    Project,
)
from ..render import audio_seconds, probe
from ..storage import (
    file_hash,
    inside,
    read_optional,
    state_mutation,
    write_json,
)
from .board import init_events
from .brief import _merge_patch, load_brief
from .project import STAGE_FILES, load_project


def style_template(projects_dir: Path) -> str | None:
    """Most recent sibling film-style text, for prefilling a new production.

    An approved brief is preferred over a newer unapproved draft. This is a
    read-only starting point, never an approval: the user can edit the style in
    the Story step before any still is generated. Malformed or empty sibling
    briefs are skipped rather than failing project creation.
    """
    best = None
    approved = None
    for path in Path(projects_dir).glob("*/brief.json"):
        value = read_optional(path)
        if not isinstance(value, dict):
            continue
        creative = value.get("creative")
        look = creative.get("look") if isinstance(creative, dict) else None
        if not isinstance(look, str) or not look.strip():
            look = value.get("style")
        if not isinstance(look, str) or not look.strip():
            continue
        look = look.strip()
        stamp = path.stat().st_mtime
        if best is None or stamp > best[0]:
            best = (stamp, look)
        records = read_optional(path.parent / "work/approvals.json")
        if isinstance(records, dict) and isinstance(records.get("brief"), dict):
            if approved is None or stamp > approved[0]:
                approved = (stamp, look)
    chosen = approved or best
    return chosen[1] if chosen else None


def init_project(
    root: Path,
    source: Path,
    slug: str,
    aspect="16:9",
    fps=24,
    music_mode="vocal",
    *,
    image_model=None,
    image_settings=None,
    image_seed=None,
    style=None,
    style_preset=None,
    native_size=None,
    title=None,
    kind="music_video",
    length_seconds=None,
    window_start=0.0,
    fade_in=0.0,
    fade_out=0.0,
    intent=None,
) -> Project:
    # An empty directory is a reservation made by intake: the caller owns it and
    # must clean it up on failure. A directory with any entry is an existing
    # production and must never be reused.
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("project directory already exists; use its existing artifacts")
    source = source.resolve(strict=True)
    if source.suffix.lower() != ".mp3":
        raise ValueError("MVP input is an MP3; convert other sources explicitly first")
    info = probe(source)
    if not any(s.get("codec_type") == "audio" for s in info["streams"]):
        raise ValueError("source has no audio stream")
    source_duration = audio_seconds(source)
    profile = kinds.get(kind)
    window = _intake_window(
        profile,
        source_duration,
        length_seconds=length_seconds,
        window_start=window_start,
        fade_in=fade_in,
        fade_out=fade_out,
    )
    duration = window.duration if window is not None else source_duration
    width, height = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    style_preset = style_preset or None
    if style is not None and not style.strip():
        raise ValueError("an explicit style override must not be blank")
    if style is not None and style_preset is not None:
        raise ValueError("choose an explicit style or a style preset, not both")
    if title is not None and not title.strip():
        raise ValueError("film title must not be blank")

    selected_preset = None
    inherited = None
    if style is None:
        if style_preset is not None:
            selected_preset = styles.preset(style_preset)
        elif profile.id == "music_video":
            inherited = style_template(root.parent)
            selected_preset = _matching_preset(inherited)
        if selected_preset is None and inherited is None:
            selected_preset = styles.default_for(profile.id)
    if style is not None:
        look, preset_id = style, "custom"
        image_rules = list(profiles.DEFAULT_IMAGE_RULES)
    elif inherited is not None:
        look, preset_id = inherited, (selected_preset.id if selected_preset else "custom")
        image_rules = list(
            selected_preset.image_rules if selected_preset else profiles.DEFAULT_IMAGE_RULES
        )
    else:
        assert selected_preset is not None
        look, preset_id = selected_preset.look, selected_preset.id
        image_rules = list(selected_preset.image_rules)

    selected_model = (
        image_model
        or (selected_preset.model if selected_preset is not None else None)
        or profiles.DEFAULT_MODEL
    )
    selected_settings = image_settings
    if selected_settings is None and selected_preset is not None:
        selected_settings = selected_preset.settings or None
    if selected_settings is None and selected_model == profiles.DEFAULT_MODEL:
        selected_settings = profiles.default_settings()

    if intent is None and profile.id != "music_video":
        intent_value = Intent(kind=profile.id)
    elif intent is None:
        intent_value = None
    elif isinstance(intent, Intent):
        intent_value = intent
    else:
        intent_value = Intent.model_validate(intent)
    if intent_value is not None:
        intent_value = intent_value.model_copy(
            update={
                "kind": profile.id,
                "length_seconds": int(round(duration)),
                "audio_window": window,
            }
        )

    project = Project(
        slug=slug,
        schema_version=3,
        title=title.strip() if title is not None else slug.replace("-", " ").title(),
        source_sha256=file_hash(source),
        duration=duration,
        kind=profile.id,
        source_duration=source_duration,
        audio_window=window,
        aspect=aspect,
        fps=fps,
        width=width,
        height=height,
        music_mode=music_mode,
        workflow_version=2,
        prompt_version=2,
        signature_required=profile.signature_required,
        source_filename=source.name,
        renderer_backend="remotion",
        image_model=selected_model,
        image_settings=selected_settings,
        image_seed=image_seed,
        style_preset=preset_id,
        native_size=native_size if native_size is not None else profiles.default_size(aspect),
    )
    (root / "media").mkdir(parents=True)
    shutil.copy2(source, root / project.source)
    write_json(root / "project.json", project.model_dump())
    # New productions use the explicit creative profile; the event map starts empty
    # and reviewed-by-human. No stage is approved on the user's behalf.
    creative = CreativeProfile(look=look, image_rules=image_rules)
    write_json(root / "brief.json", Brief(creative=creative, intent=intent_value).model_dump())
    write_json(root / "work/approvals.json", {})
    write_json(root / "work/assets.json", {})
    write_json(root / "work/tasks.json", {})
    init_events(root)
    if profile.signature_required:
        _init_signature(root, project)
    flow.mark(root)
    return project


def _intake_window(
    profile: kinds.KindProfile,
    source_duration: float,
    *,
    length_seconds,
    window_start,
    fade_in,
    fade_out,
) -> AudioWindow | None:
    """The excerpt contract for this kind; music videos always use the full track."""
    if profile.id == "music_video":
        if length_seconds is not None or float(window_start or 0) or fade_in or fade_out:
            raise ValueError("a music video uses the whole track; no excerpt window")
        return None
    if length_seconds is None:
        if profile.allows_full_track:
            return None
        raise ValueError("an advert needs a target length")
    try:
        length = float(length_seconds)
        start = float(window_start or 0)
        fade_start = float(fade_in or 0)
        fade_end = float(fade_out or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("length, window start and fades must be numbers") from exc
    if length < 1:
        raise ValueError("the excerpt must be at least one second")
    if start < 0:
        raise ValueError("the excerpt start cannot be negative")
    if start + length > source_duration + 1e-6:
        raise ValueError("the excerpt ends after the source recording")
    return AudioWindow(
        start=round(start, 6),
        end=round(start + length, 6),
        fade_in=round(fade_start, 6),
        fade_out=round(fade_end, 6),
    )


def _matching_preset(look: str | None) -> styles.StylePreset | None:
    if not look:
        return None
    for value in styles.presets():
        if look == value.look or look.startswith(value.look + "\n\n"):
            return value
    return None


def _init_signature(root: Path, project: Project) -> None:
    """The music-video signature package; other kinds never inherit it."""
    from ..signature import credits_template, draft_spec

    spec = draft_spec(project.title)
    template = credits_template(root.parent)
    if template:
        spec["credits"]["cards"] = template
    spec["renderer"] = "remotion"
    spec["design"] = "joint-v1"
    spec["intro"]["names"] = "MAHA KALA  ◆  VJDJ69"
    from ..models import BrandPackage

    write_json(
        root / "brand.json",
        BrandPackage(
            id="mh-vj-filmstrip",
            mark="filmstrip",
            plate=False,
            name=spec["intro"]["names"],
            accent="#D4AE6A",
        ).model_dump(),
    )
    write_json(root / "work/graphics-spec.json", spec)


@state_mutation
def apply_intake(
    root: Path,
    *,
    intent: dict | None = None,
    style_preset: str | None = None,
    audio_window: dict | None = None,
) -> dict:
    """Apply the Story intake card as one validated change.

    A window change is refused once timed artifacts exist, because silently
    shifting a storyboard or lyric map would make every later approval a lie.
    """
    project = load_project(root)
    brief = load_brief(root)
    analysis_needed = False
    previous_window = project.audio_window
    if audio_window is not None:
        project, analysis_needed = _apply_window(root, project, audio_window)
    if style_preset is not None:
        if style_preset == "":
            # An explicit empty value detaches the film from a preset and keeps
            # the look the owner already has. The protected-core rule only
            # applies while a protected preset stays selected.
            project = project.model_copy(update={"style_preset": None})
        else:
            chosen = styles.preset(style_preset)
            project = project.model_copy(update={"style_preset": chosen.id})
            creative = brief.creative or CreativeProfile()
            brief = brief.model_copy(
                update={
                    "creative": creative.model_copy(
                        update={"look": chosen.look, "image_rules": list(chosen.image_rules)}
                    )
                }
            )
    if intent is not None:
        if not isinstance(intent, dict):
            raise ValueError("intent must be a JSON object")
        current = (
            brief.intent.model_dump()
            if brief.intent is not None
            else {"kind": project.kind or "music_video"}
        )
        merged = _merge_patch(current, intent)
        try:
            value = Intent.model_validate(merged)
        except ValueError as exc:
            raise ValueError(f"intent is invalid: {exc}") from exc
        if project.kind is not None and value.kind != project.kind:
            value = value.model_copy(update={"kind": project.kind})
        if project.kind in ("promo", "advert"):
            value = value.model_copy(
                update={
                    "length_seconds": int(round(project.duration)),
                    "audio_window": project.audio_window,
                }
            )
        brief = brief.model_copy(update={"intent": value})
    elif brief.intent is not None and project.kind in ("promo", "advert"):
        brief = brief.model_copy(
            update={
                "intent": brief.intent.model_copy(
                    update={
                        "length_seconds": int(round(project.duration)),
                        "audio_window": project.audio_window,
                    }
                )
            }
        )
    # Last before the writes, so a refused intake keeps the story on the song. A new fade
    # plays the same music at the same times, so only a new start or end sets it aside.
    window = project.audio_window
    if window is not None and (
        previous_window is None
        or (previous_window.start, previous_window.end) != (window.start, window.end)
    ):
        from .. import story_beats

        story_beats.set_aside(root)
    write_json(root / "project.json", project.model_dump())
    write_json(root / "brief.json", brief.model_dump())
    return {
        "project": project,
        "brief": brief,
        "analysis_needed": analysis_needed,
    }


def _apply_window(root: Path, project: Project, payload: dict) -> tuple[Project, bool]:
    if project.kind in (None, "music_video"):
        raise ValueError("music videos use the whole track; no excerpt window")
    if not isinstance(payload, dict):
        raise ValueError("audio window must be a JSON object")
    try:
        window = AudioWindow.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"audio window is invalid: {exc}") from exc
    source_duration = project.source_duration
    if source_duration is None:
        source_duration = audio_seconds(inside(root, project.source))
    if window.end > source_duration + 1e-6:
        raise ValueError("audio window ends after the source recording")
    unchanged = (
        project.audio_window is not None
        and project.audio_window.model_dump() == window.model_dump()
    )
    if unchanged:
        return project, False

    board_path = root / "work" / "storyboard.json"
    if board_path.is_file():
        raise ValueError(
            "a storyboard already exists; rebuild it before changing the excerpt window"
        )
    events = read_optional(root / STAGE_FILES["events"], {})
    if isinstance(events, dict) and events.get("events"):
        raise ValueError(
            "musical events already exist; rebuild the event map before changing the excerpt"
        )
    lyrics = read_optional(root / STAGE_FILES["lyrics"], {})
    if isinstance(lyrics, dict) and lyrics.get("segments"):
        raise ValueError("lyrics already exist; rebuild the lyric map before changing the excerpt")

    for relative in ("work/music.json", "work/music-deep.json"):
        (root / relative).unlink(missing_ok=True)
    value = project.model_copy(
        update={
            "duration": window.duration,
            "source_duration": source_duration,
            "audio_window": window,
        }
    )
    return value, True
