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

from mp3_to_videoclip.storage import inside, read_json, read_optional

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
