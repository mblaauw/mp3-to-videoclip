"""Director tools: schemas and handlers.

Phase 2 provides the read tools and the safe write tools that the engine already
supports. Paid tools are stubs that return a clear "not wired yet" error rather
than inventing a charge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import read_json, write_json


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOLS: list[dict] = [
    _tool("get_project", "Read the project summary.", {"slug": {"type": "string"}}, ["slug"]),
    _tool("get_brief", "Read the brief.", {"slug": {"type": "string"}}, ["slug"]),
    _tool("get_storyboard", "Read the storyboard.", {"slug": {"type": "string"}}, ["slug"]),
    _tool(
        "get_music_summary",
        "Read the measured music summary.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool("get_lyrics", "Read the lyrics.", {"slug": {"type": "string"}}, ["slug"]),
    _tool(
        "update_brief",
        "Patch the brief with a JSON merge. Returns the new brief.",
        {"slug": {"type": "string"}, "patch": {"type": "object"}},
        ["slug", "patch"],
    ),
    _tool(
        "update_shots",
        "Edit fields of named shots. Returns the new storyboard.",
        {"slug": {"type": "string"}, "changes": {"type": "array", "items": {"type": "object"}}},
        ["slug", "changes"],
    ),
    _tool(
        "create_storyboard",
        "Build a timing skeleton for the project.",
        {
            "slug": {"type": "string"},
            "seconds": {"type": "number"},
            "timing": {"type": "string"},
        },
        ["slug"],
    ),
    _tool(
        "set_proof_shots",
        "Choose the proof shots (max 3).",
        {"slug": {"type": "string"}, "shot_ids": {"type": "array", "items": {"type": "string"}}},
        ["slug", "shot_ids"],
    ),
    _tool(
        "ask_user",
        "Ask the user a question and end the turn.",
        {"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
        ["question"],
    ),
]


def _root(slug: str) -> Path:
    return Path("projects") / slug


async def dispatch(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call. Returns a JSON string result."""
    try:
        return json.dumps(_dispatch(name, arguments), ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def _dispatch(name: str, arguments: dict[str, Any]) -> Any:
    from mp3_to_videoclip import production as P

    root = _root(arguments["slug"])

    if name == "get_project":
        project = P.load_project(root)
        return {"slug": project.slug, "title": project.title, "duration": project.duration}

    if name == "get_brief":
        return P.load_brief(root).model_dump()

    if name == "get_storyboard":
        return P.load_board(root).model_dump()

    if name == "get_music_summary":
        path = root / "work" / "music.json"
        if not path.is_file():
            return {"available": False}
        data = read_json(path)
        return {
            "estimated_tempo_bpm": data.get("estimated_tempo_bpm"),
            "sections": data.get("sections"),
            "warnings": data.get("warnings"),
        }

    if name == "get_lyrics":
        path = root / "work" / "lyrics.json"
        return read_json(path) if path.is_file() else {"available": False}

    if name == "update_brief":
        from mp3_to_videoclip.models import Brief

        brief = P.load_brief(root)
        merged = brief.model_dump()
        merged.update(arguments.get("patch") or {})
        new_brief = Brief.model_validate(merged)
        write_json(root / "brief.json", new_brief.model_dump())
        return new_brief.model_dump()

    if name == "update_shots":
        board = P.load_board(root)
        by_id = {s.id: s for s in board.shots}
        for change in arguments.get("changes") or []:
            shot_id = change.get("id")
            if shot_id not in by_id:
                continue
            shot = by_id[shot_id]
            for key, value in change.items():
                if key != "id" and hasattr(shot, key):
                    setattr(shot, key, value)
        write_json(root / "work" / "storyboard.json", board.model_dump())
        return board.model_dump()

    if name == "create_storyboard":
        board = P.skeleton(
            root,
            arguments.get("seconds"),
            arguments.get("timing"),
        )
        write_json(root / "work" / "storyboard.json", board.model_dump())
        return board.model_dump()

    if name == "set_proof_shots":
        from mp3_to_videoclip.models import Brief

        brief = P.load_brief(root)
        creative = brief.creative
        if creative is None:
            raise ValueError("a creative profile is required")
        creative.proof_shot_ids = (arguments.get("shot_ids") or [])[:3]
        write_json(root / "brief.json", brief.model_dump())
        return {"proof_shot_ids": creative.proof_shot_ids}

    if name == "ask_user":
        return {"ask_user": arguments.get("question"), "options": arguments.get("options") or []}

    raise ValueError(f"unknown tool: {name}")
