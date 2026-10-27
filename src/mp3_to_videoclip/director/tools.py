"""Director tools: schemas and handlers.

Phase 2 provides the read tools and the safe write tools that the engine already
supports. Paid tools are stubs that return a clear "not wired yet" error rather
than inventing a charge.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mp3_to_videoclip.storage import read_json, read_optional, write_json

MAX_TOOL_IMAGES = 8
THUMBNAIL_PIXELS = 512


@dataclass(frozen=True)
class ToolResult:
    """A text result plus optional image parts for the next model call."""

    text: str
    images: tuple[str, ...] = field(default_factory=tuple)


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
        "get_edit",
        "Read the edit decision list and its computed report, if an edit exists.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "update_edit",
        "Write the edit decision list (timing, motion, transitions, accents, text, grade). "
        "Returns the saved edit and its report; fix every hard finding.",
        {"slug": {"type": "string"}, "edit": {"type": "object"}},
        ["slug", "edit"],
    ),
    _tool(
        "get_music_summary",
        "Read the measured music summary.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool("get_lyrics", "Read the lyrics.", {"slug": {"type": "string"}}, ["slug"]),
    _tool(
        "get_treatments",
        "Read the three concepts and the chosen concept ID, if any.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "update_treatments",
        "Write exactly three structurally different concepts. Returns the saved artifact.",
        {
            "slug": {"type": "string"},
            "concepts": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string", "maxLength": 120},
                        "structure": {"type": "string", "maxLength": 80},
                        "logline": {"type": "string", "maxLength": 300},
                        "why": {"type": "string", "maxLength": 1200},
                        "world": {"type": "string", "maxLength": 1200},
                        "shape": {
                            "type": "array",
                            "minItems": 4,
                            "maxItems": 6,
                            "items": {"type": "string"},
                        },
                        "signature_moment": {"type": "string", "maxLength": 300},
                        "risk": {"type": "string", "maxLength": 800},
                    },
                    "required": [
                        "id",
                        "title",
                        "structure",
                        "logline",
                        "why",
                        "world",
                        "shape",
                        "signature_moment",
                        "risk",
                    ],
                },
            },
            "chosen_id": {"type": "string"},
        },
        ["slug", "concepts"],
    ),
    _tool(
        "get_images",
        "Inspect up to eight selected stills as thumbnails. Use this before reviewing images.",
        {
            "slug": {"type": "string"},
            "shot_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
        ["slug", "shot_ids"],
    ),
    _tool(
        "update_brief",
        "Patch the brief with an RFC 7396 JSON merge. Omit fields you do not change; "
        "direction, style and treatment cannot be blanked. Returns the new brief.",
        {"slug": {"type": "string"}, "patch": {"type": "object"}},
        ["slug", "patch"],
    ),
    _tool(
        "update_shots",
        "Edit content fields of named shots. Timing and motion are refused once an edit exists. "
        "Returns the changed IDs and the new storyboard.",
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
        "generate_images",
        "Start a paid image batch for the selected shots. Checks the production budget first.",
        {
            "slug": {"type": "string"},
            "shot_ids": {"type": "array", "items": {"type": "string"}},
            "regenerate": {"type": "boolean"},
            "scope": {"type": "string", "enum": ["proof", "stills"]},
            "reserve_usd": {"type": "string"},
            "note": {"type": "string"},
        },
        ["slug", "shot_ids"],
    ),
    _tool(
        "transcribe_lyrics",
        "Start a paid transcription when the user has no lyrics to paste.",
        {"slug": {"type": "string"}, "language": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "render",
        "Start a render job (preview or final). Free and local.",
        {"slug": {"type": "string"}, "kind": {"type": "string", "enum": ["preview", "final"]}},
        ["slug", "kind"],
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


def _root(slug: str, projects_dir: Path | None = None) -> Path:
    return (projects_dir or Path("projects")) / slug


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    runner=None,
    projects_dir: Path | None = None,
) -> str | ToolResult:
    """Dispatch a tool call. Returns JSON text or a text+images result."""
    try:
        value = _dispatch(name, arguments, runner, projects_dir)
        if isinstance(value, ToolResult):
            return value
        return json.dumps(value, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def _dispatch(
    name: str,
    arguments: dict[str, Any],
    runner=None,
    projects_dir: Path | None = None,
) -> Any:
    from mp3_to_videoclip import production as P

    root = _root(arguments["slug"], projects_dir)

    if name == "get_project":
        project = P.load_project(root)
        return {"slug": project.slug, "title": project.title, "duration": project.duration}

    if name == "get_brief":
        return P.load_brief(root).model_dump()

    if name == "get_storyboard":
        return P.load_board(root).model_dump()

    if name == "get_edit":
        from mp3_to_videoclip import edits

        return edits.summary(root)

    if name == "update_edit":
        from mp3_to_videoclip import edits

        edit = edits.save_edit(root, arguments.get("edit") or {})
        return edits.summary(root, edit)

    if name == "get_music_summary":
        from mp3_to_videoclip.domain import music_notes

        path = root / "work" / "music.json"
        if not path.is_file():
            return {"available": False}
        data = read_json(path)
        return {
            "estimated_tempo_bpm": data.get("estimated_tempo_bpm"),
            "sections": (music_notes.apply_names(data, music_notes.read(root)) or {}).get(
                "sections"
            ),
            "warnings": data.get("warnings"),
        }

    if name == "get_lyrics":
        path = root / "work" / "lyrics.json"
        return read_json(path) if path.is_file() else {"available": False}

    if name == "get_treatments":
        treatments = P.load_treatments(root)
        return treatments.model_dump() if treatments is not None else {"concepts": []}

    if name == "update_treatments":
        return P.update_treatments(
            root, {key: value for key, value in arguments.items() if key != "slug"}
        ).model_dump()

    if name == "get_images":
        return _get_images(root, arguments.get("shot_ids") or [])

    if name == "update_brief":
        patch = arguments.get("patch") or {}
        if not isinstance(patch, dict):
            raise ValueError("brief patch must be a JSON object")
        for field in ("direction", "style", "treatment"):
            if field in patch and (not isinstance(patch[field], str) or not patch[field].strip()):
                raise ValueError(f"brief {field} cannot be blank; omit it to keep the current text")
        return P.update_brief(root, patch).model_dump()

    if name == "update_shots":
        board, changed = P.update_shots(root, arguments.get("changes") or [])
        return {"changed": changed, "storyboard": board.model_dump()}

    if name == "create_storyboard":
        board = P.skeleton(
            root,
            arguments.get("seconds"),
            arguments.get("timing"),
        )
        write_json(root / "work" / "storyboard.json", board.model_dump())
        from mp3_to_videoclip import promptlog

        promptlog.record(root, "storyboard-skeleton")
        return board.model_dump()

    if name == "generate_images":
        return _generate_images(root, arguments, runner)

    if name == "transcribe_lyrics":
        return _transcribe(root, arguments, runner)

    if name == "render":
        return _render(root, arguments, runner)

    if name == "set_proof_shots":
        return {"proof_shot_ids": P.set_proof_ids(root, arguments.get("shot_ids") or [])}

    if name == "ask_user":
        return {"ask_user": arguments.get("question"), "options": arguments.get("options") or []}

    raise ValueError(f"unknown tool: {name}")


def _thumbnail(path: Path) -> tuple[str, int, int]:
    from PIL import Image

    with Image.open(path) as source:
        source.load()
        if source.mode in ("RGBA", "LA", "P"):
            rgba = source.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = source.convert("RGB")
        image.thumbnail((THUMBNAIL_PIXELS, THUMBNAIL_PIXELS))
        width, height = image.size
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", width, height


def _get_images(root: Path, shot_ids) -> ToolResult:
    from mp3_to_videoclip import production as P

    if not isinstance(shot_ids, list) or not all(isinstance(value, str) for value in shot_ids):
        return ToolResult(json.dumps({"error": "shot_ids must be a list of shot IDs"}))
    requested = list(dict.fromkeys(shot_ids))
    if not requested:
        return ToolResult(json.dumps({"error": "choose at least one shot"}))
    if len(requested) > MAX_TOOL_IMAGES:
        return ToolResult(
            json.dumps({"error": f"ask for at most {MAX_TOOL_IMAGES} shots per call"})
        )
    assets = read_optional(root / "work/assets.json", {})
    if not isinstance(assets, dict):
        assets = {}
    images: list[str] = []
    entries: list[dict] = []
    errors: list[str] = []
    for shot_id in requested:
        try:
            resolved = P.resolved_assets(root, [shot_id])[0]
            owner = resolved.shot.asset_shot_id or resolved.shot.id
            entry = assets.get(owner, {})
            data_url, width, height = _thumbnail(Path(resolved.image))
            images.append(data_url)
            entries.append(
                {
                    "shot_id": shot_id,
                    "owner": owner,
                    "version": entry.get("selected"),
                    "width": width,
                    "height": height,
                }
            )
        except (OSError, ValueError, KeyError, IndexError) as exc:
            errors.append(f"{shot_id}: {exc}")
    text = json.dumps(
        {
            "images": entries,
            "errors": errors,
            "image_count": len(images),
            "note": "Thumbnails are attached for review; no image bytes are stored in chat history.",
        }
    )
    return ToolResult(text=text, images=tuple(images))


def _generate_images(root, arguments, runner):
    from mp3_to_videoclip import services
    from mp3_to_videoclip.domain import budget

    shot_ids = arguments.get("shot_ids") or []
    if not shot_ids:
        return {"error": "shot_ids required"}
    try:
        estimate = services.generation.estimate(
            root,
            shot_ids,
            scope=arguments.get("scope", "stills"),
            reserve=arguments.get("reserve_usd", "0.05"),
            regenerate=bool(arguments.get("regenerate")),
        )
    except ValueError as exc:
        return {"error": str(exc), "needs_approval": True}
    decision = budget.check(root, estimate["reserve_usd"])
    if not decision["ok"]:
        return {"needs_budget": True, "estimate": estimate, "decision": decision}
    if estimate["uploads_required"]:
        return {
            "needs_confirmation": "reference images will be uploaded; confirm in the Images stage",
            "estimate": estimate,
        }
    if runner is None:
        return {"error": "job runner unavailable; cannot queue a paid batch"}

    services.generation.authorize(
        root,
        estimate["quote_id"],
        note=arguments.get("note") or "confirmed in director chat",
    )

    import asyncio

    async def work():
        return await asyncio.to_thread(services.generation.run, root, estimate["quote_id"])

    job_id = runner.submit("images", root.name, work)
    return {"job_id": job_id, "estimate": estimate, "status": "queued"}


def _transcribe(root, arguments, runner):
    from mp3_to_videoclip import services
    from mp3_to_videoclip.domain import budget

    quote = services.transcription.quote(root, language=arguments.get("language"))
    decision = budget.check(root, quote.get("reserve_total_usd") or quote.get("reserve_usd") or "0")
    if not decision["ok"]:
        return {"needs_budget": True, "quote": quote, "decision": decision}
    # Uploading personal audio is a separate consent; the director cannot give it.
    return {
        "needs_confirmation": "the source audio will be uploaded; confirm transcription in the Track stage",
        "quote": {key: quote.get(key) for key in ("id", "reserve_total_usd", "language")},
    }


def _render(root, arguments, runner):
    from mp3_to_videoclip import services

    kind = arguments.get("kind", "preview")
    if runner is None:
        return {"error": "job runner unavailable; cannot queue a render"}

    import asyncio

    async def work():
        fn = services.render.render_final if kind == "final" else services.render.render_preview
        return await asyncio.to_thread(fn, root)

    job_id = runner.submit("render", root.name, work)
    return {"job_id": job_id, "kind": kind, "status": "queued"}
