"""Director chat: one streaming turn per request, persisted to work/chat.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.config import effective_settings
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
    )
    gateway = GATEWAYS.get(key)
    if gateway is None:
        gateway = OpenCodeGateway(
            binary=binary,
            workspace=workspace,
            projects_dir=projects_dir,
            writer_model=settings.writer_model,
            editor_model=settings.editor_model,
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


def _role(payload: dict, stage: str | None) -> str:
    role = payload.get("role")
    if role is None:
        role = "editor" if stage == "film" else "writer"
    if role not in ("writer", "editor"):
        raise HTTPException(status_code=400, detail="role must be writer or editor")
    return role


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


@router.get("/chat")
async def get_chat(slug: str, request: Request):
    from mp3_to_videoclip.director.conversation import load_messages

    root = project_root(request, slug)
    return {"messages": load_messages(root)}


@router.post("/chat")
async def post_chat(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    message = payload.get("message", "")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message required")
    if len(message) > 8000:
        raise HTTPException(status_code=400, detail="message is too long")
    settings = effective_settings()
    stage = payload.get("stage")
    role = _role(payload, stage)
    system = build_context(slug, root.parent, stage=stage) + "\n\n" + _system_prompt(stage)

    if settings.gateway == "opencode":
        try:
            gateway = await get_gateway(settings, root.parent)
        except OpenCodeError as exc:
            if not settings.llm_api_key:
                raise HTTPException(
                    status_code=503,
                    detail=f"OpenCode gateway unavailable: {exc}",
                ) from exc
            gateway = None
        if gateway is not None:
            client = gateway.client()
            model = settings.writer_model if role == "writer" else settings.editor_model
            try:
                available = await client.model_available(model)
            except Exception as exc:  # noqa: BLE001 - gateway boundary
                await client.aclose()
                raise HTTPException(
                    status_code=503, detail=f"OpenCode gateway unavailable: {exc}"
                ) from exc
            if not available:
                await client.aclose()
                raise HTTPException(
                    status_code=503,
                    detail=f"model {model} is not available in OpenCode; check Settings",
                )
            if hasattr(client, "wait_for_mcp"):
                try:
                    await client.wait_for_mcp()
                except Exception as exc:  # noqa: BLE001 - gateway boundary
                    await client.aclose()
                    raise HTTPException(
                        status_code=503,
                        detail=f"clipstudio MCP server did not connect: {exc}",
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
                    ):
                        yield _line(event)
                finally:
                    await client.aclose()

            return StreamingResponse(gateway_stream(), media_type="application/x-ndjson")

    if not settings.llm_api_key:
        raise HTTPException(status_code=503, detail="no LLM key configured; open Settings")
    llm = DirectorLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        session_id=f"studio-{slug}",
    )

    async def stream():
        runner = getattr(request.app.state, "runner", None)
        async for event in run_turn(
            llm, root, slug, message, system, runner=runner, projects_dir=root.parent
        ):
            yield _line(event)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


STAGES = ("track", "story", "storyboard", "images", "film")


def _system_prompt(stage: str | None = None) -> str:
    """The shared director prompt plus the guide for the stage the user is in."""
    prompts = Path(__file__).resolve().parent.parent / "director" / "prompts"
    base = prompts / "system.md"
    text = base.read_text() if base.is_file() else "You are the director."
    if stage in STAGES:
        guide = prompts / f"{stage}.md"
        if guide.is_file():
            text += "\n\n---\n\n" + guide.read_text()
    return text
