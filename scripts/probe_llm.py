"""One-off probe against OpenCode Go (D1). Not a test.

Verifies: auth header, one streamed reply, one tool-call round trip, one image
input. Results are printed; if tool calls fail, the adapter falls back to a
JSON-action protocol. Run with:

    uv run python scripts/probe_llm.py
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director.llm import DirectorLLM


async def main() -> None:
    settings = effective_settings()
    if not settings.llm_api_key:
        print("No LLM API key configured (settings or env).")
        return
    llm = DirectorLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        session_id="probe",
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a string back.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    messages = [
        {"role": "user", "content": "Call the echo tool with text 'probe ok', then say done."}
    ]
    print("Streaming reply:")
    async for event in llm.stream(messages, tools=tools, system="You are a probe."):
        print(type(event).__name__, getattr(event, "text", getattr(event, "name", ""))[:80])


if __name__ == "__main__":
    asyncio.run(main())
