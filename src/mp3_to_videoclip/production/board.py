"""The event map and the storyboard, including its first skeleton."""

from pathlib import Path

from .. import flow
from ..models import (
    EventMap,
    Shot,
    Storyboard,
)
from ..storage import (
    inside,
    read_json,
    require_revision,
    snapshot_read,
    state_mutation,
    write_json,
)
from .brief import _record_prompt_write, load_brief
from .project import STAGE_FILES, creative_workflow, load_project


def load_events(root: Path) -> EventMap:
    events = EventMap.model_validate(read_json(root / STAGE_FILES["events"]))
    events.check_project(load_project(root))
    return events


@state_mutation
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


@snapshot_read
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


@state_mutation
def update_shots(
    root: Path, changes: list[dict], *, expected_hash: str | None = None
) -> tuple[Storyboard, list[str]]:
    """Apply named shot edits atomically after validating the whole board."""
    if not isinstance(changes, list):
        raise ValueError("shot changes must be a list")
    board = load_board(root)
    require_revision(root / STAGE_FILES["storyboard"], expected_hash, value=board.model_dump())
    from .. import edits

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
    from ..domain import history

    history.snapshot(root, "storyboard", raw)
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


@state_mutation
def skeleton(root: Path, nominal_seconds=None, timing=None, *, min_seconds=None, max_seconds=None):
    """Build a timing-only skeleton (TODO content, never creative approval).

    ``timing`` selects the boundary source: ``beats`` (local beat estimates),
    ``events`` (reviewed *manual* musical-event boundaries; the nearest boundary
    within one second of the nominal target is acceptable, so shots are
    music-aware rather than rigidly uniform) or ``free`` (uniform, no beats).
    Shot IDs stay stable and the timeline always covers ``total_frames`` exactly.
    """
    from .approvals import require_approval

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
        from ..pacing import plan_boundaries

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
