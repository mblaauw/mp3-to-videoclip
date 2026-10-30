"""Edit-owned timing, motion and the computed edit report.

``work/edit.json`` is the authoritative cut once it exists. The storyboard keeps
content: what is in each shot and the source still for it. The effective board
applies the edit's order and spans, while the renderer receives the matching
``EditShot`` beside each resolved shot. Legacy productions without an edit keep
their storyboard timing and hashes unchanged.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    EditAccent,
    EditDecisionList,
    EditMotion,
    EditSection,
    EditShot,
    EditTransition,
    Grade,
    Project,
    RenderShot,
    Storyboard,
)
from .storage import digest, read_json, read_optional, require_revision, state_mutation, write_json

EDIT = "work/edit.json"
HARD = "hard"
WARNING = "warning"

TRANSITION_LABELS = {
    "cut": "Cut",
    "fade": "Fade",
    "wipe_left": "Wipe left",
    "wipe_right": "Wipe right",
    "dip_to_black": "Dip to black",
    "dip_to_white": "Dip to white",
    "whip_pan": "Whip pan",
    "push": "Push",
    "slide": "Slide",
}
MOTION_LABELS = {
    "hold": "Hold",
    "push_in": "Push in",
    "pull_back": "Pull back",
    "pan_left": "Pan left",
    "pan_right": "Pan right",
}
ACCENT_LABELS = {"punch_in": "Punch in", "flash": "Flash", "light_leak": "Light leak"}


def transition_label(value: EditTransition) -> str:
    label = TRANSITION_LABELS.get(value.type, value.type.replace("_", " ").title())
    if value.frames:
        return f"{label} {value.frames} f"
    return label


def motion_label(value: EditMotion) -> str:
    return MOTION_LABELS.get(value.type, value.type.replace("_", " ").title())


def accent_label(value: EditAccent) -> str:
    return ACCENT_LABELS.get(value.type, value.type.replace("_", " ").title())


def _section_names(root: Path) -> list[str]:
    """Measured sections with their human names, in measured order."""
    from .domain import music_notes

    music = read_optional(root / "work" / "music.json")
    if not isinstance(music, dict):
        return []
    named = music_notes.apply_names(music, music_notes.read(root)) or {}
    return [
        str(item.get("name") or music_notes.default_name(index))
        for index, item in enumerate(named.get("sections") or [])
        if isinstance(item, dict)
    ]


# Storyboard fields that belong to the edit once work/edit.json exists.
EDIT_OWNED = {
    "start_frame",
    "duration_frames",
    "dissolve_frames",
    "camera",
    "camera_path",
    "camera_keyframes",
    "post_effects",
    "transition",
}

TECHNIQUE_NAMES = {
    "hold": "breathing hold",
    "push_in": "push-in",
    "pull_back": "pull-back",
    "pan_left": "lateral pan",
    "pan_right": "lateral pan",
    "cut": "hard cut",
    "fade": "dissolve",
    "wipe_left": "wipe",
    "wipe_right": "wipe",
    "dip_to_black": "dip to black",
    "dip_to_white": "dip to white",
    "whip_pan": "whip pan",
    "push": "push transition",
    "slide": "slide transition",
    "punch_in": "punch-in",
    "flash": "flash frame",
    "light_leak": "light leak",
    "fade_text": "text fade",
    "type_on": "type-on",
    "slide_up": "slide-up type",
    "pop": "pop type",
    "kinetic_words": "kinetic typography",
}

ENERGY_WORDS = {
    "high": ("chorus", "drop", "climax", "release", "peak", "explode", "loud"),
    "low": ("intro", "outro", "verse", "calm", "quiet", "breakdown", "bridge", "breath"),
}


def edit_path(root: Path) -> Path:
    return root / EDIT


def load_edit(root: Path, *, board: Storyboard | None = None) -> EditDecisionList | None:
    """Read and validate the edit against the current storyboard, if present."""
    path = edit_path(root)
    if not path.is_file():
        return None
    edit = EditDecisionList.model_validate(read_json(path))
    if board is not None:
        edit.check_board(board)
    return edit


@state_mutation
def save_edit(
    root: Path,
    value: EditDecisionList | dict,
    *,
    board: Storyboard | None = None,
    record: bool = True,
    expected_hash: str | None = None,
) -> EditDecisionList:
    """Validate the whole cut and write it atomically.

    Coverage and shot identity are structural requirements: an edit that leaves a
    gap cannot produce an effective board. Report-level hard findings such as a
    missing transition reason or too many flashes are still saved, so the Editor
    can read the report and correct them instead of guessing in the dark.
    """
    from . import production as P

    require_revision(edit_path(root), expected_hash)
    if not P.load_project(root, verify_source=False).uses_remotion:
        raise ValueError("edit lists require the Remotion renderer")
    board = board or P.load_board(root)
    edit = value if isinstance(value, EditDecisionList) else EditDecisionList.model_validate(value)
    edit.check_board(board)
    edit_path(root).parent.mkdir(parents=True, exist_ok=True)
    from .domain import history

    history.snapshot(root, "edit")
    write_json(edit_path(root), edit.model_dump(by_alias=True))
    if record:
        P._record_prompt_write(root, "edit")
    return edit


def edit_digest(root: Path, edit: EditDecisionList | None = None) -> str | None:
    edit = edit or load_edit(root)
    if edit is None:
        return None
    return digest(edit.model_dump(by_alias=True))


def effective_board(root: Path, board: Storyboard | None = None) -> Storyboard:
    """The storyboard content with edit-owned order and timing applied."""
    from . import production as P

    board = board or P.load_board(root)
    edit = load_edit(root, board=board)
    return edit.effective_board(board) if edit is not None else board


def _section_windows(edit: EditDecisionList, total: int) -> list[tuple[EditSection, int, int]]:
    windows = []
    for index, section in enumerate(edit.sections):
        end = section.end_frame
        if end is None:
            end = edit.sections[index + 1].start_frame if index + 1 < len(edit.sections) else total
        windows.append((section, section.start_frame, end))
    return windows


def _energy(label: str) -> str | None:
    text = label.lower()
    for energy in ("high", "low"):
        if any(word in text for word in ENERGY_WORDS[energy]):
            return energy
    return None


def _event_energy(root: Path, start: int, end: int) -> str | None:
    """Best-effort energy label for a section window from the reviewed event map."""
    value = read_optional(root / "work/events.json")
    if not isinstance(value, dict):
        return None
    candidates = []
    for event in value.get("events", []):
        if not isinstance(event, dict) or event.get("kind") != "section":
            continue
        frame = event.get("frame")
        if not isinstance(frame, int):
            continue
        if start <= frame < end or start <= (event.get("end_frame") or frame) <= end:
            energy = _energy(str(event.get("label") or ""))
            if energy is not None:
                candidates.append(energy)
    if "high" in candidates:
        return "high"
    if "low" in candidates:
        return "low"
    return None


def _flash_frames(edit: EditDecisionList) -> list[int]:
    return sorted(
        accent.frame for shot in edit.shots for accent in shot.accents if accent.type == "flash"
    )


def flash_violations(edit: EditDecisionList, fps: int) -> list[dict]:
    """Every 1-second window with more than three flash accents.

    The window starts at each flash, which is sufficient for a fixed-width count:
    any earlier start contains no more flashes than the first flash inside it.
    """
    frames = _flash_frames(edit)
    bad = []
    left = 0
    for right, frame in enumerate(frames):
        while frame - frames[left] >= fps:
            left += 1
        count = right - left + 1
        if count > 3:
            bad.append({"start_frame": frames[left], "frames": count, "window_frames": fps})
    return bad


def _technique_rows(edit: EditDecisionList, board: Storyboard) -> list[dict]:
    counts: dict[str, list[str]] = {}
    storyboard = {shot.id: shot for shot in board.shots}

    def add(name: str, reason: str = "") -> None:
        entry = counts.setdefault(name, [])
        if reason and reason not in entry:
            entry.append(reason)

    for shot in edit.shots:
        motion_name = TECHNIQUE_NAMES.get(shot.motion.type)
        if motion_name:
            add(motion_name, shot.motion.reason)
        transition_name = TECHNIQUE_NAMES.get(shot.transition_in.type)
        if transition_name and shot.transition_in.type != "cut":
            add(transition_name, shot.transition_in.reason)
        for accent in shot.accents:
            add(TECHNIQUE_NAMES[accent.type], accent.reason)
        for item in shot.text:
            key = "fade_text" if item.animation == "fade" else item.animation
            add(TECHNIQUE_NAMES[key], item.reason)
        content = storyboard.get(shot.shot_id)
        if content is not None and content.kind == "split":
            add("split screen", "storyboard split shot")
    for section in edit.sections:
        for name in section.techniques:
            add(name, section.feel)
    rows = [
        {
            "name": name,
            "count": len(
                [
                    decision
                    for decision in edit.shots
                    if TECHNIQUE_NAMES.get(decision.motion.type) == name
                    or TECHNIQUE_NAMES.get(decision.transition_in.type) == name
                    or any(TECHNIQUE_NAMES.get(a.type) == name for a in decision.accents)
                    or any(
                        TECHNIQUE_NAMES.get("fade_text" if t.animation == "fade" else t.animation)
                        == name
                        for t in decision.text
                    )
                ]
            ),
            "reasons": reasons,
            "reasoned": bool(reasons),
        }
        for name, reasons in counts.items()
    ]
    return sorted(
        (row for row in rows if row["count"] > 0),
        key=lambda row: (-row["count"], row["name"]),
    )


def _ad_checks(root: Path, project: Project, board: Storyboard, edit: EditDecisionList) -> dict:
    """The advert/promo checks from the brief, reported as warnings."""
    if project.kind not in ("promo", "advert"):
        return {"applicable": False, "checks": []}
    content = {shot.id: shot for shot in board.shots}
    first_five = [decision for decision in edit.shots if decision.start_frame < 5 * project.fps]
    visible = any(
        content[decision.shot_id].kind in ("product", "logo", "end_card")
        or content[decision.shot_id].product_ref
        or content[decision.shot_id].text
        for decision in first_five
        if decision.shot_id in content
    )
    end_cards = [
        decision
        for decision in edit.shots
        if content.get(decision.shot_id) is not None
        and content[decision.shot_id].kind == "end_card"
    ]
    end_ok = bool(end_cards) and all(
        decision.duration_frames >= 3 * project.fps for decision in end_cards
    )
    checks = [
        {
            "id": "brand_or_product_first_5s",
            "ok": visible,
            "automatic": True,
            "message": (
                "brand, product or a text card is visible in the first five seconds"
                if visible
                else "no brand, product or text card appears in the first five seconds"
            ),
        },
        {
            "id": "end_card_3s",
            "ok": end_ok,
            "automatic": True,
            "message": (
                "the end card holds for at least three seconds"
                if end_ok
                else "the advert/promo has no end card of at least three seconds"
            ),
        },
    ]
    try:
        from . import production as P

        brief = P.load_brief(root)
    except (OSError, ValueError):
        brief = None
    mandatories = list(brief.intent.mandatories) if brief and brief.intent else []
    if mandatories:
        haystack = " ".join(
            " ".join(
                [
                    content[decision.shot_id].message,
                    content[decision.shot_id].purpose,
                    *content[decision.shot_id].text,
                ]
            )
            for decision in edit.shots
            if decision.shot_id in content
        ).lower()
        missing = [value for value in mandatories if value.lower() not in haystack]
        checks.append(
            {
                "id": "mandatories_present",
                "ok": not missing,
                "automatic": False,
                "message": (
                    "every mandatory is present"
                    if not missing
                    else "missing mandatory wording: " + ", ".join(missing)
                ),
            }
        )
    return {"applicable": True, "checks": checks}


def report(
    root: Path,
    *,
    edit: EditDecisionList | None = None,
    board: Storyboard | None = None,
    project: Project | None = None,
) -> dict:
    """Compute the edit report the Editor reads and the Film stage shows."""
    from . import production as P

    board = board or P.load_board(root)
    project = project or P.load_project(root)
    edit = edit if edit is not None else load_edit(root, board=board)
    if edit is None:
        return {
            "present": False,
            "ok": True,
            "hard": [],
            "warnings": [],
            "sections": [],
            "techniques": [],
            "counts": {"shots": len(board.shots), "cuts": max(0, len(board.shots) - 1)},
            "coverage": {"ok": True, "total_frames": board.total_frames},
            "ad": {"applicable": False, "checks": []},
        }

    hard: list[dict] = []
    warnings: list[dict] = []

    try:
        edit.check_board(board)
        coverage = {
            "ok": True,
            "start_frame": 0,
            "end_frame": board.total_frames,
            "total_frames": board.total_frames,
        }
    except ValueError as exc:
        coverage = {
            "ok": False,
            "start_frame": 0,
            "end_frame": edit.shots[-1].start_frame + edit.shots[-1].duration_frames,
            "total_frames": board.total_frames,
        }
        hard.append({"code": "coverage", "message": str(exc)})

    fps = project.fps
    flashes = _flash_frames(edit)
    for violation in flash_violations(edit, fps):
        hard.append(
            {
                "code": "flash_rate",
                "message": (
                    f"{violation['frames']} flash frames inside "
                    f"{violation['window_frames']} frames starting at "
                    f"{violation['start_frame']}; the limit is 3 per second"
                ),
            }
        )

    for index, shot in enumerate(edit.shots):
        transition = shot.transition_in
        if transition.type != "cut" and transition.frames <= 0:
            hard.append(
                {
                    "code": "transition_handle",
                    "shot_id": shot.shot_id,
                    "message": f"{shot.shot_id} uses {transition.type} without handle frames",
                }
            )
        if transition.type != "cut" and not transition.reason.strip():
            hard.append(
                {
                    "code": "transition_reason",
                    "shot_id": shot.shot_id,
                    "message": f"{shot.shot_id} uses {transition.type} without a stated reason",
                }
            )
        if index == 0 and transition.type != "cut":
            warnings.append(
                {
                    "code": "opening_transition",
                    "shot_id": shot.shot_id,
                    "message": "the first shot has no outgoing plate to transition from",
                }
            )

    content = {shot.id: shot for shot in board.shots}
    shots = []
    for shot in edit.shots:
        source = content.get(shot.shot_id)
        shots.append(
            {
                "shot_id": shot.shot_id,
                "kind": source.kind if source else "scene",
                "start_frame": shot.start_frame,
                "duration_frames": shot.duration_frames,
                "seconds": round(shot.duration_frames / fps, 3),
                "motion": shot.motion.type,
                "transition_in": shot.transition_in.type,
                "accents": [accent.type for accent in shot.accents],
                "text": [item.text for item in shot.text],
            }
        )

    windows = _section_windows(edit, board.total_frames)
    sections = []
    total_holds = 0
    hold_excused = False
    for section, start, end in windows:
        decisions = [shot for shot in edit.shots if start <= shot.start_frame < end]
        cuts = sum(1 for shot in decisions if shot.start_frame > start)
        seconds = max((end - start) / fps, 1 / fps)
        density = round(cuts / seconds * 10, 2)
        holds = sum(1 for shot in decisions if shot.motion.type == "hold")
        total_holds += holds
        techniques = [value for value in section.techniques]
        hold_planned = any("hold" in value.lower() for value in techniques)
        if hold_planned:
            hold_excused = True
        energy = _energy(section.feel) or _event_energy(root, start, end)
        if decisions and not hold_planned and holds / len(decisions) > 0.5:
            warnings.append(
                {
                    "code": "hold_ratio",
                    "section": section.id,
                    "message": (
                        f"section {section.id} holds {holds} of {len(decisions)} shots; "
                        "name a breathing-hold technique if that is the plan"
                    ),
                }
            )
        # A seeded section has no target (0), so there is nothing to compare against.
        if section.density_per_10s > 0 and abs(density - section.density_per_10s) > 2.0:
            warnings.append(
                {
                    "code": "density_target",
                    "section": section.id,
                    "message": (
                        f"section {section.id} cuts {density}/10s against a "
                        f"{section.density_per_10s}/10s target"
                    ),
                }
            )
        if energy == "high" and density < 2.0 and decisions:
            warnings.append(
                {
                    "code": "energy_density",
                    "section": section.id,
                    "message": f"high-energy section {section.id} cuts at only {density}/10s",
                }
            )
        elif energy == "low" and density > 5.0:
            warnings.append(
                {
                    "code": "energy_density",
                    "section": section.id,
                    "message": f"low-energy section {section.id} cuts at {density}/10s",
                }
            )
        sections.append(
            {
                "id": section.id,
                "start_frame": start,
                "end_frame": end,
                "feel": section.feel,
                "energy": energy,
                "target_density_per_10s": section.density_per_10s,
                "density_per_10s": density,
                "cuts": cuts,
                "shots": len(decisions),
                "holds": holds,
                "accents": sum(len(shot.accents) for shot in decisions),
                "flashes": sum(
                    1 for shot in decisions for accent in shot.accents if accent.type == "flash"
                ),
                "techniques": techniques,
            }
        )

    total_shots = len(edit.shots)
    hold_ratio = round(total_holds / total_shots, 3) if total_shots else 0
    if hold_ratio > 0.5 and not hold_excused:
        warnings.append(
            {
                "code": "hold_ratio_total",
                "message": f"{total_holds} of {total_shots} shots are holds",
            }
        )

    # Repetition: the same move or transition until it becomes mechanical.
    run = 0
    previous = None
    for shot in edit.shots:
        if shot.motion.type == previous:
            run += 1
        else:
            run = 1
            previous = shot.motion.type
        if run == 3:
            warnings.append(
                {
                    "code": "motion_repetition",
                    "shot_id": shot.shot_id,
                    "message": f"three {shot.motion.type} moves in a row",
                }
            )
    # Hard cut is the default and is not repetition; only named transitions are.
    joins = [shot.transition_in.type for shot in edit.shots[1:] if shot.transition_in.type != "cut"]
    for name in sorted(set(joins)):
        count = joins.count(name)
        if len(joins) and count / len(joins) > 0.3:
            warnings.append(
                {
                    "code": "transition_repetition",
                    "message": f"{count} of {len(joins)} named joins use {name}",
                }
            )
    previous_framing = None
    for shot in edit.shots:
        framing = content[shot.shot_id].framing if shot.shot_id in content else None
        if framing is not None and framing == previous_framing:
            warnings.append(
                {
                    "code": "framing_repetition",
                    "shot_id": shot.shot_id,
                    "message": f"back-to-back {framing} framings",
                }
            )
        previous_framing = framing

    # Reading time. Card text is measured from the storyboard, timed text from
    # the edit layer, because both are words the viewer has to read.
    for shot in edit.shots:
        source = content.get(shot.shot_id)
        if source is None:
            continue
        words = sum(len(line.split()) for line in source.text)
        if source.kind in ("card", "end_card", "logo") and words:
            needed = 0.3 * words + 1.0
            if shot.duration_frames / fps < needed:
                warnings.append(
                    {
                        "code": "reading_time",
                        "shot_id": shot.shot_id,
                        "message": (
                            f"card {shot.shot_id} holds {shot.duration_frames / fps:.2f}s; "
                            f"{words} words need {needed:.2f}s"
                        ),
                    }
                )
        elif shot.duration_frames / fps < 1.0 and source.kind not in (
            "card",
            "end_card",
            "logo",
        ):
            warnings.append(
                {
                    "code": "reading_time",
                    "shot_id": shot.shot_id,
                    "message": f"{shot.shot_id} is an insert shorter than one second",
                }
            )
        for item in shot.text:
            needed = 0.3 * len(item.text.split()) + 1.0
            held = (item.out_frame - item.in_frame) / fps
            if held < needed:
                warnings.append(
                    {
                        "code": "text_reading_time",
                        "shot_id": shot.shot_id,
                        "text_id": item.id,
                        "message": (
                            f"text {item.id} holds {held:.2f}s; "
                            f"{len(item.text.split())} words need {needed:.2f}s"
                        ),
                    }
                )

    transition_counts: dict[str, int] = {}
    accent_counts: dict[str, int] = {}
    motion_counts: dict[str, int] = {}
    for shot in edit.shots:
        transition_counts[shot.transition_in.type] = (
            transition_counts.get(shot.transition_in.type, 0) + 1
        )
        motion_counts[shot.motion.type] = motion_counts.get(shot.motion.type, 0) + 1
        for accent in shot.accents:
            accent_counts[accent.type] = accent_counts.get(accent.type, 0) + 1

    ad = _ad_checks(root, project, board, edit)
    for check in ad.get("checks", []):
        if not check["ok"]:
            warnings.append({"code": "ad_check", "message": check["message"]})

    techniques = _technique_rows(edit, board)
    return {
        "present": True,
        "ok": not hard,
        "hard": hard,
        "warnings": warnings,
        "hash": edit_digest(root, edit),
        "coverage": coverage,
        "sections": sections,
        "counts": {
            "shots": total_shots,
            "cuts": max(0, total_shots - 1),
            "holds": total_holds,
            "hold_ratio": hold_ratio,
            "text_layers": sum(len(shot.text) for shot in edit.shots),
            "accents": sum(len(shot.accents) for shot in edit.shots),
            "flashes": len(flashes),
            "motions": motion_counts,
            "transitions": transition_counts,
            "accents_by_type": accent_counts,
        },
        "techniques": techniques,
        "shots": shots,
        "ad": ad,
    }


def _seed_sections(root: Path, project: Project, total: int) -> list[EditSection]:
    music = read_optional(root / "work" / "music.json")
    values = music.get("sections") if isinstance(music, dict) else None
    if isinstance(values, list) and values:
        starts = []
        for item in values:
            if not isinstance(item, dict):
                continue
            try:
                start = max(0, min(total, round(float(item["start"]) * project.fps)))
                end = max(start + 1, min(total, round(float(item["end"]) * project.fps)))
            except (KeyError, TypeError, ValueError):
                continue
            label = str(item.get("label") or "section").strip() or "section"
            starts.append((start, end, label))
        if starts:
            sections = []
            for index, (start, end, label) in enumerate(starts):
                sections.append(
                    EditSection(
                        id=f"section-{index + 1}",
                        start_frame=start,
                        end_frame=end,
                        feel=label,
                        density_per_10s=0,
                    )
                )
            return sections
    events = read_optional(root / "work" / "events.json")
    if isinstance(events, dict):
        values = [
            event
            for event in events.get("events", [])
            if isinstance(event, dict) and event.get("kind") == "section"
        ]
        if values:
            sections = []
            for index, event in enumerate(values):
                start = int(event.get("frame") or 0)
                end = int(
                    event.get("end_frame")
                    or (values[index + 1]["frame"] if index + 1 < len(values) else total)
                )
                sections.append(
                    EditSection(
                        id=f"section-{index + 1}",
                        start_frame=max(0, min(total - 1, start)),
                        end_frame=max(start + 1, min(total, end)),
                        feel=str(event.get("label") or "section"),
                    )
                )
            return sections
    return [EditSection(id="section-1", start_frame=0, end_frame=total, feel="whole film")]


def _seed_motion(shot) -> EditMotion:
    reason = "seeded from the storyboard camera"
    if shot.camera_path is not None:
        start = shot.camera_path.start
        end = shot.camera_path.end
        if start.zoom != end.zoom:
            return EditMotion(
                type="push_in" if end.zoom > start.zoom else "pull_back",
                **{"from": start.zoom, "to": end.zoom},
                easing=shot.camera_path.easing,
                anchor=[end.x, end.y],
                reason=reason,
            )
        return EditMotion(
            type="hold",
            **{"from": 1.0, "to": 1.0},
            anchor=[end.x, end.y],
            reason=reason,
        )
    if shot.camera == "hold":
        return EditMotion(type="hold", reason=reason)
    if shot.camera == "zoom_in":
        return EditMotion(type="push_in", **{"from": 1.0, "to": 1.08}, reason=reason)
    if shot.camera == "zoom_out":
        return EditMotion(type="pull_back", **{"from": 1.08, "to": 1.0}, reason=reason)
    if shot.camera == "pan_left":
        return EditMotion(type="pan_left", **{"from": 1.08, "to": 1.08}, reason=reason)
    return EditMotion(type="pan_right", **{"from": 1.08, "to": 1.08}, reason=reason)


@state_mutation
def seed_edit(root: Path) -> EditDecisionList:
    """Create the first edit without changing the approved cut.

    The storyboard's join and camera controls are translated into edit language so
    seeding is a move of ownership, not a rewrite of the film.
    """
    from . import production as P

    board = P.load_board(root)
    project = P.load_project(root)
    sections = _seed_sections(root, project, board.total_frames)
    shots: list[EditShot] = []
    previous = None
    for shot in board.shots:
        transition = EditTransition(type="cut")
        if previous is not None and previous.transition is not None and previous.dissolve_frames:
            transition = EditTransition(
                type=previous.transition,
                frames=previous.dissolve_frames,
                direction="left" if previous.transition == "wipe_left" else None,
                reason="seeded from the storyboard join",
            )
        shots.append(
            EditShot(
                shot_id=shot.id,
                start_frame=shot.start_frame,
                duration_frames=shot.duration_frames,
                motion=_seed_motion(shot),
                transition_in=transition,
            )
        )
        previous = shot
    edit = EditDecisionList(
        sections=sections,
        shots=shots,
        grade=Grade(),
        notes="Seeded from the storyboard; timing, motion and joins are now edit-owned.",
    )
    return save_edit(root, edit, board=board)


def attach_edit(shots: list[RenderShot], edit: EditDecisionList | None) -> list[RenderShot]:
    """Add the matching edit decision and grade to resolved render shots."""
    if edit is None:
        return shots
    decisions = {shot.shot_id: shot for shot in edit.shots}
    for render_shot in shots:
        decision = decisions.get(render_shot.shot.id)
        if decision is None:
            raise ValueError(f"edit has no decision for shot {render_shot.shot.id}")
        render_shot.edit = decision
        render_shot.grade = edit.grade
    return shots


def summary(root: Path, edit: EditDecisionList | None = None) -> dict:
    """Compact state for the Film UI and the Editor context."""
    edit = edit or load_edit(root)
    if edit is None:
        return {
            "available": False,
            "present": False,
            "report": report(root),
        }
    value = report(root, edit=edit)
    return {
        "available": True,
        "present": True,
        "edit": edit.model_dump(by_alias=True),
        "report": value,
    }


def cut_summary(root: Path, edit: EditDecisionList | None = None) -> dict:
    """The cut list Film shows: human joins, moves, reasons and section names.

    The edit bytes stay authoritative; this is a read-only presentation layer so
    the UI never decodes engine keys or computes timing of its own.
    """
    from . import production as P

    if not (root / "work" / "storyboard.json").is_file():
        return {
            "available": False,
            "present": False,
            "edit": None,
            "sections": [],
            "shots": [],
            "techniques": [],
            "counts": {"shots": 0},
            "hard": [],
            "warnings": [],
            "notes": "",
            "grade": None,
        }
    board = P.load_board(root)
    project = P.load_project(root)
    edit = edit if edit is not None else load_edit(root, board=board)
    if edit is None:
        return {
            "available": False,
            "present": False,
            "edit": None,
            "sections": [],
            "shots": [],
            "techniques": [],
            "counts": {"shots": len(board.shots)},
            "hard": [],
            "warnings": [],
            "notes": "",
            "grade": None,
        }

    value = report(root, edit=edit, board=board, project=project)
    names = _section_names(root)
    windows = _section_windows(edit, board.total_frames)
    sections = []
    for index, (section, start, end) in enumerate(windows):
        sections.append(
            {
                "id": section.id,
                "name": names[index] if index < len(names) else (section.feel or section.id),
                "feel": section.feel,
                "start_frame": start,
                "end_frame": end,
                "techniques": list(section.techniques),
            }
        )

    content = {shot.id: shot for shot in board.shots}
    shots = []
    for shot in edit.shots:
        source = content.get(shot.shot_id)
        home_index = next(
            (
                index
                for index, (_, start, end) in enumerate(windows)
                if start <= shot.start_frame < end
            ),
            len(windows) - 1 if windows else -1,
        )
        home = sections[home_index] if home_index >= 0 else None
        reasons = []
        if shot.transition_in.reason:
            reasons.append(
                {
                    "kind": "transition",
                    "label": transition_label(shot.transition_in),
                    "reason": shot.transition_in.reason,
                }
            )
        if shot.motion.reason:
            reasons.append(
                {
                    "kind": "motion",
                    "label": motion_label(shot.motion),
                    "reason": shot.motion.reason,
                }
            )
        for accent in shot.accents:
            if accent.reason:
                reasons.append(
                    {
                        "kind": "accent",
                        "label": accent_label(accent),
                        "reason": accent.reason,
                    }
                )
        shots.append(
            {
                "shot_id": shot.shot_id,
                "kind": source.kind if source else "scene",
                "section_id": home["id"] if home else None,
                "section_name": home["name"] if home else None,
                "start_frame": shot.start_frame,
                "duration_frames": shot.duration_frames,
                "seconds": round(shot.duration_frames / project.fps, 3),
                "transition": {
                    "type": shot.transition_in.type,
                    "frames": shot.transition_in.frames,
                    "label": transition_label(shot.transition_in),
                    "reason": shot.transition_in.reason,
                },
                "motion": {
                    "type": shot.motion.type,
                    "label": motion_label(shot.motion),
                    "reason": shot.motion.reason,
                },
                "accents": [
                    {
                        "frame": accent.frame,
                        "type": accent.type,
                        "label": accent_label(accent),
                        "reason": accent.reason,
                    }
                    for accent in shot.accents
                ],
                "text": [
                    {
                        "id": item.id,
                        "text": item.text,
                        "style": item.style,
                        "in_frame": item.in_frame,
                        "out_frame": item.out_frame,
                    }
                    for item in shot.text
                ],
                "reasons": reasons,
                "reason": reasons[0]["reason"] if reasons else "",
            }
        )

    return {
        "available": True,
        "present": True,
        "edit": edit.model_dump(by_alias=True),
        "sections": sections,
        "shots": shots,
        "techniques": value["techniques"],
        "counts": value["counts"],
        "hard": value["hard"],
        "warnings": value["warnings"],
        "notes": edit.notes,
        "grade": edit.grade.preset,
    }
