"""A film's sound layer: cues over the music or the soundtrack, under the speech.

A cue is a music bed, an ambience under a place or an effect on a moment. Each one has a
prompt, a span and a list of immutable versions, bought through the journal or brought as the
owner's own file; the selected version plays. Cues sit in no approval hash and never move a
clock: they are a layer that :func:`with_cues` lays over whatever the film sounds like, keyed
by the base's bytes and every selected cue, so a film without cues keeps its file byte for
byte. What proves the owner heard them is the watched-with-sound gate on the final.
"""

from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np

from . import audio as music
from .models import Project
from .storage import (
    digest,
    file_hash,
    inside,
    read_optional,
    state_mutation,
    write_json,
)

FILE = "work/sound.json"
VERSION = 1
#: Default gain under the film, per kind.
GAIN_DB = {"music": -14.0, "ambience": -24.0, "effect": -6.0}
#: How far each kind drops under speech by default.
DUCK_DB = {"music": -10.0, "ambience": -10.0, "effect": 0.0}
#: Beds and ambience fade at their edges; an effect is its own shape.
FADE_SECONDS = {"music": 1.0, "ambience": 1.0, "effect": 0.0}
PEAK = 0.98
#: A viewer notices silence past this.
SILENCE_SECONDS = 8.0
SILENCE_DBFS = -50.0
#: Speech sits at this level in both mixers (``voice.SPEECH_LEVEL_DB``).
SPEECH_LEVEL_DB = -14.0
MARGIN_DB = 6.0
MAX_PROMPT = 600
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


# ------------------------------------------------------------------ the spec


def read(root: Path) -> dict:
    value = read_optional(Path(root) / FILE)
    if not isinstance(value, dict) or not isinstance(value.get("cues"), list):
        return {"version": VERSION, "cues": []}
    return value


def _number(value, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return float(value)


def _anchor(value, project: Project, *, lines: set[str]) -> dict:
    """``{"frame": n}`` on any film, ``{"line": id}`` on a story film; -1 is the end."""
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError("an anchor is {frame: n} or {line: id}")
    if "frame" in value:
        frame = value["frame"]
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < -1:
            raise ValueError("an anchor frame is a whole number, or -1 for the end")
        if frame > project.total_frames:
            raise ValueError("an anchor frame is inside the film")
        return {"frame": frame}
    if "line" in value:
        if project.spine != "soundtrack":
            raise ValueError("only a story film anchors a sound to a line")
        if value["line"] not in lines:
            raise ValueError(f"the script has no line {value['line']}")
        return {"line": value["line"]}
    raise ValueError("an anchor is {frame: n} or {line: id}")


def _script_lines(root: Path, project: Project) -> set[str]:
    if project.spine != "soundtrack":
        return set()
    from .production.script import load_script

    script = load_script(root)
    return {line.id for line in script.lines} if script else set()


def _cue(root: Path, project: Project, value: dict, previous: dict | None, lines: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError("a cue is an object")
    cue_id = value.get("id")
    if not isinstance(cue_id, str) or not _ID.match(cue_id):
        raise ValueError("a cue needs a short lowercase id")
    kind = value.get("kind", "ambience")
    if kind not in GAIN_DB:
        raise ValueError(f"a cue is one of {', '.join(GAIN_DB)}")
    prompt = value.get("prompt", "")
    if not isinstance(prompt, str) or len(prompt) > MAX_PROMPT:
        raise ValueError(f"a cue's prompt is text of at most {MAX_PROMPT} characters")
    start = _anchor(value.get("start", {"frame": 0}), project, lines=lines)
    end = _anchor(value.get("end", {"frame": -1}), project, lines=lines)
    cue = {
        "id": cue_id,
        "kind": kind,
        "prompt": prompt.strip(),
        "start": start,
        "end": end,
        "gain_db": _number(value.get("gain_db", GAIN_DB[kind]), -60, 12, "gain"),
        "duck_db": _number(value.get("duck_db", DUCK_DB[kind]), -40, 0, "duck"),
        "loop": bool(value.get("loop", kind != "effect")),
        # Versions are immutable evidence: a cue list can never rewrite them.
        "versions": list((previous or {}).get("versions", [])),
        "selected": (previous or {}).get("selected"),
    }
    why = value.get("why")
    if isinstance(why, str) and why.strip():
        cue["why"] = why.strip()[:240]
    return cue


@state_mutation
def set_cues(root: Path, cues: list) -> dict:
    """Replace the cue list. A cue that stays keeps its versions; one that leaves keeps its files."""
    from .production import load_project

    if not isinstance(cues, list):
        raise ValueError("cues is a list")
    project = load_project(root, verify_source=False)
    lines = _script_lines(root, project)
    known = {cue["id"]: cue for cue in read(root)["cues"]}
    rows = [_cue(root, project, item, known.get(item.get("id")), lines) for item in cues]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("name each cue once")
    spec = {"version": VERSION, "cues": rows}
    write_json(root / FILE, spec)
    return spec


def _entry(spec: dict, cue_id: str) -> dict:
    cue = next((item for item in spec["cues"] if item["id"] == cue_id), None)
    if cue is None:
        raise ValueError(f"this film has no cue {cue_id}")
    return cue


def _chosen(cue: dict) -> dict | None:
    return next((v for v in cue.get("versions", []) if v["version"] == cue.get("selected")), None)


def next_version(root: Path, cue_id: str) -> int:
    used = [v["version"] for v in _entry(read(root), cue_id).get("versions", [])]
    journal = read_optional(Path(root) / "work/tasks.json")
    if isinstance(journal, dict):
        used += [t["version"] for t in journal.values() if t.get("kind") == "sound" and t.get("cue_id") == cue_id]  # fmt: skip
    return max(used + [0]) + 1


@state_mutation
def record_version(root: Path, cue_id: str, version: dict) -> dict:
    """A cue's first sound goes straight into the mix; a later one waits to be kept."""
    spec = read(root)
    cue = _entry(spec, cue_id)
    if any(v["version"] == version["version"] for v in cue["versions"]):
        return cue
    cue["versions"].append(version)
    if cue["selected"] is None:
        cue["selected"] = version["version"]
    write_json(root / FILE, spec)
    return cue


def import_sound(root: Path, cue_id: str, source: Path) -> dict:
    """The owner's own file as a version of this cue; nothing is charged."""
    from .ffmpeg import audio_seconds
    from .production import soundtrack
    from .production.project import now

    _entry(read(root), cue_id)
    relative = soundtrack.add_sound(root, Path(source))
    path = inside(root, relative)
    version = {
        "version": next_version(root, cue_id),
        "path": relative,
        "sha256": file_hash(path),
        "source": "upload",
        "seconds": round(audio_seconds(path), 3),
        "at": now(),
    }
    return record_version(root, cue_id, version)


@state_mutation
def select(root: Path, cue_id: str, version: int | None) -> dict:
    spec = read(root)
    cue = _entry(spec, cue_id)
    if version is not None and not any(v["version"] == version for v in cue["versions"]):
        raise ValueError(f"cue {cue_id} has no version {version}")
    cue["selected"] = version
    write_json(root / FILE, spec)
    return cue


# ------------------------------------------------------------------ spans


def _layout(root: Path, project: Project) -> list[dict]:
    if project.spine != "soundtrack":
        return []
    from . import narration_timing

    return narration_timing.layout(root)


def span_seconds(project: Project, cue: dict, rows: list[dict]) -> tuple[float, float]:
    """Where a cue plays, in seconds of the film. A line anchor follows its take."""
    places = {row["id"]: row for row in rows}

    def at(anchor: dict, *, end: bool) -> float:
        if "frame" in anchor:
            frame = anchor["frame"]
            return project.duration if frame == -1 else frame / project.fps
        row = places.get(anchor["line"])
        if row is None:
            raise ValueError(f"line {anchor['line']} has left the script")
        return row["end"] + row["pause_after"] if end else row["start"]

    return at(cue["start"], end=False), at(cue["end"], end=True)


def speech_spans(root: Path, project: Project) -> list[tuple[int, int]]:
    """Where someone speaks, in samples: a story film's takes or a song film's placed lines."""
    rate = music.SAMPLE_RATE
    if project.spine == "soundtrack":
        from . import narration

        takes = narration.selected_takes(root)
        return [
            (round(row["start"] * rate), round(row["end"] * rate))
            for row in _layout(root, project)
            if row["id"] in takes
        ]
    from . import voice

    spans = []
    for line, take in voice._placed(root, project, strict=False):
        first = round(line.start_frame * rate / project.fps)
        spans.append((first, first + round(float(take["seconds"]) * rate)))
    return spans


def placed(root: Path, project: Project) -> list[tuple[dict, dict, float, float]]:
    """Every cue with a selected sound and a span that is still in the film."""
    rows = _layout(root, project)
    result = []
    for cue in read(root)["cues"]:
        chosen = _chosen(cue)
        if chosen is None:
            continue
        try:
            start, end = span_seconds(project, cue, rows)
        except ValueError:
            continue
        end = min(end, project.duration)
        if end <= start:
            continue
        result.append((cue, chosen, start, end))
    return result


# ------------------------------------------------------------------ the layer


def key(base: Path, rows: list[tuple[dict, dict, float, float]], spans) -> str:
    return digest(
        {
            "version": VERSION,
            "base": file_hash(base),
            "spans": spans,
            "cues": [
                {
                    "id": cue["id"],
                    "sha256": chosen["sha256"],
                    "start": start,
                    "end": end,
                    "gain_db": cue["gain_db"],
                    "duck_db": cue["duck_db"],
                    "loop": cue["loop"],
                    "fade": FADE_SECONDS[cue["kind"]],
                }
                for cue, chosen, start, end in rows
            ],
        }
    )[:20]


def _fades(samples: np.ndarray, seconds: float) -> None:
    count = min(len(samples) // 2, round(seconds * music.SAMPLE_RATE))
    if count > 0:
        samples[:count] *= np.linspace(0, 1, count)[:, None]
        samples[len(samples) - count :] *= np.linspace(1, 0, count)[:, None]


def _write(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(music.CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(music.SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def with_cues(root: Path, project: Project, base: Path, spans: list[tuple[int, int]]) -> Path:
    """The base with every selected cue under the speech, or the base itself when none."""
    from . import voice

    rows = placed(root, project)
    if not rows:
        return base
    value = key(base, rows, spans)
    target = root / "work" / "audio" / f"sound-{value}.wav"
    if target.is_file():
        return target
    out = voice._decode(base, music.CHANNELS)
    total = out.shape[0]
    rate = music.SAMPLE_RATE
    # 0 where nobody speaks, 1 in the middle of a line, with the speech mixer's own ramps.
    depth = (1 - voice._duck(total, spans)) / (1 - 10 ** (voice.DUCK_DB / 20))
    layer = np.zeros_like(out)
    for cue, chosen, start, end in rows:
        path = inside(root, chosen["path"])
        if file_hash(path) != chosen["sha256"]:
            raise ValueError(f"the sound {chosen['path']} changed on disk; recover it")
        first = min(total, round(start * rate))
        last = min(total, round(end * rate))
        if last <= first:
            continue
        sound = voice._decode(path, music.CHANNELS)
        if cue["loop"] and sound.shape[0] < last - first:
            sound = np.tile(sound, (int(np.ceil((last - first) / max(1, sound.shape[0]))), 1))
        sound = sound[: last - first] * 10 ** (float(cue["gain_db"]) / 20)
        _fades(sound, FADE_SECONDS[cue["kind"]])
        duck = 1 - depth[first : first + sound.shape[0]] * (1 - 10 ** (float(cue["duck_db"]) / 20))
        layer[first : first + sound.shape[0]] += sound * duck[:, None]
    mixed = out + layer
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > PEAK:
        # The film's own sound is never rescaled for a cue: the layer gives way instead.
        room = PEAK - float(np.max(np.abs(out)))
        scale = max(room, 0.0) / max(float(np.max(np.abs(layer))), 1e-9)
        layer *= min(1.0, scale)
        mixed = out + layer
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".partial.wav")
    temp.unlink(missing_ok=True)
    _write(temp, mixed)
    write_json(
        target.with_suffix(".json"),
        {
            "key": value,
            "base": base.name,
            "cues": [cue["id"] for cue, *_ in rows],
            "peak": round(float(np.max(np.abs(mixed))), 4) if mixed.size else 0.0,
            "layer_scaled": peak > PEAK,
        },
    )
    temp.replace(target)
    return target


def layer_version(root: Path, project: Project) -> str | None:
    """Names the cue layer a Player should load, or ``None`` when no cue plays."""
    rows = placed(root, project)
    if not rows:
        return None
    return digest(
        [
            [cue["id"], chosen["sha256"], start, end, cue["gain_db"], cue["duck_db"], cue["loop"]]
            for cue, chosen, start, end in rows
        ]
    )[:12]


# ------------------------------------------------------------------ suggestions


def suggest(root: Path) -> list[dict]:
    """A cue list with no model: a bed and an ambience per beat on a story film, else nothing."""
    from .production import load_brief, load_project
    from .production.script import load_script, read_beats

    project = load_project(root, verify_source=False)
    if project.spine != "soundtrack":
        return []
    brief = load_brief(root)
    intent = brief.intent
    tone = ", ".join(intent.tone) if intent and intent.tone else ""
    creative = brief.creative
    place = creative.place.description if creative and creative.place else ""
    cues = [
        {
            "id": "bed",
            "kind": "music",
            "prompt": " ".join(
                part
                for part in (
                    "Instrumental score for a narrated short film,",
                    f"{tone}," if tone else "",
                    "sparse, no drums, room for a voice.",
                )
                if part
            ),
            "start": {"frame": 0},
            "end": {"frame": -1},
            "why": "A bed under the whole narration, so the silence between lines has a floor.",
        }
    ]
    script = load_script(root)
    beats = read_beats(root)
    if script is None or not beats:
        return cues
    by_beat: dict[str, list[str]] = {}
    for line in script.lines:
        by_beat.setdefault(line.beat, []).append(line.id)
    for beat in beats.get("beats", []):
        ids = by_beat.get(beat["id"])
        if not ids:
            continue
        where = f" of {place}" if place else ""
        cues.append(
            {
                "id": f"room-{beat['id']}",
                "kind": "ambience",
                "prompt": f"Room tone and ambience{where} during the {beat['label'].lower()}, steady, no music, no voices.",  # fmt: skip
                "start": {"line": ids[0]},
                "end": {"line": ids[-1]},
                "why": f"The {beat['label'].lower()} is one place; its air should not change mid-beat.",
            }
        )
    return cues


# ------------------------------------------------------------------ the ear


def _silences(path: Path) -> list[tuple[float, float]]:
    from . import voice

    samples = voice._decode(path, 1)[:, 0]
    rate = music.SAMPLE_RATE
    seconds = samples.shape[0] // rate
    if seconds == 0:
        return []
    chunks = samples[: seconds * rate].reshape(seconds, rate)
    rms = np.sqrt(np.mean(np.square(chunks), axis=1))
    quiet = 20 * np.log10(np.maximum(rms, 1e-9)) < SILENCE_DBFS
    runs, start = [], None
    for index, flag in enumerate([*quiet, False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            if index - start >= SILENCE_SECONDS:
                runs.append((float(start), float(index)))
            start = None
    return runs


def report(root: Path, project: Project | None = None) -> dict:
    """What the Critic can read of the sound: cue problems and the mix measured."""
    from .production import load_project

    project = project or load_project(root, verify_source=False)
    spec = read(root)
    rows = _layout(root, project)
    notes = []
    for cue in spec["cues"]:
        chosen = _chosen(cue)
        if chosen is None:
            notes.append({"code": "cue_silent", "cue": cue["id"], "message": f"{cue['id']} has no sound yet."})  # fmt: skip
        try:
            start, end = span_seconds(project, cue, rows)
        except ValueError as exc:
            notes.append({"code": "cue_unplaced", "cue": cue["id"], "message": f"{cue['id']}: {exc}."})  # fmt: skip
            continue
        if end <= start:
            notes.append({"code": "cue_empty", "cue": cue["id"], "message": f"{cue['id']} ends before it starts."})  # fmt: skip
        elif end > project.duration + 1e-6:
            notes.append({"code": "cue_past_end", "cue": cue["id"], "message": f"{cue['id']} runs {end - project.duration:.1f} s past the end; it is cut there."})  # fmt: skip
        if cue["gain_db"] + cue["duck_db"] > SPEECH_LEVEL_DB - MARGIN_DB:
            notes.append({"code": "cue_under_speech", "cue": cue["id"], "message": f"{cue['id']} sits within {MARGIN_DB:g} dB of the voice while someone speaks; lower it or duck it more."})  # fmt: skip
    measured = None
    try:
        from .production import film_audio

        mixed = film_audio(root, project)
    except (OSError, ValueError, RuntimeError):
        mixed = None
    if mixed is not None:
        for start, end in _silences(mixed):
            notes.append({"code": "silence", "at": start, "message": f"Silence from {start:.0f} s to {end:.0f} s, {end - start:.0f} s with nothing to hear."})  # fmt: skip
        stats = music.loudness_stats(mixed)
        if stats is not None:
            measured = {"lufs": round(float(stats["input_i"]), 1), "true_peak_db": round(float(stats.get("input_tp", 0.0)), 1)}  # fmt: skip
    return {
        "cues": len(spec["cues"]),
        "sounding": len([cue for cue in spec["cues"] if _chosen(cue) is not None]),
        "mixed": mixed is not None,
        "loudness": measured,
        "notes": notes,
    }


def summary_lines(root: Path, project: Project) -> list[str]:
    """The sound as a few lines of a Director snapshot."""
    value = report(root, project)
    if not value["cues"] and not value["notes"]:
        return ["- No cues. The film's sound is its music or its narration alone."]
    lines = [f"- Cues: {value['cues']}, with a sound: {value['sounding']}."]
    if value["loudness"]:
        lines.append(f"- Mix loudness: {value['loudness']['lufs']} LUFS.")
    for note in value["notes"][:8]:
        lines.append(f"- {note['code']}: {note['message']}")
    return lines
