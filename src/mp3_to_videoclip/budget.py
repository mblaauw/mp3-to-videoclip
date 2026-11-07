"""Cumulative production budget, correction-cycle limits and durable reporting.

This module intentionally never imports :mod:`generation` (which imports it), so
the small USD validator is duplicated here rather than shared, avoiding an import
cycle.

Admission model
---------------
A reservation is taken at :func:`generation.begin_task`, immediately before a
chargeable request is sent. Authorizing a quote does *not* reserve its scope, so
unsent authorized quotes are not liabilities; every new task re-checks the
cumulative commitment (reported costs plus unknown reservations for *every* kind:
images, audio uploads, transcriptions and listening passes) against the cap.
``authorize`` additionally checks that the journal commitment plus that one quote
still fits, which is what stops two independent quote submissions from
overcommitting the production cap once they start admitting tasks.

Model spend
-----------
The Director's model turns come out of the same cap. ``work/model-usage.jsonl`` holds each
turn's cost, estimated from the catalogue's stated price once the turn has finished; a turn
whose model has no stated price adds nothing to the commitment and is counted as unpriced
where the usage is shown. A turn has no reservation, so the Director checks the cap before
it starts one instead.

Reported costs are provider-reported or locally calculated, never provider
enforced caps. An ambiguous error is never auto-resolved: it stays an unresolved
reservation until the user reconciles it explicitly, and the summary never
fabricates a ``$0`` for a task with neither a reported cost nor a reservation.

Correction cycles
-----------------
``max_corrections`` is the number of *alternatives after the original*: one
successful image plus ``max_corrections`` successful images are allowed per shot.
Additional quotes for the same shot are refused with a diagnosis/restaging
requirement once that is used. Only an explicit
:func:`authorize_restaging` starts a new counted cycle; a prompt/hash change never
does. Restaging grants no spending by itself.
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .profiles import DEFAULT_MAX_CORRECTIONS
from .storage import digest, read_json, state_mutation, write_json

_SHOT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

BUDGET_PATH = "work/production-budget.json"
RESTAGING_PATH = "work/restaging.json"
TASKS_PATH = "work/tasks.json"
MODEL_USAGE_PATH = "work/model-usage.jsonl"
PROJECT_PATH = "project.json"
BUDGET_VERSION = 1
RESTAGING_VERSION = 1
MAX_CORRECTIONS_LIMIT = 10
SUCCESSFUL_STATUS = "ready"
UNRESOLVED_STATUSES = frozenset({"submitted", "result"})


def money(value) -> Decimal:
    """Finite, nonnegative USD amount; mirrors :func:`generation.money`."""
    if isinstance(value, bool):
        raise ValueError("money must be a finite nonnegative USD amount")
    try:
        result = Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError("invalid USD amount") from e
    if not result.is_finite() or result < 0:
        raise ValueError("money must be a finite nonnegative USD amount")
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _journal(root: Path) -> dict:
    path = root / TASKS_PATH
    return read_json(path) if path.exists() else {}


# --------------------------------------------------------------------------- #
# budget artifact
# --------------------------------------------------------------------------- #
def _validate_budget_record(record) -> dict:
    if not isinstance(record, dict) or record.get("version") != BUDGET_VERSION:
        raise ValueError("production budget artifact is invalid; recreate it explicitly")
    cap = money(record.get("cap_usd"))
    if cap <= 0:
        raise ValueError("production budget artifact has a non-positive cap")
    corrections = record.get("max_corrections")
    if (
        isinstance(corrections, bool)
        or not isinstance(corrections, int)
        or not 0 <= corrections <= MAX_CORRECTIONS_LIMIT
    ):
        raise ValueError("production budget artifact has invalid max_corrections")
    if not str(record.get("note", "")).strip():
        raise ValueError("production budget artifact is missing its authority note")
    return record


def _schema_budget(root: Path) -> dict | None:
    """Schema 3 keeps the cap history in project.json; synthesise the same record."""
    path = root / PROJECT_PATH
    if not path.exists():
        return None
    project = read_json(path)
    if not isinstance(project, dict):
        return None
    entries = project.get("budget") or []
    if not entries:
        return None
    latest = entries[-1]
    if not isinstance(latest, dict):
        raise ValueError("project budget history is invalid; inspect it locally")
    corrections = latest.get("max_corrections")
    if corrections is None:
        # Schema 3 stores None when no explicit correction limit was recorded.
        # The engine's documented default is the policy in that case.
        corrections = DEFAULT_MAX_CORRECTIONS
    return _validate_budget_record(
        {
            "version": BUDGET_VERSION,
            "cap_usd": latest.get("cap_usd"),
            "max_corrections": corrections,
            "note": str(latest.get("reason") or "schema 3 production budget"),
            "at": latest.get("at") or _now(),
        }
    )


def read_budget(root: Path) -> dict | None:
    """Validated production budget, or ``None`` before one is set."""
    path = root / BUDGET_PATH
    record = _schema_budget(root)
    if path.exists():
        legacy = _validate_budget_record(read_json(path))
        if (
            record is None
            or money(legacy["cap_usd"]) != money(record["cap_usd"])
            or legacy["max_corrections"] != record["max_corrections"]
        ):
            raise ValueError(
                "conflicting schema-3 budget files; inspect and explicitly reconcile "
                "work/production-budget.json with project.json before spending"
            )
    return record


def model_spend(root: Path) -> Decimal:
    """What the Director's priced model turns cost, by the catalogue's stated prices."""
    path = Path(root) / MODEL_USAGE_PATH
    total = Decimal(0)
    for line in path.read_text().splitlines() if path.is_file() else []:
        try:
            cost = json.loads(line).get("cost_usd")
        except (json.JSONDecodeError, AttributeError):
            continue
        if cost is not None:
            total += money(cost)
    return total


def split_commitment(root: Path) -> tuple[Decimal, Decimal, int]:
    """Return reported spend, unresolved reservations and ready paid stills.

    Spend includes the Director's priced model turns. A task with neither a cost
    nor a reservation blocks admission rather than silently contributing zero.
    The report still lists such unpriced tasks.
    """
    spent = model_spend(root)
    reserved = Decimal(0)
    paid_stills = 0
    for task in _journal(root).values():
        if task.get("cost_usd") is not None:
            spent += money(task["cost_usd"])
            if task.get("kind") == "images" and task.get("status") == SUCCESSFUL_STATUS:
                paid_stills += 1
        elif task.get("reserve_usd") is not None:
            reserved += money(task["reserve_usd"])
        else:
            raise ValueError(
                "unpriced journal task needs cost/reservation reconciliation before spending"
            )
    return spent, reserved, paid_stills


def cost_summary(root: Path) -> dict:
    """One film's reported spend and open reservations by kind of task. Only reads.

    Unlike ``split_commitment``, an unpriced task is counted rather than refused,
    because this answers "what did it cost", not "may more be spent".
    """
    by_kind: dict[str, dict[str, Decimal]] = {}
    unpriced = 0
    for task in _journal(root).values():
        row = by_kind.setdefault(
            str(task.get("kind") or "other"), {"spent": Decimal(0), "reserved": Decimal(0)}
        )
        if task.get("cost_usd") is not None:
            row["spent"] += money(task["cost_usd"])
        elif task.get("reserve_usd") is not None:
            row["reserved"] += money(task["reserve_usd"])
        else:
            unpriced += 1
    model = model_spend(root)
    if model:
        by_kind.setdefault("model", {"spent": Decimal(0), "reserved": Decimal(0)})["spent"] += model
    return {"by_kind": by_kind, "unpriced": unpriced}


def costs_across(projects_dir: Path) -> dict:
    """Every production's journal summed by film and by kind of task."""
    films = []
    kinds: dict[str, dict[str, Decimal]] = {}
    spent = reserved = Decimal(0)
    unpriced = 0
    for root in sorted(projects_dir.iterdir()) if projects_dir.is_dir() else []:
        if not (root / TASKS_PATH).is_file():
            continue
        try:
            summary = cost_summary(root)
        except (ValueError, TypeError, AttributeError):
            films.append({"slug": root.name, "unreadable": True})
            continue
        film_spent = sum((row["spent"] for row in summary["by_kind"].values()), Decimal(0))
        film_reserved = sum((row["reserved"] for row in summary["by_kind"].values()), Decimal(0))
        films.append(
            {
                "slug": root.name,
                "spent_usd": str(film_spent),
                "reserved_usd": str(film_reserved),
                "unpriced": summary["unpriced"],
            }
        )
        spent += film_spent
        reserved += film_reserved
        unpriced += summary["unpriced"]
        for kind, row in summary["by_kind"].items():
            total = kinds.setdefault(kind, {"spent": Decimal(0), "reserved": Decimal(0)})
            total["spent"] += row["spent"]
            total["reserved"] += row["reserved"]
    return {
        "films": films,
        "by_kind": [
            {"kind": kind, "spent_usd": str(row["spent"]), "reserved_usd": str(row["reserved"])}
            for kind, row in sorted(kinds.items())
        ],
        "spent_usd": str(spent),
        "reserved_usd": str(reserved),
        "unpriced": unpriced,
    }


def commitment(root: Path) -> Decimal:
    """Reported cost plus unknown reservation for every journal task."""
    spent, reserved, _ = split_commitment(root)
    return spent + reserved


@state_mutation
def set_budget(root: Path, cap_usd, note: str, max_corrections: int | None = None) -> dict:
    """Write the explicit production cap. Never lowers it below committed spend."""
    cap = money(cap_usd)
    if cap <= 0:
        raise ValueError("production cap must be a finite positive USD amount")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("record the user's spending authority in a note")
    if max_corrections is None:
        previous = read_budget(root)
        max_corrections = previous["max_corrections"] if previous else DEFAULT_MAX_CORRECTIONS
    if (
        isinstance(max_corrections, bool)
        or not isinstance(max_corrections, int)
        or not 0 <= max_corrections <= MAX_CORRECTIONS_LIMIT
    ):
        raise ValueError(
            f"max_corrections must be an integer between 0 and {MAX_CORRECTIONS_LIMIT}"
        )
    committed = commitment(root)
    if cap < committed:
        raise ValueError(
            f"cap {cap} is below the {committed} already accounted/reserved in the journal; "
            "reconcile that spend or choose a cap that covers it"
        )
    record = {
        "version": BUDGET_VERSION,
        "cap_usd": str(cap),
        "max_corrections": max_corrections,
        "note": note,
        "at": _now(),
    }
    read_budget(root)
    if (root / BUDGET_PATH).exists():
        raise ValueError("reconcile the legacy budget file before changing a cap")
    project = read_json(root / PROJECT_PATH)
    project.setdefault("budget", []).append(
        {
            "at": record["at"],
            "cap_usd": str(cap),
            "reason": note,
            "max_corrections": max_corrections,
        }
    )
    write_json(root / PROJECT_PATH, project)
    return record


# --------------------------------------------------------------------------- #
# admission
# --------------------------------------------------------------------------- #
def require_budget(root: Path) -> dict | None:
    """Every film needs a budget before anything can be bought."""
    record = read_budget(root)
    if record is None:
        raise ValueError("a film needs an explicit production budget before authorized paid tasks")
    return record


def check_capacity(root: Path, additional_usd, *, context: str = "submission"):
    """Would one more task of ``additional_usd`` fit the cumulative production cap?

    Returns the budget record, or ``None`` when no budget applies (legacy
    behaviour preserved). Raises before anything is submitted when it would not
    fit, or when a strict workflow 2 project has no budget at all.
    """
    record = require_budget(root)
    if record is None:
        return None
    cap = money(record["cap_usd"])
    amount = money(additional_usd)
    committed = commitment(root)
    if committed + amount > cap:
        raise ValueError(
            f"production budget exhausted ({context}): {committed} accounted/reserved plus "
            f"{amount} requested exceeds the {cap} cap; nothing was submitted"
        )
    return record


class Unreconciled(ValueError):
    """A paid task still out holds the film's spending until the owner settles it."""

    code = "unresolved_task"


def require_reconciled(root: Path, admitted=()):
    """No new work after ambiguous prior tasks; allow this run's live workers."""
    allowed = set(admitted)
    unresolved = [
        t.get("uuid", key)
        for key, t in _journal(root).items()
        if t.get("status") in UNRESOLVED_STATUSES and t.get("uuid", key) not in allowed
    ]
    if unresolved:
        raise Unreconciled(
            "A paid task hasn't come back, so nothing new can be bought on this film. Open the "
            "budget to check it again or record what it billed (unresolved tasks need "
            "recovery/reconciliation before new spending: " + ", ".join(unresolved) + ")"
        )


def unresolved_tasks(root: Path) -> list[dict]:
    """The paid tasks holding a film's spending, in words the owner can act on."""
    return [
        {
            "id": t.get("uuid", key),
            "kind": t.get("kind"),
            "shot_id": t.get("shot_id") or t.get("line_id") or t.get("cue_id"),
            "reserve_usd": t.get("reserve_usd"),
            "at": t.get("submitted_at") or t.get("at"),
        }
        for key, t in _journal(root).items()
        if t.get("status") in UNRESOLVED_STATUSES
    ]


# --------------------------------------------------------------------------- #
# correction cycles
# --------------------------------------------------------------------------- #
def _successful_images(journal: dict, shot_id: str) -> int:
    return sum(
        1
        for task in journal.values()
        if task.get("kind") == "images"
        and task.get("shot_id") == shot_id
        and task.get("status") == SUCCESSFUL_STATUS
    )


def correction_policy(root: Path) -> tuple[bool, int]:
    """``(enforced, max_corrections)``; every film is controlled."""
    record = read_budget(root)
    if record is not None:
        return True, record["max_corrections"]
    return True, DEFAULT_MAX_CORRECTIONS


def _stored_cycle(root: Path, shot_id: str):
    path = root / RESTAGING_PATH
    if not path.exists():
        return None
    record = read_json(path)
    shots = record.get("shots") if isinstance(record, dict) else None
    entry = shots.get(shot_id) if isinstance(shots, dict) else None
    if not isinstance(entry, dict):
        return None
    baseline = entry.get("baseline")
    if isinstance(baseline, bool) or not isinstance(baseline, int) or baseline < 0:
        raise ValueError("restaging artifact is invalid; recreate it explicitly")
    return {"baseline": baseline, "cycle_hash": entry.get("cycle_hash")}


def correction_cycle(root: Path, shot_id: str) -> dict:
    """Identity stamped into a quote task so a later run cannot bypass a restaging."""
    stored = _stored_cycle(root, shot_id)
    return {
        "baseline": stored["baseline"] if stored else 0,
        "restage_hash": stored["cycle_hash"] if stored else None,
    }


def check_correction_cycle(root: Path, shot_id: str, cycle: dict | None = None):
    """Refuse a further quote/generation once this shot's alternatives are used.

    ``cycle`` is the identity recorded on the quote task. At generation time a
    mismatch against the currently stored restaging means the cycle changed after
    the quote and the quote must be remade, so a stale quote is never a bypass.
    """
    enforced, max_corrections = correction_policy(root)
    if not enforced:
        return
    successful = _successful_images(_journal(root), shot_id)
    stored = _stored_cycle(root, shot_id)
    baseline = stored["baseline"] if stored else 0
    current_hash = stored["cycle_hash"] if stored else None
    if cycle is not None and (
        cycle.get("baseline", 0) != baseline or cycle.get("restage_hash") != current_hash
    ):
        raise ValueError(
            f"shot {shot_id} retry cycle changed since this quote; requote before spending"
        )
    used = successful - baseline
    if used >= 1 + max_corrections:
        raise ValueError(
            f"shot {shot_id} already has {used} successful image generation(s); only "
            f"{max_corrections} correction(s) after the original are allowed. Diagnose the "
            "failure and start an explicit restaging cycle before quoting again."
        )


def require_correction_cycles(root: Path, shot_ids):
    """Quote-time guard for every source shot that would create a new image task."""
    for shot_id in shot_ids:
        check_correction_cycle(root, shot_id)


def used_up_corrections(root: Path, shot_ids) -> list[str]:
    """The named shots that need a new correction cycle before another image."""
    used = []
    for shot_id in shot_ids:
        try:
            check_correction_cycle(root, shot_id)
        except ValueError:
            used.append(shot_id)
    return used


@state_mutation
def authorize_restaging(root: Path, shot_ids, note: str) -> dict:
    """Explicit new correction cycle for named shots; grants no spending.

    The successful-generation count at this moment becomes the cycle baseline, so
    the shot is allowed one new original plus ``max_corrections`` alternatives.
    Recorded ``cycle_hash`` binds any quote made afterwards; a later restage (or a
    quoted cycle from before this one) no longer matches and must be requoted.
    """
    if isinstance(shot_ids, (str, bytes)):
        raise ValueError("name a non-empty list of shot IDs for a restaging cycle")
    ids = list(shot_ids)
    if (
        not ids
        or len(set(ids)) != len(ids)
        or any(not isinstance(shot_id, str) or not shot_id.strip() for shot_id in ids)
    ):
        raise ValueError("restaging needs unique, non-empty shot IDs")
    # Record the exact identifier the rest of the pipeline quotes with: a padded
    # or mistyped token would otherwise grant a phantom cycle to a different key.
    if any(shot_id != shot_id.strip() or not _SHOT_ID.fullmatch(shot_id) for shot_id in ids):
        raise ValueError("shot IDs must be exact, unpadded storyboard IDs")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("record the diagnosis that justifies a new correction cycle in a note")
    journal = _journal(root)
    path = root / RESTAGING_PATH
    previous = read_json(path) if path.exists() else {}
    shots = dict(previous.get("shots", {}))
    for shot_id in ids:
        baseline = _successful_images(journal, shot_id)
        shots[shot_id] = {
            "baseline": baseline,
            "cycle_hash": digest({"shot_id": shot_id, "baseline": baseline, "note": note}),
        }
    record = {"version": RESTAGING_VERSION, "note": note, "at": _now(), "shots": shots}
    write_json(root / RESTAGING_PATH, record)
    return record


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _latency_seconds(task: dict):
    start = task.get("submitted_at")
    end = task.get("completed_at") or task.get("reconciled_at")
    if not start or not end:
        return None
    try:
        elapsed = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (TypeError, ValueError):
        return None
    return elapsed if elapsed >= 0 else None


def summary(root: Path) -> dict:
    """Aggregate every journal task and the budget into one durable report.

    Reported costs are known; ``reserved_unknown_usd`` keeps every task whose cost
    is genuinely unknown (including a ``ready`` mediaStorage upload) as a
    reservation rather than assuming ``$0``. Latency mixes upload/inference steps
    and is not labelled inference-only.
    """
    journal = _journal(root)
    record = read_budget(root)
    reported = Decimal(0)
    reserved = Decimal(0)
    unpriced = []
    statuses: dict = {}
    kinds: dict = {}
    models: dict = {}
    quotes: dict = {}
    shots: dict = {}
    successful_by_kind: dict = {}
    successful_images: dict = {}
    unresolved = 0
    latencies = []
    for task in journal.values():
        status = task.get("status")
        statuses[status] = statuses.get(status, 0) + 1
        kind = task.get("kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        model = task.get("model") or task.get("request", {}).get("model")
        if model:
            models[model] = models.get(model, 0) + 1
        if task.get("quote_id"):
            qid = task["quote_id"]
            quotes[qid] = quotes.get(qid, 0) + 1
        shot_id = task.get("shot_id")
        if shot_id:
            shots[shot_id] = shots.get(shot_id, 0) + 1
        if task.get("cost_usd") is not None:
            reported += money(task["cost_usd"])
        elif task.get("reserve_usd") is not None:
            reserved += money(task["reserve_usd"])
        else:
            unpriced.append(task.get("uuid"))
        if status in UNRESOLVED_STATUSES:
            unresolved += 1
        if status == SUCCESSFUL_STATUS:
            successful_by_kind[kind] = successful_by_kind.get(kind, 0) + 1
            if kind == "images" and shot_id:
                successful_images[shot_id] = successful_images.get(shot_id, 0) + 1
        latency = _latency_seconds(task)
        if latency is not None:
            latencies.append(latency)
    model = model_spend(root)
    total = reported + model + reserved
    cap = money(record["cap_usd"]) if record else None
    latency_summary = {
        "count": len(latencies),
        "min_seconds": round(min(latencies), 6) if latencies else None,
        "max_seconds": round(max(latencies), 6) if latencies else None,
        "mean_seconds": round(sum(latencies) / len(latencies), 6) if latencies else None,
        "coverage": "submitted→completed where both timestamps exist; mixes upload and "
        "inference steps, not inference-only",
    }
    board_path = root / "work/storyboard.json"
    board = read_json(board_path) if board_path.exists() else {}
    source_count = sum(not s.get("asset_shot_id") for s in board.get("shots", []))
    return {
        "currency": "USD",
        "budget_configured": record is not None,
        "cap_usd": str(cap) if cap is not None else None,
        "max_corrections": record["max_corrections"] if record else None,
        "note": record["note"] if record else None,
        "reported_usd": str(reported),
        "model_usd": str(model),
        "reserved_unknown_usd": str(reserved),
        "total_accounted_usd": str(total),
        "cap_remaining_usd": str(cap - total) if cap is not None else None,
        "over_cap": bool(cap is not None and total > cap),
        "task_count": len(journal),
        "unresolved_tasks": unresolved,
        "unpriced_tasks": sorted(uuid for uuid in unpriced if uuid),
        "statuses": statuses,
        "kinds": kinds,
        "models": models,
        "quotes": quotes,
        "source_panel_count": source_count,
        "successful_image_calls_per_source": (
            round(sum(successful_images.values()) / source_count, 6) if source_count else None
        ),
        "shots_with_alternatives": sum(count > 1 for count in successful_images.values()),
        "shots": shots,
        "successful_calls_by_kind": successful_by_kind,
        "successful_image_generations_by_shot": successful_images,
        "task_latency_seconds": latency_summary,
        "admission_note": "Reservations are admitted at begin_task (submission) only; authorized "
        "but unsubmitted quotes are not reserved, and every new task revalidates the cumulative "
        "cap. Reported costs are provider-reported or calculated, never provider-enforced caps.",
    }
