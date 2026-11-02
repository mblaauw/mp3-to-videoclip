"""The prompt compiler: what each shot asks the image model for."""

import hashlib
from pathlib import Path

from PIL import Image

from .. import profiles, shotkinds, styles
from ..models import (
    Brief,
    CreativeProfile,
    Project,
    Shot,
)
from ..storage import (
    digest,
    file_hash,
    inside,
    read_json,
    snapshot_read,
)
from .board import load_board
from .brief import load_brief
from .project import compile_order, load_project

MAX_REFERENCES = 14

# Framing is visual content, not a camera move: it is transmitted to the model.
FRAMING_TEXT = {
    "wide": "wide establishing shot",
    "medium": "medium shot",
    "close_up": "close-up",
    "detail": "detail shot",
}


def out_of_date_stills(root: Path) -> list[str]:
    """Paid shots whose selected still was made from a different prompt than today's."""
    path = root / "work/assets.json"
    assets = read_json(path) if path.is_file() else {}
    stale = []
    try:
        shots = load_board(root).shots
    except (OSError, ValueError):
        # A board that can't load yet is another check's job to report.
        return stale
    for shot in shots:
        entry = assets.get(shot.asset_shot_id or shot.id) or {}
        chosen = next(
            (
                item
                for item in entry.get("versions", [])
                if item["version"] == entry.get("selected")
            ),
            None,
        )
        if chosen is None or shot.asset_shot_id is not None or not shotkinds.is_paid(shot):
            continue
        try:
            if chosen.get("input_hash") != digest(image_spec(root, shot)):
                stale.append(shot.id)
        except (OSError, ValueError):
            # A shot the profile can't compile yet is another check's job to report.
            continue
    return stale


def _avoid_list(brief: Brief) -> list[str]:
    """What pictures must leave out: the profile's list plus the owner's own in the intent."""
    owner = brief.intent.avoid if brief.intent else []
    return list(dict.fromkeys([*brief.avoid, *owner]))


def _permission_refusal(subject: str, *, where: str = "") -> ValueError:
    return ValueError(
        f"permission to upload/depict {subject} is not confirmed. Only the owner can confirm "
        f"it{where}: ask them and wait; retrying or rewriting the profile will not change it."
    )


def _character_refusal(subject: str) -> ValueError:
    return _permission_refusal(subject, where=" on Story's Characters card")


def character_refs(root: Path, brief: Brief, character_ids: list[str], states=None) -> list[dict]:
    refs = []
    for character in brief.characters:
        if character.id in character_ids:
            if not character.permission_confirmed:
                raise _character_refusal(character.id)
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
            raise _permission_refusal(ref_id)
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


def creative_profile_version(brief: Brief) -> str:
    """Explicit appearance version; story arc, proof IDs and editorial notes are excluded."""
    creative = brief.creative
    return digest(
        {
            "schema_version": 1,
            "look": creative.look,
            "image_rules": creative.image_rules,
            "avoid": brief.avoid,
            **(
                {"sections": [s.model_dump() for s in creative.sections]}
                if creative.sections
                else {}
            ),
        }
    )


def _section_look(project: Project, creative: CreativeProfile, shot: Shot) -> str:
    """The colour script's line for this shot's first frame. Version 3 only."""
    if project.prompt_version != 3:
        return ""
    at = shot.start_frame / project.fps
    for section in creative.sections:
        if section.start <= at < section.end:
            lens = f"; lens {section.lens}" if section.lens else ""
            return (
                f"Section look: palette {', '.join(section.palette)}; light {section.light}{lens}"
            )
    return ""


#: The one thing every picture of a place across time must not change.
ERA_FRAMING = "Keep the camera, the horizon and the building line of the place."
DOCUMENT_FRAMING = (
    "A close-up of this one object filling the frame, its shape and surface legible; "
    "any writing on it stays too small to read."
)


def _era_lines(creative: CreativeProfile, shot: Shot) -> list[str]:
    """What an era shot adds: the place that stays, then this time's look of it."""
    if creative.place is None:
        raise ValueError(f"era shot {shot.id} needs the profile's place")
    era = next((value for value in creative.eras if value.id == shot.era_id), None)
    if era is None:
        raise ValueError(f"unknown era {shot.era_id} in shot {shot.id}")
    place = creative.place
    return [
        f"Place: {place.description}" + (f" Camera: {place.camera}" if place.camera else ""),
        ERA_FRAMING,
        f"Era {era.year}: {era.state}",
        "Palette: " + ", ".join(era.palette) if era.palette else "",
        f"Light: {era.light}" if era.light else "",
        f"What persists: {era.persists}" if era.persists else "",
        f"What changed: {era.changed}" if era.changed else "",
    ]


def shot_seed(seed: int, shot_id: str) -> int:
    """A stable seed per shot, so a redo of one shot never moves its neighbours.

    Kept inside the 31 bits the image models' schemas allow.
    """
    return int(hashlib.sha256(f"{seed}:{shot_id}".encode()).hexdigest()[:8], 16) % 2**31


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
    # The anchor goes first, so the model reads every other image against it.
    anchor = []
    if shot.kind == "era" and creative.place is not None and creative.place.reference_id:
        anchor = reference_refs(root, brief, [creative.place.reference_id])
    refs = anchor + character_refs(root, brief, shot.character_ids, shot.character_states)
    refs += reference_refs(root, brief, bound_ids)
    refs += product_refs
    refs = list({item["path"]: item for item in refs}.values())
    if len(refs) > MAX_REFERENCES:
        raise ValueError(
            f"the application permits at most {MAX_REFERENCES} reference images; "
            "the live model schema may require fewer"
        )
    characters = []
    for character in brief.characters:
        if character.id not in shot.character_ids:
            continue
        identity = character.identity or character.description
        characters.append(f"{character.id} identity: {identity}")
        state_id = shot.character_states.get(character.id, character.default_state)
        if state_id:
            characters.append(
                f"{character.id} state ({state_id}): {character.states[state_id].description}"
            )
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
        if anchor and ref["path"] == anchor[0]["path"]:
            roles.append(f"Image {index}: the place itself; keep its camera and geometry.")
            continue
        roles.append(f"Image {index}: {role} reference; do not copy incidental pose or background.")
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
    look_first = compile_order(project) == "look-first"
    prompt = "\n".join(
        filter(
            None,
            [
                creative.look if look_first else "",
                shot.image_prompt,
                bridge_line,
                DOCUMENT_FRAMING if shot.kind == "document" else "",
                *(_era_lines(creative, shot) if shot.kind == "era" else []),
                "Framing: " + FRAMING_TEXT[shot.framing] if shot.framing else "",
                "Must show: " + "; ".join(shot.must_show) if shot.must_show else "",
                _section_look(project, creative, shot),
                scene.description if scene else "",
                *[by_id[i].description for i in bound_ids],
                *characters,
                creative.look if not look_first else "",
                *creative.image_rules,
                "Avoid: " + "; ".join(_avoid_list(brief)) if _avoid_list(brief) else "",
            ],
        )
    )
    spec = {
        "shot_id": shot.id,
        "positivePrompt": prompt,
        "size": list(project.image_size),
        "references": refs,
        "profile_version": creative_profile_version(brief),
    }
    # The quote moves these to negativePrompt where the live schema has one.
    if project.prompt_version == 3 and _avoid_list(brief):
        spec["avoid"] = _avoid_list(brief)
    return spec


@snapshot_read
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
        raise ValueError("the creative workflow requires a creative profile for state prompts")
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
            "seed": shot_seed(project.image_seed, shot.id)
            if project.prompt_version == 3 and project.image_seed is not None
            else project.image_seed,
        }
    return spec
