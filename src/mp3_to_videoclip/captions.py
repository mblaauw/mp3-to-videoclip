"""Timed sung lines as text layers and as SRT and VTT files.

A caption is an ordinary ``lyric`` text layer named ``cap-<line>``, so choosing
captions is a cut change: its approval goes stale like any other, and a cut with no
captions serialises exactly as before. The sidecars always hold every timed line,
whichever were burned in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import timeline
from .domain import lyric_timing
from .models import EditDecisionList, EditText

PREFIX = "cap-"
MIN_SECONDS = 1.0
MAX_SECONDS = 6.0
#: Frames left clear before the next line, so two lines never touch.
GAP_FRAMES = 2
#: A continuation shorter than this would only flash at the end of a line.
MIN_TAIL_SECONDS = 0.5
MAX_TEXT = 160
NAMED = ("hook", "chorus", "refrain")


def _clipped(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1].rstrip() + "…"


def timed_lines(root: Path, fps: int, total_frames: int) -> list[dict[str, Any]]:
    """Each timed sung line with the frames it is on screen, in order."""
    rows = [
        row
        for row in lyric_timing.view(root)["lines"]
        if row["start"] is not None and not row["tag"]
    ]
    lines = []
    for position, row in enumerate(rows):
        start = timeline.frame_number(row["start"], fps)
        if start >= total_frames:
            continue
        end = timeline.frame_number(row["end"], fps) if row.get("end") else None
        following = rows[position + 1]["start"] if position + 1 < len(rows) else None
        limit = total_frames
        if following is not None:
            limit = min(limit, timeline.frame_number(following, fps) - GAP_FRAMES)
        if end is None:
            end = limit
        end = max(end, start + round(MIN_SECONDS * fps))
        end = min(end, start + round(MAX_SECONDS * fps), limit)
        if end > start:
            line = {"index": row["index"], "text": row["text"], "start": start, "end": end}
            if row.get("words"):
                line["words"] = [
                    {"text": word["text"], "in_frame": timeline.frame_number(word["start"], fps)}
                    for word in row["words"]
                ]
            lines.append(line)
    return lines


def named_indexes(root: Path, lines: list[dict[str, Any]]) -> list[int]:
    """The lines inside sections the owner named hook, chorus or refrain."""
    from .song_map import song_map

    spans = [
        (section["start_frame"], section["end_frame"])
        for section in song_map(root).get("sections", [])
        if any(word in section["name"].lower() for word in NAMED)
    ]
    return [
        line["index"] for line in lines if any(start <= line["start"] < end for start, end in spans)
    ]


def caption_layers(
    edit: EditDecisionList,
    lines: list[dict[str, Any]],
    indexes: set[int] | None,
    fps: int,
    style: str = "lyric",
) -> dict[str, list[EditText]]:
    """The layers per shot: clipped to the shot, continued when a line crosses a join."""
    layers: dict[str, list[EditText]] = {shot.shot_id: [] for shot in edit.shots}
    for line in lines:
        if indexes is not None and line["index"] not in indexes:
            continue
        part = 0
        for shot in edit.shots:
            shot_end = shot.start_frame + shot.duration_frames
            start = max(line["start"], shot.start_frame)
            end = min(line["end"], shot_end)
            if end <= start:
                continue
            part += 1
            if part > 1 and end - start < MIN_TAIL_SECONDS * fps:
                continue
            # Words land where they were heard, when the whole line was and it fits one shot.
            words = line.get("words") or []
            whole = (
                words
                and part == 1
                and start == line["start"]
                and end == line["end"]
                and len(line["text"]) <= MAX_TEXT
                and all(start <= word["in_frame"] < end for word in words)
            )
            layers[shot.shot_id].append(
                EditText(
                    id=f"{PREFIX}{line['index']}" + (f"-{part}" if part > 1 else ""),
                    style=style,
                    text=_clipped(line["text"]),
                    in_frame=start,
                    out_frame=end,
                    animation="kinetic_words" if whole else "fade",
                    **({"words": words} if whole else {}),
                )
            )
    return layers


def _stamp(frame: int, fps: int, separator: str) -> str:
    milliseconds = frame * 1000 // fps
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def srt(lines: list[dict[str, Any]], fps: int) -> str:
    blocks = [
        f"{number}\n{_stamp(line['start'], fps, ',')} --> {_stamp(line['end'], fps, ',')}\n"
        f"{line['text']}\n"
        for number, line in enumerate(lines, start=1)
    ]
    return "\n".join(blocks)


def vtt(lines: list[dict[str, Any]], fps: int) -> str:
    blocks = [
        f"{_stamp(line['start'], fps, '.')} --> {_stamp(line['end'], fps, '.')}\n{line['text']}\n"
        for line in lines
    ]
    return "\n".join(["WEBVTT\n", *blocks])


def sidecars_for(root: Path, output: Path, project) -> list[str]:
    """Write the two files beside a new final. They never replace an existing file."""
    lines = timed_lines(root, project.fps, round(project.duration * project.fps))
    if not lines:
        return []
    written = []
    for suffix, text in ((".srt", srt(lines, project.fps)), (".vtt", vtt(lines, project.fps))):
        path = Path(output).with_suffix(suffix)
        if not path.exists():
            path.write_text(text, encoding="utf-8")
            written.append(path.name)
    return written
