"""Image generation: estimate, run and recover through the existing journal.

The journal and recovery stay exactly as strict as today. This module adds the
small surface the app and the director need: a quote-based estimate, a run that
checks the production budget, and a recovery that never resubmits.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import generation as G


def estimate(root: Path, shot_ids: list[str]) -> dict:
    """Quote the selected shots at live schema/pricing; saves the quote."""
    quote = G.quote_images(root, shot_ids)
    return {
        "quote_id": quote["id"],
        "tasks": len(quote["tasks"]),
        "reserve_usd": quote["reserve_total_usd"],
        "cap_usd": quote.get("cap_usd"),
        "quote": quote,
    }


def run(root: Path, quote_id: str, *, concurrency: int = 1) -> dict:
    """Execute an authorized quote exactly once; never resubmits."""
    return G.generate(root, quote_id, concurrency=concurrency)


def recover(root: Path, task_uuid: str) -> dict:
    return G.recover(root, task_uuid)


def costs(root: Path) -> dict:
    return G.costs(root)
