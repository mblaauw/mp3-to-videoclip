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
REASON_SNIPPET = 200
KEEP_REASONS = 8
ROLES = ("writer", "editor", "critic")


def chat_path(root: Path) -> Path:
    return root / "work" / "chat.jsonl"


def _prompt_role(message: dict[str, Any]) -> str | None:
    """The role whose prompt files a recorded user turn was assembled from."""
    prompt = message.get("prompt")
    files = prompt.get("files") if isinstance(prompt, dict) else None
    for item in files if isinstance(files, list) else ():
        path = item.get("path") if isinstance(item, dict) else None
        head = path.split("/", 1)[0] if isinstance(path, str) else None
        if head in ROLES:
            return head
    return None


def _for_role(messages: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """Keep one role's turns; rows from before the split stay visible to both.

    New rows carry ``agent``. Older rows are attributed through their user turn's
    recorded prompt files (or an older reply's ``name``) and the rows after it;
    a turn that recorded neither predates the two roles and is shared.
    """
    kept: list[dict[str, Any]] = []
    current: str | None = None
    for message in messages:
        agent = message.get("agent")
        if agent not in ROLES:
            agent = None
        if message.get("role") == "user":
            current = agent or _prompt_role(message)
        elif agent is None and message.get("name") in ROLES and message.get("role") == "assistant":
            agent = message["name"]
        owner = agent or current
        if owner in (None, role):
            kept.append(message)
    return kept


def load_messages(root: Path, role: str | None = None) -> list[dict[str, Any]]:
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
    return messages if role is None else _for_role(messages, role)


def append_message(root: Path, message: dict[str, Any], *, agent: str | None = None) -> None:
    if agent is not None:
        message = {**message, "agent": agent}
    path = chat_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(message, ensure_ascii=False) + "\n")


def history_for_model(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What earlier turns a model is sent: what was asked and what it said.

    Only role and content, because the log's bookkeeping is refused by real APIs. A logged tool
    result has lost the call it answered, which real APIs refuse too; the snapshot rebuilt each
    turn is the current state. An empty reply is refused by some, so it is left out.
    """
    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message.get("role") in ("user", "assistant")
        and isinstance(message.get("content"), str)
        and message["content"].strip()
    ]


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = MAX_CONTEXT_MESSAGES,
    keep: int = KEEP_RECENT_MESSAGES,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return a bounded prompt and a summary of the dropped history.

    User requests, tool names and the reasoning given between tool calls enter the summary,
    so a long film keeps why it did things as well as what. Tool outputs can be large and
    stale, and the current project state is rebuilt into the system prompt every turn.
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
    reasons = [
        " ".join(message["content"].split())[:REASON_SNIPPET]
        for message in older
        if message.get("with_tools") and isinstance(message.get("content"), str)
    ]
    if reasons:
        summary += " Reasoning along the way: " + " | ".join(reasons[-KEEP_REASONS:]) + "."
    return recent, summary
