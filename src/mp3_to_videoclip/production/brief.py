"""The film's brief, creative profile and treatments."""

from pathlib import Path

from .. import styles
from ..models import (
    Brief,
    Character,
    CreativeProfile,
    Scene,
    Treatments,
    VisualBeat,
)
from ..storage import (
    digest,
    read_json,
    read_optional,
    require_revision,
    snapshot_read,
    state_mutation,
    write_json,
)
from .project import load_project


def legacy_brief_hash(brief: Brief) -> str:
    """Legacy content hash: the new creative profile is not part of old artifacts."""
    return digest(brief.model_dump(exclude={"creative"}))


@snapshot_read
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


def _keep_stored_permissions(previous: Brief, brief: Brief) -> Brief:
    """Only the owner sets the permission gate: keep what is stored, new entries start false."""
    characters = {value.id: value.permission_confirmed for value in previous.characters}
    update: dict = {
        "characters": [
            value.model_copy(update={"permission_confirmed": characters.get(value.id, False)})
            for value in brief.characters
        ]
    }
    if brief.creative is not None:
        stored = previous.creative.references if previous.creative else []
        references = {value.id: value.permission_confirmed for value in stored}
        update["creative"] = brief.creative.model_copy(
            update={
                "references": [
                    value.model_copy(
                        update={"permission_confirmed": references.get(value.id, False)}
                    )
                    for value in brief.creative.references
                ]
            }
        )
    return brief.model_copy(update=update)


def unconfirmed_permissions(brief: Brief) -> list[str]:
    """Character and reference IDs still waiting for the owner's permission."""
    references = brief.creative.references if brief.creative else []
    return [
        value.id for value in [*brief.characters, *references] if not value.permission_confirmed
    ]


@state_mutation
def update_brief(
    root: Path, patch: dict, *, expected_hash: str | None = None, owner: bool = False
) -> Brief:
    """Apply one validated merge patch and keep the previous brief in history.

    Only ``owner=True``, the Studio's own route, may change the permission gate.
    """
    if not isinstance(patch, dict):
        raise ValueError("brief patch must be a JSON object")
    previous = load_brief(root)
    previous_value = previous.model_dump()
    require_revision(root / "brief.json", expected_hash, value=previous_value)
    merged = _merge_patch(previous_value, patch)
    try:
        brief = Brief.model_validate(merged)
    except ValueError as exc:
        raise ValueError(f"brief patch is invalid: {exc}") from exc
    if not owner:
        brief = _keep_stored_permissions(previous, brief)
    if brief.model_dump() == previous_value:
        return previous
    history = root / f"work/brief-history/{digest(previous_value)}.json"
    if not history.exists():
        write_json(history, previous_value)
    write_json(root / "brief.json", brief.model_dump())
    _record_prompt_write(root, "brief")
    return brief


PROFILE_MAX_LOOK_WORDS = 180
PROFILE_MAX_LOOK_ADDITIONS = 60
PROFILE_MAX_IMAGE_RULES = 6
PROFILE_MAX_AVOID = 8
PROFILE_MAX_ARC = 12


@state_mutation
def set_creative_profile(
    root: Path,
    *,
    characters: list,
    scenes: list,
    arc: list,
    image_rules: list,
    avoid: list,
    look: str,
) -> Brief:
    """Create or replace the film's structured cast, places, rules and look.

    The Writer calls this once after the treatment. It is deliberately separate
    from the generic brief patch: the cast, places and rendering rules have one
    validated home, so they cannot drift back into ``direction`` or every shot.
    A rewrite keeps the owner's permission gate as stored.
    """
    if not all(isinstance(value, list) for value in (characters, scenes, arc)):
        raise ValueError("characters, scenes and arc must be lists")
    if not isinstance(image_rules, list) or not isinstance(avoid, list):
        raise ValueError("image_rules and avoid must be lists")
    if not isinstance(look, str):
        raise ValueError("look must be text")

    try:
        character_values = [Character.model_validate(value) for value in characters]
        scene_values = [Scene.model_validate(value) for value in scenes]
        arc_values = [VisualBeat.model_validate(value) for value in arc]
    except ValueError as exc:
        raise ValueError(f"creative profile is invalid: {exc}") from exc

    character_ids = [value.id for value in character_values]
    if len(set(character_ids)) != len(character_ids):
        raise ValueError("character IDs must be unique")
    scene_ids = [value.id for value in scene_values]
    if len(set(scene_ids)) != len(scene_ids):
        raise ValueError("scene IDs must be unique")

    rules = [value.strip() for value in image_rules if isinstance(value, str) and value.strip()]
    if len(rules) != len(image_rules):
        raise ValueError("image rules must be non-empty text")
    if len(rules) > PROFILE_MAX_IMAGE_RULES:
        raise ValueError(f"keep at most {PROFILE_MAX_IMAGE_RULES} global image rules")
    avoid_values = [value.strip() for value in avoid if isinstance(value, str) and value.strip()]
    if len(avoid_values) != len(avoid):
        raise ValueError("avoid entries must be non-empty text")
    if len(avoid_values) > PROFILE_MAX_AVOID:
        raise ValueError(f"keep at most {PROFILE_MAX_AVOID} avoid entries")
    if len(arc_values) > PROFILE_MAX_ARC:
        raise ValueError(f"keep at most {PROFILE_MAX_ARC} arc beats")

    look_text = look.strip()
    if not look_text:
        raise ValueError("define creative.look before creating the profile")
    project = load_project(root)
    guarded = styles.protected_preset(project.style_preset)
    if guarded is not None:
        problem = styles.core_problem(project.style_preset, look_text)
        if problem:
            raise ValueError(problem)
        additions = look_text[len(guarded.look) :].strip()
        if len(additions.split()) > PROFILE_MAX_LOOK_ADDITIONS:
            raise ValueError(
                f"keep film-specific look additions to {PROFILE_MAX_LOOK_ADDITIONS} words"
            )
    elif len(look_text.split()) > PROFILE_MAX_LOOK_WORDS:
        raise ValueError(
            f"keep the custom look to {PROFILE_MAX_LOOK_WORDS} words; "
            "move cast, places and per-scene light into the profile"
        )

    brief = load_brief(root)
    creative = brief.creative or CreativeProfile()
    updated = brief.model_copy(
        update={
            "characters": character_values,
            "avoid": avoid_values,
            "creative": creative.model_copy(
                update={
                    "look": look_text,
                    "image_rules": rules,
                    "arc": arc_values,
                    "scenes": scene_values,
                    "profile_version": 1,
                }
            ),
        }
    )
    try:
        updated = Brief.model_validate(updated.model_dump())
    except ValueError as exc:
        raise ValueError(f"creative profile is invalid: {exc}") from exc
    updated = _keep_stored_permissions(brief, updated)

    previous_value = brief.model_dump()
    value = updated.model_dump()
    if value == previous_value:
        return brief
    history = root / f"work/brief-history/{digest(previous_value)}.json"
    if not history.exists():
        write_json(history, previous_value)
    write_json(root / "brief.json", value)
    _record_prompt_write(root, "brief")
    return updated


@state_mutation
def update_treatments(root: Path, payload: dict) -> Treatments:
    """Write one to three structurally distinct concepts as one validated artifact."""
    if not isinstance(payload, dict):
        raise ValueError("treatments must be a JSON object")
    try:
        treatments = Treatments.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"treatments are invalid: {exc}") from exc
    project = read_optional(root / "project.json")
    duration = project.get("duration") if isinstance(project, dict) else None
    if duration:
        for concept in treatments.concepts:
            for beat in concept.beats:
                if beat.end > duration + 0.5:
                    raise ValueError(
                        f"concept {concept.id}: a beat ends at {beat.end:.1f} s, "
                        f"but the film is {duration:.1f} s"
                    )
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
    from .. import promptlog

    promptlog.record(root, artifact)


def is_creative(root: Path) -> bool:
    return load_brief(root).creative is not None
