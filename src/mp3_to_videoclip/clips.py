"""A short moving version of a selected still, bought as its own journaled asset.

The still stays selected and stays the fallback: a clip sits beside the versions in
``work/assets.json`` under ``clips``, and ``clip`` names the one in use. A clip belongs to the
still it was made from, so choosing another picture turns it off. It is journaled like any paid
image: the reservation and the task id are written before the request, it is never resubmitted,
and it is only used when the owner chooses it.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from . import shotkinds
from .generation import (
    authorization,
    begin_task,
    budget,
    money,
    now,
    read_quote,
    save_quote,
    validate_request,
)
from .production import load_board, load_project, require_approval, resolved_assets
from .production.assets import still_root
from .providers import RunwareClient, runware_api_key
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

DEFAULT_SECONDS = 5
#: No clip is admitted for less than a cent, whatever the rate says.
MIN_RESERVE = Decimal("0.01")
MOTION_FILE = "work/motion-proposals.json"
POLL_SECONDS = 5.0
#: A slow clip stays journaled and is collected later; it is never bought again.
POLL_LIMIT_SECONDS = 600.0


def _chosen(entry: dict) -> dict | None:
    return next(
        (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None
    )


def _numeric_rule(rule) -> dict | None:
    """The numeric branch of a duration rule: a plain rule, or one branch of an anyOf/oneOf."""
    if not isinstance(rule, dict):
        return None
    if rule.get("enum") or "minimum" in rule or "maximum" in rule:
        return rule
    for branch in rule.get("anyOf") or rule.get("oneOf") or []:
        found = _numeric_rule(branch)
        if found is not None:
            return found
    return None


def durations(props: dict) -> list:
    """The lengths a model offers: its enum, or its range's whole seconds; [] for none."""
    rule = _numeric_rule(props.get("duration"))
    if rule is None:
        return []
    if rule.get("enum"):
        return sorted(value for value in rule["enum"] if isinstance(value, (int, float)))
    low = rule.get("minimum", 1)
    high = rule.get("maximum", low)
    first = int(math.ceil(low))
    return list(range(first, int(math.floor(high)) + 1))


def _duration(props: dict, wanted: float) -> float | int:
    """The length this model offers nearest above the one wanted, else the longest it has."""
    rule = _numeric_rule(props.get("duration"))
    if rule is None:
        raise ValueError("this model does not say how long its clips are")
    if rule.get("enum"):
        offered = sorted(value for value in rule["enum"] if isinstance(value, (int, float)))
        if not offered:
            raise ValueError("this model does not say how long its clips are")
        return next((value for value in offered if value >= wanted), offered[-1])
    low, high = rule.get("minimum", wanted), rule.get("maximum", wanted)
    value = min(max(wanted, low), high)
    return int(value) if float(value).is_integer() else float(value)


def resolutions(props: dict) -> list[str]:
    """The sizes a model names when it starts from a still, as the schema words them."""
    rule = props.get("resolution")
    if isinstance(rule, dict) and isinstance(rule.get("enum"), list):
        return [str(value) for value in rule["enum"]]
    return []


def _audio_path(props: dict) -> tuple[str, ...] | None:
    """Where this model takes its own-sound switch, or ``None`` when it has none."""
    settings = props.get("settings")
    if isinstance(settings, dict) and "audio" in (settings.get("properties") or {}):
        return ("settings", "audio")
    provider = props.get("providerSettings")
    for vendor, rule in ((provider or {}).get("properties") or {}).items():
        keys = (rule or {}).get("properties") or {}
        for key in ("generateAudio", "sound", "audio"):
            if key in keys:
                return ("providerSettings", vendor, key)
    return None


def _with_audio(request: dict, path: tuple[str, ...], on: bool) -> dict:
    """The request with its own-sound switch set, so a priced default is never left unsaid."""
    request = dict(request)
    target = request
    for key in path[:-1]:
        target[key] = dict(target.get(key) or {})
        target = target[key]
    target[path[-1]] = on
    return request


def model_options(props: dict) -> dict:
    """What a model lets the owner choose: lengths, sizes, and whether it makes its own sound."""
    return {
        "durations": durations(props),
        "resolutions": resolutions(props),
        "sized": "width" in props and "height" in props,
        "audio": _audio_path(props) is not None,
    }


_RESOLUTION_WORDS = re.compile(r"(\d{3,4}p|4k)", re.IGNORECASE)


def _rate_matches(label: str, resolution: str | None, audio: bool) -> bool:
    words = label.lower()
    named = {word.lower() for word in _RESOLUTION_WORDS.findall(words)}
    if named and (resolution is None or resolution.lower() not in named):
        return False
    says_audio = "audio" in words or "sound" in words
    without = "without" in words or "no audio" in words or "no sound" in words
    if says_audio:
        return audio is not without
    return not audio or not named


def typical_seconds(info: dict) -> float | None:
    """How long the provider's own example runs took, the median in seconds; None without any."""
    examples = (
        ((info.get("x-pricing") or {}).get("examples") or []) if isinstance(info, dict) else []
    )
    times = sorted(
        float(item["latencyMs"]) / 1000
        for item in examples
        if isinstance(item, dict)
        and isinstance(item.get("latencyMs"), (int, float))
        and not isinstance(item.get("latencyMs"), bool)
        and item["latencyMs"] > 0
    )
    if not times:
        return None
    middle = len(times) // 2
    value = times[middle] if len(times) % 2 else (times[middle - 1] + times[middle]) / 2
    return round(value, 1)


def published_price(info: dict, resolution: str | None, audio: bool, length: float) -> dict | None:
    """The model's published price for these choices, or ``None`` when no rate fits.

    A rate per second is multiplied by the length; a rate per clip ("output") counts
    once. Unlabeled rates fit any choice; a labeled one must name the resolution and say
    the same about the model's own sound.
    """
    rates = ((info.get("x-pricing") or {}).get("rates") or []) if isinstance(info, dict) else []
    fitting = []
    for rate in rates:
        if not isinstance(rate, dict):
            continue
        amount, unit = rate.get("amount"), rate.get("unit")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            continue
        if unit not in ("durationSecond", "output"):
            continue
        label = str(rate.get("label") or "")
        if label and not _rate_matches(label, resolution, audio):
            continue
        fitting.append(rate)
    if not fitting:
        return None
    # The most specific rate wins: a labeled one over an unlabeled one.
    rate = sorted(fitting, key=lambda item: 0 if item.get("label") else 1)[0]
    amount = Decimal(str(rate["amount"]))
    usd = amount * Decimal(str(length)) if rate["unit"] == "durationSecond" else amount
    return {
        "amount": str(amount),
        "unit": "second" if rate["unit"] == "durationSecond" else "clip",
        "label": str(rate.get("label") or ""),
        "display": str(rate.get("display") or ""),
        "usd": str(usd.quantize(Decimal("0.0001"))),
    }


def quote_clips(
    root: Path,
    shot_ids: list[str],
    *,
    seconds: float | None = None,
    model: str | None = None,
    resolution: str | None = None,
    audio: bool = False,
    prompt: str | None = None,
    reserve_per_second: str | None = None,
    client=None,
) -> dict:
    """Quote one clip per chosen still. Reads the free public schema and spends nothing.

    The request takes the schema's shape: the nearest length it offers, its ``resolution``
    word or the film's own size when it accepts one with a frame, and its own-sound switch
    set as asked whenever it has one. The price is the rate the model publishes for these
    choices; when no rate fits, Settings' reserve per second stands in and the quote says so.
    """
    from .config import load_settings

    root = Path(root)
    pictures = load_settings().pictures
    model = model or pictures.video_model
    if not model:
        raise ValueError("choose a video model in Settings first")
    project = load_project(root)
    board = load_board(root)
    shots = {shot.id: shot for shot in board.shots}
    named = list(dict.fromkeys(shot_ids))
    if not named or not set(named) <= set(shots):
        raise ValueError("choose shots from this storyboard")
    for shot_id in named:
        shot = shots[shot_id]
        if _motion_problem(shot):
            raise ValueError(f"shot {shot_id} has no still of its own to make a clip from")
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
        raise ValueError("a motion prompt is text")
    if prompt is not None and len(named) > 1:
        raise ValueError("one motion prompt fits one shot; quote the shots one at a time")
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
    item = schema["components"]["schemas"]["RequestBody"]["items"]
    props = item["properties"]
    if props.get("taskType", {}).get("const") != "videoInference":
        raise ValueError(f"{model} is not a video model")
    if "frameImages" not in props.get("inputs", {}).get("properties", {}):
        raise ValueError(f"{model} cannot start from a still")
    length = _duration(props, seconds if seconds is not None else DEFAULT_SECONDS)
    offered = resolutions(props)
    if resolution is not None and offered and resolution not in offered:
        raise ValueError(f"{model} offers {', '.join(offered)}, not {resolution}")
    chosen_resolution = resolution or (offered[0] if offered else None)
    sound = _audio_path(props)
    if audio and sound is None:
        raise ValueError(f"{model} makes no sound of its own")
    published = published_price(info, chosen_resolution, bool(audio), float(length))
    if published is not None:
        allowance = max(MIN_RESERVE, money(published["usd"]))
        basis = "published rate"
    else:
        per_second = money(
            reserve_per_second
            if reserve_per_second is not None
            else str(pictures.reserve_usd_per_clip_second)
        )
        allowance = max(MIN_RESERVE, per_second * Decimal(str(length)))
        basis = "settings reserve"
    schema_path = f"work/schemas/{digest(schema)}.json"
    write_json(inside(root, schema_path), schema)
    # Refuses a still that isn't the current one, so a stale picture never starts moving.
    resolved_assets(root, named)
    assets = read_json(root / "work/assets.json")
    journal = read_json(root / "work/tasks.json")
    tasks = []
    for shot_id in named:
        entry = assets.get(shot_id, {})
        chosen = _chosen(entry)
        if chosen is None:
            raise ValueError(f"shot {shot_id} has no selected still to make a clip from")
        if any(
            t.get("shot_id") == shot_id and t["status"] in ("submitted", "result")
            for t in journal.values()
        ):
            raise ValueError(f"shot {shot_id} has an unresolved task; recover it first")
        version = (
            max(
                [v["version"] for v in entry.get("versions", [])]
                + [c["version"] for c in entry.get("clips", [])]
                + [t["version"] for t in journal.values() if t.get("shot_id") == shot_id]
                + [0]
            )
            + 1
        )
        shot = shots[shot_id]
        words = (prompt or "").strip() or shot.motion_prompt.strip() or shot.image_prompt.strip()
        task_uuid = str(uuid4())
        request = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": info["x-air-id"],
            "positivePrompt": words,
            "duration": length,
            "outputType": "URL",
            "outputFormat": "MP4",
            "deliveryMethod": "async",
            "includeCost": True,
        }
        if sound is not None:
            request = _with_audio(request, sound, bool(audio))
        check = {**request, "inputs": {"frameImages": [str(uuid4())]}}
        if chosen_resolution is not None and "resolution" in props:
            request["resolution"] = chosen_resolution
            check["resolution"] = chosen_resolution
        elif "width" in props and "height" in props:
            sized = {**check, "width": project.width, "height": project.height}
            try:
                validate_request(schema, sized)
            except ValueError:
                pass  # The model chooses its own canvas; the film covers the frame with it.
            else:
                request.update(width=project.width, height=project.height)
                check = sized
        validate_request(schema, check)
        tasks.append(
            {
                "uuid": task_uuid,
                "shot_id": shot_id,
                "version": version,
                "input_hash": chosen["input_hash"],
                "references": [],
                "request": request,
                "reserve_usd": str(allowance),
                "seconds": length,
                "model": model,
                "derived_from": {"version": chosen["version"], "sha256": chosen["sha256"]},
                "still_root": still_root(chosen),
                "clip_input_hash": digest(
                    {
                        "model": model,
                        "seconds": length,
                        "source": chosen["sha256"],
                        "prompt": words,
                        "resolution": chosen_resolution,
                        "audio": bool(audio),
                    }
                ),
            }
        )
    return save_quote(
        root,
        {
            "kind": "clip",
            "scope": "clip",
            "model": model,
            "seconds": length,
            "choices": {
                "resolution": chosen_resolution,
                "audio": bool(audio) if sound else None,
                "prompt": prompt,
            },  # fmt: skip
            "price_basis": basis,
            "rate": published,
            "typical_seconds": typical_seconds(info),
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "reserve_total_usd": str(allowance * len(tasks)),
            "published_pricing": info.get("x-pricing"),
            "warning": (
                "The price is the model's published rate for these choices."
                if basis == "published rate"
                else "No published rate fits these choices; the reserve is Settings' rate per second, a limit on admission, not an exact price."  # fmt: skip
            ),
        },
    )


def options_for(model: str, client=None) -> dict:
    """What a model lets the owner choose, from its free public schema. Spends nothing."""
    own = client is None
    client = client or RunwareClient("public-schema-only")
    try:
        schema = client.schema(model)
    finally:
        if own:
            client.close()
    info = schema.get("info") or {}
    props = schema["components"]["schemas"]["RequestBody"]["items"]["properties"]
    if props.get("taskType", {}).get("const") != "videoInference":
        raise ValueError(f"{model} is not a video model")
    return {
        "model": model,
        "live": info.get("x-status") == "live",
        "typical_seconds": typical_seconds(info),
        **model_options(props),
        "rates": [
            {
                "amount": str(r.get("amount")),
                "unit": r.get("unit"),
                "label": str(r.get("label") or ""),
                "display": str(r.get("display") or ""),
            }  # fmt: skip
            for r in ((info.get("x-pricing") or {}).get("rates") or [])
            if isinstance(r, dict)
        ],
    }


def _motion_problem(shot) -> str | None:
    if shot.asset_shot_id is not None or not shotkinds.is_paid(shot):
        return f"shot {shot.id} has no still of its own to move"
    return None


@state_mutation
def propose_motion(root: Path, items: list) -> dict:
    """The Writer's list of shots that earn motion. A suggestion: nothing here can spend."""
    shots = {shot.id: shot for shot in load_board(root).shots}
    rows = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in shots:
            raise ValueError("propose shots from this storyboard")
        problem = _motion_problem(shots[item["id"]])
        if problem:
            raise ValueError(problem)
        why = str(item.get("why") or "").strip()
        if not why:
            raise ValueError(f"say why {item['id']} earns motion")
        rows.append({"id": item["id"], "why": why[:240]})
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("name each shot once")
    write_json(root / MOTION_FILE, {"shots": rows})
    return {"proposed": [row["id"] for row in rows], "note": "Only the owner buys a clip."}


def proposed_motion(root: Path) -> dict[str, str]:
    value = read_optional(root / MOTION_FILE)
    rows = value.get("shots", []) if isinstance(value, dict) else []
    return {row["id"]: row["why"] for row in rows}


def check_before_spend(root: Path, task: dict) -> None:
    """Called while the reservation is written: the source must still be what was quoted."""
    require_approval(root, "storyboard")
    chosen = _chosen(read_json(root / "work/assets.json").get(task["shot_id"], {}))
    if chosen is None or chosen["sha256"] != task["derived_from"]["sha256"]:
        raise ValueError("the selected still changed since the quote; estimate again")
    path = inside(root, chosen["path"])
    if not path.is_file() or file_hash(path) != chosen["sha256"]:
        raise ValueError(f"selected still for {task['shot_id']} changed; recover it first")


def probe(path: Path) -> dict:
    """What the file really is. A clip the composition could not draw is refused here."""
    binary = shutil.which("ffprobe")
    if binary is None:
        raise ValueError("ffprobe is required to check a clip")
    completed = subprocess.run(
        [
            binary,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=codec_name,nb_read_packets,avg_frame_rate:format=duration,format_name",
            "-of",
            "json",
            str(path),
        ],  # fmt: skip
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError("the clip is not a readable video")
    value = json.loads(completed.stdout)
    stream = (value.get("streams") or [{}])[0]
    if stream.get("codec_name") != "h264" or "mp4" not in value["format"].get("format_name", ""):
        raise ValueError("a clip must be H.264 in an MP4")
    top, _, bottom = stream.get("avg_frame_rate", "0/1").partition("/")
    fps = float(top) / float(bottom or 1) if float(bottom or 1) else 0.0
    frames = int(stream.get("nb_read_packets") or 0)
    if frames <= 0 or fps <= 0:
        raise ValueError("the clip has no frames")
    return {"frames": frames, "fps": round(fps, 3), "seconds": float(value["format"]["duration"])}


@state_mutation
def record_clip(root: Path, task: dict, path: Path, facts: dict) -> None:
    index = root / "work/assets.json"
    assets = read_json(index)
    entry = assets.setdefault(task["shot_id"], {"versions": [], "selected": None})
    value = {
        "version": task["version"],
        "path": str(path.relative_to(root)),
        "sha256": file_hash(path),
        "media": "video",
        "frames": facts["frames"],
        "fps": facts["fps"],
        "seconds": facts["seconds"],
        "model": task["model"],
        "input_hash": task["input_hash"],
        "clip_input_hash": task["clip_input_hash"],
        "derived_from": task["derived_from"],
        "still_root": task["still_root"],
        "task_id": task["uuid"],
    }
    clips = entry.setdefault("clips", [])
    existing = next((c for c in clips if c["version"] == task["version"]), None)
    if existing and existing != value:
        raise ValueError("cannot overwrite a prior clip")
    if not existing:
        clips.append(value)
    write_json(index, assets)


def finish_clip(root: Path, task_uuid: str, result: dict, client) -> bool:
    """Record what the provider billed, then fetch, check and index the file."""
    if "videoURL" not in result:
        return False
    if result.get("taskUUID") != task_uuid:
        raise ValueError("provider returned another task")
    cost = str(money(result["cost"]))
    with state_lock(root):
        journal = read_json(root / "work/tasks.json")
        task = dict(journal[task_uuid])
        if task.get("cost_usd") is not None and money(task["cost_usd"]) != money(cost):
            raise ValueError("provider task cost changed; reconcile manually")
        if task.get("status") == "resolved":
            raise ValueError("task was manually reconciled; inspect the result before recovery")
        task.update(status="result", result=result, cost_usd=cost, cost_basis="provider reported")
        journal[task_uuid] = task
        write_json(root / "work/tasks.json", journal)  # Billed cost BEFORE download.
    relative = f"assets/{task['shot_id']}/v{task['version']:03d}-{task_uuid}.mp4"
    path = inside(root, relative)
    expected = task.get("sha256")
    if path.exists() and expected and file_hash(path) != expected:
        # Preserve changed bytes before restoring the paid original.
        quarantine = root / f"work/quarantine/{task_uuid}-{file_hash(path)}.mp4"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        if not quarantine.exists():
            os.link(path, quarantine)
        path.unlink()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        client.download_video(result["videoURL"], path)
    if expected and file_hash(path) != expected:
        raise ValueError("recovered clip differs from its recorded original; inspect manually")
    facts = probe(path)
    with state_lock(root):
        journal = read_json(root / "work/tasks.json")
        current = journal[task_uuid]
        if current.get("status") == "resolved":
            raise ValueError("task was manually reconciled during download; inspect the result")
        record_clip(root, task, path.resolve() if not path.is_absolute() else path, facts)
        current.update(status="ready", path=relative, sha256=file_hash(path), completed_at=now())
        write_json(root / "work/tasks.json", journal)
    return True


def generate_clips(root: Path, quote_id: str, client=None, *, sleep=time.sleep) -> dict:
    """Run an authorized quote, one clip at a time. Never retries a paid call."""
    root = Path(root).resolve()
    quote = read_quote(root, quote_id)
    if quote["kind"] != "clip":
        raise ValueError("this quote is not for clips")
    authorization(root, quote)
    schema = read_json(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    budget.require_reconciled(root)
    journal = read_json(root / "work/tasks.json")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    done, pending = [], []
    try:
        for task in quote["tasks"]:
            if task["uuid"] in journal:
                raise ValueError(f"task {task['uuid']} needs recover; no paid resubmission")
            chosen = _chosen(read_json(root / "work/assets.json").get(task["shot_id"], {}))
            source = inside(root, chosen["path"]) if chosen else None
            request = dict(task["request"])
            if source is not None:
                request["inputs"] = {"frameImages": [client.reference_image(source)]}
                validate_request(schema, request)
            begin_task(root, quote, task)
            result = client.submit_video(request)
            waited = 0.0
            while "videoURL" not in result and waited < POLL_LIMIT_SECONDS:
                sleep(POLL_SECONDS)
                waited += POLL_SECONDS
                result = client.recover_video(task["uuid"]) or result
            if finish_clip(root, task["uuid"], result, client):
                done.append(task["shot_id"])
            else:
                # Later clips would only be refused: a task still out holds the film's spending.
                pending.append(task["shot_id"])
                break
    finally:
        if own:
            client.close()
    return {"quote_id": quote_id, "done": done, "pending": pending}


def recover_clip(root: Path, task_uuid: str, client=None) -> bool:
    """Collect a paid clip that was interrupted; this never submits anything new."""
    root = Path(root).resolve()
    task = read_json(root / "work/tasks.json").get(task_uuid)
    if not task or task.get("kind") != "clip":
        raise ValueError("unknown clip task")
    if task["status"] == "resolved":
        raise ValueError("task was manually reconciled; use a newly authorized quote if needed")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        result = task.get("result") or client.recover_video(task_uuid)
        return finish_clip(root, task_uuid, result, client) if result else False
    finally:
        if own:
            client.close()


@state_mutation
def select_clip(root: Path, shot_id: str, version: int | None) -> None:
    """Use this clip, or go back to the still. A clip of another picture cannot be used."""
    index = root / "work/assets.json"
    assets = read_json(index)
    entry = assets.get(shot_id)
    if entry is None:
        raise ValueError(f"shot {shot_id} has no assets")
    if version is None:
        entry.pop("clip", None)
    else:
        clip = next((c for c in entry.get("clips", []) if c["version"] == version), None)
        chosen = _chosen(entry)
        if clip is None:
            raise ValueError("unknown clip")
        if chosen is None or clip["still_root"] != still_root(chosen):
            raise ValueError("that clip was made from another still; select that still first")
        entry["clip"] = version
    write_json(index, assets)
