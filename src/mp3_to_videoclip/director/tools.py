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

from mp3_to_videoclip.storage import file_hash, inside, read_json, read_optional

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


# A skeleton cannot be rebuilt, and one giant shot cannot be split by update_shots.
MAX_SKELETON_SHOT_SECONDS = 30

#: What the Critic may call. It reads, looks and leaves notes; it can change nothing.
CRITIC_TOOLS = frozenset(
    {
        "get_project",
        "get_brief",
        "get_storyboard",
        "get_edit",
        "get_cut_material",
        "get_music_summary",
        "get_song_map",
        "get_images",
        "get_film_frames",
        "get_preview_frames",
        "save_critique",
    }
)

TOOLS: list[dict] = [
    _tool("get_project", "Read the project summary.", {"slug": {"type": "string"}}, ["slug"]),
    _tool("get_brief", "Read the brief.", {"slug": {"type": "string"}}, ["slug"]),
    _tool("get_storyboard", "Read the storyboard.", {"slug": {"type": "string"}}, ["slug"]),
    _tool(
        "get_edit",
        "Read the cut, up to 30 shots at a time. The first page also has its sections, "
        "grade and report; follow next_first for the rest.",
        {"slug": {"type": "string"}, "first": {"type": "integer"}, "count": {"type": "integer"}},
        ["slug"],
    ),
    _tool(
        "get_film_frames",
        "Look at the newest render as delivered, with grade, crops and type: up to eight "
        "film frames per call. Frames are 24 per second unless the project says otherwise.",
        {
            "slug": {"type": "string"},
            "frames": {"type": "array", "items": {"type": "integer"}, "maxItems": 8},
        },
        ["slug", "frames"],
    ),
    _tool(
        "save_critique",
        "Save the Critic's review of the newest render: a verdict and up to twelve notes, "
        "each with severity (must_fix, should_fix or consider), note, and optional shot_id, "
        "frame and suggestion. Advice only; it changes nothing.",
        {
            "slug": {"type": "string"},
            "verdict": {"type": "string"},
            "notes": {"type": "array", "items": {"type": "object"}, "maxItems": 12},
        },
        ["slug", "verdict", "notes"],
    ),
    _tool(
        "update_edit_shots",
        "Change motion, crops, accents, text or transition_in on named shots, leaving the "
        "rest of the cut alone. Returns the report.",
        {
            "slug": {"type": "string"},
            "shots": {"type": "array", "items": {"type": "object"}},
        },
        ["slug", "shots"],
    ),
    _tool(
        "update_voice_lines",
        "Set the film's spoken voiceover lines: id, text, start_frame, optional gain_db and "
        "reason, ordered by start_frame. Replaces the list. Use the user's words exactly. "
        "Making the audio is the user's decision in Studio; this only places the lines.",
        {
            "slug": {"type": "string"},
            "lines": {"type": "array", "items": {"type": "object"}},
        },
        ["slug", "lines"],
    ),
    _tool(
        "update_edit",
        "Write the edit decision list (timing, motion, transitions, accents, text, grade). "
        "Returns the saved edit and its report; fix every hard finding.",
        {"slug": {"type": "string"}, "edit": {"type": "object"}},
        ["slug", "edit"],
    ),
    _tool(
        "get_cut_material",
        "Read what the music and words offer to cut on, in film frames: named sections, sung "
        "line starts, strong changes and beat estimates.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "get_music_summary",
        "Read the measured music summary.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "set_captions",
        "Choose which timed sung lines are drawn as captions: mode off, all or named, or a "
        "list of line indexes. Saves the cut. SRT and VTT always carry every timed line.",
        {
            "slug": {"type": "string"},
            "mode": {"type": "string", "enum": ["off", "all", "named"]},
            "indexes": {"type": "array", "items": {"type": "integer"}},
        },
        ["slug"],
    ),
    _tool(
        "get_song_map",
        "Read the song map in film frames: tempo with its octave rival, key, bars, downbeats, "
        "beats, sections with energy words, density targets and first sung lines, and changes.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool("get_lyrics", "Read the lyrics.", {"slug": {"type": "string"}}, ["slug"]),
    _tool(
        "get_treatments",
        "Read the concepts and the chosen concept ID, if any.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "update_treatments",
        "Write one to three structurally different concepts, including any you keep. "
        "Returns the saved artifact.",
        {
            "slug": {"type": "string"},
            "concepts": {
                "type": "array",
                "minItems": 1,
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
                        "beats": {
                            "type": "array",
                            "minItems": 4,
                            "maxItems": 6,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"},
                                    "label": {"type": "string", "maxLength": 60},
                                    "text": {"type": "string", "maxLength": 400},
                                },
                                "required": ["start", "end", "label", "text"],
                            },
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
                        "beats",
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
        "get_idea",
        "Read the user's newest pasted idea, exactly as written, and how it is sorted.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "sort_idea",
        "Say which of the user's own sentences are story, style, rules or things to avoid. "
        "Copy them word for word: anything not in the paste, used twice or left out is "
        "refused. Saves them to the brief and returns the saved idea.",
        {
            "slug": {"type": "string"},
            "story": {"type": "array", "items": {"type": "string"}},
            "style": {"type": "array", "items": {"type": "string"}},
            "rules": {"type": "array", "items": {"type": "string"}},
            "avoid": {"type": "array", "items": {"type": "string"}},
        },
        ["slug", "story", "style", "rules", "avoid"],
    ),
    _tool(
        "place_story",
        "Say when each passage of brief.treatment plays. Together the passages must hold "
        "every word of the treatment, unchanged and in order; times are seconds from the "
        "film's first frame. Does not change the story or its approval.",
        {
            "slug": {"type": "string"},
            "passages": {
                "type": "array",
                "minItems": 1,
                "maxItems": 40,
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "text": {"type": "string"},
                    },
                    "required": ["start", "end", "text"],
                },
            },
        },
        ["slug", "passages"],
    ),
    _tool(
        "get_images",
        "Inspect up to eight selected stills as thumbnails. Use this before reviewing images.",
        {
            "slug": {"type": "string"},
            "shot_ids": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": "Shot ids, reference ids, character:<id> or sheet:<id>.",
            },
        },
        ["slug", "shot_ids"],
    ),
    _tool(
        "propose_alternatives",
        "Offer the owner two or three versions of one field and let them choose. Nothing is "
        "written. Use it when the choice is theirs; then stop and wait.",
        {
            "slug": {"type": "string"},
            "target": {"type": "string", "description": "Such as shots.s004.image_prompt."},
            "options": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        ["slug", "target", "options"],
    ),
    _tool(
        "batch_update_prompts",
        "Change many shots' image prompts as one change, validated as a whole board.",
        {
            "slug": {"type": "string"},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "image_prompt": {"type": "string"}},
                    "required": ["id", "image_prompt"],
                },
            },
        },
        ["slug", "changes"],
    ),
    _tool(
        "describe_images",
        "One or two plain sentences per still, from your vision model; cached per still.",
        {
            "slug": {"type": "string"},
            "shot_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
        ["slug", "shot_ids"],
    ),
    _tool(
        "compare_versions",
        "Two versions of one shot as thumbnails, with what differed in how they were made.",
        {
            "slug": {"type": "string"},
            "shot_id": {"type": "string"},
            "a": {"type": "integer"},
            "b": {"type": "integer"},
        },
        ["slug", "shot_id", "a", "b"],
    ),
    _tool(
        "get_preview_frames",
        "Frames of the latest preview at the given seconds, as thumbnails.",
        {
            "slug": {"type": "string"},
            "seconds": {"type": "array", "items": {"type": "number"}, "maxItems": 8},
        },
        ["slug", "seconds"],
    ),
    _tool(
        "get_script",
        "Read a story film's script and its structure's beats with their budgets.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "write_script",
        "Write a story film's whole script. Refused after its approval unless revising is true, "
        "which you only send when the owner asked for a revision. Every invented fact is a claim "
        "with invented true, and only a fictional world may have one.",
        {
            "slug": {"type": "string"},
            "structure": {"type": "string"},
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "beat": {"type": "string"},
                        "target_seconds": {"type": "number"},
                        "pause_after": {"type": "number"},
                        "direction": {"type": "string"},
                        "claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "invented": {"type": "boolean"},
                                },
                                "required": ["text"],
                            },
                        },
                    },
                    "required": ["id", "text", "beat"],
                },
            },
            "notes": {"type": "string"},
            "revising": {"type": "boolean"},
        },
        ["slug", "structure", "lines"],
    ),
    _tool(
        "update_lines",
        "Change named lines of a story film's script. A changed line's take goes stale, and "
        "re-recording it costs money, so say which ones you changed.",
        {
            "slug": {"type": "string"},
            "changes": {"type": "array", "items": {"type": "object"}},
            "revising": {"type": "boolean"},
        },
        ["slug", "changes"],
    ),
    _tool(
        "get_narration",
        "Read a story film's takes, its timing, and each beat's budget against the real takes. "
        "Nothing here spends: the owner records from the Script stage.",
        {"slug": {"type": "string"}},
        ["slug"],
    ),
    _tool(
        "update_brief",
        "Patch the brief with an RFC 7396 JSON merge. Omit fields you do not change; "
        "direction, style and treatment cannot be blanked. Returns the new brief. "
        "Use set_creative_profile for characters, scenes, image rules, avoid and look.",
        {"slug": {"type": "string"}, "patch": {"type": "object"}},
        ["slug", "patch"],
    ),
    _tool(
        "set_creative_profile",
        "Create or replace the film's cast, places, arc, global image rules, avoid list "
        "and compact rendering look. Call once after the treatment, before the storyboard. "
        "Characters carry identity and changeable states; never repeat identity or wardrobe "
        "in shot prompts. Only the owner can confirm permission to depict someone: the result "
        "lists anyone still waiting in owner_must_confirm, so ask the owner about them.",
        {
            "slug": {"type": "string"},
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "identity": {
                            "type": "string",
                            "description": "One line: age, build, skin, hair, eyes. No wardrobe.",
                        },
                        "description": {"type": "string"},
                        "states": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "attributes": {
                                        "type": "object",
                                        "additionalProperties": {"type": "string"},
                                    },
                                    "references": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["description"],
                            },
                        },
                        "default_state": {"type": "string"},
                        "references": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "identity"],
                },
            },
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "Place, time and light; no plot or cast.",
                        },
                        "reference_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "description"],
                },
            },
            "arc": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "phase": {"type": "string"},
                        "intention": {"type": "string"},
                    },
                    "required": ["phase", "intention"],
                },
            },
            "image_rules": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 6,
            },
            "avoid": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "sections": {
                "type": "array",
                "description": "Optional colour script: one palette and light per song section.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "palette": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                        "light": {"type": "string"},
                        "lens": {"type": "string"},
                    },
                    "required": ["id", "start", "end", "palette", "light"],
                },
            },
            "narrator": {
                "type": "object",
                "properties": {
                    "persona": {"type": "string"},
                    "era": {"type": "string"},
                    "attitude": {"type": "string"},
                    "gets_wrong": {"type": "string"},
                    "voice_id": {"type": "string"},
                    "real_person": {"type": "boolean"},
                },
                "required": ["persona"],
            },
            "place": {
                "type": "object",
                "properties": {"description": {"type": "string"}, "camera": {"type": "string"}},
                "required": ["description"],
            },
            "eras": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "year": {"type": "string"},
                        "state": {"type": "string"},
                        "palette": {"type": "array", "items": {"type": "string"}},
                        "light": {"type": "string"},
                        "persists": {"type": "string"},
                        "changed": {"type": "string"},
                    },
                    "required": ["id", "year", "state"],
                },
            },
            "look": {
                "type": "string",
                "description": "Rendering only, 90-150 words. With a style preset: send the current "
                "look unchanged, or the preset's words verbatim plus at most 60 words.",
            },
        },
        ["slug", "characters", "scenes", "arc", "image_rules", "avoid", "look"],
    ),
    _tool(
        "update_shots",
        "Edit content fields of named shots. Timing and motion are refused once an edit exists. "
        "It cannot add or remove shots; use write_storyboard for that. Returns the changed "
        "shots and the board's size.",
        {"slug": {"type": "string"}, "changes": {"type": "array", "items": {"type": "object"}}},
        ["slug", "changes"],
    ),
    _tool(
        "write_storyboard",
        "Replace the whole shot list so the board has the shots its story needs, adding, "
        "removing or retiming freely. Send every shot; together they must cover the film "
        "exactly. Refused once a cut exists, or if it drops a shot with paid stills. "
        "Returns the board's size and each shot's id, span and kind.",
        {"slug": {"type": "string"}, "shots": {"type": "array", "items": {"type": "object"}}},
        ["slug", "shots"],
    ),
    _tool(
        "create_storyboard",
        "Build the film's timing skeleton once; it cannot be rebuilt afterwards. Leave "
        "seconds and timing out unless you have a reason: the defaults follow the music.",
        {
            "slug": {"type": "string"},
            "seconds": {
                "type": "number",
                "description": "Target length of ONE shot, not of the film.",
                "maximum": MAX_SKELETON_SHOT_SECONDS,
            },
            "timing": {"type": "string", "enum": ["adaptive", "beats", "events", "free"]},
        },
        ["slug"],
    ),
    _tool(
        "generate_images",
        "Price a paid image batch for the selected shots. It buys nothing: the owner buys it "
        "with the button this puts in the conversation.",
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
        "Price a paid transcription. It cannot be run from the Studio.",
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


#: A schema's words are for a reader; past this they only cost tokens on every turn.
MAX_SCHEMA_DESCRIPTION = 120


def _lean_schema(schema: dict) -> dict:
    """A model's JSON schema with its references inlined and its titles and long notes gone."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
        kept = {}
        for key, value in node.items():
            # The server validates these; a model only needs the shape and the choices.
            if key in ("title", "$defs", "default", "maxLength", "minLength", "pattern", "maxItems", "minItems"):  # fmt: skip
                continue
            if key == "description" and len(str(value)) > MAX_SCHEMA_DESCRIPTION:
                continue
            kept[key] = (
                walk(value) if key != "properties" else {k: walk(v) for k, v in value.items()}
            )
        return kept

    return walk(schema)


def _typed_tools() -> None:
    """The tools a model writes the cut and the board with, typed from the contract."""
    from mp3_to_videoclip import edits
    from mp3_to_videoclip.models import EditDecisionList, EditShot, Shot

    shot = _lean_schema(Shot.model_json_schema())
    shot["properties"] = {
        key: value for key, value in shot["properties"].items() if key not in edits.EDIT_OWNED
    }
    shot["required"] = ["id"]
    edit_shot = _lean_schema(EditShot.model_json_schema())
    edit_shot["properties"] = {
        key: value
        for key, value in edit_shot["properties"].items()
        if key in {*edits.EDITABLE_SHOT_FIELDS, "shot_id"}
    }
    edit_shot["required"] = ["shot_id"]
    cut = _lean_schema(EditDecisionList.model_json_schema())
    # The whole cut's items are what update_edit_shots already spells out in full.
    cut["properties"]["shots"]["items"] = {
        "type": "object",
        "description": "shot_id, start_frame, duration_frames and the fields of update_edit_shots",
    }
    cut["properties"]["grade"] = {"type": "object", "description": "preset, strength, look, typeface"}  # fmt: skip
    cut["properties"]["sections"] = {"type": "array", "items": {"type": "object"}}
    cut["properties"]["voice"] = {"type": "array", "items": {"type": "object"}}
    for tool in TOOLS:
        function = tool["function"]
        properties = function["parameters"]["properties"]
        if function["name"] == "update_shots":
            properties["changes"] = {"type": "array", "items": shot}
        elif function["name"] == "update_edit_shots":
            properties["shots"] = {"type": "array", "items": edit_shot}
        elif function["name"] == "update_edit":
            properties["edit"] = cut


def _with_reasons() -> None:
    """Every write says why, in the owner's hearing."""
    from .decisions import MAX_REASON, WRITE_TOOLS

    for tool in TOOLS:
        function = tool["function"]
        if function["name"] in WRITE_TOOLS:
            function["parameters"]["properties"]["reason"] = {
                "type": "string",
                "maxLength": MAX_REASON,
                "description": "Why, in one plain sentence the owner would understand.",
            }
            function["parameters"]["required"] = [*function["parameters"]["required"], "reason"]


_typed_tools()
_with_reasons()
#: Past this a result is cut down to what changed; the artifact is one get_ call away.
MAX_WRITE_RESULT = 2000


def _recorded_write(
    root: Path,
    name: str,
    arguments: dict[str, Any],
    run,
    *,
    role: str | None,
    turn_id: str | None,
    prompt_hash: str | None,
    require_reason: bool,
) -> Any:
    from . import decisions

    reason = str(arguments.get("reason") or "").strip()
    if require_reason and not reason:
        raise ValueError("say why in reason, in one plain sentence; nothing was changed")
    if len(reason) > decisions.MAX_REASON:
        raise ValueError(f"keep the reason to {decisions.MAX_REASON} characters")
    before = decisions.snapshot(root, name)
    value = run()
    changes = decisions.diff(before, decisions.snapshot(root, name))
    identifier = decisions.record(
        root,
        turn_id=turn_id,
        role=role,
        tool=name,
        reason=reason,
        changes=changes,
        prompt_hash=prompt_hash,
    )
    fields = sorted(changes)
    if isinstance(value, dict):
        extra = {"changed_fields": fields, "reason": reason, "decision_id": identifier}
        if require_reason and len(json.dumps(value, ensure_ascii=False)) > MAX_WRITE_RESULT:
            kept = {
                key: item
                for key, item in value.items()
                if isinstance(item, (int, float, bool))
                or item is None
                or (isinstance(item, str) and len(item) <= 200)
            }
            return {**kept, **extra, "note": "The whole artifact is one get_ call away."}
        return {**value, **extra}
    return value


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    runner=None,
    projects_dir: Path | None = None,
    *,
    role: str | None = None,
    turn_id: str | None = None,
    prompt_hash: str | None = None,
    require_reason: bool = False,
) -> str | ToolResult:
    """Dispatch a tool call. Returns JSON text or a text+images result.

    A real turn passes ``require_reason``; a write without one changes nothing.
    """
    from .decisions import WRITE_TOOLS

    try:
        if name == "describe_images":
            value = await _describe_images(
                _root(arguments["slug"], projects_dir), arguments.get("shot_ids") or [], role
            )
        elif name in WRITE_TOOLS:
            value = _recorded_write(
                _root(arguments["slug"], projects_dir),
                name,
                arguments,
                lambda: _dispatch(name, arguments, runner, projects_dir),
                role=role,
                turn_id=turn_id,
                prompt_hash=prompt_hash,
                require_reason=require_reason,
            )
        else:
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

        return edits.tool_page(root, arguments.get("first") or 0, arguments.get("count") or 30)

    if name == "get_film_frames":
        return _get_film_frames(root, arguments.get("frames") or [])

    if name == "save_critique":
        from mp3_to_videoclip import critique

        return critique.save(
            root,
            arguments.get("verdict") or "",
            arguments.get("notes") or [],
            P.load_project(root).fps,
        )

    if name == "update_edit_shots":
        from mp3_to_videoclip import edits

        return edits.patch_shots(root, arguments.get("shots") or [])

    if name == "update_voice_lines":
        from mp3_to_videoclip import edits

        return edits.set_voice_lines(root, arguments.get("lines") or [])

    if name == "get_cut_material":
        from mp3_to_videoclip import edits

        return edits.cut_material(root)

    if name == "update_edit":
        from mp3_to_videoclip import edits

        edit = edits.save_edit(root, arguments.get("edit") or {})
        return {"saved": True, "report": edits._tool_report(edits.report(root, edit=edit))}

    if name == "set_captions":
        from mp3_to_videoclip import edits

        return edits.apply_captions(root, arguments.get("indexes"), mode=arguments.get("mode"))

    if name == "get_song_map":
        from mp3_to_videoclip import song_map

        return song_map.song_map(root)

    if name == "get_music_summary":
        from mp3_to_videoclip.domain import section_map

        path = root / "work" / "music.json"
        if not path.is_file():
            return {"available": False}
        data = read_json(path)
        return {
            "estimated_tempo_bpm": data.get("estimated_tempo_bpm"),
            "sections": (section_map.apply(root, data) or {}).get("sections"),
            "warnings": data.get("warnings"),
        }

    if name == "get_lyrics":
        from mp3_to_videoclip.domain import lyric_timing

        path = root / "work" / "lyrics.json"
        if not path.is_file():
            return {"available": False}
        lines = lyric_timing.view(root)["lines"]
        timed = [
            {"text": line["text"], "start": line["start"], "source": line["source"]}
            for line in lines
            if line["start"] is not None
        ]
        if not timed:
            return read_json(path)
        return {
            **read_json(path),
            "line_times": timed,
            "line_times_note": "Automatic times are estimates; tapped times are the owner's.",
        }

    if name == "get_treatments":
        treatments = P.load_treatments(root)
        return treatments.model_dump() if treatments is not None else {"concepts": []}

    if name == "update_treatments":
        payload = {key: value for key, value in arguments.items() if key != "slug"}
        # A model with no choice to report tends to send an empty string for this field.
        if not payload.get("chosen_id"):
            payload["chosen_id"] = None
        return P.update_treatments(root, payload).model_dump()

    if name == "get_idea":
        from mp3_to_videoclip import idea

        return idea.latest(root) or {"available": False}

    if name == "sort_idea":
        from mp3_to_videoclip import idea

        parts = {key: arguments.get(key) or [] for key in idea.PARTS}
        return idea.apply_sort(root, parts, by="writer")

    if name == "place_story":
        from mp3_to_videoclip import story_beats

        placement = story_beats.place_story(root, {"passages": arguments.get("passages")})
        return {"placed": len(placement.passages)}

    if name == "get_images":
        return _get_images(root, arguments.get("shot_ids") or [])

    if name in ("get_script", "write_script", "update_lines", "get_narration"):
        return _script_tool(root, name, arguments)

    if name == "propose_alternatives":
        return _propose(arguments)

    if name == "batch_update_prompts":
        return _batch_prompts(root, arguments.get("changes") or [])

    if name == "compare_versions":
        return _compare_versions(root, arguments)

    if name == "get_preview_frames":
        return _preview_frames(root, arguments.get("seconds") or [])

    if name == "update_brief":
        patch = arguments.get("patch") or {}
        if not isinstance(patch, dict):
            raise ValueError("brief patch must be a JSON object")
        for field in ("direction", "style", "treatment"):
            if field in patch and (not isinstance(patch[field], str) or not patch[field].strip()):
                raise ValueError(f"brief {field} cannot be blank; omit it to keep the current text")
        before = P.out_of_date_stills(root) if (root / "work/storyboard.json").is_file() else []
        return _with_still_cost(root, before, _brief_result(P.update_brief(root, patch)))

    if name == "set_creative_profile":
        before = P.out_of_date_stills(root) if (root / "work/storyboard.json").is_file() else []
        return _with_still_cost(
            root,
            before,
            _brief_result(
                P.set_creative_profile(
                    root,
                    characters=arguments.get("characters") or [],
                    scenes=arguments.get("scenes") or [],
                    arc=arguments.get("arc") or [],
                    image_rules=arguments.get("image_rules") or [],
                    avoid=arguments.get("avoid") or [],
                    look=arguments.get("look") or "",
                    sections=arguments.get("sections"),
                    narrator=arguments.get("narrator"),
                    place=arguments.get("place"),
                    eras=arguments.get("eras"),
                )
            ),
        )

    if name == "update_shots":
        before = P.out_of_date_stills(root)
        board, changed = P.update_shots(root, arguments.get("changes") or [])
        # A whole board can outgrow what a client carries back to the model.
        return _with_still_cost(
            root,
            before,
            {
                "changed": changed,
                "shots": [shot.model_dump() for shot in board.shots if shot.id in changed],
                "shot_total": len(board.shots),
            },
        )

    if name == "write_storyboard":
        from mp3_to_videoclip import shotkinds

        board = P.write_storyboard(root, arguments.get("shots") or [])
        return {
            "saved": True,
            "shot_total": len(board.shots),
            "paid": sum(1 for shot in board.shots if shotkinds.is_paid(shot)),
            "total_frames": board.total_frames,
            "shots": [
                {
                    "id": shot.id,
                    "start_frame": shot.start_frame,
                    "duration_frames": shot.duration_frames,
                    "kind": shot.kind,
                }
                for shot in board.shots
            ],
        }

    if name == "create_storyboard":
        seconds = arguments.get("seconds")
        if seconds is not None and seconds > MAX_SKELETON_SHOT_SECONDS:
            raise ValueError(
                f"seconds is the length of one shot, at most {MAX_SKELETON_SHOT_SECONDS}; "
                "leave it out to follow the music"
            )
        board = P.skeleton(
            root,
            arguments.get("seconds"),
            arguments.get("timing"),
        )
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


def _with_still_cost(root: Path, before: list[str], value: dict) -> dict:
    """Say plainly when a change just made kept stills out of date."""
    from mp3_to_videoclip import production as P

    try:
        lost = [shot for shot in P.out_of_date_stills(root) if shot not in before]
    except (OSError, ValueError):
        return value
    if lost:
        value["stills_now_out_of_date"] = lost
        value["warning"] = (
            f"This change made {len(lost)} kept stills out of date, and each costs money to remake. "
            "Tell the user. If only some shots need it, undo this and change those shots' prompts."
        )
    return value


def _brief_result(brief) -> dict:
    from mp3_to_videoclip import production as P

    value = brief.model_dump()
    waiting = P.unconfirmed_permissions(brief)
    if waiting:
        value["owner_must_confirm"] = waiting
    return value


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


def _propose(arguments: dict) -> dict:
    """Two or three versions of one field, written nowhere: the owner chooses one."""
    options = arguments.get("options") or []
    if not 2 <= len(options) <= 3 or not all(isinstance(o, str) and o.strip() for o in options):
        raise ValueError("offer two or three options, each as text")
    if not str(arguments.get("target") or "").strip():
        raise ValueError("say which field these are options for")
    return {
        "target": arguments["target"],
        "options": options,
        "note": "Nothing was written. Stop here and let the owner choose.",
    }


def _batch_prompts(root: Path, changes: list) -> dict:
    """Many shots' prompts as one change, validated as a whole board."""
    from mp3_to_videoclip import production as P

    if not isinstance(changes, list) or not changes:
        raise ValueError("name at least one shot")
    extra = [c for c in changes if not isinstance(c, dict) or set(c) != {"id", "image_prompt"}]
    if extra:
        raise ValueError("each change is exactly an id and an image_prompt")
    board, changed = P.update_shots(root, changes)
    return {"changed": changed, "shot_total": len(board.shots)}


def _version_spec(root: Path, shot_id: str, version: int) -> tuple[dict, dict]:
    assets = read_optional(root / "work/assets.json", {})
    take = next(
        (v for v in (assets.get(shot_id) or {}).get("versions", []) if v["version"] == version),
        None,
    )
    if take is None:
        raise ValueError(f"shot {shot_id} has no version {version}")
    task = read_optional(root / "work/tasks.json", {}).get(take.get("task_id")) or {}
    request = task.get("request") or {}
    return take, {
        "prompt": request.get("positivePrompt"),
        "seed": request.get("seed"),
        "references": [ref.get("path") for ref in task.get("references", [])],
        "input_hash": take.get("input_hash"),
    }


def _compare_versions(root: Path, arguments: dict) -> ToolResult:
    from .decisions import diff

    shot_id = str(arguments.get("shot_id"))
    first, second = arguments.get("a"), arguments.get("b")
    take_a, spec_a = _version_spec(root, shot_id, first)
    take_b, spec_b = _version_spec(root, shot_id, second)
    images = [_thumbnail(inside(root, take["path"]))[0] for take in (take_a, take_b)]
    changes = {field: {"a": a, "b": b} for field, (a, b) in diff(spec_a, spec_b).items()}
    text = json.dumps({"shot_id": shot_id, "a": first, "b": second, "differences": changes})
    return ToolResult(text=text, images=tuple(images))


def _preview_frames(root: Path, seconds: list) -> ToolResult:
    """Frames of the latest preview, for an Editor who wants to look at the film itself."""
    import subprocess
    import tempfile

    from mp3_to_videoclip.audio import _ffmpeg

    if not isinstance(seconds, list) or not seconds or len(seconds) > MAX_TOOL_IMAGES:
        raise ValueError(f"ask for one to {MAX_TOOL_IMAGES} moments, in seconds")
    previews = sorted((root / "previews").glob("*.mp4"), key=lambda path: path.stat().st_mtime)
    if not previews:
        raise ValueError("there is no preview yet")
    images = []
    with tempfile.TemporaryDirectory(prefix="preview-frames-") as folder:
        for index, moment in enumerate(seconds):
            target = Path(folder) / f"{index}.jpg"
            subprocess.run(
                [
                    _ffmpeg(),
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(float(moment)),
                    "-i",
                    str(previews[-1]),
                    "-frames:v",
                    "1",
                    str(target),
                ],  # fmt: skip
                capture_output=True,
                check=True,
            )
            images.append(_thumbnail(target)[0])
    text = json.dumps(
        {"preview": previews[-1].name, "seconds": seconds, "image_count": len(images)}
    )
    return ToolResult(text=text, images=tuple(images))


async def _describe_images(root: Path, shot_ids: list, role: str | None) -> dict:
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.config import effective_settings

    from . import captions
    from .routing import route_for

    if not isinstance(shot_ids, list) or not shot_ids or len(shot_ids) > MAX_TOOL_IMAGES:
        raise ValueError(f"ask for one to {MAX_TOOL_IMAGES} stills")
    who = role if role in ("writer", "editor", "critic") else "writer"
    route = route_for(effective_settings(), who)
    if not route.key:
        raise ValueError(f"the {who} has no key for {route.model}")
    rows = []
    for shot_id in shot_ids:
        resolved = P.resolved_assets(root, [shot_id])[0]
        path = Path(resolved.image)
        rows.append(
            await captions.describe(root, route, shot_id, file_hash(path), _thumbnail(path)[0], who)
        )
    return {"captions": rows}


def _script_tool(root: Path, name: str, arguments: dict) -> dict:
    from mp3_to_videoclip import narration, narration_timing, structures
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.production import script as scripts

    if P.load_project(root, verify_source=False).spine != "soundtrack":
        raise ValueError("only a story film has a script")
    if name == "get_script":
        script = scripts.load_script(root)
        intent = P.load_brief(root).intent
        return {
            "script": script.model_dump() if script else None,
            "beats": scripts.read_beats(root)
            or structures.instance(
                (intent.structure if intent else None) or structures.DEFAULT,
                float((intent.length_seconds if intent else None) or 0),
            ),
        }
    if name == "get_narration":
        return {
            "takes": narration.view(root),
            "timing": narration_timing.read(root),
            "report": scripts.script_report(root),
        }
    # Writing a line after its approval un-approves what stands on it: only on the owner's word.
    approved = "script" in read_json(root / "work/approvals.json")
    if approved and not arguments.get("revising"):
        raise ValueError("the script is approved; change it only if the owner asks for a revision")
    if name == "write_script":
        script = scripts.write_script(
            root,
            {
                "structure": arguments.get("structure"),
                "lines": arguments.get("lines") or [],
                "notes": arguments.get("notes") or "",
            },
        )
    else:
        script = scripts.update_lines(root, arguments.get("changes") or [])
    return {"saved": True, "lines": len(script.lines), "report": scripts.script_report(root)}


def _world_picture(root: Path, name: str, assets: dict) -> Path | None:
    """The file behind a reference, character or sheet id; ``None`` means it names a shot."""
    from mp3_to_videoclip import production as P

    brief = P.load_brief(root)
    if name.startswith("sheet:"):
        entry = assets.get(name) or {}
        chosen = next(
            (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None
        )
        if chosen is None:
            raise ValueError("no sheet has been made for it")
        return inside(root, chosen["path"])
    if name.startswith("character:"):
        wanted = name.removeprefix("character:")
        character = next((item for item in brief.characters if item.id == wanted), None)
        if character is None or not character.references:
            raise ValueError("this character has no reference image")
        return inside(root, character.references[0])
    creative = brief.creative
    reference = next((r for r in creative.references if r.id == name), None) if creative else None
    return inside(root, reference.path) if reference is not None else None


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
            picture = _world_picture(root, shot_id, assets)
            if picture is not None:
                data_url, width, height = _thumbnail(picture)
                images.append(data_url)
                entries.append({"id": shot_id, "width": width, "height": height})
                continue
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


def _get_film_frames(root: Path, frames) -> ToolResult:
    from mp3_to_videoclip import critique
    from mp3_to_videoclip import production as P

    try:
        value = critique.film_frames(root, frames, P.load_project(root).fps)
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult(json.dumps({"error": str(exc)}))
    images = tuple(
        "data:image/jpeg;base64," + base64.b64encode(item["jpeg"]).decode("ascii")
        for item in value["frames"]
    )
    return ToolResult(
        text=json.dumps(
            {
                "render": value["render"],
                "cut_is_current": value["cut_is_current"],
                "frames": [
                    {"frame": item["frame"], "seconds": item["seconds"]} for item in value["frames"]
                ],
                "image_count": len(images),
                "note": "Frames are attached in this order.",
            }
        ),
        images=images,
    )


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
    # The Director asks; spending is the owner's click on this price.
    return {
        "needs_owner": True,
        "estimate": estimate,
        "message": (
            f"{estimate['tasks']} stills, up to ${estimate['reserve_usd']}. "
            "The owner buys them with the button in this conversation."
        ),
    }


def _transcribe(root, arguments, runner):
    from mp3_to_videoclip import services
    from mp3_to_videoclip.domain import budget

    quote = services.transcription.quote(root, language=arguments.get("language"))
    decision = budget.check(root, quote.get("reserve_total_usd") or quote.get("reserve_usd") or "0")
    if not decision["ok"]:
        return {"needs_budget": True, "quote": quote, "decision": decision}
    # Uploading personal audio is a separate consent; the director cannot give it.
    return {
        "needs_confirmation": (
            "transcription uploads the source audio and can't be started in the Studio; ask the "
            "owner to paste the words in Track, or to run it from the command line"
        ),
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

    job_id = runner.submit("render", root.name, work, blocking=True, render_kind=kind)
    return {"job_id": job_id, "kind": kind, "status": "queued"}


def tools_for(role: str | None) -> list[dict]:
    """The tool list one role is offered."""
    if role != "critic":
        return TOOLS
    return [tool for tool in TOOLS if tool["function"]["name"] in CRITIC_TOOLS]
