"""Production budget for schema 3: one cap, a history, admission and a pause.

The task journal stays the source of truth for commitments. The cap lives in
``project.json`` as a history list; a paid job that cannot admit its next task
pauses as ``needs_budget`` and the UI asks the user to approve more.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from mp3_to_videoclip import budget as engine_budget
from mp3_to_videoclip.storage import read_json, write_json

from .models import BudgetEntry, Project


def money(value) -> Decimal:
    return Decimal(str(value))


def fmt(value) -> str:
    return str(money(value).quantize(Decimal("0.01")))


def _project(root: Path) -> Project:
    return Project.model_validate(read_json(root / "project.json"))


def cap(root: Path) -> Decimal | None:
    project = _project(root)
    return money(project.cap_usd) if project.cap_usd else None


def history(root: Path) -> list[dict]:
    return [entry.model_dump() for entry in _project(root).budget]


def add_budget(root: Path, amount, reason: str) -> dict:
    """Append a cap entry; the newest cap is the active one."""
    project = _project(root)
    previous = project.budget[-1].max_corrections if project.budget else None
    project.budget.append(
        BudgetEntry(
            at=datetime.now(UTC).isoformat(),
            cap_usd=str(money(amount)),
            reason=reason,
            max_corrections=previous,
        )
    )
    write_json(root / "project.json", project.model_dump())
    return project.budget[-1].model_dump()


def committed(root: Path) -> Decimal:
    """Costs plus unresolved reservations; the engine's admission model is canonical."""
    return engine_budget.commitment(root)


def remaining(root: Path) -> Decimal | None:
    current = cap(root)
    return None if current is None else current - committed(root)


def check(root: Path, additional) -> dict:
    """Admission check for one more task; returns a `needs_budget` decision."""
    current = cap(root)
    amount = money(additional)
    spent = committed(root)
    if current is None:
        return {
            "ok": False,
            "needs_budget": True,
            "remaining": None,
            "suggested_usd": fmt(amount),
        }
    room = current - spent
    if amount <= room:
        return {"ok": True, "needs_budget": False, "remaining": str(room), "cap_usd": str(current)}
    suggestion = ((amount - room) + (amount * Decimal("0.20"))).quantize(Decimal("0.01"))
    return {
        "ok": False,
        "needs_budget": True,
        "remaining": str(room),
        "cap_usd": str(current),
        "requested_usd": str(amount),
        "suggested_usd": str(money(suggestion)),
    }
