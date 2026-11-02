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
    except Exception as exc:
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
    except Exception as exc:
        return f"unreadable ({_clip(exc, 80)})"
    if current != chosen.get("input_hash"):
        return f"stale (inputs changed), selected v{selected}"
    return f"current v{selected}"


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _song(root: Path) -> list[str]:
    """What the song does, on every task. Compact, because it is sent every turn."""
    from mp3_to_videoclip import song_map

    heading = "## The song (measured estimates)"
    try:
        song = song_map.song_map(root)
    except Exception as exc:
        return [heading, f"- Unavailable ({_clip(exc, 80)})."]
    if not song.get("available"):
        return [heading, "- Not analysed yet."]
    tempo, key = song["tempo"], song["key"]
    parts = [f"tempo {tempo['bpm'] if tempo['bpm'] is not None else 'unknown'} BPM"]
    if tempo.get("half_bpm"):
        parts[0] += f" (could be {tempo['half_bpm']} or {tempo['double_bpm']})"
    if key.get("tonic"):
        rival = f", or {key['runner_up']}" if key.get("runner_up") else ""
        parts.append(f"key {key['tonic']} {key['mode']}{rival}")
    if song.get("grid_trusted"):
        parts.append(f"{song['beats_per_bar']} beats a bar, {song['bar_frames']} frames a bar")
    else:
        parts.append("no trusted bar grid")
    lines = [heading, "- " + "; ".join(parts) + "."]
    for section in song["sections"]:
        first = section.get("first_line")
        lines.append(
            f"- {section['name']} {_clock(section['start'])}-{_clock(section['end'])}, "
            f"{section['energy_word']}, about {section['target_per_10s']} cuts per 10 s"
            + (f', first sung "{_clip(first, 60)}"' if first else "")
        )
    if song.get("sparkline"):
        digits = "".join(str(value) for value in song["sparkline"])
        lines.append(f"- Loudness across the song, 0 to 9: {digits}")
    return lines


#: Writer tasks that write words against the song, so they need the sung lines in front of them.
LYRIC_TASKS = frozenset({"concepts", "script_mv", "script_ad", "import", "storyboard"})
TREATMENT_LIMIT = 4000
PASSAGE_LIMIT = 1200


def _writes(task: str | None) -> bool:
    from mp3_to_videoclip.director.prompts import TASKS

    return task in TASKS["writer"]


def _treatment(text: str | None, task: str | None) -> str:
    """Whole where the task writes from it, with a cap that protects the budget."""
    if not _writes(task):
        return _clip(text, 420)
    clipped = _clip(text, TREATMENT_LIMIT)
    return clipped + (" (cut at 4,000 characters)" if clipped.endswith("…") else "")


def _sung_lines(root: Path) -> list[str]:
    from mp3_to_videoclip.domain import lyric_timing

    rows = [row for row in lyric_timing.view(root)["lines"] if not row["tag"]]
    if not rows:
        return []
    timed = sum(1 for row in rows if row["start"] is not None)
    lines = [f"## Sung lines ({timed} of {len(rows)} timed)"]
    for row in rows:
        if row["start"] is None:
            lines.append(f"- {_clip(row['text'], 160)}")
        else:
            lines.append(f"- {_clock(row['start'])} ({row['source']}) {_clip(row['text'], 160)}")
    return lines


def _pictures(brief, assets: dict) -> list[str]:
    """What the model can look at before it writes a prompt, under the ids get_images takes."""
    rows = []
    creative = brief.creative
    for reference in creative.references if creative else []:
        rows.append(f"- {reference.id} ({reference.kind}): {_clip(reference.description, 160)}")
    for character in brief.characters:
        if character.references:
            rows.append(
                f"- character:{character.id}: {len(character.references)} reference image(s) "
                f"of {_clip(character.identity or character.description, 90)}"
            )
    for key, entry in assets.items():
        if key.startswith("sheet:") and isinstance(entry, dict) and entry.get("selected"):
            rows.append(f"- {key}: the sheet or plate made for it, version {entry['selected']}")
    return ["## Pictures to look at with get_images", *rows] if rows else []


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
                lines.append(f"- not on the song: {_clip(item['text'], PASSAGE_LIMIT)}")
                continue
            first = timeline.frame_number(start, project.fps)
            last = min(timeline.frame_number(end, project.fps), project.total_frames)
            lines.append(
                f"- {start:.2f}-{end:.2f}s (frames {first}-{last}): {_clip(item['text'], PASSAGE_LIMIT)}"
            )
            placed += 1
    except Exception as exc:
        return [
            heading,
            f"- Unavailable ({_clip(exc, 80)}): treat every passage as not on the song.",
        ]
    if not lines:
        return [heading, "- No treatment yet."]
    return [f"{heading}: {placed} of {len(lines)} placed", *lines]


def _narration(root: Path) -> list[str]:
    """A story film's clock: its structure, its budgets and its lines, on every task."""
    from mp3_to_videoclip import narration, narration_timing
    from mp3_to_videoclip.production import script as scripts

    heading = "## The narration"
    report = scripts.script_report(root)
    if not report["beats"]:
        return [heading, "- No script yet. There is no song: the kept takes will be the clock."]
    lines = [heading, f"- Voice: {narration.current_voice(root)}."]
    rate = report.get("measured_rate")
    lines.append(
        f"- Reading rate: {rate} words a second, measured."
        if rate
        else f"- Reading rate: {report['assumed_rate']} words a second, assumed until takes exist."
    )
    for beat in report["beats"]:
        lines.append(
            f"- Beat {beat['id']}: budget {beat['budget']:.1f} s, estimate {beat['estimate']:.1f} s"
            + (f", measured {beat['measured']:.1f} s" if beat["measured"] is not None else "")
        )
    for row in narration_timing.read(root)["lines"]:
        lines.append(
            f"- {row['id']} ({row['beat']}, {row['source']}) {_clock(row['start'])}-{_clock(row['end'])}: "
            f"{_clip(row['text'], 200)}"
        )
    if report["stale"]:
        lines.append(f"- Stale takes, whose words changed: {', '.join(report['stale'])}.")
    if report["invented"]:
        lines.append(f"- Invented claims listed: {len(report['invented'])}.")
    lines.extend(f"- {note}" for note in report["notes"])
    return lines


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
            f"- Budget: {_budget(root)}",
            f"- Recorded approvals (not revalidated): {_approvals(root)}",
            "- Still status checks the recorded input hash and file presence; "
            "exact bytes are verified when a stage loads them.",
        ]
        if stage:
            lines.append(f"- Current stage: {stage}")
        lines.append("")
        lines.extend(_narration(root) if project.spine == "soundtrack" else _song(root))
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
        lines.append(f"- Treatment: {_treatment(brief.treatment, task)}")
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
        waiting = P.unconfirmed_permissions(brief)
        if waiting:
            lines.append(f"- Owner must confirm permission for: {', '.join(waiting)}.")
        lines.append("")
        if task in LYRIC_TASKS:
            sung = _sung_lines(root)
            if sung:
                lines.extend([*sung, ""])
        if _writes(task):
            pictures = _pictures(brief, assets)
            if pictures:
                lines.extend([*pictures, ""])
            if project.spine != "soundtrack":
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
        except (OSError, ValueError) as exc:
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
    except Exception as exc:
        return f"Project {slug}: {exc}"
