"""One live probe of a role's model, by the route a Studio turn uses. Not a test.

Two requests: one with a picture and a tool, then the tool's result sent back. It checks
streamed text, a tool call, the round trip, that the picture was read and that usage came
back, and exits non-zero when any fails. It is a live call, so run it only when the owner says:

    uv run python scripts/probe_llm.py [writer|editor|critic]
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director import routing
from mp3_to_videoclip.director.llm import DirectorLLM, TextDelta, ToolCall, Usage

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echo a word back.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    }
]
ASK = "Call the echo tool once with the one word that names the colour of this picture."
SYSTEM = "You are a probe. Use the tool, then answer in one short line."


def red_square() -> str:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 20, 20)).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


async def _collect(llm: DirectorLLM, messages: list[dict]) -> tuple[str, list[ToolCall], Usage]:
    text, calls, usage = "", [], Usage()
    async for event in llm.stream(messages, tools=TOOLS, system=SYSTEM):
        if isinstance(event, TextDelta):
            text += event.text
        elif isinstance(event, ToolCall):
            calls.append(event)
        elif isinstance(event, Usage):
            usage = event
    return text, calls, usage


async def probe(llm: DirectorLLM) -> dict[str, bool]:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": ASK},
                {"type": "image_url", "image_url": {"url": red_square(), "detail": "low"}},
            ],
        }
    ]
    first_text, calls, first_usage = await _collect(llm, messages)
    checks = {"tool call": bool(calls), "usage reported": first_usage.reported}
    word = second_text = ""
    if calls:
        call = calls[0]
        word = str(json.loads(call.arguments or "{}").get("text", ""))
        messages += [
            {
                "role": "assistant",
                "content": first_text or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                        **({"signature": call.signature} if call.signature else {}),
                    }
                ],
            },
            {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": word},
        ]
        second_text, _, _ = await _collect(llm, messages)
        checks["tool result answered"] = bool(second_text.strip())
    checks["streamed text"] = bool((first_text + second_text).strip())
    checks["picture read"] = "red" in word.lower()
    print(f"  echo({word!r})" if calls else "  no tool call")
    return checks


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "writer"
    route = routing.route_for(effective_settings(), role)
    if not route.key:
        print(f"No key for the {role}'s route ({route.label}).")
        return 1
    print(f"{role}: {route.model} through {route.label}")
    llm = DirectorLLM(
        base_url=route.base_url,
        api_key=route.key,
        model=route.model,
        kind=route.kind,
        session_id="probe",
    )
    checks = asyncio.run(probe(llm))
    for name, passed in checks.items():
        print(f"  {'pass' if passed else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
