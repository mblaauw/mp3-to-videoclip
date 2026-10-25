"""Image generation: estimate, run and recover through the existing journal.

The journal and recovery stay exactly as strict as today. This module adds the
small surface the app and the director need: a quote-based estimate, a run that
checks the production budget, and a recovery that never resubmits.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import generation as G


def estimate(
    root: Path,
    shot_ids: list[str],
    *,
    scope: str = "stills",
    reserve: str = "0.05",
    regenerate: bool = False,
) -> dict:
    """Quote the selected shots at live schema/pricing; saves the quote."""
    from mp3_to_videoclip.storage import project_lock

    with project_lock(root):
        quote = G.quote_images(root, scope, reserve, ids=shot_ids, regenerate=regenerate)
    return {
        "quote_id": quote["id"],
        "scope": quote["scope"],
        "tasks": len(quote["tasks"]),
        "reserve_usd": quote["reserve_total_usd"],
        "cap_usd": quote.get("cap_usd"),
        "uploads_required": G.quote_uploads_required(quote),
        "shot_ids": [task["shot_id"] for task in quote["tasks"]],
    }


def quote(root: Path, quote_id: str) -> dict:
    return G.read_quote(root, quote_id)


def uploads_required(quote: dict) -> bool:
    return G.quote_uploads_required(quote)


def authorize(root: Path, quote_id: str, *, note: str, uploads_confirmed: bool = False) -> dict:
    """Authorize one quoted batch at exactly its reserved total, then return it.

    The caller must have shown the user this quote. Nothing is submitted here;
    ``run`` executes the authorized quote exactly once.
    """
    quote = G.read_quote(root, quote_id)
    if G.quote_uploads_required(quote) and not uploads_confirmed:
        raise ValueError("confirm the reference upload before authorizing this quote")
    from mp3_to_videoclip.storage import project_lock

    with project_lock(root):
        G.authorize(
            root,
            quote_id,
            quote["reserve_total_usd"],
            note,
            via="studio",
            review_confirmed=True,
            uploads_confirmed=True if G.quote_uploads_required(quote) else None,
        )
    return quote


def run(root: Path, quote_id: str, *, concurrency: int = 1) -> dict:
    """Execute an authorized quote exactly once; never resubmits."""
    from mp3_to_videoclip.storage import project_lock

    with project_lock(root):
        return G.generate(root, quote_id, concurrency=concurrency)


def recover(root: Path, task_uuid: str) -> dict:
    return G.recover(root, task_uuid)


def costs(root: Path) -> dict:
    return G.costs(root)
