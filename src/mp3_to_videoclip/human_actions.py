"""Typed local human decisions; no provider calls or generic command dispatch.

HTTP capability checks live in serve. These operations additionally enforce exact
review identities under the same project lock used by the CLI. Same-OS process
isolation is explicitly not a claim of this workflow.
"""

import re
from pathlib import Path
from uuid import UUID

from . import budget
from . import generation as G
from . import production as P
from .storage import digest, project_lock, read_json


class ActionError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def stage_name(stage):
    if stage not in P.UPSTREAM:
        raise ActionError("unknown approval stage", 404)
    return stage


def quote_id(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ActionError("invalid quote identity", 404) from exc
    return value


def _body(body, allowed, hash_key):
    if not isinstance(body, dict) or set(body) - allowed:
        raise ActionError("unexpected decision fields")
    if body.get("confirmed") is not True:
        raise ActionError("explicit review confirmation is required")
    note = body.get("note")
    if not isinstance(note, str) or not 1 <= len(note.strip()) <= 2000:
        raise ActionError("record a decision note (1–2000 characters)")
    if not isinstance(body.get(hash_key), str) or not re.fullmatch(r"[0-9a-f]{64}", body[hash_key]):
        raise ActionError("the reviewed content hash is required")
    return note.strip()


def review_stage(root: Path, stage: str):
    stage_name(stage)
    if stage == "lyrics" and P.load_project(root).music_mode == "instrumental":
        raise ActionError("instrumental productions have no lyrics approval")
    with project_lock(root):
        current = P.stage_hash(root, stage)
        if stage in P.STAGE_FILES:
            artifact = read_json(root / P.STAGE_FILES[stage])
        else:
            from .appdata import stills

            artifact = stills(root)
    return {"stage": stage, "expected_hash": current, "artifact": artifact}


def approve_stage(root: Path, stage: str, body: dict):
    stage_name(stage)
    note = _body(
        body,
        {
            "note",
            "expected_hash",
            "confirmed",
            "acknowledge_uncertain",
            "inspected",
            "preview_watched",
        },
        "expected_hash",
    )
    for flag, applicable in (
        ("inspected", "graphics"),
        ("acknowledge_uncertain", "lyrics"),
        ("preview_watched", "preview"),
    ):
        if flag in body and (type(body[flag]) is not bool or stage != applicable):
            raise ActionError(f"{flag} is only valid for {applicable}")
    if stage == "preview" and body.get("preview_watched") is not True:
        raise ActionError("confirm continuous preview playback with the actual music")
    with project_lock(root):
        saved = read_json(root / "work/approvals.json")
        if not isinstance(saved, dict) or any(
            not isinstance(item, dict) for item in saved.values()
        ):
            raise ActionError("saved approval records are invalid; inspect them locally")
        if P.stage_hash(root, stage) != body["expected_hash"]:
            raise ActionError("Stage changed. Inspect the current artifacts before deciding.", 409)
        P.approve(
            root,
            stage,
            note,
            body.get("acknowledge_uncertain", False),
            inspected=body.get("inspected", False),
            expected_hash=body["expected_hash"],
            via="studio",
            preview_watched=body.get("preview_watched", False),
            review_confirmed=True,
        )
        record = read_json(root / "work/approvals.json")[stage]
    return {"approved": stage, "record": record, "generated": False}


def _quote(root, identity):
    quote_id(identity)
    q = G.read_quote(root, identity)
    if q.get("kind") not in {"images", "transcription", "music-analysis"}:
        raise ActionError("this quote kind is outside Studio authorization scope")
    if not isinstance(q.get("model"), str) or not q["model"].strip():
        raise ActionError("the quoted model must be explicit")
    provider = q.get("provider", "openai" if q["kind"] == "transcription" else "runware")
    allowed = {"openai", "runware"} if q["kind"] == "transcription" else {"runware"}
    if provider not in allowed:
        raise ActionError("the quote provider does not match its executor")
    amount = budget.money(q["reserve_total_usd"])
    if amount <= 0:
        raise ActionError("quote reservation must be positive")
    tasks = q.get("tasks", [])
    if not isinstance(tasks, list) or any(
        not isinstance(task, dict)
        or not isinstance(task.get("request", {}), dict)
        or not isinstance(task.get("references", []), list)
        or any(not isinstance(ref, dict) for ref in task.get("references", []))
        for task in tasks
    ):
        raise ActionError("quote tasks are invalid")
    if not isinstance(q.get("request", {}), dict):
        raise ActionError("quote inference request is invalid")
    return q


def uploads_required(q):
    return G.quote_uploads_required(q)


def _authorizations(root):
    path = root / "work/authorizations.json"
    values = read_json(path) if path.exists() else {}
    if not isinstance(values, dict) or any(not isinstance(item, dict) for item in values.values()):
        raise ActionError("saved authorization records are invalid; inspect them locally")
    return values


def review_quote(root: Path, identity: str):
    q = _quote(root, identity)
    safe_keys = (
        "id",
        "kind",
        "scope",
        "created_at",
        "model",
        "model_slug",
        "provider",
        "language",
        "source_hash",
        "duration",
        "schema_hash",
        "reserve_total_usd",
        "upload_reserve_usd",
        "inference_reserve_usd",
        "reuse_upload",
        "published_pricing",
        "warning",
    )
    result = {key: q[key] for key in safe_keys if key in q}
    # The legacy transcription executor defaults to OpenAI when provider is absent.
    result["provider"] = q.get("provider", "openai" if q["kind"] == "transcription" else "runware")
    settings = (
        "model",
        "positivePrompt",
        "negativePrompt",
        "width",
        "height",
        "seed",
        "steps",
        "CFGScale",
        "outputFormat",
        "numberResults",
        "settings",
    )
    result["tasks"] = [
        {
            "shot_id": task.get("shot_id"),
            "version": task.get("version"),
            "input_hash": task.get("input_hash"),
            "reserve_usd": task.get("reserve_usd"),
            "reference_count": len(task.get("references", [])),
            "references": [
                {k: ref[k] for k in ("path", "sha256", "role", "id") if k in ref}
                for ref in task.get("references", [])
            ],
            "settings": {
                k: task.get("request", {})[k] for k in settings if k in task.get("request", {})
            },
        }
        for task in q.get("tasks", [])
    ]
    result["inference_settings"] = {
        key: q.get("request", {})[key]
        for key in (*settings, "messages", "jsonSchema")
        if key in q.get("request", {})
    }
    values = _authorizations(root)
    auth = values.get(identity)
    expected = digest(q)
    state = "missing"
    if auth:
        state = "stale"
        if auth.get("quote_hash") == expected:
            state = (
                "current"
                if budget.money(auth.get("cap_usd")) == budget.money(q["reserve_total_usd"])
                else "different authority"
            )
            if state == "current":
                try:
                    G.authorization(root, q)
                except ValueError:
                    state = "incomplete consent"
    result.update(
        expected_quote_hash=expected,
        uploads_required=uploads_required(q),
        authorization_state=state,
        authorization={
            k: auth.get(k)
            for k in ("at", "note", "cap_usd", "via", "uploads_confirmed", "review_confirmed")
        }
        if auth
        else None,
        budget=budget.summary(root),
    )
    return result


def quotes(root: Path):
    rows = []
    for path in sorted((root / "work/quotes").glob("*.json"), reverse=True):
        try:
            rows.append(review_quote(root, path.stem))
        except (OSError, ValueError, KeyError):
            rows.append(
                {"id": path.stem, "problem": "Quote unavailable or unsupported; inspect locally"}
            )
    return {"quotes": rows}


def authorize_quote(root: Path, identity: str, body: dict):
    note = _body(
        body, {"note", "expected_quote_hash", "confirmed", "confirm_uploads"}, "expected_quote_hash"
    )
    if "confirm_uploads" in body and type(body["confirm_uploads"]) is not bool:
        raise ActionError("upload confirmation must be a boolean")
    with project_lock(root):
        q = _quote(root, identity)
        expected = digest(q)
        if expected != body["expected_quote_hash"]:
            raise ActionError("Quote changed. Review its current scope and amount again.", 409)
        if uploads_required(q) and body.get("confirm_uploads") is not True:
            raise ActionError(
                "explicit permission for the quoted external data transfer is required"
            )
        values = _authorizations(root)
        prior = values.get(identity)
        if prior:
            if prior.get("quote_hash") != expected or budget.money(
                prior["cap_usd"]
            ) != budget.money(q["reserve_total_usd"]):
                raise ActionError(
                    "Different authority already exists; inspect it locally before changing it.",
                    409,
                )
            try:
                G.authorization(root, q)
            except ValueError as exc:
                raise ActionError(
                    "Recorded authority has incomplete consent; inspect it locally.", 409
                ) from exc
            return {
                "authorized_quote": identity,
                "already_authorized": True,
                "record": prior,
                "generated": False,
            }
        G.authorize(
            root,
            identity,
            q["reserve_total_usd"],
            note,
            expected_quote_hash=expected,
            via="studio",
            uploads_confirmed=body.get("confirm_uploads", False),
            review_confirmed=True,
        )
        record = read_json(root / "work/authorizations.json")[identity]
    return {"authorized_quote": identity, "record": record, "generated": False}
