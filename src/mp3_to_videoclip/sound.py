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


#: How often a repeated sound may recur, at the least, and how many placements a cue may name.
MIN_EVERY_SECONDS = 0.25
MAX_PLACES = 200
_ANCHOR_WORDS = "an anchor is {frame: n}, {shot: id}, {line: id} or {beat: id}"


def _anchor(value, project: Project, *, known: dict) -> dict:
    """Where a cue starts or ends: a frame, a shot's cut, or on a story film a line or a beat.

    ``{"frame": -1}`` is the film's end. A shot or a beat follows the cut and the takes, as
    a line does, so a sound placed on them moves with the film.
    """
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError(_ANCHOR_WORDS)
    if "frame" in value:
        frame = value["frame"]
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < -1:
            raise ValueError("an anchor frame is a whole number, or -1 for the end")
        if frame > project.total_frames:
            raise ValueError("an anchor frame is inside the film")
        return {"frame": frame}
    if "shot" in value:
        if value["shot"] not in known["shots"]:
            raise ValueError(f"the storyboard has no shot {value['shot']}")
        return {"shot": value["shot"]}
    if "line" in value:
        if project.spine != "soundtrack":
            raise ValueError("only a story film anchors a sound to a line")
        if value["line"] not in known["lines"]:
            raise ValueError(f"the script has no line {value['line']}")
        return {"line": value["line"]}
    if "beat" in value:
        if project.spine != "soundtrack":
            raise ValueError("only a story film anchors a sound to a beat")
        if value["beat"] not in known["beats"]:
            raise ValueError(f"the structure has no beat {value['beat']}")
        return {"beat": value["beat"]}
    raise ValueError(_ANCHOR_WORDS)


def _places(value, project: Project, *, known: dict) -> dict | None:
    """One sound in many places: every so many seconds, or at a list of anchors."""
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or len(value) == 0
        or not set(value) <= {"every", "jitter", "at"}
    ):
        raise ValueError("places are {every: seconds, jitter: seconds} or {at: [anchors]}")
    if "at" in value:
        if "every" in value or "jitter" in value:
            raise ValueError("places are either every so many seconds or at anchors, not both")
        anchors = value["at"]
        if not isinstance(anchors, list) or not 1 <= len(anchors) <= MAX_PLACES:
            raise ValueError(f"places name between 1 and {MAX_PLACES} anchors")
        return {"at": [_anchor(item, project, known=known) for item in anchors]}
    every = _number(value.get("every"), MIN_EVERY_SECONDS, max(project.duration, MIN_EVERY_SECONDS), "every")  # fmt: skip
    jitter = _number(value.get("jitter", 0.0), 0.0, every / 2, "jitter")
    return {"every": every, "jitter": jitter}


def _script_lines(root: Path, project: Project) -> set[str]:
    if project.spine != "soundtrack":
        return set()
    from .production.script import load_script

    script = load_script(root)
    return {line.id for line in script.lines} if script else set()


def sources(root: Path, project: Project) -> dict:
    """Everything an anchor can name, with where each thing is in seconds.

    The shots are the cut's, so a sound on a cut follows the Film stage's edit; the beats
    are the story film's, from the first word of their first line to the pause after their
    last. The line rows are the narration layout, as before.
    """
    from . import edits
    from .production import load_board

    rows = _layout(root, project)
    shots: dict[str, tuple[float, float]] = {}
    try:
        board = edits.effective_board(root, load_board(root))
    except (OSError, ValueError):
        board = None
    if board is not None:
        for shot in board.shots:
            start = shot.start_frame / project.fps
            shots[shot.id] = (start, (shot.start_frame + shot.duration_frames) / project.fps)
    beats: dict[str, tuple[float, float]] = {}
    for row in rows:
        beat = row.get("beat")
        if not beat:
            continue
        first, last = beats.get(beat, (row["start"], row["end"] + row["pause_after"]))
        beats[beat] = (min(first, row["start"]), max(last, row["end"] + row["pause_after"]))
    return {"rows": rows, "shots": shots, "beats": beats}


def _sound_models() -> list:
    from . import catalog

    return [m for m in catalog.load().models if {"music", "effects"} & set(m.capabilities)]


def _known(root: Path, project: Project) -> dict:
    found = sources(root, project)
    return {
        "lines": _script_lines(root, project),
        "shots": set(found["shots"]),
        "beats": set(found["beats"]),
    }


def _cue(root: Path, project: Project, value: dict, previous: dict | None, known: dict) -> dict:
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
    start = _anchor(value.get("start", {"frame": 0}), project, known=known)
    end = _anchor(value.get("end", {"frame": -1}), project, known=known)
    places = _places(value.get("places"), project, known=known)
    model = value.get("model")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a cue's model is a catalogue id, or left out for Settings' choice")
        model = model.strip()
        wanted = "music" if kind == "music" else "effects"
        if model not in {m.id for m in _sound_models() if wanted in m.capabilities}:
            raise ValueError(f"the catalogue lists no {wanted} model {model}")
    cue = {
        "id": cue_id,
        "kind": kind,
        "prompt": prompt.strip(),
        "start": start,
        "end": end,
        "gain_db": _number(value.get("gain_db", GAIN_DB[kind]), -60, 12, "gain"),
        "duck_db": _number(value.get("duck_db", DUCK_DB[kind]), -40, 0, "duck"),
        "loop": bool(value.get("loop", kind != "effect")),
        "places": places,
        # The model this cue is made with; absent, Settings' choice for its kind.
        "model": model,
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
    known = _known(root, project)
    before = {cue["id"]: cue for cue in read(root)["cues"]}
    rows = [_cue(root, project, item, before.get(item.get("id")), known) for item in cues]
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


def soundtrack_suffixes() -> set[str]:
    from .production import soundtrack

    return soundtrack.AUDIO_SUFFIXES


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


def _sources(found) -> dict:
    """The line rows alone, as older callers pass them, or everything an anchor can name."""
    if isinstance(found, dict):
        return found
    return {"rows": found, "shots": {}, "beats": {}}


def anchor_seconds(project: Project, anchor: dict, found, *, end: bool = False) -> float:
    """Where an anchor is in the film now: a frame, a shot's cut, a line's take or a beat."""
    found = _sources(found)
    if "frame" in anchor:
        frame = anchor["frame"]
        return project.duration if frame == -1 else frame / project.fps
    if "shot" in anchor:
        span = found["shots"].get(anchor["shot"])
        if span is None:
            raise ValueError(f"shot {anchor['shot']} has left the cut")
        return span[1] if end else span[0]
    if "beat" in anchor:
        span = found["beats"].get(anchor["beat"])
        if span is None:
            raise ValueError(f"beat {anchor['beat']} has no lines yet")
        return span[1] if end else span[0]
    row = next((row for row in found["rows"] if row["id"] == anchor["line"]), None)
    if row is None:
        raise ValueError(f"line {anchor['line']} has left the script")
    return row["end"] + row["pause_after"] if end else row["start"]


def span_seconds(project: Project, cue: dict, found) -> tuple[float, float]:
    """Where a cue plays, in seconds of the film. Every anchor follows what it names."""
    return (
        anchor_seconds(project, cue["start"], found),
        anchor_seconds(project, cue["end"], found, end=True),
    )


def _jitter(cue_id: str, index: int, jitter: float) -> float:
    """A fixed offset per placement, so the same cue list mixes the same bytes every time."""
    if jitter <= 0:
        return 0.0
    share = int(digest([cue_id, index])[:8], 16) / 0xFFFFFFFF
    return (share * 2 - 1) * jitter


def place_times(project: Project, cue: dict, found, start: float, end: float) -> list[float] | None:
    """Where one sound is placed between a cue's start and end; ``None`` for a plain cue."""
    places = cue.get("places")
    if not places:
        return None
    if "at" in places:
        times = []
        for anchor in places["at"]:
            try:
                at = anchor_seconds(project, anchor, found)
            except ValueError:
                continue
            if start <= at < end:
                times.append(round(at, 4))
        return sorted(times)
    every, jitter = places["every"], places.get("jitter", 0.0)
    times = []
    index = 0
    while start + index * every < end and index < MAX_PLACES * 10:
        at = start + index * every + _jitter(cue["id"], index, jitter)
        if start <= at < end:
            times.append(round(at, 4))
        index += 1
    return times


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


def placed(root: Path, project: Project) -> list[tuple[dict, dict, float, float, list[float] | None]]:  # fmt: skip
    """Every cue with a selected sound and a span still in the film, with its placements."""
    found = sources(root, project)
    result = []
    for cue in read(root)["cues"]:
        chosen = _chosen(cue)
        if chosen is None:
            continue
        try:
            start, end = span_seconds(project, cue, found)
        except ValueError:
            continue
        end = min(end, project.duration)
        if end <= start:
            # A cue at one moment, its end on its start, plays its sound whole from there.
            end = min(project.duration, start + float(chosen.get("seconds") or 0))
        if end <= start:
            continue
        times = place_times(project, cue, found, start, end)
        if times is not None and not times:
            continue
        result.append((cue, chosen, start, end, times))
    return result


# ------------------------------------------------------------------ the layer


def key(base: Path, rows: list, spans) -> str:
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
                    "times": times,
                }
                for cue, chosen, start, end, times in rows
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
    for cue, chosen, start, end, times in rows:
        path = inside(root, chosen["path"])
        if file_hash(path) != chosen["sha256"]:
            raise ValueError(f"the sound {chosen['path']} changed on disk; recover it")
        last = min(total, round(end * rate))
        decoded = voice._decode(path, music.CHANNELS)
        gain = 10 ** (float(cue["gain_db"]) / 20)
        # One sound in many places plays whole at each, cut only by the cue's end.
        starts = [start] if times is None else times
        for at in starts:
            first = min(total, round(at * rate))
            if last <= first:
                continue
            sound = decoded
            if times is None and cue["loop"] and sound.shape[0] < last - first:
                sound = np.tile(sound, (int(np.ceil((last - first) / max(1, sound.shape[0]))), 1))
            sound = sound[: last - first] * gain
            _fades(sound, FADE_SECONDS[cue["kind"]])
            duck = 1 - depth[first : first + sound.shape[0]] * (1 - 10 ** (float(cue["duck_db"]) / 20))  # fmt: skip
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
            "placements": {cue["id"]: len(times) for cue, _c, _s, _e, times in rows if times},
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
            [
                cue["id"],
                chosen["sha256"],
                start,
                end,
                cue["gain_db"],
                cue["duck_db"],
                cue["loop"],
                times,
            ]  # fmt: skip
            for cue, chosen, start, end, times in rows
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
    found = sources(root, project)
    notes = []
    for cue in spec["cues"]:
        chosen = _chosen(cue)
        if chosen is None:
            notes.append({"code": "cue_silent", "cue": cue["id"], "message": f"{cue['id']} has no sound yet."})  # fmt: skip
        try:
            start, end = span_seconds(project, cue, found)
        except ValueError as exc:
            notes.append({"code": "cue_unplaced", "cue": cue["id"], "message": f"{cue['id']}: {exc}."})  # fmt: skip
            continue
        if end < start:
            notes.append({"code": "cue_empty", "cue": cue["id"], "message": f"{cue['id']} ends before it starts."})  # fmt: skip
        elif end == start and chosen is None:
            notes.append({"code": "cue_moment", "cue": cue["id"], "message": f"{cue['id']} is a moment; its sound will play whole from there once it has one."})  # fmt: skip
        elif end > project.duration + 1e-6:
            notes.append({"code": "cue_past_end", "cue": cue["id"], "message": f"{cue['id']} runs {end - project.duration:.1f} s past the end; it is cut there."})  # fmt: skip
        times = place_times(project, cue, found, start, min(end, project.duration))
        if times is not None and not times:
            notes.append({"code": "cue_no_places", "cue": cue["id"], "message": f"{cue['id']} is placed nowhere between its start and its end."})  # fmt: skip
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


# ------------------------------------------------------------------ paid cues

from decimal import Decimal  # noqa: E402
from uuid import uuid4  # noqa: E402

POLL_SECONDS = 5.0
#: A slow music task stays journaled and is collected later; it is never bought again.
POLL_LIMIT_SECONDS = 600.0
MIN_RESERVE = Decimal("0.01")
#: How long a sound placed at anchors is bought for, when its places set no gap.
PLACED_HIT_SECONDS = 1.5
#: A price per run is by compute time, which is not known before the run.
RUN_PRICE_MARGIN = 2


def model_for(kind: str, settings=None) -> str:
    from .config import load_settings

    settings = settings or load_settings()
    return settings.sounds.music_model if kind == "music" else settings.sounds.effects_model


def _reserve(model: str, seconds: float | None, fallback: float) -> Decimal:
    from . import catalog
    from .generation import money

    row = next((m for m in catalog.load().models if m.id == model), None)
    price = row.price if row else None
    if price is None:
        return max(MIN_RESERVE, money(str(fallback)))
    amount = money(price.amount)
    if price.unit == "second" and seconds:
        return max(MIN_RESERVE, amount * Decimal(str(round(seconds, 1))))
    if price.unit == "run":
        return max(MIN_RESERVE, amount * RUN_PRICE_MARGIN)
    return max(MIN_RESERVE, amount)


def _clamped_duration(rule: dict, wanted: float) -> float | int:
    """Whole seconds inside the model's range: a float step like 0.1 fails its own check."""
    low, high = float(rule.get("minimum", wanted)), float(rule.get("maximum", wanted))
    value = min(max(wanted, low), high)
    if rule.get("type") == "integer":
        return int(min(max(round(value), low), high))
    whole = float(round(value))
    return whole if low <= whole <= high else value


def build_request(cue: dict, span: float, schema: dict, task_uuid: str) -> dict:
    """The one request shape the three model pages share, fitted to this model's own schema."""
    from .generation import validate_request

    info = schema["info"]
    item = schema["components"]["schemas"]["RequestBody"]["items"]
    props = item.get("properties", {})
    if props.get("taskType", {}).get("const") not in (None, "audioInference"):
        raise ValueError(f"{info.get('x-air-id', 'this model')} is not a sound model")
    if "speech" in item.get("required", []):
        raise ValueError("this model speaks; choose a music or effects model")
    formats = props.get("outputFormat", {}).get("enum") or ["WAV"]
    request = {
        "taskType": "audioInference",
        "taskUUID": task_uuid,
        "model": info["x-air-id"],
        "positivePrompt": cue["prompt"],
        "outputType": "URL",
        "outputFormat": "WAV" if "WAV" in formats else formats[0],
        "deliveryMethod": "async",
        "numberResults": 1,
        "includeCost": True,
    }
    if "duration" in props:
        request["duration"] = _clamped_duration(props["duration"], span)
    settings = (props.get("settings") or {}).get("properties") or {}
    if cue["kind"] == "music" and "instrumental" in settings:
        request["settings"] = {"instrumental": True}
    validate_request(schema, request)
    return request


def quote_cues(root: Path, cue_ids: list[str] | None = None, *, model: str | None = None, client=None) -> dict:  # fmt: skip
    """Quote one sound per cue, from the model's public schema. Spends nothing."""
    from .config import load_settings
    from .generation import money, save_quote
    from .production import load_project
    from .providers import RunwareClient

    root = Path(root)
    project = load_project(root, verify_source=False)
    spec = read(root)
    chosen = [cue for cue in spec["cues"] if cue_ids is None or cue["id"] in cue_ids]
    if cue_ids is not None and len(chosen) != len(set(cue_ids)):
        raise ValueError("choose cues from this film")
    if not chosen:
        raise ValueError("add a cue first")
    for cue in chosen:
        if not cue["prompt"]:
            raise ValueError(f"{cue['id']} needs a prompt before it can be made")
    kinds = {cue["kind"] for cue in chosen}
    if model is None and len({"music" if k == "music" else "effects" for k in kinds}) > 1:
        raise ValueError("quote music and effects separately; they use different models")
    settings = load_settings()
    if model is None:
        # A cue that named its model is made with it; cues of different models go separately.
        named = {cue["model"] for cue in chosen if cue.get("model")}
        if len(named) > 1 or (named and any(not cue.get("model") for cue in chosen)):
            raise ValueError("quote cues of different models separately")
        model = named.pop() if named else model_for(chosen[0]["kind"], settings)
    if not model:
        raise ValueError("choose a sound model in Settings first")
    own = client is None
    client = client or RunwareClient("public-schema-only")
    try:
        schema = client.schema(model)  # public GET only; no generation
    finally:
        if own:
            client.close()
    info = schema["info"]
    if info.get("x-status") != "live":
        raise ValueError("model is not confirmed live")
    schema_path = f"work/schemas/{digest(schema)}.json"
    write_json(inside(root, schema_path), schema)
    found = sources(root, project)
    journal = read_optional(root / "work/tasks.json") or {}
    tasks = []
    for cue in chosen:
        if any(t.get("cue_id") == cue["id"] and t["status"] in ("submitted", "result") for t in journal.values()):  # fmt: skip
            raise ValueError(f"{cue['id']} has an unresolved task; recover it first")
        start, end = span_seconds(project, cue, found)
        span = max(0.5, min(end, project.duration) - start)
        if cue.get("places"):
            # One sound placed many times is bought once, as long as its gap or a short hit.
            span = max(0.5, min(span, cue["places"].get("every") or PLACED_HIT_SECONDS))
        task_uuid = str(uuid4())
        request = build_request(cue, span, schema, task_uuid)
        seconds = request.get("duration")
        tasks.append(
            {
                "uuid": task_uuid,
                "cue_id": cue["id"],
                "kind_of_cue": cue["kind"],
                "prompt": cue["prompt"],
                "version": next_version(root, cue["id"]),
                "input_hash": digest({"model": model, "prompt": cue["prompt"], "seconds": seconds}),
                "request": request,
                "seconds": seconds,
                "model": model,
                "reserve_usd": str(_reserve(model, seconds, settings.sounds.reserve_usd_per_cue)),
            }
        )
    return save_quote(
        root,
        {
            "kind": "sound",
            "model": model,
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "reserve_total_usd": str(sum((money(t["reserve_usd"]) for t in tasks), Decimal(0))),
            "published_pricing": info.get("x-pricing"),
            "warning": "The reserve is a limit on admission, not an exact price.",
        },
    )


def check_before_spend(root: Path, task: dict) -> None:
    """Called while the reservation is written: the cue must still ask for what was quoted."""
    cue = _entry(read(root), task["cue_id"])
    if cue["prompt"] != task["prompt"]:
        raise ValueError("a cue changed since the quote; estimate and authorize again")


def finish_cue(root: Path, task_uuid: str, result: dict, client) -> bool:
    """Record what the provider billed, then fetch, measure and index the file."""
    import shutil

    from .ffmpeg import audio_seconds
    from .generation import money, update_task
    from .production.project import now
    from .storage import state_lock

    if "audioURL" not in result:
        return False
    if result.get("taskUUID") != task_uuid:
        raise ValueError("provider returned another task")
    cost = str(money(result["cost"]))
    with state_lock(root):
        journal = read_optional(root / "work/tasks.json") or {}
        task = dict(journal[task_uuid])
        if task.get("status") == "resolved":
            raise ValueError("task was manually reconciled; inspect the result before recovery")
        if task.get("cost_usd") is not None and money(task["cost_usd"]) != money(cost):
            raise ValueError("provider task cost changed; reconcile manually")
        task.update(status="result", result=result, cost_usd=cost, cost_basis="provider reported")
        journal[task_uuid] = task
        write_json(root / "work/tasks.json", journal)  # Billed cost BEFORE download.
    suffix = ".wav" if task["request"].get("outputFormat", "WAV") == "WAV" else ".mp3"
    relative = f"work/sound/{task['cue_id']}/v{task['version']:03d}-{task_uuid}{suffix}"
    path = inside(root, relative)
    expected = task.get("sha256")
    if path.exists() and expected and file_hash(path) != expected:
        quarantine = root / f"work/quarantine/{task_uuid}-{file_hash(path)}{suffix}"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        if not quarantine.exists():
            shutil.copyfile(path, quarantine)
        path.unlink()
    if not path.exists():
        client.download_audio(result["audioURL"], path)
    sha = file_hash(path)
    if expected and sha != expected:
        raise ValueError("recovered sound differs from its recorded original; inspect manually")
    version = {
        "version": task["version"],
        "path": relative,
        "sha256": sha,
        "source": "generated",
        "model": task["model"],
        "input_hash": task["input_hash"],
        "task_id": task_uuid,
        "seconds": round(audio_seconds(path), 3),
        "cost_usd": cost,
        "at": now(),
    }
    record_version(root, task["cue_id"], version)
    update_task(root, task_uuid, status="ready", path=relative, sha256=sha, completed_at=now())
    return True


def generate_cues(root: Path, quote_id: str, client=None, *, sleep=None) -> dict:
    """Run an authorized quote, one cue at a time. Never retries a paid call."""
    import time

    from .generation import _check_stop_conditions, authorization, begin_task, budget, read_quote
    from .providers import RunwareClient, runware_api_key

    sleep = sleep or time.sleep
    root = Path(root)
    quote = read_quote(root, quote_id)
    if quote["kind"] != "sound":
        raise ValueError("this quote is not for sound")
    auth = authorization(root, quote)
    schema = read_optional(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    budget.require_reconciled(root)
    journal = read_optional(root / "work/tasks.json") or {}
    own = client is None
    client = client or RunwareClient(runware_api_key())
    done, pending, stopped = [], [], None
    try:
        for task in quote["tasks"]:
            if task["uuid"] in journal:
                raise ValueError(f"task {task['uuid']} needs recover; no paid resubmission")
            try:
                _check_stop_conditions(root, quote, auth)
                begin_task(root, quote, task)
            except ValueError as exc:
                stopped = str(exc)
                break
            result = client.submit_speech(task["request"])
            waited = 0.0
            while "audioURL" not in result and waited < POLL_LIMIT_SECONDS:
                sleep(POLL_SECONDS)
                waited += POLL_SECONDS
                result = client.recover_speech(task["uuid"]) or result
            if finish_cue(root, task["uuid"], result, client):
                done.append(task["cue_id"])
            else:
                # Later cues would only be refused: a task still out holds the film's spending.
                pending.append(task["cue_id"])
                break
    finally:
        if own:
            client.close()
    return {"quote_id": quote_id, "done": done, "pending": pending, "stopped": stopped}


def recover_cue(root: Path, task_uuid: str, client=None) -> bool:
    """Collect a paid sound that was interrupted; this never submits anything new."""
    from .providers import RunwareClient, runware_api_key

    root = Path(root)
    task = (read_optional(root / "work/tasks.json") or {}).get(task_uuid)
    if not task or task.get("kind") != "sound":
        raise ValueError("unknown sound task")
    if task["status"] == "resolved":
        raise ValueError("task was manually reconciled; use a newly authorized quote if needed")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        result = task.get("result") or client.recover_speech(task_uuid)
        return finish_cue(root, task_uuid, result, client) if result else False
    finally:
        if own:
            client.close()
