"""The prompt compiler: what each shot asks the image model for."""

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
    snapshot_read,
)
from .board import load_board
from .brief import legacy_brief_hash, load_brief
from .project import creative_workflow, load_project, prompt_look_first

# Framing is visual content, not a camera move: it is transmitted to the model.
FRAMING_TEXT = {
    "wide": "wide establishing shot",
    "medium": "medium shot",
    "close_up": "close-up",
    "detail": "detail shot",
}


def _reference_cap(project: Project) -> int:
    """Stored-model profiles may use the current model capacity; legacy stays at four."""
    return 14 if project.image_model is not None else 4


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
