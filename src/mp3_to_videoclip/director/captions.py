"""What a role's vision model sees in a still, written down once per still and model."""

from __future__ import annotations

from contextlib import aclosing
from pathlib import Path

from ..storage import digest, read_optional, write_json
from . import pricing, usage
from .llm import DirectorLLM, TextDelta
from .providers.base import Usage

PROMPT = (
    "Describe this still for a film editor in one or two plain sentences: the subject, what it "
    "is doing, the framing and the light. Say only what is visible. Do not interpret it."
)


def path_for(root: Path, sha256: str, model: str) -> Path:
    return Path(root) / "work" / "captions" / f"{digest({'still': sha256, 'model': model})}.json"


async def describe(root: Path, route, shot_id: str, sha256: str, data_url: str, role: str) -> dict:
    """One caption. A cached one costs nothing; a new one is written down in the usage record."""
    path = path_for(root, sha256, route.model)
    cached = read_optional(path)
    if isinstance(cached, dict) and cached.get("caption"):
        return {"shot_id": shot_id, "caption": cached["caption"], "cached": True}
    llm = DirectorLLM(
        base_url=route.base_url, api_key=route.key, model=route.model, kind=route.kind
    )
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    }
    text = ""
    spent = Usage()
    async with aclosing(llm.stream([message])) as stream:
        async for event in stream:
            if isinstance(event, TextDelta):
                text += event.text
            elif isinstance(event, Usage):
                spent = event
    cost, basis = pricing.cost_of(route.provider, route.model, spent)
    usage.record(
        root,
        turn_id=f"caption-{shot_id}",
        role=role,
        provider=route.provider,
        model=route.model,
        usage=spent,
        cost_usd=cost,
        cost_basis=basis,
    )
    caption = " ".join(text.split())
    if caption:
        write_json(path, {"caption": caption, "model": route.model, "still": sha256})
    return {"shot_id": shot_id, "caption": caption, "cached": False}
