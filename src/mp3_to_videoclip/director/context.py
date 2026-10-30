"""Build the per-turn project context for the director.

This is a snapshot for the model, not a gate check: it reads the project, brief,
board, selected still metadata and recorded approvals without re-hashing the
source MP3 or running every approval chain. The expensive authoritative checks
stay in the stage routes and jobs.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip.storage import digest, read_optional


def _clip(value, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _approvals(root: Path) -> str:
    recorded = read_optional(root / "work" / "approvals.json", {})
    if not isinstance(recorded, dict) or not recorded:
        return "none recorded"
    parts = []
    for stage, value in recorded.items():
        if not isinstance(value, dict):
            continue
        at = str(value.get("at") or "")
        note = _clip(value.get("note"), 80)
        parts.append(f"{stage} at {at}" + (f" ({note})" if note else ""))
    return "; ".join(parts) or "none recorded"


def _budget(root: Path) -> str:
    try:
        from mp3_to_videoclip.domain import budget

        cap = budget.cap(root)
        committed = budget.committed(root)
        remaining = budget.remaining(root)
        return (
            f"cap {('$' + budget.fmt(cap)) if cap is not None else 'unset'}; "
            f"committed ${budget.fmt(committed)}; "
            f"remaining {('$' + budget.fmt(remaining)) if remaining is not None else 'unbounded'}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"unavailable ({exc})"


def _still_status(root: Path, shot, assets: dict) -> str:
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip import shotkinds

    if shot.asset_shot_id is None and shotkinds.is_local(shot):
        return f"local {shot.kind} (no paid still)"
    owner = shot.asset_shot_id or shot.id
    entry = assets.get(owner, {}) if isinstance(assets, dict) else {}
    versions = entry.get("versions", []) if isinstance(entry, dict) else []
    selected = entry.get("selected") if isinstance(entry, dict) else None
    chosen = next((version for version in versions if version.get("version") == selected), None)
    if not chosen:
        return "missing (no selected still)"
    relative = chosen.get("path")
    if not isinstance(relative, str) or not relative:
        return "missing (no stored path)"
    try:
        from mp3_to_videoclip.storage import inside

        path = inside(root, relative)
    except ValueError:
        return "unreadable (path outside project)"
    if not path.is_file():
        return "missing (selected file)"
    try:
        current = digest(P.image_spec(root, shot, verify_source=False))
    except Exception as exc:  # noqa: BLE001
        return f"unreadable ({_clip(exc, 80)})"
    if current != chosen.get("input_hash"):
        return f"stale (inputs changed), selected v{selected}"
    return f"current v{selected}"


def _music(root: Path) -> str:
    from mp3_to_videoclip.domain import music_notes

    music = read_optional(root / "work" / "music.json")
    if not isinstance(music, dict):
        return "not analysed"
    sections = music.get("sections") or []
    names = music_notes.names_by_start(root)
    labels = []
    try:
        labels = [
            f"{names.get(round(float(item.get('start', 0)), 3)) or music_notes.default_name(index)} "
            f"{float(item.get('start', 0)):.0f}-{float(item.get('end', 0)):.0f}s"
            for index, item in enumerate(sections)
            if isinstance(item, dict)
        ]
    except (TypeError, ValueError):
        labels = []
    tempo = music.get("estimated_tempo_bpm")
    text = f"tempo {tempo if tempo is not None else 'unknown'} BPM"
    if labels:
        text += "; sections: " + ", ".join(labels[:12])
    warnings = music.get("warnings") or []
    if warnings:
        text += "; warnings: " + _clip("; ".join(str(w) for w in warnings), 180)
    return text


def _story_on_song(root: Path, project) -> list[str]:
    """When each passage plays, for the board. Evidence only: no approval reads this."""
    from mp3_to_videoclip import story_beats, timeline

    heading = "## Story on the song (evidence, not an approval)"
    try:
        lines = []
        placed = 0
        for item in story_beats.passages(root):
            start, end = item["start"], item["end"]
            # A time past the film is left over from another excerpt, so it is no time at all.
            if start is None or end is None or end > project.duration + 0.5:
                lines.append(f"- not on the song: {_clip(item['text'])}")
                continue
            first = timeline.frame_number(start, project.fps)
            last = min(timeline.frame_number(end, project.fps), project.total_frames)
            lines.append(f"- {start:.2f}-{end:.2f}s (frames {first}-{last}): {_clip(item['text'])}")
            placed += 1
    except Exception as exc:  # noqa: BLE001
        return [
            heading,
            f"- Unavailable ({_clip(exc, 80)}): treat every passage as not on the song.",
        ]
    if not lines:
        return [heading, "- No treatment yet."]
    return [f"{heading}: {placed} of {len(lines)} placed", *lines]


def build_context(
    slug: str,
    projects_dir: Path | None = None,
    stage: str | None = None,
    context: dict | None = None,
    task: str | None = None,
) -> str:
    """Compact project snapshot for the director's system prompt."""
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.models import Storyboard

    root = (projects_dir or Path("projects")) / slug
    if not root.is_dir():
        return f"Project {slug} not found."
    try:
        project = P.load_project(root, verify_source=False)
        brief = P.load_brief(root)
        board_value = (
            read_optional(root / "work" / "storyboard.json")
            if (root / "work" / "storyboard.json").is_file()
            else None
        )
        board = Storyboard.model_validate(board_value) if isinstance(board_value, dict) else None
        assets = read_optional(root / "work" / "assets.json", {})
        if not isinstance(assets, dict):
            assets = {}
        lines = [
            f"# Project snapshot: {project.title} ({root.name})",
            f"- Schema {project.schema_version}; kind "
            f"{project.kind or 'music_video (legacy)'}; {project.duration:.1f}s; "
            f"{project.total_frames} frames at {project.fps}fps; {project.aspect}.",
            f"- Source: {project.source_duration or project.duration:.1f}s"
            + (
                f"; excerpt {project.audio_window.start:.1f}-{project.audio_window.end:.1f}s "
                f"(fade in {project.audio_window.fade_in:.1f}, out {project.audio_window.fade_out:.1f})"
                if project.audio_window is not None
                else "; whole track"
            ),
            f"- Music: {_music(root)}",
            f"- Budget: {_budget(root)}",
            f"- Recorded approvals (not revalidated): {_approvals(root)}",
            "- Still status checks the recorded input hash and file presence; "
            "exact bytes are verified when a stage loads them.",
        ]
        if stage:
            lines.append(f"- Current stage: {stage}")
        if context:
            lines.append("")
            lines.append("## Session context")
            if context.get("stage"):
                lines.append(f"- Stage when asked: {context['stage']}")
            if isinstance(context.get("time"), (int, float)):
                lines.append(f"- Playhead: {float(context['time']):.2f}s")
            selected = context.get("selected_shots") or []
            if selected:
                lines.append("- Selected shots: " + ", ".join(selected))
        lines.append("")
        lines.append("## Brief")
        if brief.intent is not None:
            intent = brief.intent
            lines.append(
                f"- Intent: objective {_clip(intent.objective, 120)}; audience "
                f"{_clip(intent.audience, 80)}; message {_clip(intent.message, 120)}"
            )
            if intent.reasons:
                lines.append("- Reasons: " + "; ".join(_clip(x, 80) for x in intent.reasons))
            if intent.cta is not None and (intent.cta.text or intent.cta.url):
                lines.append(
                    f"- CTA: {_clip(intent.cta.text, 60)} {_clip(intent.cta.url, 100)}".rstrip()
                )
        lines.append(f"- Direction: {_clip(brief.direction)}")
        lines.append(f"- Style: {_clip(brief.style)}")
        lines.append(f"- Treatment: {_clip(brief.treatment, 420)}")
        creative = brief.creative
        if creative is not None:
            lines.append(f"- Look: {_clip(creative.look, 360)}")
            lines.append(
                f"- World: {len(brief.characters)} characters, {len(creative.scenes)} scenes, "
                f"{len(creative.references)} visual references, {len(creative.image_rules)} image "
                f"rules; profile v{creative.profile_version or 0}; "
                f"proof {', '.join(creative.proof_shot_ids) or 'unset'}."
            )
        else:
            lines.append("- Creative profile: none (legacy brief).")
        if brief.characters:
            lines.append(
                "- Characters: "
                + "; ".join(
                    f"{character.id} ({_clip(character.identity or character.description, 90)})"
                    for character in brief.characters
                )
            )
        else:
            lines.append("- Characters: none.")
        lines.append("")
        if task == "storyboard":
            lines.extend(_story_on_song(root, project))
            lines.append("")
        if board is None:
            lines.append("## Shots\nNo storyboard yet.")
            return "\n".join(lines)
        from mp3_to_videoclip import edits

        source_board = board
        edit = edits.load_edit(root, board=board)
        if edit is not None:
            board = edit.effective_board(board)
        statuses = []
        placeholders = 0
        shot_lines = []
        for shot in board.shots:
            status = _still_status(root, shot, assets)
            statuses.append(status)
            if P.has_placeholders(shot):
                placeholders += 1
            start = shot.start_frame / project.fps
            end = (shot.start_frame + shot.duration_frames) / project.fps
            alias = f" (reprise of {shot.asset_shot_id})" if shot.asset_shot_id else ""
            shot_lines.append(
                f"- {shot.id}{alias} [{shot.kind}] {start:.1f}-{end:.1f}s "
                f"{shot.framing or 'framing unset'} | {status} | {_clip(shot.purpose, 100)}"
            )
        current = sum(1 for value in statuses if value.startswith("current"))
        missing = sum(1 for value in statuses if value.startswith("missing"))
        stale = sum(1 for value in statuses if value.startswith("stale"))
        unreadable = sum(1 for value in statuses if value.startswith("unreadable"))
        lines.append(
            f"## Shots ({len(board.shots)}: {current} current, {missing} missing, "
            f"{stale} stale, {unreadable} unreadable; {placeholders} marked placeholders)"
        )
        lines.extend(shot_lines)
        try:
            cut_report = edits.report(root, edit=edit, board=source_board, project=project)
        except (OSError, ValueError) as exc:  # noqa: BLE001
            lines.append(f"## Cut\nReport unavailable: {_clip(exc, 180)}")
            return "\n".join(lines)
        if cut_report.get("present"):
            lines.append("")
            lines.append("## Cut (edit-owned timing and motion)")
            counts = cut_report.get("counts", {})
            lines.append(
                f"- {counts.get('shots', 0)} shots, {counts.get('cuts', 0)} cuts, "
                f"{counts.get('holds', 0)} holds "
                f"({float(counts.get('hold_ratio', 0)) * 100:.0f}%); "
                f"grade {edit.grade.preset if edit is not None else 'none'}; "
                f"{len(cut_report.get('hard', []))} hard, "
                f"{len(cut_report.get('warnings', []))} warnings."
            )
            for section in cut_report.get("sections", [])[:10]:
                lines.append(
                    f"- {section['id']} {section['start_frame']}-{section['end_frame']} "
                    f"({section.get('energy') or 'energy unknown'}) "
                    f"{section['density_per_10s']}/10s target "
                    f"{section['target_density_per_10s']}/10s: {_clip(section['feel'], 90)}"
                )
            for finding in cut_report.get("hard", [])[:8]:
                lines.append(f"- HARD {finding['code']}: {_clip(finding['message'], 180)}")
            for finding in cut_report.get("warnings", [])[:8]:
                lines.append(f"- warning {finding['code']}: {_clip(finding['message'], 180)}")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"Project {slug}: {exc}"
