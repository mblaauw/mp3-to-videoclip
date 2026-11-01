"""When each line is said: estimated from the words, then measured from the kept takes.

``work/narration-timing.json`` is the one record the board, the report and the Writer read.
A line with a take is measured from the mix layout, exact by construction; a line without one
is an estimate and says so. Nothing here reads or writes audio.
"""

from __future__ import annotations

from pathlib import Path

from .production.script import line_seconds, load_script
from .storage import read_optional, write_json

FILE = "work/narration-timing.json"


def _kept(root: Path) -> dict[str, dict]:
    from . import narration

    return narration.selected_takes(root)


def layout(root: Path) -> list[dict]:
    """Every line in order, placed end to end with its pause."""
    script = load_script(root)
    if script is None:
        return []
    from .production import soundtrack

    spec = soundtrack.read_spec(root)
    takes = _kept(root)
    cursor = 0.0
    rows = []
    by_id = {line.id: line for line in script.lines}
    for line_id in soundtrack.order(script, spec):
        line = by_id[line_id]
        take = takes.get(line_id)
        seconds = float(take["seconds"]) if take else line_seconds(line, script.reading_rate_wps)
        pause = float(spec.get("pauses", {}).get(line_id, line.pause_after))
        rows.append(
            {
                "id": line_id,
                "beat": line.beat,
                "text": line.text,
                "start": round(cursor, 3),
                "end": round(cursor + seconds, 3),
                "pause_after": pause,
                "source": "measured" if take else "estimate",
            }
        )
        cursor += seconds + pause
    return rows


def duration(rows: list[dict]) -> float:
    return round(rows[-1]["end"] + rows[-1]["pause_after"], 3) if rows else 0.0


def refresh(root: Path) -> dict:
    """Recompute from the script and the kept takes. Word times survive for unchanged takes."""
    previous = read(root)
    words = {row["id"]: row for row in previous.get("lines", []) if row.get("words")}
    takes = _kept(root)
    rows = layout(root)
    for row in rows:
        kept = words.get(row["id"])
        take = takes.get(row["id"])
        if kept and take and kept.get("take_sha256") == take["sha256"]:
            offset = row["start"] - kept["start"]
            row["source"] = kept["source"]
            row["take_sha256"] = kept["take_sha256"]
            row["words"] = [
                {
                    **word,
                    "start": round(word["start"] + offset, 3),
                    "end": round(word["end"] + offset, 3),
                }  # fmt: skip
                for word in kept["words"]
            ]
    value = {"lines": rows, "duration": duration(rows)}
    write_json(root / FILE, value)
    return value


def read(root: Path) -> dict:
    value = read_optional(root / FILE)
    return value if isinstance(value, dict) else {"lines": [], "duration": 0.0}


def align(root: Path) -> dict:
    """Word times from each selected take against its own words, where the tools run here."""
    from . import lyric_tools
    from .storage import inside

    status = lyric_tools.status()
    if not status["ready"]:
        raise ValueError(status.get("reason") or "captions are per line on this computer")
    takes = _kept(root)
    value = refresh(root)
    aligned = 0
    for row in value["lines"]:
        take = takes.get(row["id"])
        if not take:
            continue
        heard = lyric_tools.heard_words(
            lyric_tools.hear(root, inside(root, take["path"]))["tokens"]
        )
        known = {word.lower().strip(".,;:!?\"'") for word in row["text"].split()}
        words = [word for word in heard if word["text"].lower().strip(".,;:!?\"'") in known]
        if not words:
            continue
        row["source"] = "aligned"
        row["take_sha256"] = take["sha256"]
        row["words"] = [
            {
                "text": word["text"],
                "start": round(row["start"] + word["start"], 3),
                "end": round(row["start"] + word["end"], 3),
            }
            for word in words
        ]
        aligned += 1
    write_json(root / FILE, value)
    return {"aligned": aligned, "lines": len(value["lines"])}


def measured_rate(root: Path) -> float | None:
    """Words a second across the kept takes, pauses excluded."""
    rows = [row for row in read(root).get("lines", []) if row["source"] != "estimate"]
    seconds = sum(row["end"] - row["start"] for row in rows)
    return (
        round(sum(len(row["text"].split()) for row in rows) / seconds, 2) if seconds > 0 else None
    )
