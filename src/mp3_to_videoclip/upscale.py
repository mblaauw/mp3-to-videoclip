"""A sharper copy of a selected still, as a new version of that still.

A 2× upscale keeps the still's ``input_hash``, so selection, staleness and the review
gates treat it as what it is: the same picture. It is journaled like any paid image: the
reservation and the task id are written before the request, it is never resubmitted, and
it is only selected when the owner selects it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .generation import (
    authorization,
    begin_task,
    budget,
    finish_image,
    money,
    read_quote,
    save_quote,
    validate_request,
)
from .production import load_board, require_approval, resolved_assets
from .providers import RunwareClient, runware_api_key
from .storage import digest, file_hash, inside, read_json, write_json

DEFAULT_MODEL = "real-esrgan"
FACTOR = 2
#: Published at $0.0006 for factor 2. A reservation covers a price rise; the journal
#: keeps what the provider reports.
RESERVE = Decimal("0.01")


def _chosen(assets: dict, shot_id: str) -> dict | None:
    entry = assets.get(shot_id) or {}
    return next((v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None)  # fmt: skip


def quote_upscale(
    root: Path, shot_ids: list[str], *, reserve: str | None = None, model: str | None = None, client=None
) -> dict:  # fmt: skip
    """Quote one task per selected still. Spends nothing."""
    from .config import load_settings

    root = Path(root)
    model = model or load_settings().pictures.upscaler or DEFAULT_MODEL
    allowance = money(reserve) if reserve is not None else RESERVE
    board = load_board(root)
    owners = {shot.id: shot.asset_shot_id or shot.id for shot in board.shots}
    named = list(dict.fromkeys(owners.get(shot_id, shot_id) for shot_id in shot_ids))
    if not named or not set(shot_ids) <= set(owners):
        raise ValueError("choose stills from this storyboard to make sharper")
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
    props = schema["components"]["schemas"]["RequestBody"]["items"]["properties"]
    if props.get("taskType", {}).get("const") != "upscale":
        raise ValueError(f"{model} is not an upscale model")
    schema_path = f"work/schemas/{digest(schema)}.json"
    write_json(inside(root, schema_path), schema)
    # Refuses a still that isn't the current one, so a stale picture is never sharpened.
    resolved_assets(root, named)
    assets = read_json(root / "work/assets.json")
    journal = read_json(root / "work/tasks.json")
    tasks = []
    for shot_id in named:
        chosen = _chosen(assets, shot_id)
        if chosen is None:
            raise ValueError(f"shot {shot_id} has no selected still to make sharper")
        versions = assets[shot_id]["versions"]
        if chosen.get("derivation") or any(
            (v.get("derived_from") or {}).get("sha256") == chosen["sha256"] for v in versions
        ):
            continue
        if any(
            t.get("shot_id") == shot_id and t["status"] in ("submitted", "result")
            for t in journal.values()
        ):
            raise ValueError(f"shot {shot_id} has an unresolved task; recover it first")
        version = (
            max(
                [v["version"] for v in versions]
                + [t["version"] for t in journal.values() if t.get("shot_id") == shot_id]
                + [0]
            )
            + 1
        )
        task_uuid = str(uuid4())
        request = {
            "taskType": "upscale",
            "taskUUID": task_uuid,
            "model": info["x-air-id"],
            "upscaleFactor": FACTOR,
            "outputType": "URL",
            "outputFormat": "JPG",
            "deliveryMethod": "sync",
            "includeCost": True,
        }
        validate_request(schema, {**request, "inputs": {"image": str(uuid4())}})
        tasks.append(
            {
                "uuid": task_uuid,
                "shot_id": shot_id,
                "version": version,
                "input_hash": chosen["input_hash"],
                "references": [],
                "request": request,
                "reserve_usd": str(allowance),
                "derived_from": {"version": chosen["version"], "sha256": chosen["sha256"]},
                "derivation": {"kind": "upscale", "model": model, "factor": FACTOR},
            }
        )
    if not tasks:
        raise ValueError("every chosen still already has a sharper version")
    return save_quote(
        root,
        {
            "kind": "upscale",
            "scope": "upscale",
            "model": model,
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
    assets = read_json(root / "work/assets.json")
    chosen = _chosen(assets, task["shot_id"])
    if chosen is None or chosen["sha256"] != task["derived_from"]["sha256"]:
        raise ValueError("the selected still changed since the quote; estimate again")
    path = inside(root, chosen["path"])
    if not path.is_file() or file_hash(path) != chosen["sha256"]:
        raise ValueError(f"selected still for {task['shot_id']} changed; recover it first")


def generate_upscale(root: Path, quote_id: str, client=None) -> dict:
    """Run an authorized quote, one still at a time. Never retries a paid call."""
    root = Path(root)
    quote = read_quote(root, quote_id)
    if quote["kind"] != "upscale":
        raise ValueError("this quote is not for sharper stills")
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
            assets = read_json(root / "work/assets.json")
            chosen = _chosen(assets, task["shot_id"])
            source = inside(root, chosen["path"]) if chosen else None
            request = dict(task["request"])
            if source is not None:
                request["inputs"] = {"image": client.reference_image(source)}
                validate_request(schema, request)
            begin_task(root, quote, task)
            result = client.submit(request)
            if finish_image(root, task["uuid"], result, client):
                done.append(task["shot_id"])
            else:
                pending.append(task["shot_id"])
    finally:
        if own:
            client.close()
    return {"quote_id": quote_id, "done": done, "pending": pending}
