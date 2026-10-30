"""Suggest a first cut from what was measured, with no model and no randomness.

The seed keeps an approved cut exactly as it was; this proposes a better one. It
moves joins onto section starts and sung lines, varies camera travel with the
song's own loudness, writes each section's feel from its name and measurement, and
marks the strongest section arrivals. Nothing is saved here, and the shots, their
order and their words stay as they are.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .edits import cut_material, load_edit, report, seed_edit_preview
from .models import EditAccent, EditDecisionList, EditMotion, EditSection, EditShot, EditTransition
from .pacing import snap_joins

# Frames a cut leads a sung line by, so the picture is there as the word lands.
LINE_LEAD = 2
MIN_SHOT_SECONDS = 1.5
REACH_SECONDS = 1.5
QUIET, FULL = 0.34, 0.67
TRAVEL = {"quiet": 0.03, "middle": 0.06, "full": 0.1}
MAX_HOLD_SECONDS = 6.0
PUNCH = 1.05
DISSOLVE_FRAMES = 12


def _bands(sections: list[dict]) -> dict[int, str]:
    """Each section's loudness against the song's own range, never an absolute."""
    values = [section["energy"] for section in sections]
    low, high = (min(values), max(values)) if values else (0.0, 1.0)
    span = (high - low) or 1.0
    bands = {}
    for index, section in enumerate(sections):
        share = (section["energy"] - low) / span
        bands[index] = "quiet" if share < QUIET else "full" if share >= FULL else "middle"
    return bands


def _section_at(sections: list[dict], frame: int) -> int:
    for index, section in enumerate(sections):
        if section["start_frame"] <= frame < section["end_frame"]:
            return index
    return max(0, len(sections) - 1)


def _motion(
    recent: list[str], framing: str | None, band: str, seconds: float, closes_section: bool
) -> str:
    """Mostly approach, travel across wide frames, and open out only to end a section."""
    previous = recent[-1] if recent else None
    if band == "quiet" and seconds <= MAX_HOLD_SECONDS and previous != "hold":
        return "hold"
    if closes_section and framing in ("wide", "medium") and previous != "pull_back":
        return "pull_back"
    if framing == "wide" and previous != "pan_right":
        return "pan_right"
    if recent[-2:] == ["push_in", "push_in"]:
        return "pan_right" if framing != "detail" else "pull_back"
    return "push_in"


def suggest(root: Path) -> dict[str, Any]:
    """A suggested cut, with what would change and its report. Nothing is written."""
    from . import production as P

    board = P.load_board(root)
    project = P.load_project(root)
    fps = project.fps
    current = load_edit(root, board=board) or seed_edit_preview(root)
    material = cut_material(root)
    sections = material["sections"]
    bands = _bands(sections)
    total = board.total_frames

    joins = [shot.start_frame for shot in current.shots[1:]]
    moved = snap_joins(
        joins,
        total_frames=total,
        min_frames=round(MIN_SHOT_SECONDS * fps),
        reach=round(REACH_SECONDS * fps),
        tiers=[
            [section["start_frame"] for section in sections],
            [max(0, line["frame"] - LINE_LEAD) for line in material["lines"]],
            [change["frame"] for change in material["changes"]],
        ],
    )
    starts = [0, *moved]
    ends = [*moved, total]

    content = {shot.id: shot for shot in board.shots}
    shots: list[EditShot] = []
    recent_moves: list[str] = []
    previous_band: str | None = None
    arrivals = {section["start_frame"]: index for index, section in enumerate(sections)}
    for shot, start, end in zip(current.shots, starts, ends, strict=True):
        source = content[shot.shot_id]
        index = _section_at(sections, start) if sections else 0
        band = bands.get(index, "middle")
        seconds = (end - start) / fps
        locked = source.kind not in (None, "scene") or bool(shot.text)
        if locked:
            motion = shot.motion
        else:
            closes = any(
                start < section["end_frame"] <= end + round(MIN_SHOT_SECONDS * fps)
                for section in sections
            )
            kind = _motion(recent_moves, source.framing, band, seconds, closes)
            travel = TRAVEL[band]
            anchor = list(shot.motion.anchor)
            if kind == "hold":
                motion = EditMotion(
                    type="hold", anchor=anchor, reason=f"{band} passage, let it sit"
                )
            elif kind == "push_in":
                motion = EditMotion(
                    type="push_in",
                    **{"from": 1.0, "to": round(1 + travel, 3)},
                    anchor=anchor,
                    reason=f"approach in a {band} passage",
                )
            elif kind == "pull_back":
                motion = EditMotion(
                    type="pull_back",
                    **{"from": round(1 + travel, 3), "to": 1.0},
                    anchor=anchor,
                    reason=f"open out in a {band} passage",
                )
            else:
                motion = EditMotion(
                    type=kind,
                    **{"from": round(1 + travel, 3), "to": round(1 + travel, 3)},
                    anchor=anchor,
                    reason=f"travel across a wide frame in a {band} passage",
                )
        accents = [accent for accent in shot.accents if start <= accent.frame < end]
        transition = shot.transition_in
        arriving = arrivals.get(start)
        if arriving is not None and start > 0 and transition.type == "cut":
            if band == "full" and previous_band != "full" and not accents:
                accents = [
                    EditAccent(
                        frame=start,
                        type="punch_in",
                        amount=PUNCH,
                        reason=f"{sections[arriving]['name']} arrives",
                    )
                ]
            elif band == "quiet" and previous_band == "full" and seconds * fps > DISSOLVE_FRAMES:
                previous_frames = starts[len(shots)] - starts[len(shots) - 1]
                if previous_frames > DISSOLVE_FRAMES:
                    transition = EditTransition(
                        type="fade",
                        frames=DISSOLVE_FRAMES,
                        reason=f"the song drops away into {sections[arriving]['name']}",
                    )
        kept_text = [item for item in shot.text if start <= item.in_frame and item.out_frame <= end]
        shots.append(
            shot.model_copy(
                update={
                    "start_frame": start,
                    "duration_frames": end - start,
                    "motion": motion,
                    "accents": accents,
                    "transition_in": transition,
                    "text": kept_text,
                }
            )
        )
        recent_moves.append(motion.type)
        previous_band = band

    feel_words = {"quiet": "quiet, let it breathe", "middle": "moving", "full": "full, open"}
    suggested_sections = [
        EditSection(
            id=f"section-{index + 1}",
            start_frame=section["start_frame"],
            end_frame=section["end_frame"],
            feel=f"{section['name']}: {feel_words[bands[index]]}",
            techniques=[],
        )
        for index, section in enumerate(sections)
        if section["start_frame"] < total
    ] or current.sections
    suggested = EditDecisionList(
        sections=suggested_sections,
        shots=shots,
        grade=current.grade,
        notes="Suggested from the measured sections and sung lines; no model was used.",
    )
    suggested.check_board(board)
    return {
        "edit": suggested.model_dump(by_alias=True),
        "report": report(root, edit=suggested, board=board, project=project),
        "changes": _changes(current, suggested, fps),
    }


def _changes(before: EditDecisionList, after: EditDecisionList, fps: int) -> dict[str, Any]:
    old = {shot.shot_id: shot for shot in before.shots}
    moved = [
        shot.shot_id
        for shot in after.shots[1:]
        if shot.start_frame != old[shot.shot_id].start_frame
    ]
    largest = max(
        (abs(shot.start_frame - old[shot.shot_id].start_frame) for shot in after.shots),
        default=0,
    )
    return {
        "joins_moved": len(moved),
        "largest_move_seconds": round(largest / fps, 2),
        "moves_changed": sum(
            1
            for shot in after.shots
            if (shot.motion.type, shot.motion.from_scale, shot.motion.to_scale)
            != (
                old[shot.shot_id].motion.type,
                old[shot.shot_id].motion.from_scale,
                old[shot.shot_id].motion.to_scale,
            )
        ),
        "accents": sum(len(shot.accents) for shot in after.shots),
        "dissolves": sum(1 for shot in after.shots if shot.transition_in.type == "fade"),
        "holds": sum(1 for shot in after.shots if shot.motion.type == "hold"),
        "sections": len(after.sections),
    }
