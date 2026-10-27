"""Import user-supplied LRC timestamps; never invent a line's position.

Only lines carrying an explicit ``[mm:ss.xx]`` tag become segments. A segment
ends where the next one starts (the last at the track duration), so the file is a
truthful coarse map, not a per-word alignment.
"""

from __future__ import annotations

import re
from pathlib import Path

from mp3_to_videoclip.models import Lyrics, Segment
from mp3_to_videoclip.storage import digest, read_json, state_mutation, write_json

_TAG = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_METADATA = re.compile(r"^\[[a-zA-Z]+:.*\]$")
MAX_TEXT = 200_000
MAX_LINES = 2_000


@state_mutation
def save_lyrics(root: Path, lyrics: Lyrics) -> None:
    """Replace the live lyrics while keeping the previous artifact in history."""
    previous = root / "work" / "lyrics.json"
    if previous.exists():
        value = read_json(previous)
        archive = root / f"work/lyrics-history/{digest(value)}.json"
        if not archive.exists():
            write_json(archive, value)
    write_json(previous, lyrics.model_dump())


def parse_text(text: str) -> Lyrics:
    """Store pasted lines as text; never invent a timestamp or alignment."""
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("paste a reasonable amount of lyrics")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("paste at least one lyric line")
    if len(lines) > MAX_LINES:
        raise ValueError(f"keep the lyrics under {MAX_LINES} lines")
    return Lyrics(
        provider="manual",
        model="text",
        segments=[],
        lines=lines,
        warning="Pasted words are unverified and untimed; no timestamps were invented.",
    )


def parse_lyrics_text(text: str, duration: float) -> Lyrics:
    """Accept plain lines or LRC in the same paste box.

    A paste with timestamps is treated as LRC. A paste without them is stored
    as untimed lines exactly as written, so the artifact never claims a timing
    the user did not give. Mixing timed and untimed lines is refused rather than
    silently dropping the lines a coarse LRC parse cannot place.
    """
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("paste a reasonable amount of lyrics")
    lyric_lines = [
        line for line in text.splitlines() if line.strip() and not _METADATA.match(line.strip())
    ]
    if not lyric_lines:
        raise ValueError("paste at least one lyric line")
    timed = [bool(_TAG.search(line)) for line in lyric_lines]
    if any(timed) and not all(timed):
        raise ValueError(
            "put a timestamp on every line, or paste plain text without any timestamps"
        )
    if any(timed):
        return parse_lrc(text, duration)
    return parse_text(text)


def parse_lrc(text: str, duration: float) -> Lyrics:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("paste at least one timestamped line")
    entries: list[tuple[float, str]] = []
    for raw in text.splitlines():
        tags = list(_TAG.finditer(raw))
        if not tags:
            continue
        body = _TAG.sub("", raw).strip()
        if not body:
            continue
        for match in tags:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            if seconds >= 60:
                raise ValueError("LRC seconds must be below 60")
            fraction = match.group(3)
            offset = float(f"0.{fraction}") if fraction else 0.0
            start = minutes * 60 + seconds + offset
            if start >= duration:
                raise ValueError("an LRC timestamp is beyond the end of the track")
            entries.append((start, body))
    if not entries:
        raise ValueError("no [mm:ss.xx] timestamps found")
    entries.sort()
    for previous, current in zip(entries, entries[1:], strict=False):
        if current[0] == previous[0]:
            raise ValueError("two lyric lines share a timestamp")
    segments = [
        Segment(
            start=start,
            end=entries[index + 1][0] if index + 1 < len(entries) else duration,
            text=body,
        )
        for index, (start, body) in enumerate(entries)
    ]
    return Lyrics(
        provider="manual",
        model="lrc",
        segments=segments,
        warning="Imported LRC timestamps; confirm the lines match what is sung.",
    )
