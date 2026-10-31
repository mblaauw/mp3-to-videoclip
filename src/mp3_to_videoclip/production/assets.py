"""Proof selection and the independently reusable image versions."""

import re
from pathlib import Path

from .. import localplate, shotkinds
from ..models import (
    Brief,
    Project,
    RenderShot,
    Shot,
    Storyboard,
)
from ..storage import (
    digest,
    file_hash,
    inside,
    read_json,
    state_mutation,
    write_json,
)
from .board import load_board
from .brief import _record_prompt_write, load_brief
from .image_specs import image_spec
from .project import STAGE_FILES, load_project


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


@state_mutation
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
    from .. import edits

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


@state_mutation
def select_asset(root: Path, shot_id: str, version: int):
    board = load_board(root)
    shot = next((s for s in board.shots if s.id == shot_id), None)
    owner = (shot.asset_shot_id or shot.id) if shot else shot_id
    assets = read_json(root / "work/assets.json")
    if not any(v["version"] == version for v in assets.get(owner, {}).get("versions", [])):
        raise ValueError("unknown image version")
    assets[owner]["selected"] = version
    write_json(root / "work/assets.json", assets)


@state_mutation
def record_asset(root: Path, shot_id: str, version: int, path: Path, input_hash: str, task_id: str):
    root = root.resolve()
    path = Path(path).resolve()
    index = root / "work/assets.json"
    assets = read_json(index) if index.exists() else {}
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
