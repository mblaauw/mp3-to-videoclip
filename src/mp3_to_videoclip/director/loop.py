"""Director turn loop: stream, execute tools, feed results back, stop cleanly.

A turn is a job. It streams text deltas to the UI, executes tool calls through
``tools.dispatch``, appends the results and continues, and stops at end_turn, an
``ask_user`` call, a max of 25 tool calls, user cancellation, or a stalled stream.
Tool calls only run once their stream has finished, so a stall never applies a
half-written one.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

from .conversation import append_message, compact_messages, load_messages
from .llm import (
    DirectorLLM,
    Progress,
    StreamStalled,
    TextDelta,
    ToolCall,
    TurnResult,
    stall_message,
)
from .tools import TOOLS, ToolResult, dispatch

MAX_TOOL_CALLS = 25


@dataclass
class TurnEvent:
    kind: str  # text / progress / tool / done / ask
    text: str = ""
    tool: str = ""
    arguments: str = ""
    result: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


async def run_turn(
    llm: DirectorLLM,
    root,
    slug: str,
    user_message: str,
    system: str,
    *,
    max_tool_calls: int = MAX_TOOL_CALLS,
    runner=None,
    projects_dir=None,
    prompt_meta: dict | None = None,
    role: str | None = None,
) -> AsyncIterator[TurnEvent]:
    # Each role keeps its own thread; the tag is bookkeeping, not model input.
    messages = [
        {key: value for key, value in message.items() if key != "agent"}
        for message in load_messages(root, role)
    ]
    messages, summary = compact_messages(messages)
    if summary:
        system = (system + "\n\n" + summary).strip()
    messages.append({"role": "user", "content": user_message})
    entry = {"role": "user", "content": user_message}
    if prompt_meta is not None:
        entry["prompt"] = prompt_meta
    append_message(root, entry, agent=role)

    tool_calls = 0
    while tool_calls < max_tool_calls:
        result: TurnResult | None = None
        assistant_text = ""
        pending: list[ToolCall] = []
        try:
            async with aclosing(llm.stream(messages, tools=TOOLS, system=system)) as stream:
                async for event in stream:
                    if isinstance(event, TextDelta):
                        assistant_text += event.text
                        yield TurnEvent(kind="text", text=event.text)
                    elif isinstance(event, Progress):
                        yield TurnEvent(
                            kind="progress", tool=event.tool, payload={"chars": event.chars}
                        )
                    elif isinstance(event, ToolCall):
                        pending.append(event)
                    elif isinstance(event, TurnResult):
                        result = event
        except StreamStalled as stalled:
            if assistant_text.strip():
                append_message(root, {"role": "assistant", "content": assistant_text}, agent=role)
            yield TurnEvent(
                kind="done",
                text=assistant_text,
                payload={"error": stall_message(role, stalled.seconds), "stalled": True},
            )
            return

        if result is None:
            break

        if not pending:
            messages.append({"role": "assistant", "content": assistant_text})
            append_message(root, {"role": "assistant", "content": assistant_text}, agent=role)
            yield TurnEvent(kind="done", text=assistant_text)
            return

        messages.append(
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in pending
                ],
            }
        )
        pending_images: list[str] = []
        image_tool = ""
        for tc in pending:
            tool_calls += 1
            yield TurnEvent(kind="tool", tool=tc.name, arguments=tc.arguments)
            try:
                args = json.loads(tc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc.name == "ask_user":
                yield TurnEvent(kind="ask", payload=args)
                append_message(
                    root, {"role": "assistant", "content": args.get("question", "")}, agent=role
                )
                return
            tool_result = await dispatch(tc.name, args, runner, projects_dir)
            if isinstance(tool_result, ToolResult):
                result_text = tool_result.text
                images = tool_result.images
            else:
                result_text = tool_result
                images = ()
            yield TurnEvent(kind="tool", tool=tc.name, result=result_text)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})
            append_message(
                root,
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result_text},
                agent=role,
            )
            if images:
                pending_images.extend(images)
                image_tool = tc.name
        if pending_images:
            content: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        f"{len(pending_images)} image thumbnails returned by {image_tool}. "
                        "Inspect them and continue; ask again for a different set."
                    ),
                }
            ]
            content.extend(
                {"type": "image_url", "image_url": {"url": url, "detail": "low"}}
                for url in pending_images
            )
            # In-memory only, after every tool result for this assistant turn:
            # chat.jsonl keeps bounded text, never base64 image bytes.
            messages.append({"role": "user", "content": content})

    yield TurnEvent(kind="done", text="Stopped after the tool-call limit.")
