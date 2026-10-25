"""Director turn loop: stream, execute tools, feed results back, stop cleanly.

A turn is a job. It streams text deltas to the UI, executes tool calls through
``tools.dispatch``, appends the results and continues, and stops at end_turn, an
``ask_user`` call, a max of 25 tool calls, or user cancellation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .conversation import append_message, load_messages
from .llm import DirectorLLM, TextDelta, ToolCall, TurnResult
from .tools import TOOLS, dispatch

MAX_TOOL_CALLS = 25


@dataclass
class TurnEvent:
    kind: str  # text / tool / done / ask
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
) -> AsyncIterator[TurnEvent]:
    messages = load_messages(root)
    messages.append({"role": "user", "content": user_message})
    append_message(root, {"role": "user", "content": user_message})

    tool_calls = 0
    while tool_calls < max_tool_calls:
        result: TurnResult | None = None
        assistant_text = ""
        pending: list[ToolCall] = []
        async for event in llm.stream(messages, tools=TOOLS, system=system):
            if isinstance(event, TextDelta):
                assistant_text += event.text
                yield TurnEvent(kind="text", text=event.text)
            elif isinstance(event, ToolCall):
                pending.append(event)
            elif isinstance(event, TurnResult):
                result = event

        if result is None:
            break

        if not pending:
            messages.append({"role": "assistant", "content": assistant_text})
            append_message(root, {"role": "assistant", "content": assistant_text})
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
        for tc in pending:
            tool_calls += 1
            yield TurnEvent(kind="tool", tool=tc.name, arguments=tc.arguments)
            try:
                args = json.loads(tc.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if tc.name == "ask_user":
                yield TurnEvent(kind="ask", payload=args)
                append_message(root, {"role": "assistant", "content": args.get("question", "")})
                return
            tool_result = await dispatch(tc.name, args, runner)
            yield TurnEvent(kind="tool", tool=tc.name, result=tool_result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
            append_message(
                root,
                {"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": tool_result},
            )

    yield TurnEvent(kind="done", text="Stopped after the tool-call limit.")
