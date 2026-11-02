"""A story film's words: the script, the beats it fills and what the numbers say."""

from pathlib import Path

from .. import structures
from ..models import Script, ScriptLine
from ..storage import read_json, read_optional, state_mutation, write_json
from .brief import _record_prompt_write, load_brief
from .project import STAGE_FILES, load_project

BEATS = "work/beats.json"
#: A beat's lines may overrun its budget by this much before the script is refused.
OVERRUN = 1.2


def load_script(root: Path) -> Script | None:
    value = read_optional(root / STAGE_FILES["script"])
    return Script.model_validate(value) if isinstance(value, dict) else None


def require_script(root: Path) -> Script:
    script = load_script(root)
    if script is None:
        raise ValueError("write the script first")
    return script


def words(text: str) -> int:
    return len(text.split())


def line_seconds(line: ScriptLine, rate: float) -> float:
    """How long a line should take at this rate, before anyone has said it."""
    return round(words(line.text) / rate, 3)


def beats_for(root: Path, structure: str) -> dict:
    """The template at this film's requested length, fixed when the film was created."""
    brief = load_brief(root)
    intent = brief.intent
    length = float(intent.length_seconds) if intent and intent.length_seconds else 0.0
    return structures.instance(structure, length or load_project(root).duration)


def _check(root: Path, script: Script) -> dict:
    instance = beats_for(root, script.structure)
    budgets = {beat["id"]: beat["budget"] for beat in instance["beats"]}
    fictional = bool((brief := load_brief(root)).intent and brief.intent.fictional)
    spent: dict[str, float] = {}
    for line in script.lines:
        if line.beat not in budgets:
            raise ValueError(f"line {line.id} is on a beat this structure does not have: {line.beat}")  # fmt: skip
        if not fictional and any(claim.invented for claim in line.claims):
            raise ValueError(
                f"line {line.id} invents a fact, and this film's world is not fictional. "
                "Use the owner's facts, or ask them to mark the world as fictional."
            )
        seconds = line.target_seconds or line_seconds(line, script.reading_rate_wps)
        spent[line.beat] = spent.get(line.beat, 0.0) + seconds
    for beat, seconds in spent.items():
        if seconds > budgets[beat] * OVERRUN:
            raise ValueError(
                f"the {beat} beat has {seconds:.1f} s of lines for a {budgets[beat]:.1f} s budget; "
                "cut a line or shorten one"
            )
    return instance


@state_mutation
def write_script(root: Path, payload: dict) -> Script:
    """Validate and write the whole script, with its beats and a fresh estimate."""
    from .. import narration_timing
    from . import soundtrack

    if load_project(root).spine != "soundtrack":
        raise ValueError("only a story film has a script")
    try:
        script = Script.model_validate(payload)
    except ValueError as exc:
        raise ValueError(f"the script is invalid: {exc}") from exc
    instance = _check(root, script)
    write_json(root / STAGE_FILES["script"], script.model_dump())
    write_json(root / BEATS, instance)
    soundtrack.ensure_spec(root, script)
    narration_timing.refresh(root)
    _record_prompt_write(root, "script")
    return script


@state_mutation
def update_lines(root: Path, changes: list) -> Script:
    """Change named lines. Unknown ids are refused; every other line stays as it is."""
    script = require_script(root)
    if not isinstance(changes, list) or not changes:
        raise ValueError("name at least one line to change")
    by_id = {line.id: line.model_dump() for line in script.lines}
    for change in changes:
        if not isinstance(change, dict) or change.get("id") not in by_id:
            raise ValueError(f"unknown script line {change.get('id') if isinstance(change, dict) else change}")  # fmt: skip
        by_id[change["id"]].update(change)
    return write_script(root, {**script.model_dump(), "lines": list(by_id.values())})


def read_beats(root: Path) -> dict | None:
    path = root / BEATS
    return read_json(path) if path.is_file() else None


def script_report(root: Path) -> dict:
    """Each beat's budget against the estimate and the real takes, in plain sentences."""
    from .. import narration, narration_timing

    script = load_script(root)
    beats = read_beats(root)
    if script is None or beats is None:
        return {"beats": [], "invented": [], "stale": [], "notes": []}
    rows = narration_timing.read(root)["lines"]
    report = []
    notes = []
    for beat in beats["beats"]:
        lines = [line for line in script.lines if line.beat == beat["id"]]
        placed = [row for row in rows if row["beat"] == beat["id"]]
        estimate = sum(line_seconds(line, script.reading_rate_wps) + line.pause_after for line in lines)  # fmt: skip
        measured_rows = [row for row in placed if row["source"] != "estimate"]
        span = sum(row["end"] - row["start"] + row["pause_after"] for row in placed)
        # A pause is a choice, so only speech can overrun: the same rule that refuses a script.
        spoken = sum(row["end"] - row["start"] for row in placed)
        over = round(spoken - beat["budget"], 2)
        complete = bool(placed) and len(measured_rows) == len(placed)
        entry = {
            "id": beat["id"],
            "label": beat["label"],
            "budget": beat["budget"],
            "estimate": round(estimate, 2),
            "measured": round(span, 2) if complete else None,
            "spoken": round(spoken, 2) if complete else None,
            "over": over if complete else None,
            "lines": [line.id for line in lines],
        }
        report.append(entry)
        if complete and over > 0:
            longest = max(placed, key=lambda row: row["end"] - row["start"])
            notes.append(
                f"{beat['label']} runs {over:.1f} s of speech over its {beat['budget']:.0f} s budget; "
                f"{longest['id']} is its longest line."
            )
    moved = read_optional(root / "work/retime-notes.json")
    return {
        "beats": report,
        "invented": [
            {"line": line.id, "text": claim.text}
            for line in script.lines
            for claim in line.claims
            if claim.invented
        ],
        "stale": narration.stale_lines(root),
        "measured_rate": narration_timing.measured_rate(root),
        "assumed_rate": script.reading_rate_wps,
        "moved": moved.get("moved", []) if isinstance(moved, dict) else [],
        "notes": notes,
    }
