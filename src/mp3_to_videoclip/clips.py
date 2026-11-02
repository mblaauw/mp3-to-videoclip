"""A short moving version of a selected still, bought as its own journaled asset.

The still stays selected and stays the fallback: a clip sits beside the versions in
``work/assets.json`` under ``clips``, and ``clip`` names the one in use. A clip belongs to the
still it was made from, so choosing another picture turns it off. It is journaled like any paid
image: the reservation and the task id are written before the request, it is never resubmitted,
and it is only used when the owner chooses it.
"""

from __future__ import annotations

import json
import os
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
    state_lock,
    state_mutation,
    write_json,
)

DEFAULT_SECONDS = 5
POLL_SECONDS = 5.0
#: A slow clip stays journaled and is collected later; it is never bought again.
POLL_LIMIT_SECONDS = 600.0


def _chosen(entry: dict) -> dict | None:
    return next(
        (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None
    )


def _duration(props: dict, wanted: int) -> int:
    """The length this model offers nearest above the one wanted, else the longest it has."""
    rule = props.get("duration")
    if not rule:
        raise ValueError("this model does not say how long its clips are")
    if rule.get("enum"):
        offered = sorted(rule["enum"])
        return next((value for value in offered if value >= wanted), offered[-1])
    low, high = rule.get("minimum", wanted), rule.get("maximum", wanted)
    return int(min(max(wanted, low), high))


def quote_clips(
    root: Path,
    shot_ids: list[str],
    *,
    seconds: int = DEFAULT_SECONDS,
    model: str | None = None,
    reserve_per_second: str | None = None,
    client=None,
) -> dict:
    """Quote one clip per chosen still. Reads the free public schema and spends nothing."""
    from .config import load_settings

    root = Path(root)
    pictures = load_settings().pictures
    model = model or pictures.video_model
    if not model:
        raise ValueError("choose a video model in Settings first")
    project = load_project(root)
    if not project.uses_remotion:
        raise ValueError("clips need a film made with the current renderer")
    board = load_board(root)
    shots = {shot.id: shot for shot in board.shots}
    named = list(dict.fromkeys(shot_ids))
    if not named or not set(named) <= set(shots):
        raise ValueError("choose shots from this storyboard")
    for shot_id in named:
        shot = shots[shot_id]
        if shot.asset_shot_id is not None or not shotkinds.is_paid(shot):
            raise ValueError(f"shot {shot_id} has no still of its own to make a clip from")
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
    length = _duration(props, seconds)
    per_second = money(
        reserve_per_second
        if reserve_per_second is not None
        else str(pictures.reserve_usd_per_clip_second)
    )
    allowance = per_second * Decimal(length)
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
        prompt = shot.motion_prompt.strip() or shot.image_prompt.strip()
        task_uuid = str(uuid4())
        request = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": info["x-air-id"],
            "positivePrompt": prompt,
            "duration": length,
            "outputType": "URL",
            "outputFormat": "MP4",
            "deliveryMethod": "async",
            "includeCost": True,
        }
        check = {**request, "inputs": {"frameImages": [str(uuid4())]}}
        if "width" in props and "height" in props:
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
                        "prompt": prompt,
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
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "reserve_total_usd": str(allowance * len(tasks)),
            "published_pricing": info.get("x-pricing"),
            "warning": "The reserve is a limit on admission, not an exact price.",
        },
    )


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
                pending.append(task["shot_id"])
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
