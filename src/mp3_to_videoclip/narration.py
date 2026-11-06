"""A story film's takes: a journaled purchase, or the owner's own recording.

One line, many takes, each immutable under ``work/narration/<line>/``. ``work/narration.json``
indexes them. The journal is the same one stills use: the reservation is written before the
request, nothing is resubmitted, and an interrupted take is recovered by its id.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from . import voices
from .ffmpeg import audio_seconds
from .generation import (
    _check_stop_conditions,
    authorization,
    begin_task,
    budget,
    money,
    read_quote,
    save_quote,
    update_task,
    validate_request,
)
from .production.approvals import require_approval
from .production.project import now
from .production.script import load_script, require_script
from .providers import ElevenLabsClient, RunwareClient, elevenlabs_api_key, runware_api_key
from .storage import (
    digest,
    file_hash,
    inside,
    read_json,
    read_optional,
    state_lock,
    state_mutation,
    write_json,
)

FILE = "work/narration.json"
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff"}
#: HD rate published by the provider, doubled so a reservation covers a price rise.
RESERVE_PER_CHARACTER = Decimal("0.0002")
MIN_RESERVE = Decimal("0.01")


def read_index(root: Path) -> dict:
    path = root / FILE
    return read_json(path) if path.is_file() else {"voice": None, "lines": {}}


def _narrator(root: Path):
    from .models import Brief

    value = read_optional(root / "brief.json")
    creative = Brief.model_validate(value).creative if isinstance(value, dict) else None
    return creative.narrator if creative else None


def current_voice(root: Path) -> str:
    """The voice chosen here, else the profile's narrator's, else the default in Settings."""
    narrator = _narrator(root)
    chosen = narrator.voice_id if narrator else None
    return read_index(root).get("voice") or chosen or voices.default_voice()


@state_mutation
def lock_voice(root: Path, voice_id: str) -> str:
    """The voice for the next takes. Takes already made keep the voice they were made with."""
    if not isinstance(voice_id, str) or not voice_id.strip():
        raise ValueError("choose a voice")
    index = read_index(root)
    index["voice"] = voice_id.strip()
    write_json(root / FILE, index)
    return index["voice"]


def input_hash(text: str, voice_id: str, model: str) -> str:
    return digest({"text": text, "voice": voice_id, "model": model})


def _selected(entry: dict) -> dict | None:
    return next(
        (take for take in entry.get("versions", []) if take["version"] == entry.get("selected")),
        None,
    )


def selected_takes(root: Path) -> dict[str, dict]:
    """The take of each line that is in the mix."""
    lines = read_index(root)["lines"]
    return {line_id: take for line_id, entry in lines.items() if (take := _selected(entry))}


def stale_lines(root: Path) -> list[str]:
    """Lines whose kept take says other words than the script does now."""
    script = load_script(root)
    if script is None:
        return []
    takes = selected_takes(root)
    return [line.id for line in script.lines if line.id in takes and takes[line.id].get("text") != line.text]  # fmt: skip


@state_mutation
def _record(root: Path, line_id: str, take: dict) -> None:
    """A line's first take goes straight into the mix; a later one waits to be kept."""
    index = read_index(root)
    entry = index["lines"].setdefault(line_id, {"selected": None, "kept": [], "versions": []})
    if any(existing["version"] == take["version"] for existing in entry["versions"]):
        return
    entry["versions"].append(take)
    if entry["selected"] is None:
        entry["selected"] = take["version"]
        entry["kept"].append(take["version"])
    write_json(root / FILE, index)


def _next_version(root: Path, line_id: str) -> int:
    used = [t["version"] for t in read_index(root)["lines"].get(line_id, {}).get("versions", [])]
    journal = read_json(root / "work/tasks.json")
    used += [t["version"] for t in journal.values() if t.get("line_id") == line_id]
    return max(used + [0]) + 1


def _line(root: Path, line_id: str):
    line = next((item for item in require_script(root).lines if item.id == line_id), None)
    if line is None:
        raise ValueError(f"the script has no line {line_id}")
    return line


def import_take(root: Path, line_id: str, source: Path, *, follow: bool = True) -> dict:
    """The owner's own recording as a new take; nothing is charged."""
    line = _line(root, line_id)
    source = Path(source)
    if source.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError("a take must be an audio file")
    seconds = audio_seconds(source)
    version = _next_version(root, line_id)
    relative = f"work/narration/{line_id}/v{version:03d}-upload{source.suffix.lower()}"
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
    _record(root, line_id, take)
    if follow:
        _follow(root)
    return take


def _follow(root: Path) -> None:
    """Bring the soundtrack, the timing and the shots into line with what is kept."""
    from .production import soundtrack

    soundtrack.build(root)
    _record_rate(root)


@state_mutation
def _record_rate(root: Path) -> None:
    """What the kept takes actually measured replaces the constant, visibly, in the script."""
    from . import narration_timing

    rate = narration_timing.measured_rate(root)
    index = read_index(root)
    if rate is not None and index.get("measured_rate") != rate:
        index["measured_rate"] = rate
        write_json(root / FILE, index)


def keep(root: Path, line_id: str, version: int) -> dict:
    """Keep this take and put it in the mix; the shots after it move with it."""
    with state_lock(root):
        index = read_index(root)
        entry = index["lines"].get(line_id)
        if not entry or not any(t["version"] == version for t in entry["versions"]):
            raise ValueError(f"line {line_id} has no take {version}")
        entry["selected"] = version
        if version not in entry["kept"]:
            entry["kept"].append(version)
        write_json(root / FILE, index)
    _follow(root)
    return read_index(root)["lines"][line_id]


def unkeep(root: Path, line_id: str) -> dict:
    """Take a line out of the mix. Its takes stay on disk; it says an estimate of silence."""
    with state_lock(root):
        index = read_index(root)
        entry = index["lines"].get(line_id)
        if not entry:
            raise ValueError(f"line {line_id} has no takes")
        entry["selected"] = None
        write_json(root / FILE, index)
    _follow(root)
    return read_index(root)["lines"][line_id]


# ------------------------------------------------------------------ paid takes


def quote_lines(
    root: Path,
    line_ids: list[str] | None = None,
    *,
    voice_id: str | None = None,
    model: str | None = None,
    regenerate: bool = False,
    client=None,
) -> dict:
    """Quote a take of each line with none of its current words. Spends nothing.

    A MiniMax voice is quoted on Runware's public schema; an ElevenLabs voice on the
    account's period and the catalogue's price, since that provider states no price
    per call. Either document is kept under ``work/schemas`` and hashed into the quote.
    """
    require_approval(root, "script")
    narrator = _narrator(root)
    if narrator is not None and narrator.real_person and not narrator.permission_confirmed:
        raise ValueError(
            "the narrator is a real person and permission is not confirmed. Only the owner can "
            "confirm it on Story's Characters card."
        )
    script = require_script(root)
    known = {line.id for line in script.lines}
    if line_ids is not None and (not line_ids or not set(line_ids) <= known):
        raise ValueError("choose lines from this script")
    chosen = [line for line in script.lines if line_ids is None or line.id in line_ids]
    voice_id = voice_id or current_voice(root)
    voice = voices.get(voice_id)
    if voice.provider not in ("runware", "elevenlabs"):
        raise ValueError(f"{voice.provider} voices can't be bought yet; choose another voice")
    model = model or _default_model(voice.provider)
    own = client is None
    client = client or (ElevenLabsClient(elevenlabs_api_key()) if voice.provider == "elevenlabs" else RunwareClient("public-schema-only"))  # fmt: skip
    try:
        if voice.provider == "elevenlabs":
            schema, rate = _elevenlabs_terms(client, model)  # free GET; no generation
            info: dict = {"x-air-id": model}
        else:
            schema = client.schema(model)  # public GET only; no generation
            info = schema["info"]
            if info.get("x-status") != "live":
                raise ValueError("model is not confirmed live")
            props = schema["components"]["schemas"]["RequestBody"]["items"]["properties"]
            offered = ((props.get("speech") or {}).get("properties") or {}).get("voice", {}).get("enum")  # fmt: skip
            if offered and voice_id not in offered:
                raise ValueError(f"{model} does not offer the voice {voice_id}; choose another one")
            rate = RESERVE_PER_CHARACTER
    finally:
        if own:
            client.close()
    schema_path = f"work/schemas/{digest(schema)}.json"
    write_json(inside(root, schema_path), schema)
    journal = read_json(root / "work/tasks.json")
    index = read_index(root)
    tasks = []
    for line in chosen:
        wanted = input_hash(line.text, voice_id, model)
        takes = index["lines"].get(line.id, {}).get("versions", [])
        if not regenerate and any(take.get("input_hash") == wanted for take in takes):
            continue
        if any(t.get("line_id") == line.id and t["status"] in ("submitted", "result") for t in journal.values()):  # fmt: skip
            raise ValueError(f"line {line.id} has an unresolved task; recover it first")
        task_uuid = str(uuid4())
        request = voice.build_request(line.text, task_uuid, info["x-air-id"])
        if voice.provider == "runware":
            validate_request(schema, request)
        tasks.append(
            {
                "uuid": task_uuid,
                "line_id": line.id,
                "text": line.text,
                "voice": voice_id,
                "provider": voice.provider,
                "version": _next_version(root, line.id),
                "input_hash": wanted,
                "request": request,
                "reserve_usd": str(max(MIN_RESERVE, rate * len(line.text))),
            }
        )
    if not tasks:
        raise ValueError("every line already has a take of these words; choose redo")
    characters = sum(len(task["text"]) for task in tasks)
    warning = "The reserve is a limit on admission, not an exact price."
    if voice.provider == "elevenlabs":
        warning = _elevenlabs_capacity(schema["subscription"], characters)
    return save_quote(
        root,
        {
            "kind": "narration",
            "provider": voice.provider,
            "model": model,
            "voice": voice_id,
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "characters": characters,
            "reserve_total_usd": str(sum((money(t["reserve_usd"]) for t in tasks), Decimal(0))),
            "published_pricing": info.get("x-pricing"),
            "warning": warning,
        },
    )


def _default_model(provider: str) -> str:
    if provider == "elevenlabs":
        from .config import load_settings

        return load_settings().voices.elevenlabs_model
    return voices.DEFAULT_MODEL


def _elevenlabs_terms(client, model: str) -> tuple[dict, Decimal]:
    """The account's period and the catalogue's price for ``model``, and the rate per character."""
    from . import catalog

    row = next(
        (m for m in catalog.load().models if m.provider == "elevenlabs" and m.id == model), None
    )
    if row is None or row.price is None or row.price.unit != "1k_chars":
        raise ValueError(
            f"{model} has no catalogue price per character; choose a priced ElevenLabs model in Settings"  # fmt: skip
        )
    terms = {
        "provider": "elevenlabs",
        "model": model,
        "price": {
            "amount": row.price.amount,
            "unit": row.price.unit,
            "checked": row.price_checked,
            "source": row.price_source,
        },
        "subscription": client.terms(),
    }
    return terms, money(row.price.amount) / 1000


def _elevenlabs_capacity(subscription: dict, characters: int) -> str:
    """What the period has left against what these lines need; refuses by number."""
    remaining = subscription["character_limit"] - subscription["character_count"]
    if characters <= remaining:
        return f"{remaining:,} characters left this period; these lines use {characters:,} at the catalogue rate."  # fmt: skip
    if not subscription.get("can_extend_character_limit"):
        raise ValueError(
            f"ElevenLabs has {remaining:,} characters left this period; these lines need {characters:,}"  # fmt: skip
        )
    return f"These lines need {characters:,} characters and the period has {remaining:,} left; the plan charges the rest, and the cost here is the catalogue rate."  # fmt: skip


def _priced(root: Path, task: dict, result: dict) -> dict:
    """An ElevenLabs result with the cost the quote's terms give it; the provider states none."""
    if "cost" in result:
        return result
    terms = read_json(inside(root, read_quote(root, task["quote_id"])["schema"]))
    price = terms["price"]
    cost = money(price["amount"]) / 1000 * len(task["text"])
    return {**result, "cost": str(cost), "cost_basis": f"catalogue price, read {price['checked']}"}


def check_before_spend(root: Path, task: dict) -> None:
    """Called while the reservation is written: the words must still be what was quoted."""
    require_approval(root, "script")
    if _line(root, task["line_id"]).text != task["text"]:
        raise ValueError("a line changed since the quote; estimate and authorize again")


def finish_take(root: Path, task_uuid: str, result: dict, client) -> bool:
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
        task.update(
            status="result",
            result=result,
            cost_usd=cost,
            cost_basis=result.get("cost_basis") or "provider reported",
        )
        if result.get("provider_characters") is not None:
            task["provider_characters"] = result["provider_characters"]
        journal[task_uuid] = task
        write_json(root / "work/tasks.json", journal)  # Billed cost BEFORE download.
    suffix = "mp3" if result.get("audio_format") == "mp3" else "wav"
    relative = f"work/narration/{task['line_id']}/v{task['version']:03d}-{task_uuid}.{suffix}"
    path = inside(root, relative)
    expected = task.get("sha256")
    if path.exists() and expected and file_hash(path) != expected:
        # Keep whatever changed these bytes, then restore the paid original.
        quarantine = root / f"work/quarantine/{task_uuid}-{file_hash(path)}.{suffix}"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        if not quarantine.exists():
            shutil.copyfile(path, quarantine)
        path.unlink()
    if not path.exists():
        client.download_audio(result["audioURL"], path)
    sha = file_hash(path)
    if expected and sha != expected:
        raise ValueError("recovered take differs from its recorded original; inspect manually")
    take = {
        "version": task["version"],
        "path": relative,
        "sha256": sha,
        "text": task["text"],
        "input_hash": task["input_hash"],
        "provider": task.get("provider") or "runware",
        "voice": task.get("voice"),
        "source": "generated",
        "task_id": task_uuid,
        "seconds": round(audio_seconds(path), 3),
        "cost_usd": cost,
        "at": now(),
    }
    if isinstance(result.get("alignment"), dict):
        # The provider's own character times, kept as words beside the take.
        take["words"] = voices.ElevenLabsVoice(id=str(task.get("voice"))).parse_result(result)["words"]  # fmt: skip
    _record(root, task["line_id"], take)
    update_task(root, task_uuid, status="ready", path=relative, sha256=sha, completed_at=now())
    return True


def generate(root: Path, quote_id: str, client=None) -> dict:
    """Run an authorized quote, one line at a time. Never retries a paid call."""
    quote = read_quote(root, quote_id)
    if quote["kind"] != "narration":
        raise ValueError("this quote is not for narration")
    auth = authorization(root, quote)
    schema = read_json(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    budget.require_reconciled(root)
    journal = read_json(root / "work/tasks.json")
    provider = quote.get("provider") or "runware"
    own = client is None
    client = client or _client_for(provider)
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
            if provider == "elevenlabs" and result and "audioURL" in result:
                result = _priced(root, {**task, "quote_id": quote_id}, result)
            if finish_take(root, task["uuid"], result, client):
                done.append(task["line_id"])
            else:
                pending.append(task["line_id"])
    finally:
        if own:
            client.close()
    if done:
        _follow(root)
    return {"quote_id": quote_id, "done": done, "pending": pending, "stopped": stopped}


def recover_take(root: Path, task_uuid: str, client=None) -> bool:
    """Collect a paid take that was interrupted; this never submits anything new."""
    task = read_json(root / "work/tasks.json").get(task_uuid)
    if not task or task.get("kind") != "narration":
        raise ValueError("unknown narration task")
    if task["status"] == "resolved":
        raise ValueError("task was manually reconciled; use a newly authorized quote if needed")
    provider = task.get("provider") or "runware"
    own = client is None
    client = client or _client_for(provider)
    try:
        if provider == "elevenlabs":
            result = task.get("result") or client.recover_speech(task_uuid, task)
            if result and "audioURL" in result:
                result = _priced(root, task, result)
        else:
            result = task.get("result") or client.recover_speech(task_uuid)
        finished = finish_take(root, task_uuid, result, client) if result else False
    finally:
        if own:
            client.close()
    if finished:
        _follow(root)
    return finished


def view(root: Path) -> dict:
    index = read_index(root)
    stale = set(stale_lines(root))
    return {
        "voice": current_voice(root),
        "measured_rate": index.get("measured_rate"),
        "stale": sorted(stale),
        "lines": index["lines"],
    }


def _client_for(provider: str):
    """A paying client for the provider a quote or task names."""
    if provider == "elevenlabs":
        return ElevenLabsClient(elevenlabs_api_key())
    return RunwareClient(runware_api_key())
