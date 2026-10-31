"""Voiceover: spoken lines, their immutable takes and the film's mix.

A line's words and timing live in the cut (``EditDecisionList.voice``). Its takes
live under ``assets/voice/<line>/`` and are indexed in ``work/voice.json``; a new
take is a new version, generated through the money journal or supplied by the
owner. The film's sound is a derived WAV in ``work/audio/``, so the source MP3 is
never changed and a changed line re-mixes the audio without touching a picture.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np

from . import audio as music
from . import edits, production
from .generation import (
    asset_intact,
    authorization,
    begin_task,
    money,
    read_quote,
    save_quote,
    update_task,
    validate_request,
)
from .models import EditVoice, Project
from .production import now
from .providers import ProviderError, RunwareClient, runware_api_key
from .render import audio_seconds
from .storage import digest, file_hash, inside, read_json, state_lock, state_mutation, write_json

VOICE_PATH = "work/voice.json"
DEFAULT_MODEL = "minimax-speech-2-8"
DEFAULT_VOICE = "English_Deep-VoicedGentleman"
#: HD rate published by the provider, doubled so a reservation covers a price rise.
RESERVE_PER_CHARACTER = Decimal("0.0002")
MIN_RESERVE = Decimal("0.01")
#: Bumping this re-mixes every film, so it must change whenever the mix does.
MIX_VERSION = 2
SPEECH_LEVEL_DB = -14.0
DUCK_DB = -10.0
DUCK_ATTACK_SECONDS = 0.2
DUCK_RELEASE_SECONDS = 0.35
PEAK_LIMIT = 0.98
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff"}


def read_index(root: Path) -> dict:
    path = root / VOICE_PATH
    return read_json(path) if path.is_file() else {"voice": DEFAULT_VOICE, "lines": {}}


def lines(root: Path) -> list[EditVoice]:
    edit = edits.load_edit(root)
    return list(edit.voice) if edit is not None else []


def _input_hash(text: str, voice: str, model: str) -> str:
    return digest({"text": text, "voice": voice, "model": model})


def _selected(root: Path, index: dict, line_id: str) -> dict | None:
    entry = index["lines"].get(line_id)
    if not entry or entry.get("selected") is None:
        return None
    return next(
        (take for take in entry["versions"] if take["version"] == entry["selected"]),
        None,
    )


def is_current(line: EditVoice, take: dict | None) -> bool:
    """A take only speaks for a line while the words it was made from still match."""
    return take is not None and take.get("text") == line.text


@state_mutation
def _record_take(root: Path, line_id: str, take: dict) -> None:
    index = read_index(root)
    entry = index["lines"].setdefault(line_id, {"selected": None, "versions": []})
    if any(existing["version"] == take["version"] for existing in entry["versions"]):
        return
    entry["versions"].append(take)
    entry["selected"] = take["version"]
    write_json(root / VOICE_PATH, index)


@state_mutation
def select_take(root: Path, line_id: str, version: int) -> None:
    index = read_index(root)
    entry = index["lines"].get(line_id)
    if not entry or not any(take["version"] == version for take in entry["versions"]):
        raise ValueError(f"line {line_id} has no take {version}")
    entry["selected"] = version
    write_json(root / VOICE_PATH, index)


def _next_version(root: Path, line_id: str) -> int:
    used = [
        take["version"] for take in read_index(root)["lines"].get(line_id, {}).get("versions", [])
    ]
    journal = read_json(root / "work/tasks.json")
    used += [t["version"] for t in journal.values() if t.get("line_id") == line_id]
    return max(used + [0]) + 1


def import_take(root: Path, line_id: str, source: Path) -> dict:
    """Use the owner's own recording as a new take of a line; nothing is charged."""
    line = next((item for item in lines(root) if item.id == line_id), None)
    if line is None:
        raise ValueError(f"the cut has no voice line {line_id}")
    source = Path(source)
    if source.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError("a voice take must be an audio file")
    seconds = audio_seconds(source)
    version = _next_version(root, line_id)
    relative = f"assets/voice/{line_id}/v{version:03d}-upload{source.suffix.lower()}"
    path = inside(root, relative)
    if path.exists():
        raise ValueError("that take already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, path)
    take = {
        "version": version,
        "path": relative,
        "sha256": file_hash(path),
        "text": line.text,
        "source": "upload",
        "seconds": round(seconds, 3),
        "at": now(),
    }
    _record_take(root, line_id, take)
    return take


# ------------------------------------------------------------------ paid takes


def quote_voice(
    root: Path,
    line_ids: list[str] | None = None,
    *,
    model: str = DEFAULT_MODEL,
    regenerate: bool = False,
    client=None,
) -> dict:
    """Quote speech for lines that have no take of their current words."""
    index = read_index(root)
    voice = index.get("voice") or DEFAULT_VOICE
    all_lines = lines(root)
    if not all_lines:
        raise ValueError("this cut has no voice lines yet")
    known = {line.id for line in all_lines}
    if line_ids is not None and not set(line_ids) <= known:
        raise ValueError("unknown voice line")
    chosen = [line for line in all_lines if line_ids is None or line.id in line_ids]
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
    journal = read_json(root / "work/tasks.json")
    tasks = []
    for line in chosen:
        input_hash = _input_hash(line.text, voice, model)
        takes = index["lines"].get(line.id, {}).get("versions", [])
        if not regenerate and any(take.get("input_hash") == input_hash for take in takes):
            continue
        if any(
            t.get("line_id") == line.id and t["status"] in ("submitted", "result")
            for t in journal.values()
        ):
            raise ValueError(f"line {line.id} has an unresolved task; recover it first")
        task_uuid = str(uuid4())
        request = {
            "taskType": "audioInference",
            "taskUUID": task_uuid,
            "model": info["x-air-id"],
            "speech": {"text": line.text, "voice": voice},
            "settings": {"turbo": False},
            "outputType": "URL",
            "outputFormat": "WAV",
            "deliveryMethod": "sync",
            "numberResults": 1,
            "includeCost": True,
        }
        validate_request(schema, request)
        reserve = max(MIN_RESERVE, RESERVE_PER_CHARACTER * len(line.text))
        tasks.append(
            {
                "uuid": task_uuid,
                "line_id": line.id,
                "text": line.text,
                "version": _next_version(root, line.id),
                "input_hash": input_hash,
                "request": request,
                "reserve_usd": str(reserve),
            }
        )
    if not tasks:
        raise ValueError("every line already has a take of these words; choose regenerate")
    return save_quote(
        root,
        {
            "kind": "voice",
            "model": model,
            "voice": voice,
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "reserve_total_usd": str(sum((money(t["reserve_usd"]) for t in tasks), Decimal(0))),
            "published_pricing": info.get("x-pricing"),
            "warning": "The reserve is a limit on admission, not an exact price.",
        },
    )


def finish_voice(root: Path, task_uuid: str, result: dict, client) -> bool:
    if "audioURL" not in result:
        return False
    if result.get("taskUUID") != task_uuid:
        raise ValueError("provider returned another task")
    cost = str(money(result["cost"]))
    with state_lock(root):
        journal = read_json(root / "work/tasks.json")
        task = dict(journal[task_uuid])
        if task.get("status") == "resolved":
            raise ValueError("task was manually reconciled; inspect the result before recovery")
        if task.get("cost_usd") is not None and money(task["cost_usd"]) != money(cost):
            raise ValueError("provider task cost changed; reconcile manually")
        task.update(status="result", result=result, cost_usd=cost, cost_basis="provider reported")
        journal[task_uuid] = task
        write_json(root / "work/tasks.json", journal)  # Billed cost BEFORE download.
    relative = f"assets/voice/{task['line_id']}/v{task['version']:03d}-{task_uuid}.wav"
    path = inside(root, relative)
    if not path.exists():
        client.download_audio(result["audioURL"], path)
    elif task.get("sha256") and file_hash(path) != task["sha256"]:
        raise ValueError("recovered take differs from its recorded original; inspect manually")
    seconds = audio_seconds(path)
    sha = file_hash(path)
    take = {
        "version": task["version"],
        "path": relative,
        "sha256": sha,
        "text": task["text"],
        "input_hash": task["input_hash"],
        "source": "generated",
        "task_id": task_uuid,
        "seconds": round(seconds, 3),
        "at": now(),
    }
    _record_take(root, task["line_id"], take)
    update_task(root, task_uuid, status="ready", path=relative, sha256=sha, completed_at=now())
    return True


def generate_voice(root: Path, quote_id: str, client=None) -> dict:
    """Run an authorized speech quote, one line at a time. Never retries a paid call."""
    quote = read_quote(root, quote_id)
    if quote["kind"] != "voice":
        raise ValueError("this quote is not for voiceover")
    authorization(root, quote)
    schema = read_json(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    current = {line.id: line.text for line in lines(root)}
    for task in quote["tasks"]:
        if current.get(task["line_id"]) != task["text"]:
            raise ValueError("a line changed since the quote; estimate and authorize again")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    done, pending = [], []
    try:
        for task in quote["tasks"]:
            begin_task(root, quote, task)
            result = client.submit_speech(task["request"])
            if finish_voice(root, task["uuid"], result, client):
                done.append(task["line_id"])
            else:
                pending.append(task["line_id"])
    finally:
        if own:
            client.close()
    return {"quote_id": quote_id, "done": done, "pending": pending}


def recover_voice(root: Path, task_uuid: str, client=None) -> bool:
    """Collect a paid take that was interrupted; this never submits anything new."""
    task = read_json(root / "work/tasks.json").get(task_uuid)
    if not task or task.get("kind") != "voice":
        raise ValueError("unknown voice task")
    if task["status"] == "resolved":
        raise ValueError("task was manually reconciled; use a newly authorized quote if needed")
    if task["status"] == "ready" and asset_intact(root, task):
        return True
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        result = task.get("result") or client.recover_speech(task_uuid)
        return finish_voice(root, task_uuid, result, client) if result else False
    except ProviderError:
        raise
    finally:
        if own:
            client.close()


# ------------------------------------------------------------------ the mix


def _decode(path: Path, channels: int) -> np.ndarray:
    completed = subprocess.run(
        [
            music._ffmpeg(),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(music.SAMPLE_RATE),
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
    )
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError(f"ffmpeg could not read {path.name}: " + music._tail(completed.stderr))
    return np.frombuffer(completed.stdout, dtype=np.float32).reshape(-1, channels).copy()


def _level(speech: np.ndarray, gain_db: float) -> np.ndarray:
    """Bring speech to one level, measured only where someone is speaking."""
    peak = float(np.max(np.abs(speech))) if speech.size else 0.0
    if peak <= 1e-6:
        raise ValueError("a voice take is silent")
    active = speech[np.abs(speech) > peak * 0.05]
    rms = float(np.sqrt(np.mean(np.square(active))))
    return speech * (10 ** ((SPEECH_LEVEL_DB + gain_db) / 20) / rms)


def _duck(length: int, spans: list[tuple[int, int]]) -> np.ndarray:
    """Music gain per sample: lowered through each line, with short ramps either side."""
    rate = music.SAMPLE_RATE
    attack = int(DUCK_ATTACK_SECONDS * rate)
    release = int(DUCK_RELEASE_SECONDS * rate)
    depth = np.zeros(length, dtype=np.float32)
    indices = np.arange(length, dtype=np.float32)
    for start, end in spans:
        rise = np.clip((indices - (start - attack)) / attack, 0, 1)
        fall = np.clip(((end + release) - indices) / release, 0, 1)
        depth = np.maximum(depth, np.minimum(rise, fall))
    return 1.0 - depth * (1.0 - 10 ** (DUCK_DB / 20))


def mix(base: Path, placed: list[tuple[int, Path, float]], target: Path) -> Path:
    """Write the film's sound: ``placed`` holds (first sample, take, gain dB) per line."""
    backing = _decode(base, music.CHANNELS)
    length = backing.shape[0]
    takes = []
    for first, path, gain in placed:
        speech = _level(_decode(path, 1)[:, 0], gain)
        if first + speech.size > length:
            raise ValueError(f"the voice take {path.name} runs past the end of the film")
        takes.append((first, speech))
    ducked = backing * _duck(length, [(f, f + s.size) for f, s in takes])[:, None]
    out = ducked.copy()
    for first, speech in takes:
        end = first + speech.size
        # Speech gives way rather than clipping, and the music is never rescaled for it.
        room = PEAK_LIMIT - float(np.max(np.abs(ducked[first:end])))
        scale = min(1.0, max(room, 0.0) / float(np.max(np.abs(speech))))
        out[first:end] += (speech * scale)[:, None]
    pcm = (np.clip(out, -1.0, 1.0) * 32767.0).astype("<i2")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".partial.wav")
    temp.unlink(missing_ok=True)
    with wave.open(str(temp), "wb") as handle:
        handle.setnchannels(music.CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(music.SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    os.replace(temp, target)
    return target


def _placed(root: Path, project: Project, *, strict: bool) -> list[tuple[EditVoice, dict]]:
    index = read_index(root)
    result = []
    for line in lines(root):
        take = _selected(root, index, line.id)
        if not is_current(line, take):
            if strict:
                raise ValueError(f"voice line {line.id} has no take of its current words")
            continue
        result.append((line, take))
    return result


def mix_key(project: Project, placed: list[tuple[EditVoice, dict]]) -> str:
    return digest(
        {
            "version": MIX_VERSION,
            "source_sha256": project.source_sha256,
            "window": project.audio_window.model_dump() if project.audio_window else None,
            "fps": project.fps,
            "lines": [
                {"start_frame": line.start_frame, "gain_db": line.gain_db, "sha256": take["sha256"]}
                for line, take in placed
            ],
        }
    )[:20]


def audio_version(root: Path, project: Project) -> str | None:
    """Identifies the mix a Player should load, or ``None`` when there is only music."""
    placed = _placed(root, project, strict=False)
    return mix_key(project, placed) if placed else None


def film_audio(root: Path, project: Project, *, strict: bool = False) -> Path:
    """The music alone with no takes; otherwise the mix, built once per set of takes.

    A final passes ``strict`` so a line without a take stops the render instead of
    silently delivering a film with a sentence missing.
    """
    base = production.render_audio(root, project)
    placed = _placed(root, project, strict=strict)
    if not placed:
        return base
    target = root / "work" / "audio" / f"mix-{mix_key(project, placed)}.wav"
    if target.is_file():
        return target
    for _line, take in placed:
        path = inside(root, take["path"])
        if not path.is_file() or file_hash(path) != take["sha256"]:
            raise ValueError(f"voice take {take['path']} is missing or has changed")
    return mix(
        base,
        [
            (
                round(line.start_frame * music.SAMPLE_RATE / project.fps),
                inside(root, take["path"]),
                line.gain_db,
            )
            for line, take in placed
        ],
        target,
    )
