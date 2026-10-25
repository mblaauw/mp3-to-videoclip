"""Director tools: schemas + handlers. Phase 3 fills in the write tools."""

from __future__ import annotations

from typing import Any

# Read-only tools available in Phase 2 skeleton.
READ_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "Read the project summary.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
    },
]


async def dispatch(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call. Returns a JSON string result."""
    import json

    if name == "get_project":
        from pathlib import Path

        from mp3_to_videoclip import production as P

        root = Path("projects") / arguments["slug"]
        try:
            project = P.load_project(root)
            return json.dumps(
                {"slug": project.slug, "title": project.title, "duration": project.duration}
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
    return json.dumps({"error": f"unknown tool: {name}"})
