"""A story film's sound: the kept takes, their pauses and an optional bed, as one WAV.

That file is the film's clock. Its key covers every input, so a changed take makes a new file and
never a rewritten one. ``set_duration`` is the only writer of a soundtrack film's length.
"""

import wave
from pathlib import Path

import numpy as np

from .. import audio as sound
from ..models import Project, Script
from ..storage import digest, file_hash, inside, read_optional, state_mutation, write_json
from .project import STAGE_FILES, load_project

SOUNDTRACK_VERSION = 1
TARGET_LUFS = -16.0
PEAK = 0.98
DEFAULT_BED = {"gain_db": -14.0, "duck_db": -10.0}
AMBIENCE_GAIN_DB = -24.0
AMBIENCE_FADE_SECONDS = 1.0
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff"}


def read_spec(root: Path) -> dict:
    value = read_optional(root / STAGE_FILES["voice"])
    return value if isinstance(value, dict) else {}


def order(script: Script, spec: dict) -> list[str]:
    """The spec's order for the lines still in the script, then any new ones in script order."""
    known = {line.id for line in script.lines}
    kept = [line_id for line_id in spec.get("order", []) if line_id in known]
    return kept + [line.id for line in script.lines if line.id not in set(kept)]


def ensure_spec(root: Path, script: Script) -> dict:
    """The mix spec follows the script's lines; anything set by hand stays."""
    project = load_project(root)
    spec = {
        "fade_in": 0.0,
        "fade_out": 0.0,
        "target_lufs": TARGET_LUFS,
        "pauses": {},
        **({"bed": {"path": project.bed, **DEFAULT_BED}} if project.bed else {}),
        **read_spec(root),
    }
    spec["order"] = order(script, spec)
    write_json(root / STAGE_FILES["voice"], spec)
    return spec


def _inputs(root: Path) -> dict:
    from .. import narration, narration_timing

    spec = read_spec(root)
    takes = narration.selected_takes(root)
    rows = narration_timing.layout(root)
    bed = spec.get("bed")
    return {
        "version": SOUNDTRACK_VERSION,
        "rate": sound.SAMPLE_RATE,
        "channels": sound.CHANNELS,
        "fade_in": spec.get("fade_in", 0.0),
        "fade_out": spec.get("fade_out", 0.0),
        "target_lufs": spec.get("target_lufs", TARGET_LUFS),
        "bed": {**bed, "sha256": file_hash(inside(root, bed["path"]))} if bed else None,
        "lines": [
            {
                "id": row["id"],
                "seconds": round(row["end"] - row["start"], 3),
                "pause": row["pause_after"],
                "take": takes[row["id"]]["sha256"] if row["id"] in takes else None,
            }
            for row in rows
        ],
        # Named only when there is some, so every key made before ambience existed holds.
        **(
            {
                "ambience": [
                    {**item, "sha256": file_hash(inside(root, item["path"]))}
                    for item in spec["ambience"]
                ]
            }
            if spec.get("ambience")
            else {}
        ),
    }


def key(root: Path) -> str:
    return digest(_inputs(root))[:20]


def path_for(root: Path, value: str) -> Path:
    return root / "work" / "audio" / f"soundtrack-{value}.wav"


def built(root: Path) -> Path | None:
    if not (root / STAGE_FILES["script"]).is_file():
        return None
    path = path_for(root, key(root))
    return path if path.is_file() else None


def current(root: Path) -> Path:
    path = built(root)
    if path is None:
        raise ValueError("build the soundtrack first")
    return path


def receipt(root: Path) -> dict | None:
    path = built(root)
    value = read_optional(path.with_suffix(".json")) if path else None
    return value if isinstance(value, dict) else None


@state_mutation
def set_duration(root: Path, seconds: float) -> Project:
    """The only place a soundtrack film's length changes."""
    project = load_project(root, verify_source=False)
    if project.spine != "soundtrack":
        raise ValueError("only a soundtrack film's length follows its takes")
    updated = project.model_copy(update={"duration": seconds, "source_duration": seconds})
    if updated != project:
        write_json(root / "project.json", updated.model_dump())
    return updated


def _measure(path: Path) -> dict | None:
    """Integrated loudness, true peak and range, or ``None`` for silence, which has none."""
    values = sound.loudness_stats(path)
    if values is None:
        return None
    return {
        "lufs": float(values["input_i"]),
        "true_peak_db": float(values.get("input_tp", "-inf")),
        "range_lu": float(values.get("input_lra", 0.0)),
    }


def _loudness(path: Path) -> float | None:
    measured = _measure(path)
    return measured["lufs"] if measured else None


def _write(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(sound.CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(sound.SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def _fades(samples: np.ndarray, fade_in: float, fade_out: float) -> None:
    rate = sound.SAMPLE_RATE
    if fade_in > 0:
        count = min(len(samples), round(fade_in * rate))
        samples[:count] *= np.linspace(0, 1, count)[:, None]
    if fade_out > 0:
        count = min(len(samples), round(fade_out * rate))
        samples[len(samples) - count :] *= np.linspace(1, 0, count)[:, None]


def _mix(root: Path, rows: list[dict], takes: dict, spec: dict) -> np.ndarray:
    from .. import voice

    rate = sound.SAMPLE_RATE
    from ..narration_timing import duration

    total = round(duration(rows) * rate)
    speech = np.zeros(total, dtype=np.float32)
    spans = []
    for row in rows:
        take = takes.get(row["id"])
        if take is None:
            continue
        path = inside(root, take["path"])
        if file_hash(path) != take["sha256"]:
            raise ValueError(f"the take {take['path']} changed on disk; recover it")
        said = voice._level(voice._decode(path, 1)[:, 0], 0.0)
        first = round(row["start"] * rate)
        end = min(total, first + said.size)
        speech[first:end] = said[: end - first]
        spans.append((first, end))
    out = np.stack([speech, speech], axis=1)
    bed = spec.get("bed")
    depth = (1 - voice._duck(total, spans)) / (1 - 10 ** (voice.DUCK_DB / 20))

    def looped(relative: str, count: int) -> np.ndarray:
        music = voice._decode(inside(root, relative), sound.CHANNELS)
        repeats = int(np.ceil(count / max(1, music.shape[0])))
        return np.tile(music, (repeats, 1))[:count]

    if bed:
        music = looped(bed["path"], total) * 10 ** (float(bed["gain_db"]) / 20)
        duck = float(bed.get("duck_db", DEFAULT_BED["duck_db"]))
        out = out + music * (1 - depth * (1 - 10 ** (duck / 20)))[:, None]
    places = {row["id"]: row for row in rows}
    for item in spec.get("ambience", []):
        if item["from_line"] not in places or item["to_line"] not in places:
            # A line this sound was tied to has left the script: it stops playing, and says so.
            continue
        first = round(places[item["from_line"]]["start"] * rate)
        last = places[item["to_line"]]
        end = min(total, round((last["end"] + last["pause_after"]) * rate))
        if end <= first:
            continue
        span = looped(item["path"], end - first) * 10 ** (float(item["gain_db"]) / 20)
        _fades(span, AMBIENCE_FADE_SECONDS, AMBIENCE_FADE_SECONDS)
        duck = float(item.get("duck_db", DEFAULT_BED["duck_db"]))
        out[first:end] += span * (1 - depth[first:end] * (1 - 10 ** (duck / 20)))[:, None]
    _fades(out, float(spec.get("fade_in", 0.0)), float(spec.get("fade_out", 0.0)))
    return out


def build(root: Path) -> dict:
    """Make the current soundtrack if it does not exist, and bring the film into line with it."""
    from .. import narration, narration_timing
    from .script import load_script

    script = load_script(root)
    if script is None:
        raise ValueError("write the script first")
    spec = read_spec(root)
    takes = narration.selected_takes(root)
    rows = narration_timing.layout(root)
    seconds = narration_timing.duration(rows)
    value = key(root)
    target = path_for(root, value)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".partial.wav")
        temp.unlink(missing_ok=True)
        samples = _mix(root, rows, takes, spec)
        _write(temp, samples)
        measured = _loudness(temp)
        goal = float(spec.get("target_lufs", TARGET_LUFS))
        gain = 0.0
        if measured is not None:
            # One gain over the whole mix, so every line stays exactly where the layout says.
            peak = float(np.max(np.abs(samples)))
            gain = min(goal - measured, 20 * float(np.log10(PEAK / peak)))
            _write(temp, samples * 10 ** (gain / 20))
        final = _measure(temp) if measured is not None else None
        write_json(
            target.with_suffix(".json"),
            {
                "key": value,
                "seconds": seconds,
                "lines_with_takes": len([row for row in rows if row["id"] in takes]),
                "lines": len(rows),
                "input_lufs": measured,
                "output_lufs": final["lufs"] if final else None,
                "output_true_peak_db": final["true_peak_db"] if final else None,
                "output_range_lu": final["range_lu"] if final else None,
                "target_lufs": goal,
                "gain_db": round(gain, 2),
            },
        )
        temp.replace(target)
    set_duration(root, seconds)
    timing = narration_timing.refresh(root)
    from ..analysis import analyze_narration
    from .script import read_beats

    write_json(root / STAGE_FILES["analysis"], analyze_narration(target, seconds, timing["lines"], read_beats(root)))  # fmt: skip
    from .board import retime_lines

    moved = retime_lines(root)
    from ..edits import refresh_captions

    refresh_captions(root)
    return {"key": value, "seconds": seconds, "path": str(target.relative_to(root)), "moved": moved}


def _number(value, low: float, high: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return float(value)


def _audio_path(root: Path, relative) -> str:
    if not isinstance(relative, str) or not inside(root, relative).is_file():
        raise ValueError("that sound is not in this film; add it first")
    return relative


def add_sound(root: Path, source: Path) -> str:
    """Copy a bed or ambience into the film under its own hash. Never replaces a file."""
    suffix = source.suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        raise ValueError(f"a sound must be one of {', '.join(sorted(AUDIO_SUFFIXES))}")
    from .. import voice

    voice._decode(source, sound.CHANNELS)
    relative = f"media/sound-{file_hash(source)[:16]}{suffix}"
    target = inside(root, relative)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(suffix + ".partial")
        temporary.write_bytes(source.read_bytes())
        temporary.replace(target)
    return relative


@state_mutation
def set_mix(root: Path, patch: dict) -> dict:
    """Change the bed, the ambience or the fades. The next build makes a new file."""
    from .script import require_script

    if not isinstance(patch, dict):
        raise ValueError("the mix must be an object")
    script = require_script(root)
    spec = ensure_spec(root, script)
    known = {line.id for line in script.lines}
    for name in ("fade_in", "fade_out"):
        if name in patch:
            spec[name] = _number(patch[name], 0, 30, name)
    if "bed" in patch:
        bed = patch["bed"]
        if bed is None:
            spec.pop("bed", None)
        else:
            spec["bed"] = {
                "path": _audio_path(root, bed.get("path")),
                "gain_db": _number(bed.get("gain_db", DEFAULT_BED["gain_db"]), -60, 0, "bed gain"),
                "duck_db": _number(bed.get("duck_db", DEFAULT_BED["duck_db"]), -40, 0, "bed duck"),
            }
    if "ambience" in patch:
        items = []
        for item in patch["ambience"] or []:
            if item.get("from_line") not in known or item.get("to_line") not in known:
                raise ValueError("ambience runs from one line of this script to another")
            items.append(
                {
                    "path": _audio_path(root, item.get("path")),
                    "from_line": item["from_line"],
                    "to_line": item["to_line"],
                    "gain_db": _number(item.get("gain_db", AMBIENCE_GAIN_DB), -60, 0, "gain"),
                    "duck_db": _number(item.get("duck_db", DEFAULT_BED["duck_db"]), -40, 0, "duck"),
                }
            )
        if items:
            spec["ambience"] = items
        else:
            spec.pop("ambience", None)
    write_json(root / STAGE_FILES["voice"], spec)
    return spec


def stale_takes(root: Path) -> list[str]:
    """Lines whose selected take was made from other words: audible, and not approvable."""
    from .. import narration

    return narration.stale_lines(root)


def require_complete(root: Path) -> None:
    from .. import narration
    from .script import require_script

    script = require_script(root)
    stale = stale_takes(root)
    if stale:
        raise ValueError(f"re-record or un-keep the stale take of {', '.join(stale)}")
    takes = narration.selected_takes(root)
    missing = [line.id for line in script.lines if line.id not in takes]
    if missing:
        raise ValueError(f"these lines have no kept take yet: {', '.join(missing)}")
    if built(root) is None:
        raise ValueError("build the soundtrack first")


def voice_content(root: Path) -> dict:
    """What the voice approval binds: the spec, each line's kept take, and the mix they make."""
    from .. import narration

    takes = narration.selected_takes(root)
    return {
        "spec": read_spec(root),
        "takes": {
            line_id: {
                "version": take["version"],
                "sha256": file_hash(inside(root, take["path"])),
                "input_hash": take.get("input_hash"),
            }
            for line_id, take in sorted(takes.items())
        },
        "key": key(root),
    }
