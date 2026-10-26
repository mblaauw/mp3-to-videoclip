"""Which storyboard shots cost money and which are designed locally.

The prose lives in ``director/prompts/kinds/<kind>.md``; this module is the
authoritative paid/local table for the engine, the UI and the Writer tools.
"""

from __future__ import annotations

from .models import Shot, ShotKind

SHOT_KINDS: dict[ShotKind, dict] = {
    "scene": {
        "label": "Scene",
        "icon": "◉",
        "paid": True,
        "purpose": "A generated still that carries story, place or performance.",
    },
    "product": {
        "label": "Product",
        "icon": "▣",
        "paid": True,
        "purpose": "A generated or uploaded product hero, packshot or in-use frame.",
    },
    "upload": {
        "label": "Upload",
        "icon": "⬒",
        "paid": False,
        "purpose": "A user-owned photograph, venue, artist or logo art, cropped locally.",
    },
    "card": {
        "label": "Card",
        "icon": "▤",
        "paid": False,
        "purpose": "A designed message card with local type, colour and optional image.",
    },
    "bridge": {
        "label": "Bridge",
        "icon": "⇄",
        "paid": False,
        "purpose": "A match cut or message that carries one idea into the next.",
    },
    "split": {
        "label": "Split",
        "icon": "◫",
        "paid": False,
        "purpose": "Two or three source shots composed side by side or in a grid.",
    },
    "reprise": {
        "label": "Reprise",
        "icon": "↺",
        "paid": False,
        "purpose": "A new crop of an existing still; no new image is bought.",
    },
    "logo": {
        "label": "Logo",
        "icon": "◆",
        "paid": False,
        "purpose": "A local brand lockup built from supplied names and assets.",
    },
    "end_card": {
        "label": "End card",
        "icon": "▮",
        "paid": False,
        "purpose": "A local close with the CTA, URL and any mandatory legal line.",
    },
}


def is_reprise(shot: Shot) -> bool:
    """The legacy alias and the explicit reprise kind mean the same thing."""
    return shot.asset_shot_id is not None or shot.kind == "reprise"


def is_paid(shot: Shot) -> bool:
    """True only when this shot requires a Runware image task."""
    if shot.asset_shot_id is not None:
        return False
    if shot.kind == "bridge":
        return shot.bridge is not None and shot.bridge.mode == "generated"
    if shot.kind == "product":
        return shot.asset is None
    return shot.kind == "scene"


def is_local(shot: Shot) -> bool:
    return not is_paid(shot)


def public_kinds() -> list[dict]:
    return [{"id": kind, **value} for kind, value in SHOT_KINDS.items()]
