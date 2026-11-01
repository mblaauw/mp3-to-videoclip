"""Director turn loop: stream, execute tools, feed results back, stop cleanly.

A turn is a job. It streams text deltas to the UI, executes tool calls through
``tools.dispatch``, appends the results and continues, and stops at end_turn, an
``ask_user`` call, a limit of tool calls the owner can extend, the same call failing
twice, user cancellation, or a stalled stream. Tool calls only run once their stream has
finished, so a stall never applies a half-written one.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from openai import APIError

from . import pricing, usage
from .conversation import append_message, compact_messages, history_for_model, load_messages
from .llm import (
    DirectorLLM,
    Progress,
    ProviderFailure,
    StreamStalled,
    TextDelta,
    ToolCall,
    TurnResult,
    service_failed_message,
    stall_message,
)
from .llm import Usage as ModelUsage
from .tools import CRITIC_TOOLS, ToolResult, dispatch, tools_for

MAX_TOOL_CALLS = 40


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
    provider: str = "",
) -> AsyncIterator[TurnEvent]:
    # A Critic reads with fresh eyes every time, as its own session always did.
    history = [] if role == "critic" else load_messages(root, role)
    messages, summary = compact_messages(history)
    messages = history_for_model(messages)
    if summary:
        system = (system + "\n\n" + summary).strip()
    messages.append({"role": "user", "content": user_message})
    entry = {"role": "user", "content": user_message}
    if prompt_meta is not None:
        entry["prompt"] = prompt_meta
    append_message(root, entry, agent=role)

    tool_calls = 0
    turn_id = uuid4().hex
    model = getattr(llm, "model", "")
    spent = ModelUsage()
    failures: dict[tuple[str, str], int] = {}

    def finished(payload: dict | None = None) -> dict:
        """Write down what this turn used, and say so with the turn's last event."""
        cost, basis = pricing.cost_of(provider, model, spent)
        usage.record(
            root,
            turn_id=turn_id,
            role=role,
            provider=provider,
            model=model,
            usage=spent,
            cost_usd=cost,
            cost_basis=basis,
            prompt_hash=(prompt_meta or {}).get("hash"),
        )
        counts = {
            "prompt_tokens": spent.prompt_tokens,
            "completion_tokens": spent.completion_tokens,
            "cost_usd": cost,
            "cost_basis": basis,
            "model": model,
        }
        return {**(payload or {}), "usage": counts}

    def count(event: ModelUsage) -> None:
        spent.prompt_tokens += event.prompt_tokens
        spent.completion_tokens += event.completion_tokens
        spent.cached_tokens += event.cached_tokens
        # One call with no counts makes the whole turn's total an underestimate.
        spent.reported = event.reported and (spent.reported or not calls_counted[0])
        calls_counted[0] += 1

    calls_counted = [0]
    while tool_calls < max_tool_calls:
        result: TurnResult | None = None
        assistant_text = ""
        pending: list[ToolCall] = []
        try:
            async with aclosing(
                llm.stream(messages, tools=tools_for(role), system=system)
            ) as stream:
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
                    elif isinstance(event, ModelUsage):
                        count(event)
                    elif isinstance(event, TurnResult):
                        result = event
        except StreamStalled as stalled:
            if assistant_text.strip():
                append_message(root, {"role": "assistant", "content": assistant_text}, agent=role)
            yield TurnEvent(
                kind="done",
                text=assistant_text,
                payload=finished({"error": stall_message(role, stalled.seconds), "stalled": True}),
            )
            return
        except (APIError, ProviderFailure) as failure:
            # The model service refused or dropped the call. Tools already run keep
            # their results, and the owner hears why instead of an empty reply.
            if assistant_text.strip():
                append_message(root, {"role": "assistant", "content": assistant_text}, agent=role)
            yield TurnEvent(
                kind="done",
                text=assistant_text,
                payload=finished({"error": service_failed_message(role, failure, model)}),
            )
            return

        if result is None:
            break

        if not pending:
            messages.append({"role": "assistant", "content": assistant_text})
            payload = finished()
            append_message(
                root,
                {"role": "assistant", "content": assistant_text, "usage": payload["usage"]},
                agent=role,
            )
            yield TurnEvent(kind="done", text=assistant_text, payload=payload)
            return

        # What it said between calls is its reasoning, and the log keeps it.
        if assistant_text.strip():
            append_message(
                root,
                {"role": "assistant", "content": assistant_text, "with_tools": True},
                agent=role,
            )
        messages.append(
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                        **({"signature": tc.signature} if tc.signature else {}),
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
            if role == "critic" and tc.name not in CRITIC_TOOLS:
                tool_result = json.dumps({"error": "the Critic changes nothing; use your notes"})
            else:
                tool_result = await dispatch(tc.name, args, runner, projects_dir)
            if isinstance(tool_result, ToolResult):
                result_text = tool_result.text
                images = tool_result.images
            else:
                result_text = tool_result
                images = ()
            yield TurnEvent(kind="tool", tool=tc.name, result=result_text)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result_text}
            )
            append_message(
                root,
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result_text},
                agent=role,
            )
            if images:
                pending_images.extend(images)
                image_tool = tc.name
            if _failed(result_text):
                attempt = (tc.name, tc.arguments or "")
                failures[attempt] = failures.get(attempt, 0) + 1
                if failures[attempt] >= 2:
                    who = (role or "director").capitalize()
                    yield TurnEvent(
                        kind="done",
                        text=assistant_text,
                        payload=finished(
                            {
                                "error": f"The {who} is repeating a failed call to {tc.name}, so this turn was stopped."
                            }  # noqa: E501
                        ),
                    )
                    return
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

    yield TurnEvent(
        kind="done",
        text=f"Stopped after {tool_calls} steps.",
        payload=finished({"limit": True, "steps": tool_calls}),
    )


def _failed(result: str) -> bool:
    """Whether a tool answered with an error rather than a result."""
    try:
        value = json.loads(result)
    except (TypeError, ValueError):
        return False
    return isinstance(value, dict) and bool(value.get("error"))
