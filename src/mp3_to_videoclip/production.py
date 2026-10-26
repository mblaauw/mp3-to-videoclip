"""Local creative artifacts, approvals and independently reusable image versions."""

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import flow, kinds, localplate, profiles, shotkinds, styles
from .branding import brand_hash, load_brand
from .models import (
    AudioWindow,
    Brief,
    CreativeProfile,
    EventMap,
    Intent,
    Lyrics,
    Project,
    RenderShot,
    Shot,
    Storyboard,
    Treatments,
)
from .render import audio_seconds, probe
from .storage import digest, file_hash, inside, read_json, read_optional, write_json

STAGE_FILES = {
    "analysis": "work/music.json",
    "lyrics": "work/lyrics.json",
    "events": "work/events.json",
    "brief": "brief.json",
    "storyboard": "work/storyboard.json",
    "preview": "work/preview-review.json",
    "listening": "work/music-listening.json",
    "brand": "brand.json",
    "graphics": "work/graphics-review.json",
}
UPSTREAM = {
    "analysis": None,
    "lyrics": "analysis",
    "events": "analysis",
    "listening": "analysis",
    "brand": "analysis",
    "brief": "lyrics",
    "storyboard": "brief",
    "proof": "storyboard",
    "preview": "proof",
    "stills": "proof",
    "graphics": "stills",
}

# Framing is visual content, not a camera move: it is transmitted to the model.
FRAMING_TEXT = {
    "wide": "wide establishing shot",
    "medium": "medium shot",
    "close_up": "close-up",
    "detail": "detail shot",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


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
    from .signature import credits_template, draft_spec

    spec = draft_spec(project.title)
    template = credits_template(root.parent)
    if template:
        spec["credits"]["cards"] = template
    spec["renderer"] = "remotion"
    spec["design"] = "joint-v1"
    spec["intro"]["names"] = "MAHA KALA  ◆  VJDJ69"
    from .models import BrandPackage

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


def load_project(root: Path, verify_source=True) -> Project:
    project = Project.model_validate(read_json(root / "project.json"))
    if verify_source and file_hash(inside(root, project.source)) != project.source_sha256:
        raise ValueError("copied source changed; create a new production instead")
    return project


def creative_workflow(project: Project) -> bool:
    """The guided creative workflow, whether recorded as v2 or as schema 3.

    Schema 3 is the migrated/native form of workflow 2: creative profile, resolved
    character state, bound references, accepted image reviews. Schema-1 projects
    without the v2 marker keep their historical legacy behaviour.
    """
    return project.workflow_version == 2 or project.schema_version == 3


def requires_signature(root: Path, project: Project | None = None) -> bool:
    """Whether delivery needs the graphics signature pass.

    The recorded flag is authoritative. A migrated schema-3 production may have
    lost it; its graphics spec proves the film was authored with a signature, so
    a missing flag must never silently turn a base into a delivery render.
    """
    project = project or load_project(root)
    if project.signature_required is not None:
        return project.signature_required
    if project.kind is not None:
        return kinds.get(project.kind).signature_required
    return project.schema_version == 3 and (root / "work" / "graphics-spec.json").is_file()


def prompt_look_first(project: Project) -> bool:
    """The v2 prompt layout puts the global look before the shot text."""
    return project.prompt_version == 2 or project.schema_version == 3


def project_payload(project: Project) -> dict:
    """Legacy projects never serialized ``music_mode``; keep their hashes stable."""
    value = project.model_dump()
    # Backend choice cannot change measured music or generation inputs. Render
    # receipts/previews bind it explicitly with the implementation revision.
    value.pop("renderer_backend", None)
    # The cap and its top-up history are administrative: adding budget must not
    # invalidate a creative approval.
    value.pop("budget", None)
    if value.get("music_mode") is None:
        value.pop("music_mode", None)
    return value


def legacy_brief_hash(brief: Brief) -> str:
    """Legacy content hash: the new creative profile is not part of old artifacts."""
    return digest(brief.model_dump(exclude={"creative"}))


def load_brief(root: Path) -> Brief:
    return Brief.model_validate(read_json(root / "brief.json"))


def _merge_patch(target, patch):
    """RFC 7396 JSON Merge Patch; ``None`` removes a key, objects merge deeply."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = _merge_patch(result.get(key), value)
        else:
            result[key] = value
    return result


def update_brief(root: Path, patch: dict) -> Brief:
    """Apply one validated merge patch and keep the previous brief in history."""
    if not isinstance(patch, dict):
        raise ValueError("brief patch must be a JSON object")
    previous = load_brief(root)
    previous_value = previous.model_dump()
    merged = _merge_patch(previous_value, patch)
    try:
        brief = Brief.model_validate(merged)
    except ValueError as exc:
        raise ValueError(f"brief patch is invalid: {exc}") from exc
    if brief.model_dump() == previous_value:
        return previous
    history = root / f"work/brief-history/{digest(previous_value)}.json"
    if not history.exists():
        write_json(history, previous_value)
    write_json(root / "brief.json", brief.model_dump())
    _record_prompt_write(root, "brief")
    return brief


def update_treatments(root: Path, payload: dict) -> Treatments:
    """Write exactly three structurally distinct concepts as one validated artifact."""
    if not isinstance(payload, dict):
        raise ValueError("treatments must be a JSON object")
    try:
        treatments = Treatments.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"treatments are invalid: {exc}") from exc
    value = treatments.model_dump()
    path = root / "work" / "treatments.json"
    previous = read_optional(path)
    if previous == value:
        return treatments
    if isinstance(previous, dict):
        history = root / f"work/treatments-history/{digest(previous)}.json"
        if not history.exists():
            write_json(history, previous)
    write_json(path, value)
    _record_prompt_write(root, "treatments")
    return treatments


def load_treatments(root: Path) -> Treatments | None:
    path = root / "work" / "treatments.json"
    if not path.is_file():
        return None
    return Treatments.model_validate(read_json(path))


def _record_prompt_write(root: Path, artifact: str) -> None:
    from . import promptlog

    promptlog.record(root, artifact)


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
    if audio_window is not None:
        project, analysis_needed = _apply_window(root, project, audio_window)
    if style_preset:
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


def render_audio(root: Path, project: Project | None = None) -> Path:
    """The excerpt for a promo/advert, or the original for a music video."""
    from . import audio

    return audio.render_audio(root, project or load_project(root))


def is_creative(root: Path) -> bool:
    return load_brief(root).creative is not None


def load_events(root: Path) -> EventMap:
    events = EventMap.model_validate(read_json(root / STAGE_FILES["events"]))
    events.check_project(load_project(root))
    return events


def init_events(root: Path) -> EventMap:
    """Seed an empty, reviewed-by-human event map; never guess structure or meter."""
    path = root / STAGE_FILES["events"]
    if path.exists():
        raise ValueError("musical events already exist; edit them rather than overwrite")
    project = load_project(root)
    events = EventMap(
        source_sha256=project.source_sha256,
        fps=project.fps,
        total_frames=project.total_frames,
        pulse="unknown",
    )
    write_json(path, events.model_dump())
    return events


def load_board(root: Path, *, verify_source: bool = True) -> Storyboard:
    board = Storyboard.model_validate(read_json(root / STAGE_FILES["storyboard"]))
    return validate_board(root, board, verify_source=verify_source)


def validate_board(root: Path, board: Storyboard, *, verify_source: bool = True) -> Storyboard:
    """Validate a candidate board against the project, brief and event map.

    Kept separate from ``load_board`` so writers can validate a board before it
    reaches disk, and so read-only snapshots can skip re-hashing the source MP3.
    """
    board.check_project(load_project(root, verify_source=verify_source))
    brief = load_brief(root)
    creative = brief.creative
    characters = {c.id for c in brief.characters}
    scenes = {s.id for s in creative.scenes} if creative else set()
    references = {r.id for r in creative.references} if creative else set()
    event_ids = None
    if any(shot.event_ids for shot in board.shots):
        if not (root / STAGE_FILES["events"]).exists():
            raise ValueError("storyboard binds musical events but work/events.json is missing")
        event_ids = {e.id for e in load_events(root).events}
    for shot in board.shots:
        if not set(shot.character_ids) <= characters:
            raise ValueError(f"unknown character in shot {shot.id}")
        if not set(shot.character_states) <= set(shot.character_ids):
            raise ValueError(f"state binding must name a bound character in shot {shot.id}")
        if not set(shot.state_requirements) <= set(shot.character_ids):
            raise ValueError(f"state requirements must name a bound character in shot {shot.id}")
        for cid, state_id in shot.character_states.items():
            character = next(c for c in brief.characters if c.id == cid)
            if state_id not in character.states:
                raise ValueError(f"unknown state {state_id} for {cid} in shot {shot.id}")
        if shot.scene_id is not None and shot.scene_id not in scenes:
            raise ValueError(f"unknown scene in shot {shot.id}")
        if not set(shot.reference_ids) <= references:
            raise ValueError(f"unknown reference in shot {shot.id}")
        if event_ids is not None and not set(shot.event_ids) <= event_ids:
            raise ValueError(f"unknown musical event in shot {shot.id}")
        if shot.asset_shot_id is not None:
            target = next((s for s in board.shots if s.id == shot.asset_shot_id), None)
            if target is None or target.id == shot.id or target.asset_shot_id is not None:
                raise ValueError(
                    "reused image must name a different, existing source shot (no chains/cycles)"
                )
        if shot.kind == "split":
            known = {s.id for s in board.shots}
            for pane in shot.panes:
                if pane.shot_id not in known:
                    raise ValueError(f"unknown split pane {pane.shot_id!r} in shot {shot.id}")
                source = next(s for s in board.shots if s.id == pane.shot_id)
                if source.kind == "split":
                    raise ValueError("split panes cannot themselves be splits")
        if shot.kind == "upload" and shot.asset is not None:
            if not inside(root, shot.asset).is_file():
                raise ValueError(f"upload asset is missing for shot {shot.id}")
        if shot.kind == "product" and shot.product_ref is not None:
            if shot.product_ref not in references and not inside(root, shot.product_ref).is_file():
                raise ValueError(
                    f"product_ref {shot.product_ref!r} is neither a known reference nor a file"
                )
        if shot.kind == "product" and shot.asset is not None:
            if not inside(root, shot.asset).is_file():
                raise ValueError(f"product asset is missing for shot {shot.id}")
    return board


def update_shots(root: Path, changes: list[dict]) -> tuple[Storyboard, list[str]]:
    """Apply named shot edits atomically after validating the whole board."""
    if not isinstance(changes, list):
        raise ValueError("shot changes must be a list")
    board = load_board(root)
    from . import edits

    existing_edit = edits.load_edit(root, board=board)
    if existing_edit is not None:
        for change in changes:
            if not isinstance(change, dict):
                continue
            owned = set(change) & edits.EDIT_OWNED
            if owned:
                raise ValueError(
                    "work/edit.json owns timing and motion; change "
                    + ", ".join(sorted(owned))
                    + " in the Film cut instead"
                )
    raw = board.model_dump()
    by_id = {shot["id"]: shot for shot in raw["shots"]}
    changed: list[str] = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("each shot change must be an object")
        shot_id = change.get("id")
        if not isinstance(shot_id, str) or shot_id not in by_id:
            raise ValueError(f"unknown shot ID: {shot_id!r}")
        unknown = set(change) - set(Shot.model_fields)
        if unknown:
            raise ValueError(f"unknown shot field(s): {', '.join(sorted(unknown))}")
        merged = {**by_id[shot_id], **{key: value for key, value in change.items() if key != "id"}}
        by_id[shot_id] = Shot.model_validate(merged).model_dump()
        if shot_id not in changed:
            changed.append(shot_id)
    candidate = Storyboard.model_validate(
        {**raw, "shots": [by_id[shot["id"]] for shot in raw["shots"]]}
    )
    updated = validate_board(root, candidate)
    if changed:
        write_json(root / STAGE_FILES["storyboard"], updated.model_dump())
        _record_prompt_write(root, "storyboard")
    return updated, changed


def _reference_cap(project: Project) -> int:
    """Stored-model profiles may use the current model capacity; legacy stays at four."""
    return 14 if project.image_model is not None else 4


def character_refs(root: Path, brief: Brief, character_ids: list[str], states=None) -> list[dict]:
    refs = []
    for character in brief.characters:
        if character.id in character_ids:
            if not character.permission_confirmed:
                raise ValueError(f"permission to upload/depict {character.id} is not confirmed")
            state_id = (states or {}).get(character.id, character.default_state)
            state = character.states.get(state_id) if state_id else None
            paths = [*character.references, *(state.references if state else [])]
            for relative in paths:
                path = inside(root, relative)
                with Image.open(path) as image:
                    image.verify()
                refs.append({"path": relative, "sha256": file_hash(path)})
    # Shared reference files are sent once; quote-time live schema sets capacity.
    return list({item["path"]: item for item in refs}.values())


def reference_refs(root: Path, brief: Brief, reference_ids: list[str]) -> list[dict]:
    """Permission/path/byte guard for declared style/location/prop references."""
    creative = brief.creative
    known = {r.id: r for r in creative.references} if creative else {}
    refs = []
    for ref_id in reference_ids:
        reference = known.get(ref_id)
        if reference is None:
            raise ValueError(f"unknown visual reference {ref_id}")
        if not reference.permission_confirmed:
            raise ValueError(f"permission to upload/depict {ref_id} is not confirmed")
        path = inside(root, reference.path)
        with Image.open(path) as image:
            image.verify()
        refs.append({"path": reference.path, "sha256": file_hash(path)})
    return list({item["path"]: item for item in refs}.values())


def brief_references(root: Path, brief: Brief) -> list[dict]:
    """Every declared reference file bound into the brief approval hash."""
    refs = character_refs(root, brief, [c.id for c in brief.characters])
    for character in brief.characters:
        for state_id in character.states:
            refs += character_refs(root, brief, [character.id], {character.id: state_id})
    if brief.creative is not None:
        refs += reference_refs(root, brief, [r.id for r in brief.creative.references])
    return list({item["path"]: item for item in refs}.values())


def _legacy_image_spec(root: Path, project: Project, brief: Brief, shot: Shot) -> dict:
    refs = character_refs(root, brief, shot.character_ids)
    product_line = ""
    if shot.product_ref is not None:
        path = inside(root, shot.product_ref)
        with Image.open(path) as image:
            image.verify()
        refs.append({"path": shot.product_ref, "sha256": file_hash(path)})
        product_line = (
            "Product reference: preserve the supplied product's geometry, label, colour and "
            "material; describe its placement and angle."
        )
    refs = list({item["path"]: item for item in refs}.values())
    limit = _reference_cap(project)
    if len(refs) > limit:
        raise ValueError(f"this production permits at most {limit} reference images per shot")
    descriptions = [c.description for c in brief.characters if c.id in shot.character_ids]
    bridge_line = ""
    if shot.kind == "bridge" and shot.bridge is not None and shot.bridge.match is not None:
        match = shot.bridge.match
        bridge_line = (
            f"Bridge match: align {match.type} at normalized anchor "
            f"({match.anchor[0]:.2f}, {match.anchor[1]:.2f})."
            + (f" {match.note}" if match.note else "")
        )
    prompt = "\n".join(
        filter(
            None,
            [
                brief.style,
                brief.direction,
                *brief.visual_rules,
                shot.image_prompt,
                bridge_line,
                product_line,
                *descriptions,
                "Avoid: " + "; ".join(brief.avoid) if brief.avoid else "",
            ],
        )
    )
    return {
        "shot_id": shot.id,
        "positivePrompt": prompt,
        "size": list(project.image_size),
        "references": refs,
        "brief_hash": legacy_brief_hash(brief),
    }


def creative_profile_version(brief: Brief) -> str:
    """Explicit appearance version; story arc, proof IDs and editorial notes are excluded."""
    creative = brief.creative
    return digest(
        {
            "schema_version": 1,
            "look": creative.look,
            "image_rules": creative.image_rules,
            "avoid": brief.avoid,
        }
    )


def _creative_scene(creative: CreativeProfile, scene_id: str | None):
    if scene_id is None:
        return None
    for scene in creative.scenes:
        if scene.id == scene_id:
            return scene
    raise ValueError(f"unknown scene {scene_id}")


def _require_default_style_core(project: Project, brief: Brief):
    """Validate, never inject: only a protected preset keeps its exact core.

    The photographic-painted core is one selectable preset now. Custom looks and
    the other presets are not forced to start with it.
    """
    if not prompt_look_first(project):
        return
    guarded = styles.protected_preset(project.style_preset)
    if guarded is None:
        return
    if digest(guarded.look) != profiles.STYLE_BENCHMARK["style_core_hash"]:
        raise ValueError(
            "approved style core changed; use a separately reviewed new preset version"
        )
    look = brief.creative.look if brief.creative else ""
    problem = styles.core_problem(project.style_preset, look)
    if problem:
        raise ValueError(problem)


def _creative_image_spec(root: Path, project: Project, brief: Brief, shot: Shot) -> dict:
    _require_default_style_core(project, brief)
    creative = brief.creative
    scene = _creative_scene(creative, shot.scene_id)
    scene_ids = list(scene.reference_ids) if scene else []
    bound_ids = list(
        dict.fromkeys([*shot.reference_ids, *scene_ids, *creative.global_reference_ids])
    )
    by_id = {r.id: r for r in creative.references}
    product_refs: list[dict] = []
    product_role = ""
    if shot.product_ref is not None:
        if shot.product_ref in by_id:
            product_refs = reference_refs(root, brief, [shot.product_ref])
            product_role = by_id[shot.product_ref].description
        else:
            path = inside(root, shot.product_ref)
            with Image.open(path) as image:
                image.verify()
            product_refs = [{"path": shot.product_ref, "sha256": file_hash(path)}]
            product_role = "the supplied product"
    refs = character_refs(root, brief, shot.character_ids, shot.character_states)
    refs += reference_refs(root, brief, bound_ids)
    refs += product_refs
    refs = list({item["path"]: item for item in refs}.values())
    limit = _reference_cap(project)
    if len(refs) > limit:
        if limit == 14:
            raise ValueError(
                "the application permits at most 14 reference images; the live model schema may require fewer"
            )
        raise ValueError(
            "this legacy production permits at most four reference images per shot; the live schema may require fewer"
        )
    characters = []
    for character in brief.characters:
        if character.id not in shot.character_ids:
            continue
        identity = character.identity or character.description
        characters.append(
            f"{character.id} identity: {identity}" if creative_workflow(project) else identity
        )
        state_id = shot.character_states.get(character.id, character.default_state)
        if state_id:
            characters.append(
                f"{character.id} state ({state_id}): {character.states[state_id].description}"
            )
    if creative_workflow(project):
        # State the role of each supplied image rather than inviting the model to
        # copy its incidental background, pose or costume into every new shot.
        roles = []
        for index, ref in enumerate(refs, start=1):
            bound_roles = []
            for c in brief.characters:
                if c.id not in shot.character_ids:
                    continue
                if ref["path"] in c.references:
                    bound_roles.append(f"{c.id} identity")
                sid = shot.character_states.get(c.id, c.default_state)
                if sid and ref["path"] in c.states[sid].references:
                    bound_roles.append(f"{c.id} state {sid}")
            bound_roles += [r.kind for r in creative.references if r.path == ref["path"]]
            role = "; ".join(dict.fromkeys(bound_roles)) or "visual"
            roles.append(
                f"Image {index}: {role} reference; do not copy incidental pose or background."
            )
        characters.extend(roles)
    if product_role:
        characters.append(
            "Product reference: preserve the supplied product's geometry, label, colour and "
            f"material; describe its placement and angle. Product: {product_role}"
        )
    bridge_line = ""
    if shot.kind == "bridge" and shot.bridge is not None and shot.bridge.match is not None:
        match = shot.bridge.match
        bridge_line = (
            f"Bridge match: align {match.type} at normalized anchor "
            f"({match.anchor[0]:.2f}, {match.anchor[1]:.2f})."
            + (f" {match.note}" if match.note else "")
        )
    prompt = "\n".join(
        filter(
            None,
            [
                creative.look if prompt_look_first(project) else "",
                shot.image_prompt,
                bridge_line,
                "Framing: " + FRAMING_TEXT[shot.framing] if shot.framing else "",
                "Must show: " + "; ".join(shot.must_show) if shot.must_show else "",
                scene.description if scene else "",
                *[by_id[i].description for i in bound_ids],
                *characters,
                creative.look if not prompt_look_first(project) else "",
                *creative.image_rules,
                "Avoid: " + "; ".join(brief.avoid) if brief.avoid else "",
            ],
        )
    )
    return {
        "shot_id": shot.id,
        "positivePrompt": prompt,
        "size": list(project.image_size),
        "references": refs,
        "profile_version": creative_profile_version(brief),
    }


def image_spec(root: Path, shot: Shot, *, verify_source: bool = True) -> dict:
    if shot.asset_shot_id is not None:
        board = load_board(root, verify_source=verify_source)
        source = next(s for s in board.shots if s.id == shot.asset_shot_id)
        return image_spec(root, source, verify_source=verify_source)
    if shotkinds.is_local(shot):
        raise ValueError(
            f"shot {shot.id} is a local {shot.kind} shot; it has no image-generation spec"
        )
    project = load_project(root, verify_source=verify_source)
    brief = load_brief(root)
    if brief.creative is None:
        if creative_workflow(project):
            raise ValueError("the creative workflow requires a creative profile for state prompts")
        spec = _legacy_image_spec(root, project, brief, shot)
    else:
        spec = _creative_image_spec(root, project, brief, shot)
    # New kind metadata is included only when non-default, so legacy exact specs
    # and approved input hashes stay untouched.
    if shot.kind != "scene":
        spec["kind"] = shot.kind
    if shot.product_ref is not None:
        spec["product_ref"] = shot.product_ref
    if shot.bridge is not None:
        spec["bridge"] = shot.bridge.model_dump()
    # Missing fields stay missing: old approved image input hashes are untouched.
    if (
        project.image_model is not None
        or project.image_settings is not None
        or project.image_seed is not None
    ):
        spec["generation"] = {
            "model": project.image_model or profiles.LEGACY_MODEL,
            "settings": project.image_settings.model_dump()
            if project.image_settings is not None
            else {},
            "seed": project.image_seed,
        }
    return spec


def proof_ids(board: Storyboard, brief: Brief | None = None) -> list[str]:
    """Legacy positional proof selection, or the new explicit creative selection.

    Only generated source shots can be proof: a card, split, logo or end card is
    inspected in the live Player from its deterministic local plate and never
    enters a paid quote or an accepted-image review.
    """
    paid_sources = [
        shot for shot in board.shots if shot.asset_shot_id is None and shotkinds.is_paid(shot)
    ]
    has_local = any(shot.asset_shot_id is None and shotkinds.is_local(shot) for shot in board.shots)
    if brief is not None and brief.creative is not None:
        selected = list(brief.creative.proof_shot_ids)
        source_ids = {shot.id for shot in paid_sources}
        expected = min(3, len(source_ids))
        if len(selected) != expected:
            raise ValueError(
                f"the creative profile must name exactly {expected} explicit proof shot IDs"
            )
        if len(set(selected)) != len(selected) or not set(selected) <= source_ids:
            raise ValueError("proof shot IDs must be unique, known generated storyboard IDs")
        return selected
    if not has_local:
        return list(
            dict.fromkeys(
                board.shots[i].asset_shot_id or board.shots[i].id
                for i in [0, len(board.shots) // 2, len(board.shots) - 1]
            )
        )
    if not paid_sources:
        return []
    indexes = [0, len(paid_sources) // 2, len(paid_sources) - 1]
    return list(dict.fromkeys(paid_sources[i].id for i in indexes))


def _current_proof_ids(root: Path, board: Storyboard) -> list[str]:
    return proof_ids(board, load_brief(root))


def set_proof_ids(root: Path, shot_ids: list[str]) -> list[str]:
    """Record the explicit proof shots; they are part of the brief's bytes."""
    if not (root / STAGE_FILES["storyboard"]).exists():
        raise ValueError("create the storyboard first")
    if not isinstance(shot_ids, list) or not all(isinstance(value, str) for value in shot_ids):
        raise ValueError("proof shots must be a list of storyboard shot IDs")
    board = load_board(root)
    brief = load_brief(root)
    if brief.creative is None:
        raise ValueError("the creative profile is required for explicit proof shots")
    brief.creative.proof_shot_ids = list(shot_ids)
    proof_ids(board, brief)
    write_json(root / STAGE_FILES["brief"], brief.model_dump())
    _record_prompt_write(root, "proof-shots")
    return list(brief.creative.proof_shot_ids)


def has_placeholders(shot: Shot) -> bool:
    # Marked placeholders, not words such as Spanish "todo" inside lyrics.
    return any(
        re.match(r"^\s*(?:todo|tbd|placeholder)(?:\s*[:\-]|\s*$)", value, re.I)
        for value in (
            shot.purpose,
            shot.message,
            shot.image_prompt,
            shot.motion_prompt,
            shot.music_context,
            shot.lyric_context,
            *shot.text,
            *shot.must_show,
        )
    )


def _local_plate(root: Path, project: Project, shot: Shot) -> Path:
    """Render a local kind; splits resolve their pane stills first."""
    sources: dict[str, Path] = {}
    if shot.kind == "split":
        for pane in shot.panes:
            resolved = resolved_assets(root, [pane.shot_id])
            sources[pane.shot_id] = Path(resolved[0].image)
    asset = None
    if shot.asset is not None:
        try:
            asset = inside(root, shot.asset)
        except ValueError:
            asset = None
    return localplate.render(root, project, shot, asset=asset, sources=sources)


def local_plate_path(root: Path, shot_id: str) -> Path:
    """Resolve one non-paid shot to its current deterministic plate."""
    board = load_board(root)
    shot = next((candidate for candidate in board.shots if candidate.id == shot_id), None)
    if shot is None:
        raise ValueError(f"unknown shot {shot_id}")
    if shot.asset_shot_id is not None or not shotkinds.is_local(shot):
        raise ValueError(f"shot {shot_id} is not a local plate")
    return _local_plate(root, load_project(root), shot)


def resolved_assets(root: Path, ids: list[str] | None = None) -> list[RenderShot]:
    from . import edits

    board = load_board(root)
    edit = edits.load_edit(root, board=board)
    effective = edit.effective_board(board) if edit is not None else board
    project = load_project(root)
    assets = read_json(root / "work/assets.json")
    result = []
    for shot in effective.shots:
        if ids is not None and shot.id not in ids:
            continue
        if shot.asset_shot_id is not None:
            owner_id = shot.asset_shot_id
        elif shotkinds.is_local(shot):
            result.append(RenderShot(shot=shot, image=str(_local_plate(root, project, shot))))
            continue
        else:
            owner_id = shot.id
        entry = assets.get(owner_id, {})
        chosen = next(
            (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None
        )
        if not chosen or chosen["input_hash"] != digest(image_spec(root, shot)):
            raise ValueError(f"shot {shot.id} has no current selected still")
        path = inside(root, chosen["path"])
        if file_hash(path) != chosen["sha256"]:
            raise ValueError(f"selected still for {shot.id} changed")
        result.append(RenderShot(shot=shot, image=str(path)))
    return edits.attach_edit(result, edit)


def effective_upstream(root: Path, stage: str) -> str | None:
    """Return the real parent artifact for a stage's current production kind.

    Promo and advert briefs are built from the measured song and the intent, not
    from a lyrics map: only music videos have a lyrics stage. Instrumental and
    music-led music videos likewise depend on analysis. Creative stills depend on
    the watched preview when that gate applies.
    """
    if stage == "brief":
        project = load_project(root)
        if project.kind not in (None, "music_video"):
            return "analysis"
        if project.music_mode in ("instrumental", "music-led"):
            return "analysis"
    if stage == "stills" and is_creative(root) and flow.settings(root)["preview_gate"]:
        return "preview"
    return UPSTREAM[stage]


def _required_parents(root: Path, stage: str) -> list[str]:
    # Guided productions treat music analysis, events and the brand package as
    # agent-owned evidence: their bytes still bind into the brief hash, but the
    # user is not asked to certify tempo, meter or section estimates before
    # agreeing the story. Recorded v2 productions keep every upstream gate.
    if stage == "brief" and flow.settings(root)["guided"]:
        return []
    upstream = effective_upstream(root, stage)
    parents = [upstream] if upstream else []
    if stage == "brief" and (root / STAGE_FILES["events"]).exists() and is_creative(root):
        parents.append("events")
    if stage == "brief" and (root / STAGE_FILES["brand"]).exists():
        parents.append("brand")
    if (
        stage == "brief"
        and load_project(root).music_mode == "music-led"
        and (root / STAGE_FILES["listening"]).exists()
    ):
        parents.append("listening")
    return parents


def preview_board_hash(root: Path):
    """Only inputs visible in a proof-only animatic, for new workflows.

    Changing a placeholder's generation prompt still requires storyboard review,
    but cannot change a movie which never displayed that future image.
    """
    value = read_json(root / STAGE_FILES["storyboard"])
    from . import edits

    board = Storyboard.model_validate(value)
    edit = edits.load_edit(root, board=board)
    if not creative_workflow(load_project(root)):
        if edit is not None:
            return digest({"storyboard": value, "edit": edit.model_dump(by_alias=True)})
        return digest(value)
    keys = (
        "id",
        "start_frame",
        "duration_frames",
        "purpose",
        "framing",
        "camera",
        "camera_path",
        "dissolve_frames",
        "asset_shot_id",
    )
    payload = {
        "fps": value["fps"],
        "aspect": value["aspect"],
        "total_frames": value["total_frames"],
        "shots": [
            {
                **{k: s.get(k) for k in keys},
                **{k: s[k] for k in ("camera_keyframes", "post_effects", "transition") if k in s},
            }
            for s in value["shots"]
        ],
    }
    if edit is not None:
        payload["edit"] = edit.model_dump(by_alias=True)
    return digest(payload)


def check_preview_binding(root: Path, report: dict):
    """Bind a reviewed preview to the current storyboard, proof set and movie bytes."""
    for key in ("movie", "movie_sha256", "storyboard_hash", "proof_hash"):
        if not report.get(key):
            raise ValueError(f"preview review report is missing {key}")
    if report["storyboard_hash"] != preview_board_hash(root):
        raise ValueError("preview was generated from a different storyboard; re-render and review")
    if report["proof_hash"] != stage_hash(root, "proof"):
        raise ValueError("preview was generated from a different proof set; re-render and review")
    if report.get("brand_hash") != brand_hash(root):
        raise ValueError("brand changed since preview; re-render and review")
    if load_project(root).uses_remotion:
        from .remotion import implementation_hash

        if report.get("renderer_revision") != implementation_hash():
            raise ValueError("Remotion changed since preview; re-render and review")
    movie = inside(root, report["movie"])
    if not movie.is_file():
        raise ValueError("reviewed preview movie is missing")
    if file_hash(movie) != report["movie_sha256"]:
        raise ValueError("reviewed preview movie changed; re-render and review")


def _local_proof_entries(root: Path, board: Storyboard, project: Project) -> list[dict]:
    """Bind local plate bytes where they can render, otherwise their definition.

    A split whose pane stills do not exist yet cannot be photographed; the proof
    gate still binds the shot definition, and the later stills gate binds the
    actual plate bytes.
    """
    entries = []
    for shot in board.shots:
        if shot.asset_shot_id is not None or shotkinds.is_paid(shot):
            continue
        try:
            path = _local_plate(root, project, shot)
        except (OSError, ValueError):
            entries.append({"id": shot.id, "definition": digest(shot.model_dump())})
        else:
            entries.append({"id": shot.id, "image": file_hash(path)})
    return entries


def stage_hash(root: Path, stage: str) -> str:
    project = load_project(root)
    upstream = effective_upstream(root, stage)
    # The current storyboard must still be explicitly approved (parents are
    # checked by require_approval). Proof identity depends only on proof inputs,
    # not on a generation-only correction to an unseen placeholder.
    parent = (
        None
        if stage == "proof" and creative_workflow(project)
        else (stage_hash(root, upstream) if upstream else None)
    )
    if stage == "preview":
        value = read_json(root / STAGE_FILES["preview"])
        check_preview_binding(root, value)
    elif stage == "brand":
        value = {"package": read_json(root / STAGE_FILES[stage]), "render_hash": brand_hash(root)}
    elif stage in STAGE_FILES:
        value = read_json(root / STAGE_FILES[stage])
        if stage == "brief":
            brief = Brief.model_validate(value)
            value = {"brief": value, "references": brief_references(root, brief)}
            if requires_signature(root, project) and not flow.settings(root)["late_credits"]:
                value["signature"] = digest(read_json(root / "work/graphics-spec.json"))
            if (root / STAGE_FILES["events"]).exists():
                value["events"] = digest(read_json(root / STAGE_FILES["events"]))
            if (root / STAGE_FILES["brand"]).exists():
                value["brand_hash"] = brand_hash(root)
            if project.music_mode == "music-led" and (root / STAGE_FILES["listening"]).exists():
                value["listening"] = stage_hash(root, "listening")
    else:
        board = load_board(root)
        if stage == "proof":
            shots = resolved_assets(root, _current_proof_ids(root, board))
            value = [{"id": s.shot.id, "image": file_hash(Path(s.image))} for s in shots]
            if creative_workflow(project):
                value = [
                    {**item, "input_hash": digest(image_spec(root, rs.shot))}
                    for item, rs in zip(value, shots, strict=True)
                ]
            value += _local_proof_entries(root, board, project)
        else:
            shots = resolved_assets(root)
            value = [{"id": s.shot.id, "image": file_hash(Path(s.image))} for s in shots]
            from . import edits

            if stage == "stills":
                edit = edits.load_edit(root, board=board)
                if edit is not None:
                    value = {"assets": value, "edit": edit.model_dump(by_alias=True)}
    return digest({"project": project_payload(project), "upstream": parent, "content": value})


def require_approval(root: Path, stage: str):
    """Check gates; Studio attestations are consistency claims, not proof of human acts."""
    if stage == "lyrics" and load_project(root).music_mode == "instrumental":
        raise ValueError("instrumental projects have no lyrics stage to approve")
    for parent in _required_parents(root, stage):
        require_approval(root, parent)
    record = read_json(root / "work/approvals.json").get(stage)
    if not record:
        raise ValueError(f"{stage} needs current user approval")
    try:
        current_hash = stage_hash(root, stage)
    except FileNotFoundError as exc:
        raise ValueError(
            f"{stage} review artifact is missing; recreate and obtain current user approval"
        ) from exc
    if record["hash"] != current_hash:
        raise ValueError(f"{stage} needs current user approval")
    if record.get("via") == "studio":
        complete = record.get("review_confirmed") is True
        if stage == "preview":
            complete = complete and record.get("preview_watched") is True
        if stage == "graphics":
            complete = complete and record.get("inspected") is True
        if stage == "lyrics":
            lyrics = Lyrics.model_validate(read_json(root / STAGE_FILES[stage]))
            if any(segment.flags for segment in lyrics.segments):
                complete = complete and record.get("acknowledge_uncertain") is True
        if not complete:
            raise ValueError(
                f"{stage} Studio approval is incomplete; review and decide again in Studio"
            )
    if stage == "graphics":
        from .signature import validate_review

        validate_review(root, load_project(root))
    if stage in ("proof", "stills") and creative_workflow(load_project(root)):
        from .reviews import require_accepted

        board = load_board(root)
        ids = (
            proof_ids(board, load_brief(root))
            if stage == "proof"
            else [s.id for s in board.shots if shotkinds.is_paid(s)]
        )
        require_accepted(root, ids)


def _require_reference_permissions(brief: Brief):
    for character in brief.characters:
        if not character.permission_confirmed:
            raise ValueError(f"permission to upload/depict {character.id} is not confirmed")
    for reference in brief.creative.references if brief.creative else []:
        if not reference.permission_confirmed:
            raise ValueError(f"permission to upload/depict {reference.id} is not confirmed")


def approve(
    root: Path,
    stage: str,
    note: str,
    acknowledge_uncertain=False,
    *,
    inspected=False,
    expected_hash: str | None = None,
    via: str | None = None,
    preview_watched: bool = False,
    review_confirmed: bool | None = None,
):
    if not note.strip():
        raise ValueError("record the user's approval decision in --note")
    if via == "studio" and review_confirmed is not True:
        raise ValueError("Studio decisions require explicit review confirmation")
    if via == "studio" and stage == "preview" and preview_watched is not True:
        raise ValueError("confirm continuous preview playback with the actual music")
    if stage == "lyrics" and load_project(root).music_mode == "instrumental":
        raise ValueError(
            "instrumental projects have no lyrics stage; approve the analysis and events instead"
        )
    for parent in _required_parents(root, stage):
        require_approval(root, parent)
    if stage == "lyrics":
        lyrics = Lyrics.model_validate(read_json(root / STAGE_FILES[stage]))
        project = load_project(root)
        if not lyrics.segments:
            raise ValueError("empty lyrics cannot be approved for this vocal project")
        for segment in lyrics.segments:
            if segment.end > project.duration + 0.1:
                raise ValueError("lyric timestamps extend beyond the source")
        if any(s.flags for s in lyrics.segments) and not acknowledge_uncertain:
            raise ValueError("review/correct flagged lyrics, then explicitly --ack-uncertain")
    elif stage == "brief":
        brief = load_brief(root)
        _require_default_style_core(load_project(root), brief)
        if requires_signature(root) and not flow.settings(root)["late_credits"]:
            from .signature import validate_spec

            validate_spec(root, load_project(root))
        _require_reference_permissions(brief)
        if creative_workflow(load_project(root)) and brief.creative is None:
            raise ValueError("the creative workflow requires a creative profile")
        if not all(x.strip() for x in [brief.direction, brief.style, brief.treatment]):
            raise ValueError("choose a treatment, direction and style before approval")
        if brief.creative is not None and not brief.creative.look.strip():
            raise ValueError("define creative.look (global appearance only) before approval")
        if creative_workflow(load_project(root)):
            from .references import validate_import

            for character in brief.characters:
                if not character.identity:
                    raise ValueError("workflow 2 characters need identity separate from shot state")
            for ref in brief_references(root, brief):
                validate_import(root, ref["path"])
    elif stage == "storyboard":
        board = load_board(root)
        if any(has_placeholders(s) for s in board.shots):
            raise ValueError("finish storyboard placeholders before approval")
        # A creative profile must name its own explicit proof selection.
        proof_ids(board, load_brief(root))
        if creative_workflow(load_project(root)):
            from .preflight import validate_before_spend

            validate_before_spend(root, [s.id for s in board.shots])
    elif stage == "analysis":
        data = read_json(root / STAGE_FILES[stage])
        if abs(data["duration"] - load_project(root).duration) > 0.05:
            raise ValueError("analysis does not match the source duration")
    elif stage == "events":
        load_events(root)  # Source identity, frame bounds and ordering.
    elif stage == "brand":
        brand = load_brand(root)
        if brand is None or brand.duration_seconds > load_project(root).duration:
            raise ValueError("brand intro is missing or longer than the music")
    elif stage == "listening":
        from .music_analysis import load_listening

        load_listening(root)
    elif stage == "graphics":
        from .signature import validate_review

        if not inspected:
            raise ValueError(
                "inspect the actual composited graphics samples, then approve graphics with --inspected"
            )
        validate_review(root, load_project(root))
    if stage in ("proof", "stills") and creative_workflow(load_project(root)):
        from .reviews import require_accepted

        board = load_board(root)
        ids = (
            proof_ids(board, load_brief(root))
            if stage == "proof"
            else [s.id for s in board.shots if shotkinds.is_paid(s)]
        )
        require_accepted(root, ids)
    approvals = read_json(root / "work/approvals.json")
    current = stage_hash(root, stage)
    if expected_hash is not None and current != expected_hash:
        raise ValueError("stage changed during review; inspect its current artifacts again")
    approvals[stage] = {"hash": current, "at": now(), "note": note}
    if via is not None:
        approvals[stage].update(
            via=via, inspected=bool(inspected), acknowledge_uncertain=bool(acknowledge_uncertain)
        )
        if via == "studio":
            approvals[stage]["review_confirmed"] = True
            if stage == "preview":
                approvals[stage]["preview_watched"] = bool(preview_watched)
    write_json(root / "work/approvals.json", approvals)


def skeleton(root: Path, nominal_seconds=None, timing=None, *, min_seconds=None, max_seconds=None):
    """Build a timing-only skeleton (TODO content, never creative approval).

    ``timing`` selects the boundary source: ``beats`` (local beat estimates),
    ``events`` (reviewed *manual* musical-event boundaries; the nearest boundary
    within one second of the nominal target is acceptable, so shots are
    music-aware rather than rigidly uniform) or ``free`` (uniform, no beats).
    Shot IDs stay stable and the timeline always covers ``total_frames`` exactly.
    """
    require_approval(root, "brief")
    if (root / STAGE_FILES["storyboard"]).exists():
        raise ValueError("storyboard already exists; edit it rather than overwrite")
    project = load_project(root)
    new_film = creative_workflow(project)
    if timing is None:
        timing = "adaptive" if project.image_model is not None else "beats"
    if timing not in ("adaptive", "beats", "events", "free"):
        raise ValueError("timing must be adaptive, beats, events or free")
    if nominal_seconds is None:
        nominal_seconds = (5 if new_film else 8) if timing == "adaptive" else 10
    if min_seconds is None:
        min_seconds = 1.5 if new_film else 4
    if max_seconds is None:
        max_seconds = 7 if new_film else 12
    if timing == "adaptive":
        from .pacing import plan_boundaries

        local = read_json(root / STAGE_FILES["analysis"])
        event_frames = []
        if (root / STAGE_FILES["events"]).exists():
            # Guided productions treat measured evidence as agent-owned; the
            # brief already binds the event bytes. Older flows still certify it.
            if not flow.settings(root)["guided"]:
                require_approval(root, "events")
            for event in load_events(root).events:
                if event.timing_basis == "manual":
                    event_frames += [event.frame] + (
                        [event.end_frame] if event.end_frame is not None else []
                    )
        boundaries = plan_boundaries(
            project.total_frames,
            project.fps,
            target_seconds=nominal_seconds,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            event_frames=event_frames,
            change_frames=[
                round(float(c["time"]) * project.fps) for c in local.get("candidate_changes", [])
            ],
            beat_frames=[round(float(t) * project.fps) for t in local.get("beats", [])],
        )
        shots = [
            Shot(
                id=f"s{i + 1:03d}",
                start_frame=start,
                duration_frames=end - start,
                purpose="TODO: approved story purpose",
                image_prompt="TODO: compose this shot",
            )
            for i, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False))
        ]
        board = Storyboard(
            aspect=project.aspect, fps=project.fps, total_frames=project.total_frames, shots=shots
        )
        write_json(root / STAGE_FILES["storyboard"], board.model_dump())
        return board
    boundaries: list[int] = []
    if timing == "beats":
        music = read_json(root / STAGE_FILES["analysis"])
        boundaries = sorted({round(float(t) * project.fps) for t in music["beats"]})
    elif timing == "events":
        require_approval(root, "events")
        event_map = load_events(root)  # Validates source identity and frame bounds.
        reviewed = [e for e in event_map.events if e.timing_basis == "manual"]
        if len(reviewed) != len(event_map.events):
            raise ValueError("estimated event boundaries are not usable; review them as manual")
        if not reviewed:
            raise ValueError(
                "event timing needs reviewed (manual) musical events; add and approve them first"
            )
        boundaries = sorted(
            {e.frame for e in reviewed} | {e.end_frame for e in reviewed if e.end_frame is not None}
        )
    shots, cursor = [], 0
    target = max(1, round(nominal_seconds * project.fps))
    while cursor < project.total_frames:
        ideal = min(cursor + target, project.total_frames)
        candidates = [
            b
            for b in boundaries
            if cursor + project.fps <= b <= project.total_frames and abs(b - ideal) <= project.fps
        ]
        end = (
            min(candidates, key=lambda b: abs(b - ideal))
            if candidates and ideal < project.total_frames
            else ideal
        )
        # Avoid a tiny accidental final remainder.
        if project.total_frames - end < (
            min(project.fps, target) if timing == "free" else project.fps
        ):
            end = project.total_frames
        shots.append(
            Shot(
                id=f"s{len(shots) + 1:03d}",
                start_frame=cursor,
                duration_frames=end - cursor,
                purpose="TODO: approved story purpose",
                image_prompt="TODO: compose this shot",
            )
        )
        cursor = end
    board = Storyboard(
        aspect=project.aspect, fps=project.fps, total_frames=project.total_frames, shots=shots
    )
    write_json(root / STAGE_FILES["storyboard"], board.model_dump())
    return board


def select_asset(root: Path, shot_id: str, version: int):
    board = load_board(root)
    shot = next((s for s in board.shots if s.id == shot_id), None)
    owner = (shot.asset_shot_id or shot.id) if shot else shot_id
    assets = read_json(root / "work/assets.json")
    if not any(v["version"] == version for v in assets.get(owner, {}).get("versions", [])):
        raise ValueError("unknown image version")
    assets[owner]["selected"] = version
    write_json(root / "work/assets.json", assets)


def record_asset(root: Path, shot_id: str, version: int, path: Path, input_hash: str, task_id: str):
    assets = read_json(root / "work/assets.json")
    entry = assets.setdefault(shot_id, {"versions": [], "selected": None})
    existing = next((v for v in entry["versions"] if v["version"] == version), None)
    value = {
        "version": version,
        "path": str(path.relative_to(root)),
        "sha256": file_hash(path),
        "input_hash": input_hash,
        "task_id": task_id,
    }
    if existing and existing != value:
        raise ValueError("cannot overwrite a prior image version")
    if not existing:
        entry["versions"].append(value)
    if entry["selected"] is None:
        entry["selected"] = version
    write_json(root / "work/assets.json", assets)


def status(root: Path) -> dict:
    project = load_project(root)
    approvals = {}
    for stage in UPSTREAM:
        try:
            require_approval(root, stage)
            approvals[stage] = "approved"
        except (OSError, ValueError, KeyError):
            approvals[stage] = "missing/stale/unapproved"
    from . import edits

    edit = None
    try:
        board = load_board(root)
        edit = edits.load_edit(root, board=board)
        if edit is not None:
            board = edit.effective_board(board)
        shots = []
        for shot in board.shots:
            try:
                resolved_assets(root, [shot.id])
                image = "current"
            except (OSError, ValueError, KeyError):
                image = "missing/stale"
            shots.append(
                {
                    "id": shot.id,
                    "start": shot.start_frame / project.fps,
                    "duration": shot.duration_frames / project.fps,
                    "still": image,
                }
            )
    except (OSError, ValueError):
        shots = []
    return {
        "project": project.slug,
        "duration": project.duration,
        "total_frames": project.total_frames,
        "aspect": project.aspect,
        "approvals": approvals,
        "edit": edit is not None,
        "shots": shots,
    }
