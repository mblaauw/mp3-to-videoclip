"""Director chat: one streaming turn per request, persisted to work/chat.jsonl."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from mp3_to_videoclip import production as P
from mp3_to_videoclip import promptlog
from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.api.errors import ApiError
from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director import prompts as prompt_suite
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.director.llm import DirectorLLM
from mp3_to_videoclip.director.loop import run_turn
from mp3_to_videoclip.director.routing import ROLE_LABEL, Route, route_for

router = APIRouter(prefix="/api/projects/{slug}", tags=["director"])

# A pasted treatment is legitimate context, not a chat message we should reject
# at the old 8k convenience cap. Keep a bound so one turn cannot become a dump.
MAX_CHAT_MESSAGE = 24_000
KEEP_GOING = "Keep going from where you stopped."


def _role(payload: dict, stage: str | None) -> str:
    role = payload.get("role")
    if role is None:
        role = prompt_suite.role_for_stage(stage)
    if role not in prompt_suite.TASKS:
        raise HTTPException(status_code=400, detail="role must be writer, editor or critic")
    return role


def _announce_tool(request: Request, slug: str, event) -> None:
    """A finished tool that may have written the production: tell every open view.

    The watcher sees files, not meaning, so the turn itself announces each finished write
    while it streams.
    """
    if getattr(event, "kind", None) != "tool" or not getattr(event, "result", None):
        return
    tool = getattr(event, "tool", None) or ""
    if tool.startswith("get_") or tool == "ask_user":
        return
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        return
    runner.bus.publish("project.changed", {"project": slug, "source": "director", "tool": tool})


def _line(event) -> str:
    return (
        json.dumps(
            {
                "kind": event.kind,
                "text": event.text,
                "tool": event.tool,
                "arguments": event.arguments,
                "result": event.result,
                "payload": event.payload,
            }
        )
        + "\n"
    )


def _context(payload: dict) -> dict | None:
    value = payload.get("context")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="context must be an object")
    unknown = set(value) - {"stage", "time", "selected_shots"}
    if unknown:
        raise HTTPException(status_code=400, detail="unexpected context fields")
    context: dict = {}
    stage = value.get("stage")
    if stage is not None:
        # The stages the prompt suite answers on: one list, so a new stage is never
        # refused here after it was given a role there.
        if not isinstance(stage, str) or stage not in prompt_suite.STAGE_ROLE:
            raise HTTPException(status_code=400, detail="context stage is invalid")
        context["stage"] = stage
    time = value.get("time")
    if time is not None:
        if isinstance(time, bool) or not isinstance(time, (int, float)) or time < 0:
            raise HTTPException(status_code=400, detail="context time must be seconds")
        context["time"] = float(time)
    selected = value.get("selected_shots")
    if selected is not None:
        if (
            not isinstance(selected, list)
            or len(selected) > 8
            or not all(
                isinstance(item, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", item)
                for item in selected
            )
        ):
            raise HTTPException(status_code=400, detail="context selected_shots must be shot IDs")
        context["selected_shots"] = selected
    return context


def _can_see(route: Route) -> bool | None:
    """Whether the catalogue knows this model takes pictures. Unknown stays unknown."""
    from mp3_to_videoclip import catalog

    maker = route.listed_under or route.provider
    known = next(
        (m for m in catalog.load().models if m.id == route.model and m.provider == maker),
        None,
    )
    return None if known is None or not known.capabilities else "vision" in known.capabilities


@router.get("/director/model")
async def get_director_model(slug: str, request: Request, role: str = "writer"):
    """Who actually answers for this role, and whether it can look at a still."""
    if role not in prompt_suite.TASKS:
        raise HTTPException(status_code=400, detail="role must be writer, editor or critic")
    project_root(request, slug)
    route = route_for(effective_settings(), role)
    return {
        "model": route.model,
        "provider": route.provider,
        "provider_label": route.label,
        "has_key": bool(route.key),
        "can_see": _can_see(route),
    }


@router.get("/decisions/{decision_id}")
async def get_decision(slug: str, decision_id: str, request: Request):
    """Why one write happened and what it changed, field by field."""
    from mp3_to_videoclip.director import decisions

    found = decisions.find(project_root(request, slug), decision_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such decision")
    return found


@router.get("/model-usage")
async def get_model_usage(slug: str, request: Request):
    """What the Director's models have used on this film. Beside picture spend, not in it."""
    from mp3_to_videoclip.director import usage

    return usage.summary(project_root(request, slug))


@router.get("/chat")
async def get_chat(slug: str, request: Request, role: str | None = None):
    from mp3_to_videoclip.director.conversation import ROLES, load_messages

    if role is not None and role not in ROLES:
        raise HTTPException(status_code=400, detail="role must be writer, editor or critic")
    root = project_root(request, slug)
    return {"messages": load_messages(root, role)}


@router.post("/chat")
async def post_chat(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    # Keep going after the step limit: the same turn's work, with the same prompt.
    message = KEEP_GOING if payload.get("continue") else payload.get("message", "")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message required")
    if len(message) > MAX_CHAT_MESSAGE:
        raise ApiError(
            400,
            "That message is too long. Paste your idea into Story under Start instead.",
            "message_too_long",
        )
    settings = effective_settings()
    stage = payload.get("stage")
    role = _role(payload, stage)
    context = _context(payload)
    project = P.load_project(root, verify_source=False)
    # A button that means one job names it; a typed message is routed by the artifacts.
    task = payload.get("task")
    if task is not None and task not in prompt_suite.TASKS[role]:
        raise HTTPException(status_code=400, detail=f"unknown {role} task")
    bundle = prompt_suite.assemble(
        root,
        stage,
        role=role,
        kind=project.kind,
        style_preset=project.style_preset,
        task=task,
    )
    # Written down per turn, so the model that answered is known afterwards. Approval
    # hashes never read this, so changing a model un-approves nothing.
    route = route_for(settings, role)
    if not route.key:
        raise ApiError(
            503,
            f"The {ROLE_LABEL[role]} uses {route.model} from {route.label}, which has no key yet. "
            "Add one in Settings, or choose another model for it.",
            "no_llm_key",
        )
    meta = {**bundle.meta, "provider": route.provider, "model": route.model}
    promptlog.remember(root, meta)
    snapshot = build_context(slug, root.parent, stage=stage, context=context, task=bundle.task)
    from mp3_to_videoclip.director import decisions

    handoff = decisions.handoff(root, role)
    system = bundle.text + "\n\n---\n\n" + snapshot + (f"\n\n{handoff}" if handoff else "")

    llm = DirectorLLM(
        base_url=route.base_url,
        api_key=route.key,
        model=route.model,
        kind=route.kind,
        session_id=f"studio-{slug}-{role}",
    )

    async def stream():
        runner = getattr(request.app.state, "runner", None)
        async for event in run_turn(
            llm,
            root,
            slug,
            message,
            system,
            runner=runner,
            projects_dir=root.parent,
            prompt_meta=meta,
            role=role,
            provider=route.provider,
            max_tokens=getattr(settings.roles, role).max_tokens_per_turn,
        ):
            _announce_tool(request, slug, event)
            yield _line(event)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


STAGES = ("track", "story", "storyboard", "images", "film")


def _system_prompt(
    stage: str | None = None,
    *,
    kind: str | None = None,
    style_preset: str | None = None,
    role: str | None = None,
    task: str | None = None,
) -> str:
    """Preview the assembled prompt without a project; project data is added live."""
    root = Path("__prompt_preview__")
    return prompt_suite.assemble(
        root,
        stage,
        role=role,
        kind=kind,
        style_preset=style_preset,
        task=task,
    ).text
