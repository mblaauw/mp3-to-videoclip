"""Resolved local production manifest and deliberately limited conflict checks.

These checks flag known failures, not general natural-language understanding.
Only workflow-v2 spending/approval treats errors as blocking. Older projects can
inspect the same diagnostics without changing their historical approvals.
"""

import re
from pathlib import Path

from .storage import digest, read_json


def strict_workflow(root: Path):
    """The creative workflow: explicit v2 or the migrated/native schema 3."""
    project = read_json(root / "project.json")
    return project.get("workflow_version") == 2 or project.get("schema_version") == 3


def manifest(root: Path, ids=None):
    from . import production as P
    from .references import validate_import

    project, brief, board = P.load_project(root), P.load_brief(root), P.load_board(root)
    known = {s.id for s in board.shots}
    chosen = list(known) if ids is None else list(ids)
    if not chosen or len(chosen) != len(set(chosen)) or not set(chosen) <= known:
        raise ValueError("preflight needs unique known shot IDs")
    issues, shots = [], []

    def issue(sid, code, text):
        issues.append({"shot_id": sid, "severity": "error", "code": code, "message": text})

    for shot in board.shots:
        if shot.id not in chosen:
            continue
        owner = next(s for s in board.shots if s.id == (shot.asset_shot_id or shot.id))
        spec = P.image_spec(root, owner)
        states = {}
        if shot.asset_shot_id:
            if shot.character_ids and set(shot.character_ids) != set(owner.character_ids):
                issue(
                    shot.id,
                    "alias-state",
                    "reused shot cannot change its source character identities",
                )
            for cid, required_state in shot.character_states.items():
                character = next(c for c in brief.characters if c.id == cid)
                actual = owner.character_states.get(cid, character.default_state)
                if required_state != actual:
                    issue(
                        shot.id,
                        "alias-state",
                        f"reused {cid} state {actual!r} cannot become {required_state!r}",
                    )
        for character in brief.characters:
            if character.id not in owner.character_ids:
                continue
            state_id = owner.character_states.get(character.id, character.default_state)
            state = character.states.get(state_id) if state_id else None
            states[character.id] = {
                "identity": character.identity or character.description,
                "state": state_id,
                "description": state.description if state else None,
                "attributes": state.attributes if state else {},
            }
            if P.creative_workflow(project) and not character.identity:
                issue(
                    shot.id,
                    "identity",
                    f"{character.id} needs identity separate from legacy description",
                )
            if character.states and state is None:
                issue(shot.id, "state", f"{character.id} needs an explicit or default state")
            requirements = [owner.state_requirements.get(character.id, {})]
            if shot.asset_shot_id:
                requirements.append(shot.state_requirements.get(character.id, {}))
            for attribute, expected in (item for req in requirements for item in req.items()):
                actual = state.attributes.get(attribute) if state else None
                if actual != expected:
                    issue(
                        shot.id,
                        "state",
                        f"{character.id}.{attribute}: required {expected!r}, resolved {actual!r}",
                    )
            # Known clothing/prop conflicts: inspect positive identity/state text,
            # not the global avoid list, which naturally contains prohibitions.
            description = " ".join(
                filter(
                    None,
                    [
                        character.identity or character.description,
                        state.description if state else "",
                    ],
                )
            )
            requested = " ".join([owner.image_prompt, *owner.must_show])
            for noun in ("parka", "jacket", "coat", "sunglasses"):
                forbidden = re.search(rf"\b(?:no|without)\s+{noun}\b", requested, re.I)
                positive = re.search(rf"\b{noun}\b", description, re.I)
                description_forbids = re.search(rf"\b(?:no|without)\s+{noun}\b", description, re.I)
                # Prose cannot reliably attribute 'no jacket' to one person
                # in a two-character shot; use per-character requirements there.
                if (
                    forbidden
                    and positive
                    and not description_forbids
                    and len(owner.character_ids) == 1
                ):
                    issue(
                        shot.id,
                        "state-conflict",
                        f"shot forbids {noun}, but {character.id} identity/state supplies it",
                    )
            if re.search(
                r"glasses.*(?:off|held down)|(?:remov|lower)\w*.*glasses", requested, re.I
            ) and re.search(r"glasses stay on|glasses.*never.*off", description, re.I):
                issue(
                    shot.id,
                    "state-conflict",
                    "shot removes glasses but identity/state requires them on",
                )

        required = " ".join(owner.must_show)
        if re.search(r"\bapart\b|not touching|gap of air", owner.image_prompt, re.I) and re.search(
            r"\bclasp(?:ed)?\b|hands touching", required, re.I
        ):
            issue(
                shot.id,
                "must-show-conflict",
                "image prompt separates hands but must_show requires a clasp",
            )
        if re.search(r"\bclasp(?:ed)?\b", owner.image_prompt, re.I) and re.search(
            r"\bapart\b|not touching", required, re.I
        ):
            issue(
                shot.id,
                "must-show-conflict",
                "image prompt clasps hands but must_show separates them",
            )
        scene = next(
            (
                s
                for s in (brief.creative.scenes if brief.creative else [])
                if s.id == owner.scene_id
            ),
            None,
        )
        if scene and re.search(
            r"no people|completely empty|not a single person", owner.image_prompt, re.I
        ):
            if re.search(r"dense crowd|crowded|packed with people", scene.description, re.I):
                issue(
                    shot.id, "scene-conflict", "empty shot inherits an occupied scene description"
                )
        if re.search(
            r"five\s+(?:clean\s+)?fingers\s+and\s+(?:one|a)\s+thumb", spec["positivePrompt"], re.I
        ):
            issue(
                shot.id,
                "digit-count",
                "ambiguous five fingers plus a thumb; use four fingers and a thumb",
            )
        if P.creative_workflow(project):
            for ref in spec["references"]:
                try:
                    validate_import(root, ref["path"])
                except (ValueError, OSError) as exc:
                    issue(shot.id, "immutable-reference", str(exc))
        shots.append(
            {
                "id": shot.id,
                "owner_shot_id": owner.id,
                "start_frame": shot.start_frame,
                "end_frame": shot.start_frame + shot.duration_frames,
                "start_seconds": shot.start_frame / project.fps,
                "end_seconds": (shot.start_frame + shot.duration_frames) / project.fps,
                "purpose": shot.purpose,
                "framing": owner.framing,
                "must_show": owner.must_show,
                "characters": states,
                "input_hash": digest(spec),
                "spec": spec,
            }
        )
    return {
        "workflow_version": project.workflow_version,
        "generated": False,
        "ok": not issues,
        "issues": issues,
        "shots": shots,
        "warning": "Known-conflict checks only; visual and compiled-prompt review are still required.",
    }


def validate_before_spend(root: Path, ids):
    if not strict_workflow(root):
        return
    result = manifest(root, ids)
    if not result["ok"]:
        details = "; ".join(f"{i['shot_id']}: {i['message']}" for i in result["issues"])
        raise ValueError(f"preflight blocked: {details}")
