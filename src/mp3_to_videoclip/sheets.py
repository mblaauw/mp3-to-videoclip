"""Character sheets and scene plates: pictures made to keep a film's world consistent.

One paid task from a synthetic spec, priced and journaled like a still, kept under
``work/sheets/<entry-id>/`` and recorded in ``work/assets.json`` as ``sheet:<entry-id>``.
A sheet is only shown until the owner chooses to use it as a reference, because binding
one changes the brief and so asks for the story to be approved again.
"""

from __future__ import annotations

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
from .models import Brief, VisualReference
from .production import load_brief, load_project
from .profiles import DEFAULT_MODEL
from .providers import RunwareClient, runware_api_key
from .storage import digest, file_hash, inside, read_json, state_lock, write_json

PREFIX = "sheet:"
SHEET = "A character reference sheet of one person: front, three-quarter, profile and back views on a plain neutral ground, even light, the same clothes in every view."
PLATE = "A scene plate of this place with nobody in it, an establishing view that shows its geography and its light."


def _entry(brief: Brief, entry_id: str) -> tuple[str, object]:
    character = next((item for item in brief.characters if item.id == entry_id), None)
    scenes = brief.creative.scenes if brief.creative else []
    scene = next((item for item in scenes if item.id == entry_id), None)
    if character is not None and scene is not None:
        raise ValueError(f"{entry_id} names both a character and a place; rename one")
    if character is not None:
        return "character", character
    if scene is not None:
        return "scene", scene
    raise ValueError(f"nothing in this film's world is called {entry_id}")


def sheet_spec(root: Path, entry_id: str) -> dict:
    """What a sheet is made from. Its digest says whether a made sheet is still current."""
    project = load_project(root)
    brief = load_brief(root)
    kind, entry = _entry(brief, entry_id)
    look = brief.creative.look if brief.creative else ""
    if kind == "character":
        if not entry.permission_confirmed:
            from .production.image_specs import _character_refusal

            raise _character_refusal(entry_id)
        subject = [SHEET, entry.identity or entry.description]
    else:
        subject = [PLATE, entry.description]
    rules = brief.creative.image_rules if brief.creative else []
    return {
        "entry_id": entry_id,
        "kind": kind,
        "positivePrompt": "\n".join(filter(None, [*subject, look, *rules])),
        "size": list(project.image_size),
    }


def _next_version(root: Path, key: str) -> int:
    assets = read_json(root / "work/assets.json")
    journal = read_json(root / "work/tasks.json")
    return (
        max(
            [v["version"] for v in assets.get(key, {}).get("versions", [])]
            + [t["version"] for t in journal.values() if t.get("shot_id") == key]
            + [0]
        )
        + 1
    )


def quote_sheet(root: Path, entry_id: str, *, reserve: str = "0.05", client=None) -> dict:
    """Quote one sheet or plate. Spends nothing."""
    root = Path(root)
    project = load_project(root)
    model = project.image_model or DEFAULT_MODEL
    spec = sheet_spec(root, entry_id)
    key = PREFIX + entry_id
    journal = read_json(root / "work/tasks.json")
    if any(t.get("shot_id") == key and t["status"] in ("submitted", "result") for t in journal.values()):  # fmt: skip
        raise ValueError(f"{entry_id} has an unresolved task; recover it first")
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
    if props.get("taskType", {}).get("const") != "imageInference":
        raise ValueError("MVP supports imageInference models only")
    schema_path = f"work/schemas/{digest(schema)}.json"
    write_json(inside(root, schema_path), schema)
    task_uuid = str(uuid4())
    version = _next_version(root, key)
    request = {
        "taskType": "imageInference",
        "taskUUID": task_uuid,
        "model": info["x-air-id"],
        "positivePrompt": spec["positivePrompt"],
        "width": spec["size"][0],
        "height": spec["size"][1],
        "numberResults": 1,
        "outputType": "URL",
        "outputFormat": "JPG",
        "deliveryMethod": "sync",
        "includeCost": True,
    }
    if project.image_settings is not None and project.image_model in (None, model):
        request["settings"] = project.image_settings.model_dump()
    validate_request(schema, request)
    allowance = money(reserve)
    return save_quote(
        root,
        {
            "kind": "sheet",
            "scope": "sheet",
            "model": model,
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": [
                {
                    "uuid": task_uuid,
                    "shot_id": key,
                    "version": version,
                    "input_hash": digest(spec),
                    "references": [],
                    "request": request,
                    "reserve_usd": str(allowance),
                    "relative": f"work/sheets/{entry_id}/v{version:03d}.jpg",
                }
            ],
            "reserve_total_usd": str(allowance),
            "published_pricing": info.get("x-pricing"),
            "warning": "The reserve is a limit on admission, not an exact price.",
        },
    )


def check_before_spend(root: Path, task: dict) -> None:
    """Called while the reservation is written: the world must still be what was quoted."""
    entry_id = task["shot_id"].removeprefix(PREFIX)
    if digest(sheet_spec(root, entry_id)) != task["input_hash"]:
        raise ValueError(f"{entry_id} changed since the quote; estimate again")


def generate_sheet(root: Path, quote_id: str, client=None) -> dict:
    """Run an authorized quote. Never retries a paid call."""
    root = Path(root)
    quote = read_quote(root, quote_id)
    if quote["kind"] != "sheet":
        raise ValueError("this quote is not for a sheet")
    authorization(root, quote)
    schema = read_json(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    budget.require_reconciled(root)
    journal = read_json(root / "work/tasks.json")
    task = quote["tasks"][0]
    if task["uuid"] in journal:
        raise ValueError(f"task {task['uuid']} needs recover; no paid resubmission")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        validate_request(schema, task["request"])
        begin_task(root, quote, task)
        result = client.submit(task["request"])
        finished = finish_image(root, task["uuid"], result, client)
    finally:
        if own:
            client.close()
    if finished:
        # The newest sheet is the one on show; every older one stays on disk.
        with state_lock(root):
            assets = read_json(root / "work/assets.json")
            assets[task["shot_id"]]["selected"] = task["version"]
            write_json(root / "work/assets.json", assets)
    return {"quote_id": quote_id, "done": [task["shot_id"]] if finished else [], "pending": [] if finished else [task["shot_id"]]}  # fmt: skip


def view(root: Path) -> dict:
    """Every entry that could have a sheet, with what has been made for it."""
    brief = load_brief(root)
    assets = read_json(root / "work/assets.json")
    scenes = brief.creative.scenes if brief.creative else []
    rows = {}
    for kind, items in (("character", brief.characters), ("scene", scenes)):
        for item in items:
            entry = assets.get(PREFIX + item.id) or {}
            chosen = next(
                (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")),
                None,
            )
            rows[item.id] = {
                "kind": kind,
                "version": chosen["version"] if chosen else None,
                "current": bool(chosen) and _is_current(root, item.id, chosen),
            }
    return rows


def _is_current(root: Path, entry_id: str, chosen: dict) -> bool:
    try:
        return digest(sheet_spec(root, entry_id)) == chosen["input_hash"]
    except ValueError:
        return False


def picture(root: Path, entry_id: str, version: int) -> Path:
    entry = read_json(root / "work/assets.json").get(PREFIX + entry_id) or {}
    chosen = next((v for v in entry.get("versions", []) if v["version"] == version), None)
    if chosen is None:
        raise ValueError(f"{entry_id} has no sheet version {version}")
    path = inside(root, chosen["path"])
    if file_hash(path) != chosen["sha256"]:
        raise ValueError(f"the sheet for {entry_id} changed on disk; recover it")
    return path


def use_as_reference(root: Path, entry_id: str, version: int) -> Brief:
    """The owner's click: import the sheet with permission and bind it to its entry."""
    from .production.brief import update_brief
    from .references import import_reference

    brief = load_brief(root)
    kind, entry = _entry(brief, entry_id)
    if kind == "character" and not entry.permission_confirmed:
        from .production.image_specs import _character_refusal

        raise _character_refusal(entry_id)
    imported = import_reference(
        root,
        picture(root, entry_id, version),
        note=f"Sheet {entry_id} v{version} of this film, chosen by the owner",
        permission_confirmed=True,
    )
    path = imported["path"]
    if kind == "character":
        if path in entry.references:
            return brief
        characters = [
            {**item.model_dump(), "references": [*item.references, path]}
            if item.id == entry_id
            else item.model_dump()
            for item in brief.characters
        ]
        return update_brief(root, {"characters": characters}, owner=True)
    reference_id = f"sheet-{entry_id}-v{version}"
    creative = brief.creative
    if any(item.id == reference_id for item in creative.references):
        return brief
    reference = VisualReference(
        id=reference_id,
        kind="sheet",
        description=f"Plate of the place: {entry.description}",
        path=path,
        permission_confirmed=True,
    )
    scenes = [
        {**item.model_dump(), "reference_ids": [*item.reference_ids, reference_id]}
        if item.id == entry_id
        else item.model_dump()
        for item in creative.scenes
    ]
    return update_brief(
        root,
        {
            "creative": {
                "references": [
                    *[r.model_dump() for r in creative.references],
                    reference.model_dump(),
                ],
                "scenes": scenes,
            }
        },
        owner=True,
    )
