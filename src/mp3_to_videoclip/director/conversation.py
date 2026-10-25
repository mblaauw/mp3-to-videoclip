"""Chat log persistence: one JSONL file per project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
