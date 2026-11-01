"""Which provider, address, key and model answer for one role."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings

OPENAI_URL = "https://api.openai.com/v1"
OPENCODE_GO_URL = "https://opencode.ai/inference/go/openai/v1"
ROLE_LABEL = {"writer": "Writer", "editor": "Editor", "critic": "Critic"}
#: What a provider's name in Settings means. Anything else is the owner's own endpoint.
KNOWN = {
    "openai": "OpenAI",
    "opencode-go": "OpenCode Go",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "direct": "the direct endpoint",
}


@dataclass(frozen=True)
class Route:
    provider: str
    kind: str
    base_url: str | None
    key: str
    model: str
    #: The catalogue's name for this model's maker, when another provider carries it.
    listed_under: str = ""

    @property
    def label(self) -> str:
        return KNOWN.get(self.provider, self.provider)


def opencode_go_key(settings: Settings) -> str:
    """An OpenCode Go key saved as the direct endpoint's still belongs to OpenCode Go."""
    direct = settings.keys.openai_compatible
    same = direct.base_url.rstrip("/") == OPENCODE_GO_URL
    return settings.keys.opencode_go or (direct.key if same else "")


def route_for(settings: Settings, role: str) -> Route:
    """A role's real route. It never swaps to another model to find one that has a key."""
    chosen = getattr(settings.roles, role)
    provider = chosen.provider or "direct"
    keys = settings.keys
    if provider == "openai":
        # With no OpenAI key of its own, an OpenAI model goes through OpenCode Go, whose key
        # only ever goes to OpenCode Go's address. The same model answers either way.
        go_key = opencode_go_key(settings)
        if not keys.openai and go_key:
            return Route(
                "opencode-go", "openai-compatible", OPENCODE_GO_URL, go_key, chosen.model, "openai"
            )
        return Route(provider, "openai-compatible", OPENAI_URL, keys.openai, chosen.model)
    if provider == "opencode-go":
        key = opencode_go_key(settings)
        return Route(provider, "openai-compatible", OPENCODE_GO_URL, key, chosen.model)
    if provider == "anthropic":
        return Route(provider, "anthropic", None, keys.anthropic, chosen.model)
    if provider == "gemini":
        return Route(provider, "gemini", None, keys.gemini, chosen.model)
    direct = keys.openai_compatible
    if provider == "direct":
        return Route(provider, "openai-compatible", direct.base_url, direct.key, chosen.model)
    # OpenRouter and the like: a name from another tool, reached through the direct endpoint.
    return Route(provider, "openai-compatible", direct.base_url, direct.key, chosen.qualified)
