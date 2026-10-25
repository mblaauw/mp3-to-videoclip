"""Schema 1 -> 3 migration for live productions.

Reads the old project.json, drops the flags the rework removes, moves the
production budget from ``work/production-budget.json`` into the project
document, snapshots the old files under ``history/migration-<timestamp>/`` and
writes the new document atomically. The source audio, stills, storyboard, brief
and task journal are copied untouched.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from mp3_to_videoclip.storage import read_json, write_json

from .models import SCHEMA_VERSION, BudgetEntry, Project

LEGACY_KEYS = (
    "workflow_version",
    "prompt_version",
    "signature_required",
    "renderer_backend",
    "source_filename",
)


def is_legacy(root: Path) -> bool:
    data = read_json(root / "project.json") if (root / "project.json").is_file() else {}
    return data.get("schema_version") != SCHEMA_VERSION


def _budget_entries(root: Path) -> list[BudgetEntry]:
    path = root / "work" / "production-budget.json"
    if not path.is_file():
        return []
    record = read_json(path)
    return [
        BudgetEntry(
            at=str(record.get("at") or datetime.now(UTC).isoformat()),
            cap_usd=str(record.get("cap_usd")),
            reason=str(record.get("note") or "migrated from schema 1"),
            max_corrections=record.get("max_corrections"),
        )
    ]


def migrate(root: Path, *, dry_run: bool = False) -> dict:
    """Migrate one live production in place; returns a summary."""
    root = root.resolve()
    old = read_json(root / "project.json")
    if old.get("schema_version") == SCHEMA_VERSION:
        return {"slug": root.name, "migrated": False, "reason": "already schema 3"}

    budget = _budget_entries(root)
    cleaned = {k: v for k, v in old.items() if k not in LEGACY_KEYS}
    cleaned["schema_version"] = SCHEMA_VERSION
    cleaned["budget"] = [b.model_dump() for b in budget]
    project = Project.model_validate(cleaned)

    if dry_run:
        return {"slug": root.name, "migrated": False, "would_write": project.model_dump()}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    history = root / "history" / f"migration-{stamp}"
    history.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "project.json", history / "project.json")
    budget_path = root / "work" / "production-budget.json"
    if budget_path.is_file():
        shutil.copy2(budget_path, history / "production-budget.json")

    write_json(root / "project.json", project.model_dump())
    if budget_path.is_file():
        budget_path.unlink()
    return {
        "slug": root.name,
        "migrated": True,
        "history": str(history.relative_to(root)),
        "budget_entries": len(budget),
    }


def migrate_all(projects_dir: Path, *, dry_run: bool = False) -> list[dict]:
    if not projects_dir.is_dir():
        return []
    results = []
    for entry in sorted(projects_dir.iterdir()):
        if entry.is_dir() and (entry / "project.json").is_file() and is_legacy(entry):
            results.append(migrate(entry, dry_run=dry_run))
    return results
