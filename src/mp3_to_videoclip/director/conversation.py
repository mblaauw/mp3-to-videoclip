"""Chat log persistence and bounded prompt history.

The JSONL log is the durable record and is never rewritten. A turn only sends a
bounded window to the model: older user requests and tool names become a short
summary added to the system prompt, and the recent messages start at a user turn
so a tool result never begins a compacted history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_CONTEXT_MESSAGES = 60
KEEP_RECENT_MESSAGES = 24
SUMMARY_SNIPPET = 160


def chat_path(root: Path) -> Path:
    return root / "work" / "chat.jsonl"


def load_messages(root: Path) -> list[dict[str, Any]]:
    path = chat_path(root)
    if not path.is_file():
        return []
    messages: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def append_message(root: Path, message: dict[str, Any]) -> None:
    path = chat_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = MAX_CONTEXT_MESSAGES,
    keep: int = KEEP_RECENT_MESSAGES,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return a bounded prompt and a summary of the dropped history.

    Only user request snippets and tool names enter the summary; tool outputs and
    assistant prose can be large or stale, while the current project state is
    rebuilt into the system prompt on every turn anyway.
    """
    if len(messages) <= max_messages:
        return messages, None
    cutoff = max(0, len(messages) - keep)
    user_turns = [i for i, message in enumerate(messages) if message.get("role") == "user"]
    cut = next((index for index in user_turns if index >= cutoff), None)
    if cut is None:
        cut = user_turns[-1] if user_turns else cutoff
    if cut <= 0:
        return messages, None
    older = messages[:cut]
    recent = messages[cut:]
    requests = [
        message["content"].strip().replace("\n", " ")[:SUMMARY_SNIPPET]
        for message in older
        if message.get("role") == "user" and isinstance(message.get("content"), str)
    ]
    tools = sorted(
        {
            message["name"]
            for message in older
            if message.get("role") == "tool" and message.get("name")
        }
    )
    summary = f"Earlier conversation compressed ({len(older)} messages)."
    if requests:
        summary += " User requests: " + " | ".join(requests[-8:]) + "."
    if tools:
        summary += " Tools used: " + ", ".join(tools) + "."
    return recent, summary
