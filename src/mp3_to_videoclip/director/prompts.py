"""Assemble the Writer/Editor prompt for one task, with a traceable revision.

The layout is fixed: role system, shared truth, production kind, style preset
(Writer only), one task file and its worked example. Project data is appended by
the API and is not part of the word budget. Every file declares a front-matter
``version``; the assembled hash and those versions travel with the chat turn and
each artifact write.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..storage import digest, read_optional

PROMPTS = Path(__file__).resolve().parent / "prompts"
Role = Literal["writer", "editor"]

STAGE_ROLE: dict[str, Role] = {
    "track": "editor",
    "story": "writer",
    "storyboard": "writer",
    "images": "writer",
    "film": "editor",
}

TASKS: dict[Role, dict[str, str]] = {
    "writer": {
        "brief": "writer/brief.md",
        "concepts": "writer/concepts.md",
        "script_mv": "writer/script_mv.md",
        "script_ad": "writer/script_ad.md",
        "profile": "writer/profile.md",
        "storyboard": "writer/storyboard.md",
        "prompts": "writer/prompts.md",
        "review": "writer/review.md",
        "revise": "writer/revise.md",
    },
    "editor": {
        "music": "editor/music.md",
        "notes": "editor/notes.md",
        "edit": "editor/edit.md",
        "post": "editor/post.md",
    },
}

EXAMPLES = {
    "brief": "examples/brief.md",
    "concepts": "examples/concepts.md",
    "script_mv": "examples/script_mv.md",
    "script_ad": "examples/script_ad.md",
    "profile": "examples/profile.md",
    "storyboard": "examples/storyboard.md",
    "prompts": "examples/prompts.md",
    "review": "examples/review.md",
    "revise": "examples/revise.md",
}


@dataclass(frozen=True)
class PromptBundle:
    text: str
    meta: dict
    task: str
    role: Role
    stage: str | None


def _split(text: str, path: Path) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: prompt file needs a --- header")
    try:
        header, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path.name}: prompt header is not closed") from exc
    meta: dict = {}
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            raise ValueError(f"{path.name}: malformed header line {line!r}")
        raw = raw.strip()
        if raw[:1] in '[{"' or raw in ("true", "false", "null"):
            try:
                meta[key.strip()] = json.loads(raw)
                continue
            except json.JSONDecodeError:
                pass
        meta[key.strip()] = raw.strip('"')
    if "version" not in meta:
        raise ValueError(f"{path.name}: prompt files need a version")
    return meta, body.strip()


def _version(path: Path) -> int:
    meta, _ = _split(path.read_text(), path)
    return int(meta["version"])


def _json(root: Path, relative: str) -> dict:
    value = read_optional(root / relative)
    return value if isinstance(value, dict) else {}


def role_for_stage(stage: str | None) -> Role:
    return STAGE_ROLE.get(stage or "", "writer")


def select_task(root: Path, stage: str | None, role: Role) -> str:
    """Deterministic task choice from the stage and the artifacts already written."""
    if stage == "track":
        return "music"
    if stage == "storyboard":
        return "notes" if role == "editor" else "storyboard"
    if stage == "film":
        return "edit"
    if stage == "images":
        assets = _json(root, "work/assets.json")
        has_selected = any(
            isinstance(entry, dict) and entry.get("selected") is not None
            for entry in assets.values()
        )
        return "review" if has_selected else "prompts"
    if stage == "story":
        if role == "editor":
            return "notes"
        brief = _json(root, "brief.json")
        project = _json(root, "project.json")
        kind = project.get("kind") or "music_video"
        intent = brief.get("intent") if isinstance(brief.get("intent"), dict) else {}
        missing = not intent
        if kind in ("promo", "advert"):
            missing = missing or not all(
                str(intent.get(key) or "").strip() for key in ("objective", "message")
            )
            cta = intent.get("cta") if isinstance(intent.get("cta"), dict) else {}
            missing = missing or not str(cta.get("text") or "").strip()
        if missing:
            return "brief"
        treatments = _json(root, "work/treatments.json")
        concepts = treatments.get("concepts") or treatments.get("treatments") or []
        if not isinstance(concepts, list) or len(concepts) < 3:
            return "concepts"
        if not treatments.get("chosen_id"):
            return "concepts"
        if not brief.get("script"):
            return "script_ad" if kind in ("promo", "advert") else "script_mv"
        creative = brief.get("creative") if isinstance(brief.get("creative"), dict) else {}
        if int(creative.get("profile_version") or 0) < 1:
            return "profile"
        return "revise"
    return "revise"


def _style_path(style_preset: str) -> Path | None:
    for path in sorted((PROMPTS / "styles").glob("*.md")):
        meta, _ = _split(path.read_text(), path)
        if meta.get("id") == style_preset:
            return path
    return None


def assemble(
    root: Path,
    stage: str | None,
    *,
    role: str | None = None,
    kind: str | None = None,
    style_preset: str | None = None,
    task: str | None = None,
) -> PromptBundle:
    role_value: Role = role if role in ("writer", "editor") else role_for_stage(stage)
    project = _json(root, "project.json")
    kind_value = kind or project.get("kind") or "music_video"
    style_value = style_preset if style_preset is not None else project.get("style_preset")
    task_value = task or select_task(root, stage, role_value)
    if task_value not in TASKS[role_value]:
        raise ValueError(f"unknown {role_value} task {task_value!r}")

    files = [
        f"{role_value}/system.md",
        "shared/truth.md",
        f"kinds/{kind_value}.md",
    ]
    if role_value == "writer" and style_value:
        style_path = _style_path(style_value)
        if style_path is not None:
            files.append(style_path.relative_to(PROMPTS).as_posix())
    files.append(TASKS[role_value][task_value])
    example = EXAMPLES.get(task_value)
    if example and (PROMPTS / example).is_file():
        files.append(example)

    blocks: list[str] = []
    versions: list[dict] = []
    for relative in files:
        path = PROMPTS / relative
        if not path.is_file():
            raise FileNotFoundError(f"prompt file missing: {relative}")
        meta, body = _split(path.read_text(), path)
        if relative.startswith("styles/"):
            body = f"## Style preset\n\n{body}"
            if meta.get("protected") is True:
                body += (
                    "\n\nThis preset core is protected: keep it verbatim at the start "
                    "of creative.look and append film-specific additions after a blank "
                    "line. If the owner brings a different master style, ask them to "
                    "switch Story \u2192 Look to Custom before you save it; never rewrite "
                    "this core."
                )
        elif relative.startswith("examples/"):
            body = f"## Example\n\n{body}"
        blocks.append(body)
        versions.append({"path": relative, "version": _version(path)})
    text = "\n\n---\n\n".join(blocks)
    meta = {
        "hash": digest(text),
        "files": versions,
        "task": task_value,
        "role": role_value,
        "stage": stage,
        "kind": kind_value,
        "style_preset": style_value if role_value == "writer" else None,
        "words": len(text.split()),
    }
    return PromptBundle(text=text, meta=meta, task=task_value, role=role_value, stage=stage)
