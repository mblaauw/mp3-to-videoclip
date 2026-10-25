"""Director chat: one streaming turn per request, persisted to work/chat.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from mp3_to_videoclip.api._helpers import project_root
from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.director.llm import DirectorLLM
from mp3_to_videoclip.director.loop import run_turn

router = APIRouter(prefix="/api/projects/{slug}", tags=["director"])


@router.get("/chat")
async def get_chat(slug: str, request: Request):
    from mp3_to_videoclip.director.conversation import load_messages

    root = project_root(request, slug)
    return {"messages": load_messages(root)}


@router.post("/chat")
async def post_chat(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    message = payload.get("message", "")
    settings = effective_settings()
    if not settings.llm_api_key:
        return {"error": "no LLM key configured; open Settings"}
    llm = DirectorLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        session_id=f"studio-{slug}",
    )
    system = build_context(slug, root.parent) + "\n\n" + _system_prompt(payload.get("stage"))

    async def stream():
        runner = getattr(request.app.state, "runner", None)
        async for event in run_turn(llm, root, slug, message, system, runner=runner):
            yield (
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
