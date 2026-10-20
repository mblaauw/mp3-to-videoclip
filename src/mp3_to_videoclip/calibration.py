"""One tracked, reference-free style control. No audio, fake film or auto-approval."""

from pathlib import Path
from uuid import uuid4

from PIL import Image

from . import budget, profiles
from . import generation as G
from .providers import RunwareClient, runware_api_key
from .storage import digest, inside, project_lock, read_json, write_json

MANIFEST = "work/style-calibration.json"
APPROVAL = "work/style-approval.json"
MAX_USD = "0.10"


def _request(uuid: str) -> dict:
    return {
        "taskType": "imageInference",
        "taskUUID": uuid,
        "model": profiles.DEFAULT_MODEL_AIR,
        "positivePrompt": profiles.ROOFTOP_CONTROL_PROMPT,
        "width": 1376,
        "height": 768,
        "settings": profiles.default_settings(),
        "numberResults": 1,
        "outputType": "URL",
        "outputFormat": "JPG",
        "deliveryMethod": "sync",
        "includeCost": True,
    }


def _workspace(root: Path):
    if (root / "project.json").exists():
        raise ValueError("use a separate style-calibration directory, never an existing film")
    record = read_json(root / MANIFEST)
    if record.get("kind") != "style-calibration":
        raise ValueError("not a style-calibration workspace")


def quote_control(root: Path, reserve=MAX_USD, client=None) -> dict:
    root = root.resolve()
    allowance = G.money(reserve)
    if not 0 < allowance <= G.money(MAX_USD):
        raise ValueError("single control reservation must be positive and at most USD 0.10")
    if root.exists() and any(root.iterdir()) and not (root / MANIFEST).exists():
        raise ValueError("refusing to use a nonempty directory that is not a calibration workspace")
    own = client is None
    client = client or RunwareClient("public-schema-only")
    try:
        schema = client.schema(profiles.DEFAULT_MODEL)
    finally:
        if own:
            client.close()
    if schema["info"].get("x-status") != "live":
        raise ValueError("control model must be confirmed live")
    uuid = str(uuid4())
    request = _request(uuid)
    G.validate_request(schema, request)
    root.mkdir(parents=True, exist_ok=True)
    with project_lock(root):
        if not (root / MANIFEST).exists():
            write_json(
                root / MANIFEST,
                {
                    "kind": "style-calibration",
                    "preset": profiles.STYLE_PRESET_ID,
                    "candidate_only": True,
                    "prompt_hash": digest(profiles.ROOFTOP_CONTROL_PROMPT),
                },
            )
            write_json(root / "work/tasks.json", {})
            write_json(root / "work/assets.json", {})
        _workspace(root)
        if read_json(root / "work/tasks.json"):
            raise ValueError(
                "one control already submitted; recover or inspect it, do not create a retry"
            )
        schema_path = f"work/schemas/{digest(schema)}.json"
        write_json(root / schema_path, schema)
        return G.save_quote(
            root,
            {
                "kind": "style-test",
                "scope": "one-rooftop-control",
                "uuid": uuid,
                "model": profiles.DEFAULT_MODEL,
                "request": request,
                "input_hash": digest(request),
                "schema": schema_path,
                "schema_hash": digest(schema),
                "reserve_total_usd": str(allowance),
                "published_pricing": schema["info"].get("x-pricing"),
                "warning": "One reference-free control, no audio/film approvals. Reservation is not an exact price or provider-enforced cap. Candidate awaits USER visual judgement; no automatic retry.",
            },
        )


def _quote(root: Path, quote_id: str) -> dict:
    _workspace(root)
    q = G.read_quote(root, quote_id)
    if q.get("kind") != "style-test" or q.get("request") != _request(q["uuid"]):
        raise ValueError("control quote no longer matches the exact authorized control request")
    if (
        q.get("input_hash") != digest(q["request"])
        or digest(read_json(inside(root, q["schema"]))) != q["schema_hash"]
    ):
        raise ValueError("control request or schema fingerprint changed")
    G.validate_request(read_json(inside(root, q["schema"])), q["request"])
    return q


def _result(root: Path, uuid: str) -> dict:
    task = read_json(root / "work/tasks.json")[uuid]
    approval_path = root / APPROVAL
    approval = read_json(approval_path) if approval_path.exists() else None
    approved = bool(
        approval
        and approval.get("decision") == "accept"
        and approval.get("note", "").strip()
        and approval.get("binding_hash") == digest(_approval_binding(task))
        and task.get("status") == "ready"
        and G.asset_intact(root, task)
    )
    return {
        "status": task["status"],
        "task": uuid,
        "path": task.get("path"),
        "sha256": task.get("sha256"),
        "reported_cost_usd": task.get("cost_usd"),
        "candidate_only": not approved,
        "user_style_approval": approved,
        "accounted_usd": str(budget.commitment(root)),
        "warning": "User approved this exact image's rendering style only; new subjects/scenes still require inspected proofs. No upload or retry authorized."
        if approved
        else "Inspect this exact image with the user; no fingerprint acceptance or retry is automatic.",
    }


def _validate_task(task: dict, quote: dict):
    if (
        task.get("uuid") != quote["uuid"]
        or task.get("request") != quote["request"]
        or task.get("input_hash") != quote["input_hash"]
        or task.get("shot_id") != "rooftop-control"
        or task.get("version") != 1
    ):
        raise ValueError("recorded control task no longer matches its authorized request")


def _approval_binding(task: dict) -> dict:
    return {key: task.get(key) for key in ("uuid", "path", "sha256", "input_hash", "request")}


def approve_control(root: Path, uuid: str, note: str) -> dict:
    """Record the user's explicit pixel/style judgement, not delegated auto-QC."""
    root = root.resolve()
    if not note.strip():
        raise ValueError("record the user's actual style decision in --note")
    with project_lock(root):
        _workspace(root)
        task = read_json(root / "work/tasks.json").get(uuid)
        if not task or task.get("kind") != "style-test":
            raise ValueError("unknown recorded control task")
        quote = _quote(root, task["quote_id"])
        G.authorization(root, quote)
        _validate_task(task, quote)
        if task.get("status") != "ready" or not G.asset_intact(root, task):
            raise ValueError("style approval requires the intact completed control image")
        record = {
            "decision": "accept",
            "binding": _approval_binding(task),
            "binding_hash": digest(_approval_binding(task)),
            "at": G.now(),
            "note": note,
            "scope": "Rendering style only; not subject, scene, lettering, framing or future uninspected stills. No upload or spending authority.",
        }
        path = root / APPROVAL
        if path.exists():
            previous = read_json(path)
            if previous == record or (
                previous.get("binding_hash") == record["binding_hash"]
                and previous.get("note") == note
            ):
                return _result(root, uuid)
            raise ValueError(
                "style approval already recorded; preserve its original decision rather than overwrite it"
            )
        write_json(path, record)
        return _result(root, uuid)


def _finish(root: Path, uuid: str, result: dict, client):
    if G.finish_image(root, uuid, result, client):
        task = read_json(root / "work/tasks.json")[uuid]
        with Image.open(inside(root, task["path"])) as image:
            if image.size != (1376, 768):
                journal = read_json(root / "work/tasks.json")
                journal[uuid].update(status="invalid", validation_error="control_size_mismatch")
                write_json(root / "work/tasks.json", journal)
                raise ValueError("billed control has wrong dimensions; result retained, no retry")


def run_control(root: Path, quote_id: str, cap: str, note: str, client=None) -> dict:
    root = root.resolve()
    ceiling = G.money(cap)
    if not 0 < ceiling <= G.money(MAX_USD) or not note.strip():
        raise ValueError("record explicit authority for one control with a cap up to USD 0.10")
    with project_lock(root):
        q = _quote(root, quote_id)
        if ceiling < G.money(q["reserve_total_usd"]):
            raise ValueError("cap must cover the quoted control reservation")
        journal = read_json(root / "work/tasks.json")
        if q["uuid"] in journal:
            old = journal[q["uuid"]]
            G.authorization(root, q)
            _validate_task(old, q)
            if old["status"] == "ready" and G.asset_intact(root, old):
                return _result(root, q["uuid"])
            raise ValueError("control already submitted; recover the same UUID, never resubmit")
        if journal:
            raise ValueError("this workspace permits one control only, not automatic retries")
        budget.set_budget(root, str(ceiling), note, max_corrections=0)
        G.authorize(root, q["id"], str(ceiling), note)
        own = client is None
        client = client or RunwareClient(runware_api_key())
        try:
            task = {
                "uuid": q["uuid"],
                "shot_id": "rooftop-control",
                "version": 1,
                "request": q["request"],
                "input_hash": q["input_hash"],
                "reserve_usd": q["reserve_total_usd"],
            }
            G.begin_task(root, q, task, kind="style-test")
            _finish(root, q["uuid"], client.submit(q["request"]), client)
        finally:
            if own:
                client.close()
        if budget.commitment(root) > ceiling:
            raise ValueError(
                "provider cost exceeded local allowance; result/cost retained, no more calls"
            )
        return _result(root, q["uuid"])


def recover_control(root: Path, uuid: str, client=None) -> dict:
    root = root.resolve()
    with project_lock(root):
        _workspace(root)
        task = read_json(root / "work/tasks.json").get(uuid)
        if not task or task.get("kind") != "style-test":
            raise ValueError("unknown recorded control task")
        q = _quote(root, task["quote_id"])
        G.authorization(root, q)
        _validate_task(task, q)
        if task["status"] == "ready" and G.asset_intact(root, task):
            return _result(root, uuid)
        if task["status"] in ("invalid", "resolved"):
            raise ValueError("invalid/reconciled control retained; do not automatically retry it")
        own = client is None
        client = client or RunwareClient(runware_api_key())
        try:
            result = task.get("result") or client.recover(uuid)
            if result:
                _finish(root, uuid, result, client)
        finally:
            if own:
                client.close()
        return _result(root, uuid)
