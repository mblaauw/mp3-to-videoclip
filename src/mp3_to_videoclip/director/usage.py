"""What the Director's models used: an append-only record beside the money journal.

Kept apart from ``work/tasks.json`` on purpose. The journal's contract is a reservation
before a request and a cost the provider reports, and a model call has neither. So this is
shown beside picture spend, and never admitted against a film's cap.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .providers.base import Usage

FILE = "work/model-usage.jsonl"


def record(
    root: Path,
    *,
    turn_id: str,
    role: str | None,
    provider: str,
    model: str,
    usage: Usage,
    cost_usd: str | None,
    cost_basis: str,
    prompt_hash: str | None = None,
) -> None:
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "turn_id": turn_id,
        "role": role,
        "provider": provider,
        "model": model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost_usd": cost_usd,
        "cost_basis": cost_basis,
        "prompt_hash": prompt_hash,
    }
    path = Path(root) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def rows(root: Path) -> list[dict]:
    path = Path(root) / FILE
    found = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return found


def summary(root: Path) -> dict:
    """A film's totals. ``unpriced_turns`` says how much of it the dollars don't cover."""
    path = Path(root) / FILE
    total = Decimal(0)
    prompt = completion = turns = unpriced = 0
    for line in path.read_text().splitlines() if path.is_file() else []:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        turns += 1
        prompt += row.get("prompt_tokens") or 0
        completion += row.get("completion_tokens") or 0
        if row.get("cost_usd") is None:
            unpriced += 1
        else:
            total += Decimal(row["cost_usd"])
    return {
        "turns": turns,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cost_usd": str(total),
        "unpriced_turns": unpriced,
    }
