"""Validated single-shot presentation edits: the re-edit API under the studio.

An edit changes how an existing still is presented — transition, dissolve handle,
simple camera move, bounded grade — never the image, the timing of other shots or
the recording. Every edit is re-validated as a whole storyboard, recorded in
``work/edits.json``, and reports exactly which approvals it invalidated.
"""

from __future__ import annotations

from pathlib import Path

from . import production as P
from .models import PostEffects, Storyboard
from .storage import file_hash, read_json, write_json

HISTORY = "work/edits.json"
INVALIDATED = ("storyboard", "proof", "preview", "stills", "graphics")
UNSET = object()


def _parse_effects(values: list[str]) -> dict[str, float]:
    allowed = set(PostEffects.model_fields)
    parsed: dict[str, float] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"effect must be key=value, got {raw!r}")
        key, _, value = raw.partition("=")
        key = key.strip()
        if key not in allowed:
            raise ValueError(f"unknown effect {key!r}; choose from {', '.join(sorted(allowed))}")
        try:
            parsed[key] = float(value)
        except ValueError as exc:
            raise ValueError(f"effect {key} needs a number, got {value!r}") from exc
    return parsed


def edit_shot(
    root: Path,
    shot_id: str,
    *,
    note: str,
    transition=UNSET,
    dissolve=None,
    camera=None,
    effects=None,
    clear_effects: bool = False,
) -> dict:
    root = Path(root)
    if not str(note).strip():
        raise ValueError("an edit needs --note recording the intent")
    if (
        transition is UNSET
        and dissolve is None
        and camera is None
        and not effects
        and not clear_effects
    ):
        raise ValueError("nothing to change; pass a transition, dissolve, camera or effect")

    board = P.load_board(root)
    shot = next((candidate for candidate in board.shots if candidate.id == shot_id), None)
    if shot is None:
        raise ValueError(f"unknown shot ID {shot_id!r}")
    if shot.asset_shot_id is not None:
        raise ValueError(
            f"{shot.id} is an editorial reprise of {shot.asset_shot_id}; "
            "edit the source shot so both stay identical"
        )

    before = {
        "transition": shot.transition,
        "dissolve_frames": shot.dissolve_frames,
        "camera": shot.camera,
        "post_effects": shot.post_effects.model_dump() if shot.post_effects else None,
    }
    if transition is not UNSET:
        shot.transition = None if transition in (None, "none") else transition
    if dissolve is not None:
        shot.dissolve_frames = dissolve
    if camera is not None:
        shot.camera = camera
    if clear_effects:
        shot.post_effects = None
    if effects:
        current = shot.post_effects.model_dump() if shot.post_effects else {}
        shot.post_effects = PostEffects(**{**current, **_parse_effects(effects)})

    # Re-validate the whole board: contiguity, neighbour handles and effect bounds.
    rebuilt = Storyboard.model_validate(
        {
            "schema_version": board.schema_version,
            "aspect": board.aspect,
            "fps": board.fps,
            "total_frames": board.total_frames,
            "shots": [candidate.model_dump() for candidate in board.shots],
        }
    )
    after = {
        "transition": shot.transition,
        "dissolve_frames": shot.dissolve_frames,
        "camera": shot.camera,
        "post_effects": shot.post_effects.model_dump() if shot.post_effects else None,
    }
    changed = {
        key: {"before": before[key], "after": after[key]}
        for key in before
        if before[key] != after[key]
    }
    if not changed:
        raise ValueError("the requested values already match this shot; nothing recorded")

    archive = root / "work/drafts"
    archive.mkdir(parents=True, exist_ok=True)
    previous = (
        archive
        / f"board-before-edit-{shot.id}-{len(read_json(root / HISTORY)) if (root / HISTORY).is_file() else 0:03d}.json"
    )
    if not previous.exists():
        write_json(previous, board.model_dump())

    write_json(root / "work/storyboard.json", rebuilt.model_dump())
    board_hash = file_hash(root / "work/storyboard.json")

    approvals = (
        read_json(root / "work/approvals.json") if (root / "work/approvals.json").is_file() else {}
    )
    invalidated = [stage for stage in INVALIDATED if approvals.get(stage)]
    current = {}
    try:
        current["storyboard"] = P.stage_hash(root, "storyboard")
    except (OSError, ValueError, KeyError):
        current["storyboard"] = None

    history = read_json(root / HISTORY) if (root / HISTORY).is_file() else []
    entry = {
        "at": P.now(),
        "shot_id": shot.id,
        "note": str(note),
        "changes": changed,
        "board_sha256": board_hash,
        "previous_board": str(previous.relative_to(root)),
        "invalidated_approvals": invalidated,
    }
    history.append(entry)
    write_json(root / HISTORY, history)

    return {
        "edited": shot.id,
        "changes": changed,
        "board_sha256": board_hash,
        "history": HISTORY,
        "invalidated": invalidated,
        "reason": (
            "the storyboard bytes changed, so any approval recorded against the previous "
            "bytes no longer passes its gate; stills/graphics bytes are unchanged"
        ),
        "storyboard_stage_hash": current["storyboard"],
        "next": [
            "clip dashboard PROJECT --stage board",
            "clip approve PROJECT storyboard --note '...' (after re-inspection)",
        ],
    }
