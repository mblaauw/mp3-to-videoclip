"""One song map from everything already measured: what the song does, in film frames.

It merges the quick and the deep measurements with the owner's section layer and the
timed words into ``work/song-map.json``, a cache keyed by the hashes of its inputs.
``work/music.json`` is never rewritten, so no approval moves. Nothing here hears
anything new: no model, no network, and every value is an estimate unless it says the
owner made it. (``music_map.py`` is a different thing: the paid listening draft.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import pacing, timeline
from .storage import digest, file_hash, read_optional, write_json

FILE = "work/song-map.json"
VERSION = 1
INPUTS = (
    "work/music.json",
    "work/music-deep.json",
    "work/section-map.json",
    "work/music-notes.json",
    "work/lyric-timing.json",
    "work/lyrics.json",
)
#: Fewer boundaries than this and the novelty curve found no structure worth using.
MIN_BOUNDARIES = 2
MIN_SECTION_SECONDS = 2.0
#: A bar-length score near 1.0 means the downbeat phase was not found.
GRID_SCORE = 1.1
SPARK_POINTS = 20
SNAP_SECONDS = 1.0
QUIET, FULL = 0.34, 0.67


def _energy(music: dict, start: float, end: float) -> float:
    points = [
        float(point.get("energy") or 0)
        for point in music.get("energy_curve") or []
        if isinstance(point, dict) and start <= float(point.get("time") or 0) < end
    ]
    return sum(points) / len(points) if points else 0.0


def _note_starts(root: Path) -> set[float]:
    value = read_optional(Path(root) / "work" / "music-notes.json")
    items = value.get("sections") if isinstance(value, dict) else None
    return {
        round(float(item["start"]), 3)
        for item in items or []
        if isinstance(item, dict) and isinstance(item.get("start"), (int, float))
    }


def _boundaries(deep: Any, duration: float) -> list[float]:
    times = sorted(
        round(float(item["time"]), 3)
        for item in (deep.get("sections") or [] if isinstance(deep, dict) else [])
        if isinstance(item, dict)
        and isinstance(item.get("time"), (int, float))
        and 0 < item["time"] < duration
    )
    kept: list[float] = []
    for time in times:
        last = kept[-1] if kept else 0.0
        if time - last >= MIN_SECTION_SECONDS and duration - time >= MIN_SECTION_SECONDS:
            kept.append(time)
    return kept


def base_sections(root: Path, music: dict) -> tuple[list[dict], str]:
    """The sections under the owner's layer, and which measurement they came from.

    The checkerboard boundaries when the deep pass found at least two. The count-based
    sections otherwise, and also when the owner has already named those, because a
    name lives on its section's start and moving the starts would lose it.
    """
    measured = [item for item in music.get("sections") or [] if isinstance(item, dict)]
    duration = float(music.get("duration") or 0)
    times = _boundaries(read_optional(Path(root) / "work" / "music-deep.json"), duration)
    measured_starts = {round(float(item.get("start") or 0), 3) for item in measured}
    starts = [0.0, *times]
    if len(times) < MIN_BOUNDARIES or _note_starts(root) - set(starts) & measured_starts:
        return measured, "music.json"
    ends = [*times, duration]
    return [
        {
            "start": start,
            "end": end,
            "energy": _energy(music, start, end),
            "label": "section",
        }
        for start, end in zip(starts, ends, strict=True)
    ], "music-deep.json"


def _numbers(items: Any, key: str = "time") -> list[float]:
    values = []
    for item in items or []:
        value = item.get(key) if isinstance(item, dict) else item
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def bands(values: list[float]) -> list[str]:
    """Each value against the song's own range, never an absolute."""
    if not values:
        return []
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    words = []
    for value in values:
        share = (value - low) / span
        words.append("quiet" if share < QUIET else "full" if share >= FULL else "middle")
    return words


def _sparkline(music: dict) -> list[int]:
    points = [float(p.get("energy") or 0) for p in music.get("energy_curve") or [] if isinstance(p, dict)]  # fmt: skip
    if not points:
        return []
    top = max(points) or 1.0
    size = len(points) / SPARK_POINTS
    spark = []
    for index in range(min(SPARK_POINTS, len(points))):
        chunk = points[int(index * size) : max(int(index * size) + 1, int((index + 1) * size))]
        spark.append(min(9, int(sum(chunk) / len(chunk) / top * 10)))
    return spark


def _best_bar(deep: dict) -> dict | None:
    candidates = [c for c in deep.get("bar_length_candidates") or [] if isinstance(c, dict)]
    return max(candidates, key=lambda c: float(c.get("score") or 0), default=None)


def _inputs(root: Path) -> dict[str, str | None]:
    return {
        relative: file_hash(root / relative) if (root / relative).is_file() else None
        for relative in INPUTS
    }


def _build(root: Path, project) -> dict[str, Any]:
    from .domain import lyric_timing, section_map

    music = read_optional(root / "work" / "music.json")
    deep = read_optional(root / "work" / "music-deep.json")
    deep = deep if isinstance(deep, dict) else {}
    fps = project.fps
    last = round(project.duration * fps)
    frame = lambda seconds: timeline.frame_number(seconds, fps)  # noqa: E731

    tempo = deep.get("refined_tempo") if isinstance(deep.get("refined_tempo"), dict) else {}
    bpm = tempo.get("primary_bpm") or music.get("estimated_tempo_bpm")
    bar = _best_bar(deep)
    score = float(bar.get("score") or 0) if bar else 0.0
    beats_per_bar = int(bar["beats_per_bar"]) if bar and score > 0 else None
    downbeats = sorted({frame(t) for t in _numbers(deep.get("downbeats")) if frame(t) < last})
    beats = sorted({frame(t) for t in _numbers(music.get("beats")) if frame(t) < last})
    bar_frames = round(60 / float(bpm) * beats_per_bar * fps) if bpm and beats_per_bar else None
    words = [
        line
        for line in lyric_timing.view(root)["lines"]
        if line["start"] is not None and not line["tag"]
    ]

    applied = section_map.apply(root, music) or {}
    _, base_source = base_sections(root, music)
    source = "section-map.json" if section_map.read(root) is not None else base_source
    items = [item for item in applied.get("sections") or [] if isinstance(item, dict)]
    words_by_energy = bands([float(item.get("energy") or 0) for item in items])
    targets = pacing.density_plan(words_by_energy, beats_per_bar, float(bpm) if bpm else None)
    sections = []
    for index, item in enumerate(items):
        start, end = float(item["start"]), float(item["end"])
        first = next((line for line in words if start <= line["start"] < end), None)
        sections.append(
            {
                "name": item.get("name") or f"Section {index + 1}",
                "start": round(start, 3),
                "end": round(end, 3),
                "start_frame": frame(start),
                "end_frame": min(frame(end), last),
                "energy": round(float(item.get("energy") or 0), 3),
                "energy_word": words_by_energy[index],
                "target_per_10s": targets[index],
                "first_line": first["text"] if first else None,
                "first_line_frame": frame(first["start"]) if first else None,
                "source": source,
            }
        )

    reach = round(SNAP_SECONDS * fps)
    changes = []
    for item in music.get("candidate_changes") or []:
        if not isinstance(item, dict) or "time" not in item:
            continue
        at = frame(float(item["time"]))
        near = min(downbeats, key=lambda value: abs(value - at), default=None)
        snapped = near if near is not None and abs(near - at) <= reach else None
        changes.append(
            {"frame": at, "snapped_frame": snapped, "strength": item.get("spectral_change")}
        )

    key = deep.get("key") if isinstance(deep.get("key"), dict) else {}
    runner = key.get("runner_up") if isinstance(key.get("runner_up"), dict) else {}
    return {
        "available": True,
        "version": VERSION,
        "fps": fps,
        "total_frames": last,
        "deep": bool(deep),
        "tempo": {
            "bpm": bpm,
            "half_bpm": tempo.get("half_bpm"),
            "double_bpm": tempo.get("double_bpm"),
            "confidence": tempo.get("pulse_confidence"),
            "source": "music-deep.json" if tempo.get("primary_bpm") else "music.json",
        },
        "key": {
            "tonic": key.get("tonic"),
            "mode": key.get("mode"),
            "runner_up": (
                f"{runner.get('tonic')} {runner.get('mode')}" if runner.get("tonic") else None
            ),
            "source": "music-deep.json" if key.get("tonic") else None,
        },
        "beats_per_bar": beats_per_bar,
        "bar_score": round(score, 3),
        "grid_trusted": score >= GRID_SCORE and bool(downbeats),
        "bar_frames": bar_frames,
        "downbeats": downbeats,
        "beats": beats,
        "sections": sections,
        "sections_source": source,
        "changes": changes,
        "sparkline": _sparkline(music),
        "warnings": [*(music.get("warnings") or []), *(deep.get("warnings") or [])],
    }


def song_map(root: Path) -> dict[str, Any]:
    """The cached map, rebuilt only when one of its inputs changed."""
    from . import production as P

    root = Path(root)
    music = read_optional(root / "work" / "music.json")
    if not isinstance(music, dict):
        return {"available": False}
    project = P.load_project(root, verify_source=False)
    inputs = digest({"version": VERSION, "fps": project.fps, "files": _inputs(root)})
    cached = read_optional(root / FILE)
    if isinstance(cached, dict) and cached.get("inputs") == inputs:
        return cached
    value = {**_build(root, project), "inputs": inputs}
    write_json(root / FILE, value)
    return value
