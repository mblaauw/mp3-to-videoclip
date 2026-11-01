"""One adapter per wire format. Each takes the same messages and yields the same events."""

from __future__ import annotations

from .anthropic import Anthropic
from .gemini import Gemini
from .openai_compatible import OpenAICompatible

KINDS = {"openai-compatible": OpenAICompatible, "opencode-go": OpenAICompatible}
KINDS.update({"anthropic": Anthropic, "gemini": Gemini})
