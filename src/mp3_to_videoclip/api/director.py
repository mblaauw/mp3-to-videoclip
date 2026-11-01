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
from mp3_to_videoclip.config import effective_settings, split_model
from mp3_to_videoclip.director import prompts as prompt_suite
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.director.llm import DirectorLLM
from mp3_to_videoclip.director.loop import run_turn
from mp3_to_videoclip.director.opencode import (
    OpenCodeError,
    OpenCodeGateway,
    discover_binary,
    gateway_workspace,
    run_gateway_turn,
)

router = APIRouter(prefix="/api/projects/{slug}", tags=["director"])

# A pasted treatment is legitimate context, not a chat message we should reject
# at the old 8k convenience cap. Keep a bound so one turn cannot become a dump.
MAX_CHAT_MESSAGE = 24_000

GATEWAYS: dict[tuple[str, str, str, str, str], OpenCodeGateway] = {}


def _workspace(settings) -> Path:
    value = settings.opencode_workspace.strip()
    return Path(value).expanduser() if value else gateway_workspace()


async def get_gateway(settings, projects_dir: Path) -> OpenCodeGateway:
    """One gateway per binary/workspace/projects/models combination."""
    workspace = _workspace(settings)
    binary = discover_binary(settings.opencode_bin)
    key = (
        binary,
        str(workspace),
        str(projects_dir.resolve()),
        settings.writer_model,
        settings.editor_model,
        settings.critic_model,
    )
    gateway = GATEWAYS.get(key)
    if gateway is None:
        gateway = OpenCodeGateway(
            binary=binary,
            workspace=workspace,
            projects_dir=projects_dir,
            writer_model=settings.writer_model,
            editor_model=settings.editor_model,
            critic_model=settings.critic_model,
        )
        GATEWAYS[key] = gateway
    try:
        await gateway.start()
    except Exception:
        GATEWAYS.pop(key, None)
        raise
    return gateway


def close_gateways() -> None:
    for gateway in list(GATEWAYS.values()):
        gateway.stop()
    GATEWAYS.clear()


def _role_model(settings, role: str) -> str:
    return {
        "writer": settings.writer_model,
        "editor": settings.editor_model,
        "critic": settings.critic_model,
    }[role]


def _role(payload: dict, stage: str | None) -> str:
    role = payload.get("role")
    if role is None:
        role = prompt_suite.role_for_stage(stage)
    if role not in prompt_suite.TASKS:
        raise HTTPException(status_code=400, detail="role must be writer, editor or critic")
    return role


def _announce_tool(request: Request, slug: str, event) -> None:
    """A finished tool that may have written the production: tell every open view.

    The director's tools can run in the OpenCode MCP process, outside any Studio
    request, so the turn itself announces each finished write while it streams.
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
        if not isinstance(stage, str) or stage not in (
            "track",
            "story",
            "storyboard",
            "images",
            "film",
        ):
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


@router.get("/director/model")
async def get_director_model(slug: str, request: Request, role: str = "writer"):
    """Who actually answers for this role, and whether it can look at a still."""
    if role not in prompt_suite.TASKS:
        raise HTTPException(status_code=400, detail="role must be writer, editor or critic")
    root = project_root(request, slug)
    settings = effective_settings()
    if settings.gateway != "opencode":
        # The direct API doesn't report what a model takes, so this stays honest.
        return {"model": settings.llm_model, "gateway": "direct", "can_see": None}
    model = _role_model(settings, role)
    try:
        gateway = await get_gateway(settings, root.parent)
        client = gateway.client()
        try:
            can_see = await client.model_can_see(model)
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001 - gateway boundary; the chat route reports the failure
        can_see = None
    return {"model": model, "gateway": "opencode", "can_see": can_see}


def _answering(settings, role: str) -> dict:
    """The provider and model this turn will really use, on whichever path."""
    if settings.gateway != "opencode":
        return {"provider": "direct", "model": settings.llm_model}
    model = _role_model(settings, role)
    return {"provider": split_model(model)["provider"], "model": split_model(model)["model"]}


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
    message = payload.get("message", "")
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
    meta = {**bundle.meta, **_answering(settings, role)}
    promptlog.remember(root, meta)
    snapshot = build_context(slug, root.parent, stage=stage, context=context, task=bundle.task)
    system = bundle.text + "\n\n---\n\n" + snapshot

    if settings.gateway == "opencode":
        try:
            gateway = await get_gateway(settings, root.parent)
        except OpenCodeError as exc:
            if not settings.llm_api_key:
                raise ApiError(
                    503, f"OpenCode gateway unavailable: {exc}", "director_unavailable"
                ) from exc
            gateway = None
        if gateway is not None:
            client = gateway.client()
            model = _role_model(settings, role)
            try:
                available = await client.model_available(model)
            except Exception as exc:  # noqa: BLE001 - gateway boundary
                await client.aclose()
                raise ApiError(
                    503, f"OpenCode gateway unavailable: {exc}", "director_unavailable"
                ) from exc
            if not available:
                await client.aclose()
                raise ApiError(
                    503,
                    f"model {model} is not available in OpenCode; check Settings",
                    "director_model_unavailable",
                )
            if hasattr(client, "wait_for_mcp"):
                try:
                    await client.wait_for_mcp()
                except Exception as exc:  # noqa: BLE001 - gateway boundary
                    await client.aclose()
                    raise ApiError(
                        503,
                        f"clipstudio MCP server did not connect: {exc}",
                        "director_unavailable",
                    ) from exc

            async def gateway_stream():
                try:
                    async for event in run_gateway_turn(
                        client,
                        root,
                        slug,
                        role,
                        message,
                        system,
                        model=model,
                        prompt_meta=meta,
                    ):
                        _announce_tool(request, slug, event)
                        yield _line(event)
                finally:
                    await client.aclose()

            return StreamingResponse(gateway_stream(), media_type="application/x-ndjson")

    if not settings.llm_api_key:
        raise ApiError(503, "no LLM key configured; open Settings", "no_llm_key")
    llm = DirectorLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
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
