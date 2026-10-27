"""Explicit quotes/authorizations and a durable pre-submit journal for paid tasks.

Compute-priced estimates are not provider-enforced caps. Reservations control
admission; an unexpectedly expensive result stops subsequent submissions.
"""

import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from . import budget, operations, shotkinds
from .models import Lyrics, Segment
from .production import (
    has_placeholders,
    image_spec,
    load_board,
    load_brief,
    load_project,
    now,
    proof_ids,
    record_asset,
    require_approval,
)
from .profiles import DEFAULT_MODEL as DEFAULT_MODEL
from .profiles import LEGACY_MODEL
from .providers import MAX_TRANSCRIBE_BYTES, RunwareClient, runware_api_key, transcribe
from .storage import digest, file_hash, inside, read_json, state_lock, state_mutation, write_json

WHISPER_RATE = Decimal("0.006") / Decimal(60)


def money(value) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("money must be a finite nonnegative USD amount")
    try:
        result = Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError("invalid USD amount") from e
    if not result.is_finite() or result < 0:
        raise ValueError("money must be a finite nonnegative USD amount")
    return result


def _validate_before_spend(root: Path, ids: list[str]):
    """Run local workflow-v2 preflight before any provider work."""
    from .preflight import validate_before_spend

    validate_before_spend(root, list(ids))


def save_quote(root: Path, quote: dict) -> dict:
    quote_id = str(uuid4())
    quote = {"id": quote_id, "created_at": now(), **quote}
    write_json(root / f"work/quotes/{quote_id}.json", quote)
    return quote


def read_quote(root: Path, quote_id: str) -> dict:
    quote = read_json(inside(root, f"work/quotes/{quote_id}.json"))
    if not isinstance(quote, dict) or quote.get("id") != quote_id:
        raise ValueError("quote identity changed")
    return quote


def validate_request(schema: dict, request: dict):
    contract = {
        **schema["components"]["schemas"]["RequestBody"],
        "components": schema["components"],
    }
    try:
        Draft202012Validator(contract).validate([request])
    except ValidationError as e:
        raise ValueError("request rejected by model schema; revise the quote") from e


def image_controls(spec: dict, model: str) -> dict:
    """Resolve stored controls; a foreign model override never inherits Google settings."""
    config = spec.get("generation", {})
    result = {}
    if config.get("model") in (None, model) and config.get("settings"):
        result["settings"] = config["settings"]
    if config.get("seed") is not None:
        result["seed"] = config["seed"]
    return result


def effective_image_spec(spec: dict, model: str) -> dict:
    """New-profile alternatives carry their actual model/controls, not canonical currency.

    Legacy specs retain exact historical hashes. To use a model alternative as a
    final selection, persist its model/controls in the production and reapprove.
    """
    if "generation" not in spec:
        return spec
    controls = image_controls(spec, model)
    return {
        **spec,
        "generation": {
            "model": model,
            "settings": controls.get("settings", {}),
            "seed": controls.get("seed"),
        },
    }


def quote_images(
    root: Path,
    scope: str,
    reserve: str,
    model=None,
    ids: list[str] | None = None,
    regenerate=False,
    client=None,
) -> dict:
    require_approval(root, "storyboard")
    board = load_board(root)
    brief = load_brief(root)
    model = model or load_project(root).image_model or LEGACY_MODEL
    if scope not in ("proof", "stills"):
        raise ValueError("image scope must be proof or stills")
    allowed = (
        proof_ids(board, brief)
        if scope == "proof"
        else [s.id for s in board.shots if shotkinds.is_paid(s)]
    )
    if scope == "stills":
        # Guided creative full sets gate on the style check; recorded v2 projects
        # keep the mandatory watched preview. Legacy stills use the proof gate.
        from . import flow

        require_approval(
            root,
            "preview"
            if brief.creative is not None and flow.settings(root)["preview_gate"]
            else "proof",
        )
    chosen = allowed if ids is None else ids
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= set(allowed):
        raise ValueError("unknown, duplicate or out-of-scope shot IDs")
    allowance = money(reserve)
    if allowance == 0:
        raise ValueError("reserve a positive per-shot allowance")
    # Both guards run before the provider schema GET or any submit: legacy projects
    # with no preflight module and no budget keep their old behaviour.
    spend_ids = [shot.id for shot in board.shots if shot.id in chosen and shotkinds.is_paid(shot)]
    _validate_before_spend(root, spend_ids)
    budget.require_correction_cycles(root, spend_ids)
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
    assets = read_json(root / "work/assets.json")
    journal = read_json(root / "work/tasks.json")
    tasks = []
    for shot in board.shots:
        if shot.id not in chosen or not shotkinds.is_paid(shot):
            continue
        if has_placeholders(shot):
            raise ValueError("finish the storyboard's creative placeholders first")
        spec = effective_image_spec(image_spec(root, shot), model)
        input_hash = digest(spec)
        versions = assets.get(shot.id, {}).get("versions", [])
        if not regenerate and any(
            v["input_hash"] == input_hash
            and inside(root, v["path"]).is_file()
            and file_hash(inside(root, v["path"])) == v["sha256"]
            for v in versions
        ):
            continue
        if any(
            t.get("shot_id") == shot.id and t["status"] in ("submitted", "result")
            for t in journal.values()
        ):
            raise ValueError(f"shot {shot.id} has an unresolved task; recover it first")
        if not regenerate and any(
            t.get("shot_id") == shot.id
            and t.get("input_hash") == input_hash
            and t["status"] == "ready"
            and not asset_intact(root, t)
            for t in journal.values()
        ):
            raise ValueError(
                f"shot {shot.id} has a lost/changed asset; recover it instead of rebilling"
            )
        version = (
            max(
                [v["version"] for v in versions]
                + [t["version"] for t in journal.values() if t.get("shot_id") == shot.id]
                + [0]
            )
            + 1
        )
        task_uuid = str(uuid4())
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
            **image_controls(spec, model),
        }
        validation_request = dict(request)
        if spec["references"]:
            validation_request["inputs"] = {
                "referenceImages": [str(uuid4()) for _ in spec["references"]]
            }
        validate_request(schema, validation_request)
        tasks.append(
            {
                "uuid": task_uuid,
                "shot_id": shot.id,
                "version": version,
                "input_hash": input_hash,
                "references": spec["references"],
                "request": request,
                "reserve_usd": str(allowance),
                "retry_cycle": budget.correction_cycle(root, shot.id),
            }
        )
    if not tasks:
        raise ValueError(
            "all requested shots already have current images; select/review them or explicitly --regenerate"
        )
    return save_quote(
        root,
        {
            "kind": "images",
            "scope": scope,
            "model": model,
            "schema": schema_path,
            "schema_hash": digest(schema),
            "tasks": tasks,
            "reserve_total_usd": str(allowance * len(tasks)),
            "published_pricing": info.get("x-pricing"),
            "warning": "Published examples are not an exact quote. Actual compute cost can exceed reservations; subsequent calls will stop.",
        },
    )


def quote_transcription(
    root: Path,
    language: str | None = None,
    *,
    provider="runware",
    reserve="0.05",
    model="google-gemini-3-1-flash-lite",
    max_tokens=8192,
    client=None,
) -> dict:
    if load_project(root).music_mode == "instrumental":
        raise ValueError(
            "instrumental projects have no lyrics to transcribe; no upload or charge attempted"
        )
    if provider == "runware":
        from .transcription import quote_runware

        return quote_runware(root, language, reserve, model, max_tokens, client)
    if provider != "openai":
        raise ValueError("unknown transcription provider")
    project = load_project(root)
    if inside(root, project.source).stat().st_size > MAX_TRANSCRIBE_BYTES:
        raise ValueError(
            "MP3 exceeds hosted transcription's 25 MB limit; no upload/charge attempted"
        )
    estimated = money(project.duration) * WHISPER_RATE
    return save_quote(
        root,
        {
            "kind": "transcription",
            "model": "whisper-1",
            "language": language,
            "source_hash": project.source_sha256,
            "uuid": str(uuid4()),
            "estimate_usd": str(estimated),
            "reserve_total_usd": str(max(Decimal("0.01"), estimated * Decimal("1.25"))),
            "warning": "Uploads the full MP3 to OpenAI. Rate $0.006/min; sung text/timestamps require review. Configure OPENAI_API_KEY first.",
        },
    )


def quote_uploads_required(quote: dict) -> bool:
    """Quoted source/reference transfer requires an explicit human attestation."""
    return quote.get("kind") in {"transcription", "music-analysis"} or any(
        task.get("references") for task in quote.get("tasks", [])
    )


@state_mutation
def authorize(
    root: Path,
    quote_id: str,
    cap: str,
    note: str,
    *,
    expected_quote_hash: str | None = None,
    via: str | None = None,
    uploads_confirmed: bool | None = None,
    review_confirmed: bool | None = None,
):
    quote = read_quote(root, quote_id)
    quote_hash = digest(quote)
    if expected_quote_hash is not None and expected_quote_hash != quote_hash:
        raise ValueError("quote changed during review; inspect the current quote again")
    ceiling = money(cap)
    if via == "studio":
        if review_confirmed is not True or ceiling != money(quote["reserve_total_usd"]):
            raise ValueError(
                "Studio authority requires confirmed scope and the exact quoted amount"
            )
        if quote_uploads_required(quote) and uploads_confirmed is not True:
            raise ValueError("Studio authority requires explicit quoted data-transfer consent")
    if ceiling < money(quote["reserve_total_usd"]) or not note.strip():
        raise ValueError("cap must cover reserved scope; record user authorization in --note")
    # Cumulative production admission: all kinds and all already-submitted tasks.
    # Unsent authorized quotes are not reserved here; begin_task takes the actual
    # reservation immediately before each chargeable request.
    budget.check_capacity(root, quote["reserve_total_usd"], context="authorization")
    budget.require_reconciled(root)
    path = root / "work/authorizations.json"
    values = read_json(path) if path.exists() else {}
    values[quote_id] = {
        "quote_hash": quote_hash,
        "cap_usd": str(ceiling),
        "at": now(),
        "note": note,
    }
    if via is not None:
        values[quote_id]["via"] = via
    if uploads_confirmed is not None:
        values[quote_id]["uploads_confirmed"] = bool(uploads_confirmed)
    if review_confirmed is not None:
        values[quote_id]["review_confirmed"] = bool(review_confirmed)
    write_json(path, values)


def authorization(root: Path, quote: dict) -> dict:
    path = root / "work/authorizations.json"
    value = read_json(path).get(quote["id"]) if path.exists() else None
    if not value or value["quote_hash"] != digest(quote):
        raise ValueError("quote needs explicit spending authorization")
    if value.get("via") == "studio" and (
        value.get("review_confirmed") is not True
        or (quote_uploads_required(quote) and value.get("uploads_confirmed") is not True)
        or money(value["cap_usd"]) != money(quote["reserve_total_usd"])
    ):
        raise ValueError("Studio authorization has incomplete scope or data-transfer consent")
    return value


def accounted(tasks: dict, quote_id: str) -> Decimal:
    return sum(
        (
            money(t.get("cost_usd") if t.get("cost_usd") is not None else t["reserve_usd"])
            for t in tasks.values()
            if t["quote_id"] == quote_id
        ),
        Decimal(0),
    )


@state_mutation
def begin_task(root: Path, quote: dict, task: dict, *, kind=None, admitted=()):
    auth = authorization(root, quote)
    journal = read_json(root / "work/tasks.json")
    if task["uuid"] in journal:
        raise ValueError("task already submitted; recover, do not resubmit")
    if accounted(journal, quote["id"]) + money(task["reserve_usd"]) > money(auth["cap_usd"]):
        raise ValueError("spending allowance exhausted; no task submitted")
    budget.check_capacity(root, task["reserve_usd"], context="submission")
    budget.require_reconciled(root, admitted)
    if (kind or quote["kind"]) == "images":
        # Editors can change state between network calls. Revalidate the paid
        # task while admission/reservation are serialized, not only at job start.
        shot = next((s for s in load_board(root).shots if s.id == task["shot_id"]), None)
        if (
            shot is None
            or digest(effective_image_spec(image_spec(root, shot), quote["model"]))
            != task["input_hash"]
        ):
            raise ValueError(
                "shot/reference/brief changed since quote; estimate and authorize again"
            )
        require_approval(root, "storyboard")
        board = load_board(root)
        brief = load_brief(root)
        if quote["scope"] == "proof":
            if task["shot_id"] not in proof_ids(board, brief):
                raise ValueError("proof selection changed; requote before spending")
        else:
            from . import flow

            require_approval(
                root,
                "preview"
                if brief.creative is not None and flow.settings(root)["preview_gate"]
                else "proof",
            )
        budget.check_correction_cycle(root, task["shot_id"], task.get("retry_cycle"))
        if any(
            entry.get("kind") == "images"
            and entry.get("shot_id") == task["shot_id"]
            and (
                entry.get("version") == task["version"]
                or entry.get("status") in ("submitted", "result")
            )
            for entry in journal.values()
        ):
            raise ValueError("a conflicting task/version was submitted; recover or requote")
    if (kind or quote["kind"]) == "transcription" and quote.get("provider", "openai") == "openai":
        if (root / "work/lyrics.json").exists():
            raise ValueError("lyrics already exist; preserve them rather than overwrite/rebill")
    value = {
        **task,
        "kind": kind or quote["kind"],
        "quote_id": quote["id"],
        "status": "submitted",
        "submitted_at": now(),
        "cost_usd": None,
    }
    journal[task["uuid"]] = value
    write_json(root / "work/tasks.json", journal)  # Persist BEFORE the chargeable request.


def asset_intact(root: Path, task: dict) -> bool:
    if not task.get("path") or not task.get("sha256"):
        return False
    path = inside(root, task["path"])
    return path.is_file() and file_hash(path) == task["sha256"]


def finish_image(root: Path, task_uuid: str, result: dict, client: RunwareClient):
    task = read_json(root / "work/tasks.json")[task_uuid]
    if "imageURL" not in result:
        return False
    if result.get("taskUUID") != task_uuid:
        raise ValueError("provider returned another task")
    cost = str(money(result["cost"]))
    if task.get("cost_usd") is not None and money(task["cost_usd"]) != money(cost):
        raise ValueError("provider task cost changed; reconcile manually")
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
    relative = f"assets/{task['shot_id']}/v{task['version']:03d}-{task_uuid}.jpg"
    path = inside(root, relative)
    expected_hash = task.get("sha256")
    if path.exists() and expected_hash and file_hash(path) != expected_hash:
        # Preserve user-modified/corrupt bytes before restoring the paid original.
        quarantine = root / f"work/quarantine/{task_uuid}-{file_hash(path)}.jpg"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        if not quarantine.exists():
            os.link(path, quarantine)
        path.unlink()
    if not path.exists():
        client.download(result["imageURL"], path)
    if expected_hash and file_hash(path) != expected_hash:
        raise ValueError(
            "recovered provider asset differs from its recorded original; inspect manually"
        )
    # A previously saved asset may be reused after a crash between download/index writes.
    from PIL import Image

    with Image.open(path) as image:
        image.verify()
    with state_lock(root):
        journal = read_json(root / "work/tasks.json")
        current = journal[task_uuid]
        if current.get("status") == "resolved":
            raise ValueError("task was manually reconciled during download; inspect the result")
        record_asset(root, task["shot_id"], task["version"], path, task["input_hash"], task_uuid)
        current.update(status="ready", path=relative, sha256=file_hash(path), completed_at=now())
        write_json(root / "work/tasks.json", journal)
    return True


def _submit_only(client, request: dict) -> dict:
    """The only thing a worker thread is allowed to do."""
    return client.submit(request)


def _check_correction_cycles(root: Path, quote: dict):
    """Recheck each task's recorded retry cycle right before any submission."""
    journal = read_json(root / "work/tasks.json")
    for task in quote["tasks"]:
        if task["uuid"] in journal:
            continue  # Existing UUIDs are recovered/skipped, never resubmitted.
        budget.check_correction_cycle(root, task["shot_id"], task.get("retry_cycle"))


def _check_dispatch_room(root: Path, quote: dict, auth: dict, task: dict):
    """Cumulative quote and production budgets before admitting one more task."""
    journal = read_json(root / "work/tasks.json")
    if accounted(journal, quote["id"]) + money(task["reserve_usd"]) > money(auth["cap_usd"]):
        raise ValueError("spending allowance exhausted; no task submitted")
    budget.check_capacity(root, task["reserve_usd"], context="submission")


def _check_stop_conditions(root: Path, quote: dict, auth: dict):
    """Stop further admission once actual or unknown cost outruns either budget."""
    if accounted(read_json(root / "work/tasks.json"), quote["id"]) > money(auth["cap_usd"]):
        raise ValueError("actual cost exceeded allowance; stopping further submissions")
    record = budget.read_budget(root)
    if record is not None and budget.commitment(root) > budget.money(record["cap_usd"]):
        raise ValueError("actual cost exceeded the production budget; stopping further submissions")


def _execute_quote(root: Path, quote: dict, auth: dict, schema: dict, client, concurrency: int):
    """Coordinator: journal each task before submitting; workers only submit.

    Only this thread writes the journal/asset index. Admission stops on the first
    pending result, provider error or overrun; already-admitted workers are drained
    without blind retries and every completed priced result is checkpointed.

    Progress is reported to the active operation receipt (completed tasks out of
    the quote's task count); a receipt write never affects admission or retries.
    """
    journal = read_json(root / "work/tasks.json")
    prepared = []
    for task in quote["tasks"]:
        existing = journal.get(task["uuid"])
        if existing:
            if existing["status"] == "ready":
                if not asset_intact(root, existing):
                    raise ValueError(f"task {task['uuid']} has a lost/changed asset; recover it")
                continue
            raise ValueError(f"task {task['uuid']} needs recover; no paid resubmission")
        request = dict(task["request"])
        if task["references"]:
            request["inputs"] = {
                "referenceImages": [
                    client.reference_image(inside(root, ref["path"])) for ref in task["references"]
                ]
            }
        validate_request(schema, request)
        prepared.append((task, request))
    operations.phase(
        "submitting-images",
        note=f"{len(prepared)} task(s) queued",
        total=len(quote["tasks"]),
        unit="images",
        done=0,
    )
    if not prepared:
        return
    queue = list(prepared)
    futures = {}
    failure = None

    def done_count() -> int:
        return sum(
            1
            for entry in read_json(root / "work/tasks.json").values()
            if entry.get("status") == "ready"
        )

    def admit():
        nonlocal failure
        while queue and len(futures) < concurrency and failure is None:
            if operations.stop_requested():
                # The user cancelled: admit nothing new. Already-sent tasks drain
                # and are journaled as usual; the rest stay unspent in the quote.
                failure = ValueError(
                    f"stopped by the user; {len(queue)} still(s) were not sent and cost nothing"
                )
                return
            task, request = queue[0]
            try:
                _check_dispatch_room(root, quote, auth, task)
                begin_task(root, quote, task, admitted=[t["uuid"] for t in futures.values()])
            except Exception as exc:
                failure = failure or exc
                return
            queue.pop(0)
            futures[executor.submit(_submit_only, client, request)] = task

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        admit()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                task = futures.pop(future)
                try:
                    result = future.result()
                except Exception as exc:  # provider/network error: never retry blindly
                    failure = failure or exc
                    continue
                try:
                    finished = finish_image(root, task["uuid"], result, client)
                except Exception as exc:  # billed cost is already journaled
                    failure = failure or exc
                    continue
                if not finished:
                    failure = failure or ValueError(
                        f"task {task['uuid']} pending; recover before continuing"
                    )
                    continue
                operations.tick(
                    phase="receiving-images",
                    done=done_count(),
                    total=len(quote["tasks"]),
                    unit="images",
                )
                if failure is None:
                    try:
                        _check_stop_conditions(root, quote, auth)
                    except Exception as exc:
                        failure = exc
            admit()
    if failure is not None:
        raise failure


def generate(root: Path, quote_id: str, client=None, *, concurrency: int = 1):
    """Execute an authorized image quote with durable, bounded concurrency.

    The caller owns the project lock (the CLI wraps every command in
    :func:`storage.project_lock`); ``generate`` never takes a second lock. All
    journal and asset-index writes happen on this calling (coordinator) thread;
    worker threads only call ``client.submit``. At most ``concurrency`` tasks are
    admitted before any result is processed, so the whole quote is never reserved
    up front and every admitted UUID stays recoverable.
    """
    if (
        isinstance(concurrency, bool)
        or not isinstance(concurrency, int)
        or not 1 <= concurrency <= 3
    ):
        raise ValueError("concurrency must be an integer between 1 and 3")
    quote = read_quote(root, quote_id)
    if quote["kind"] != "images":
        raise ValueError("use transcribe for an audio quote")
    auth = authorization(root, quote)
    require_approval(root, "storyboard")
    board = load_board(root)
    if quote["scope"] not in ("proof", "stills"):
        raise ValueError("invalid quoted image scope")
    allowed = (
        set(proof_ids(board, load_brief(root)))
        if quote["scope"] == "proof"
        else {s.id for s in board.shots if s.asset_shot_id is None}
    )
    task_ids = [t["shot_id"] for t in quote["tasks"]]
    task_uuids = [t["uuid"] for t in quote["tasks"]]
    if (
        not task_ids
        or len(set(task_ids)) != len(task_ids)
        or len(set(task_uuids)) != len(task_uuids)
        or not set(task_ids) <= allowed
    ):
        raise ValueError(
            "quote tasks are duplicate or outside the current approved image scope; requote"
        )
    if quote["scope"] == "stills":
        # Keep admission parity with quoting: guided creative full sets gate on the
        # style check, recorded v2 projects on the mandatory watched preview.
        from . import flow

        require_approval(
            root,
            "preview"
            if load_brief(root).creative is not None and flow.settings(root)["preview_gate"]
            else "proof",
        )
    shots = {s.id: s for s in board.shots}
    schema = read_json(inside(root, quote["schema"]))
    if digest(schema) != quote["schema_hash"]:
        raise ValueError("quoted model schema changed")
    # Validate the WHOLE approved scope before any paid calls.
    journal = read_json(root / "work/tasks.json")
    assets = read_json(root / "work/assets.json")
    for task in quote["tasks"]:
        shot = shots.get(task["shot_id"])
        if (
            shot is None
            or digest(effective_image_spec(image_spec(root, shot), quote["model"]))
            != task["input_hash"]
        ):
            raise ValueError(
                "shot/reference/brief changed since quote; estimate and authorize again"
            )
        spec = effective_image_spec(image_spec(root, shot), quote["model"])
        request = task["request"]
        controls = image_controls(spec, quote["model"])
        if (
            request.get("taskUUID") != task["uuid"]
            or request.get("positivePrompt") != spec["positivePrompt"]
            or [request.get("width"), request.get("height")] != spec["size"]
            or request.get("model") != schema["info"]["x-air-id"]
            or task["references"] != spec["references"]
            or any(request.get(key) != controls.get(key) for key in ("settings", "seed"))
        ):
            raise ValueError("quote request no longer matches its approved shot specification")
        if any(
            t.get("shot_id") == shot.id
            and t["uuid"] != task["uuid"]
            and (t["version"] == task["version"] or (t["status"] in ("submitted", "result")))
            for t in journal.values()
            if t["kind"] == "images"
        ):
            raise ValueError(
                "a conflicting task/version was submitted after this quote; recover or requote"
            )
        if any(
            v["version"] == task["version"] and v["task_id"] != task["uuid"]
            for v in assets.get(shot.id, {}).get("versions", [])
        ):
            raise ValueError("quoted image version was already filled; requote before spending")
    _validate_before_spend(root, task_ids)
    _check_correction_cycles(root, quote)
    if any(t["uuid"] not in journal for t in quote["tasks"]):
        budget.require_reconciled(root)
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        _execute_quote(root, quote, auth, schema, client, concurrency)
    finally:
        if own:
            client.close()


def recover(root: Path, task_uuid: str, client=None):
    task = read_json(root / "work/tasks.json").get(task_uuid)
    if task and task.get("kind") == "music-analysis":
        from .music_analysis import recover_music

        return recover_music(root, task_uuid, client)
    if (
        task
        and task.get("provider") == "runware"
        and task["kind"] in ("audio-upload", "transcription")
    ):
        from .transcription import recover_runware

        return recover_runware(root, task_uuid, client)
    if not task or task["kind"] != "images":
        raise ValueError("unknown image task; transcription has no automatic recovery endpoint")
    if task["status"] == "ready" and asset_intact(root, task):
        # Ready journal bytes can outlive an interrupted asset-index publication.
        # This is idempotent and neither selects an alternative nor reviews it.
        record_asset(
            root,
            task["shot_id"],
            task["version"],
            inside(root, task["path"]),
            task["input_hash"],
            task_uuid,
        )
        return True
    if task["status"] == "resolved":
        raise ValueError("task was manually reconciled; use a newly authorized quote if needed")
    own = client is None
    client = client or RunwareClient(runware_api_key())
    try:
        result = task.get("result") or client.recover(task_uuid)
        return finish_image(root, task_uuid, result, client) if result else False
    finally:
        if own:
            client.close()


@state_mutation
def update_task(root: Path, task_uuid: str, **patch) -> dict:
    """Checkpoint fields into the latest journal without losing another result."""
    path = root / "work/tasks.json"
    journal = read_json(path)
    journal[task_uuid].update(patch)
    write_json(path, journal)
    return journal[task_uuid]


def transcribe_quote(root: Path, quote_id: str, transcriber=transcribe, *, client=None):
    if load_project(root).music_mode == "instrumental":
        raise ValueError(
            "instrumental projects have no lyrics to transcribe; no upload or charge attempted"
        )
    quote = read_quote(root, quote_id)
    if quote["kind"] != "transcription":
        raise ValueError("not a transcription quote")
    if quote.get("provider") == "runware":
        from .transcription import transcribe_runware

        return transcribe_runware(root, quote_id, client)
    if quote.get("provider", "openai") != "openai":
        raise ValueError("unknown transcription provider")
    authorization(root, quote)
    require_approval(root, "analysis")
    project = load_project(root)
    if inside(root, project.source).stat().st_size > MAX_TRANSCRIBE_BYTES:
        raise ValueError(
            "MP3 exceeds hosted transcription's 25 MB limit; no upload/charge attempted"
        )
    if project.source_sha256 != quote["source_hash"]:
        raise ValueError("source changed since quote")
    if (root / "work/lyrics.json").exists():
        raise ValueError("lyrics already exist; preserve them rather than overwrite/rebill")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is not configured; no upload made")
    journal = read_json(root / "work/tasks.json")
    if any(
        t["kind"] == "transcription"
        and t["status"] not in ("resolved", "invalid", "conflict", "stale")
        for t in journal.values()
    ):
        raise ValueError(
            "a transcription was already submitted; reconcile its result before any retry"
        )
    task = {"uuid": quote["uuid"], "reserve_usd": quote["reserve_total_usd"]}
    begin_task(root, quote, task)
    raw = transcriber(os.environ["OPENAI_API_KEY"], inside(root, project.source), quote["language"])
    finish_openai_transcript(root, quote, project, raw)
    # The OpenAI path returns nothing; the CLI derives its payload from work/lyrics.json.
    return None


@state_mutation
def finish_openai_transcript(root: Path, quote: dict, project, raw: dict):
    """Keep billed evidence before validation; never overwrite a concurrent import."""
    write_json(root / "work/transcription-raw.json", raw)
    update_task(
        root,
        quote["uuid"],
        status="result",
        cost_usd=str(money(raw.get("duration", project.duration)) * WHISPER_RATE),
        cost_basis="duration-rate estimate, not provider invoice",
    )
    try:
        lyrics = _openai_lyrics(raw)
    except (ValueError, TypeError, KeyError) as exc:
        update_task(root, quote["uuid"], status="invalid", validation_error="invalid_transcript")
        raise ValueError("billed transcription is invalid; raw evidence and cost retained") from exc
    current = load_project(root)
    if (current.source_sha256, current.duration) != (project.source_sha256, project.duration):
        update_task(root, quote["uuid"], status="stale", validation_error="different_source")
        raise ValueError("source changed during transcription; raw billed evidence retained")
    if (root / "work/lyrics.json").exists():
        update_task(
            root, quote["uuid"], status="conflict", validation_error="lyrics_conflict_preserved"
        )
        raise ValueError("lyrics were imported during transcription; existing lyrics preserved")
    write_json(root / "work/lyrics.json", lyrics.model_dump())
    update_task(root, quote["uuid"], status="ready", completed_at=now())


def _openai_lyrics(raw: dict) -> Lyrics:
    segments = []
    for segment in raw.get("segments", []):
        flags = ["unreviewed sung text"]
        if segment.get("avg_logprob", 0) < -1:
            flags.append("low transcription confidence")
        if segment.get("compression_ratio", 0) > 2.4:
            flags.append("possible repetitive hallucination")
        if segment.get("no_speech_prob", 0) > 0.6:
            flags.append("possible instrumental/silence")
        segments.append(
            Segment(start=segment["start"], end=segment["end"], text=segment["text"], flags=flags)
        )
    return Lyrics(
        provider="OpenAI",
        model="whisper-1",
        language=raw.get("language"),
        segments=segments,
        words=raw.get("words", []),
    )


@state_mutation
def resolve_task(root: Path, task_uuid: str, cost: str, note: str):
    """Explicit user reconciliation, not a provider retry or a presumed refund."""
    journal = read_json(root / "work/tasks.json")
    task = journal.get(task_uuid)
    if not task or task["status"] != "submitted" or task.get("cost_usd") is not None:
        raise ValueError("only an unresolved, unpriced submission can be manually reconciled")
    if not note.strip():
        raise ValueError("record the user's provider-status/billing evidence in --note")
    amount = money(cost)
    task.update(
        status="resolved",
        cost_usd=str(amount),
        cost_basis="user reconciled",
        reconciliation_note=note,
        reconciled_at=now(),
    )
    write_json(root / "work/tasks.json", journal)


def costs(root: Path) -> dict:
    journal = read_json(root / "work/tasks.json")
    spent = sum(
        (money(t["cost_usd"]) for t in journal.values() if t.get("cost_usd") is not None),
        Decimal(0),
    )
    # A task with neither a cost nor a reservation is *unpriced*, exactly as
    # budget.summary models it; it is listed rather than raising KeyError.
    unresolved = sum(
        (
            money(t["reserve_usd"])
            for t in journal.values()
            if t.get("cost_usd") is None and t.get("reserve_usd") is not None
        ),
        Decimal(0),
    )
    unpriced = sorted(
        key
        for key, t in journal.items()
        if t.get("cost_usd") is None and t.get("reserve_usd") is None
    )
    return {
        "currency": "USD",
        "reported_or_calculated_usd": str(spent),
        "unresolved_reservations_usd": str(unresolved),
        "unpriced_tasks": unpriced,
        "unpriced_note": (
            "Tasks with neither a reported cost nor a reservation are listed, "
            "not counted as zero; reconcile them before further spending."
        ),
        "tasks": [
            {
                k: t[k]
                for k in ("uuid", "kind", "status", "cost_usd", "reserve_usd", "cost_basis")
                if k in t
            }
            for t in journal.values()
        ],
        "budget": budget.summary(root),
        "warning": "Runware inference costs are provider reported; mediaStorage reports no cost so its reservation remains. Legacy OpenAI costs are duration-rate estimates, not invoices. Reservations are admission controls, not provider-enforced hard caps.",
    }
