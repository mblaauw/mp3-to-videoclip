"""Typed local human decisions; no provider calls or generic command dispatch.

HTTP capability checks live in serve. These operations additionally enforce exact
review identities under the same project lock used by the CLI. Same-OS process
isolation is explicitly not a claim of this workflow.
"""

import re
from pathlib import Path
from uuid import UUID

from . import budget, flow
from . import generation as G
from . import production as P
from .storage import digest, project_lock, read_json, write_json


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


def review_story(root: Path):
    """One human-readable, hash-bound view of the two story decisions.

    A read-only snapshot deliberately takes no project lock: browsing Studio must
    not create files. The approval route re-derives and checks this combined hash
    under the lock before writing either record.
    """
    brief_hash = P.stage_hash(root, "brief")
    board_hash = P.stage_hash(root, "storyboard")
    return {
        "brief": {
            "hash": brief_hash,
            "artifact": read_json(root / P.STAGE_FILES["brief"]),
        },
        "storyboard": {
            "hash": board_hash,
            "artifact": read_json(root / P.STAGE_FILES["storyboard"]),
        },
        "combined_hash": digest({"brief": brief_hash, "storyboard": board_hash}),
        "guided": flow.guided(root),
    }


def approve_story(root: Path, body: dict):
    """Record one human decision for the agreed brief and storyboard.

    This is the guided-flow decision. Recorded v2 productions keep separate
    brief and storyboard approvals. Both guided gates are still validated and
    both content hashes are required; the approval file is restored
    byte-for-byte if the second gate fails, so a single click can never leave a
    half-approved story.
    """
    if not flow.guided(root):
        raise ActionError(
            "This production records brief and storyboard as separate decisions.",
            409,
        )
    note = _body(body, {"note", "expected_hash", "confirmed"}, "expected_hash")
    with project_lock(root):
        path = root / "work/approvals.json"
        try:
            saved = read_json(path)
        except (OSError, ValueError) as exc:
            raise ActionError(
                "saved approval records are unavailable; inspect locally", 409
            ) from exc
        if not isinstance(saved, dict) or any(
            not isinstance(item, dict) for item in saved.values()
        ):
            raise ActionError("saved approval records are invalid; inspect them locally", 409)
        brief_hash = P.stage_hash(root, "brief")
        board_hash = P.stage_hash(root, "storyboard")
        combined = digest({"brief": brief_hash, "storyboard": board_hash})
        if combined != body["expected_hash"]:
            raise ActionError("Story changed. Review the current brief and storyboard again.", 409)
        before = path.read_bytes()
        try:
            P.approve(
                root,
                "brief",
                note,
                expected_hash=brief_hash,
                via="studio",
                review_confirmed=True,
            )
            P.approve(
                root,
                "storyboard",
                note,
                expected_hash=board_hash,
                via="studio",
                review_confirmed=True,
            )
        except Exception:
            path.write_bytes(before)
            raise
        saved = read_json(path)
    return {
        "approved": ["brief", "storyboard"],
        "records": {"brief": saved["brief"], "storyboard": saved["storyboard"]},
        "generated": False,
    }


def record_shot_review(root: Path, body: dict):
    """Record an exact inspected still verdict; never a generation request."""
    if set(body) - {"shot_id", "version", "sha256", "verdict", "note", "confirmed"}:
        raise ActionError("unexpected review fields")
    if body.get("confirmed") is not True:
        raise ActionError("explicit inspection confirmation is required")
    note = _clean_text(body.get("note"), "review note", 2000)
    shot_id = _clean_text(body.get("shot_id"), "shot", 120)
    digest_value = body.get("sha256")
    if not isinstance(digest_value, str) or not re.fullmatch(r"[0-9a-f]{64}", digest_value):
        raise ActionError("the reviewed image hash is required")
    version = body.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ActionError("review version must be a positive integer")
    verdict = body.get("verdict")
    if verdict not in ("accept", "reject", "uncertain"):
        raise ActionError("verdict must be accept, reject or uncertain")
    from .reviews import record_review

    with project_lock(root):
        board = P.load_board(root)
        shot = next((item for item in board.shots if item.id == shot_id), None)
        if shot is None:
            raise ActionError("unknown review shot", 404)
        owner = shot.asset_shot_id or shot.id
        assets = read_json(root / "work/assets.json")
        entry = assets.get(owner) or {}
        chosen = next(
            (item for item in entry.get("versions", []) if item.get("version") == version),
            None,
        )
        if chosen is None or chosen.get("sha256") != digest_value:
            raise ActionError(
                "That image version changed. Refresh and inspect the current bytes.", 409
            )
        record = record_review(
            root,
            shot_id,
            version,
            verdict,
            note=note,
            reviewer="studio",
            inspected=True,
        )
    return {"review": record, "approved": False, "generated": False}


def save_credits(root: Path, body: dict):
    """Edit late-bound credit cards for a guided production.

    The guided flow deliberately keeps the signature out of the brief hash, so a
    factual credit correction at the end does not invalidate image approvals.
    Recorded v2 productions retain their existing coupling and are refused here.
    """
    if not flow.guided(root):
        raise ActionError(
            "This production records credits inside its brief approval. Ask your agent "
            "to revise the signature and reapprove the brief.",
            409,
        )
    if set(body) - {
        "expected_spec_hash",
        "title",
        "cards",
        "confirmed",
        "note",
        "use_as_template",
    }:
        raise ActionError("unexpected credit fields")
    if body.get("confirmed") is not True:
        raise ActionError("confirm that these factual roles are correct for this film")
    expected = body.get("expected_spec_hash")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ActionError("the current graphics specification hash is required")
    note = _clean_text(body.get("note"), "credit note", 2000)
    title = _clean_text(body.get("title"), "film title", 120)
    project = P.load_project(root)
    if title.casefold() != project.title.casefold():
        raise ActionError("credits belong to this film; the title must match its project title")
    raw_cards = body.get("cards")
    if not isinstance(raw_cards, list) or len(raw_cards) > 40:
        raise ActionError("credit cards must be a list of at most 40 role/name pairs")
    cards = []
    for card in raw_cards:
        if not isinstance(card, (list, tuple)) or len(card) != 2:
            raise ActionError("each credit card needs exactly a role and a name")
        role, name = (_clean_text(value, "credit role/name", 120) for value in card)
        cards.append([role, name])
    if not cards:
        raise ActionError("record at least one factual role/name pair")
    use_as_template = body.get("use_as_template", False)
    if type(use_as_template) is not bool:
        raise ActionError("use_as_template must be a boolean")
    with project_lock(root):
        spec = read_json(root / "work/graphics-spec.json")
        if digest(spec) != expected:
            raise ActionError(
                "Credits changed. Reload the current specification before saving.", 409
            )
        spec.setdefault("credits", {})
        spec["credits"]["cards"] = cards
        spec["credit_roles_confirmed"] = True
        spec.pop("warning", None)
        write_json(root / "work/graphics-spec.json", spec)
        if use_as_template:
            write_json(
                root / "work/credits-template.json",
                {
                    "cards": cards,
                    "saved_at": P.now(),
                    "source_project": root.name,
                    "note": note,
                },
            )
    return {
        "spec_hash": digest(spec),
        "spec": spec,
        "approved": False,
        "note": note,
    }


def _clean_text(value, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ActionError(f"{name} must be text")
    text = value.strip()
    if not text or len(text) > limit:
        raise ActionError(f"{name} must be 1–{limit} characters")
    return text


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
