"""An opinion from a model, only when asked for and only when spending is allowed.

Anchored so scores mean the same thing on two days, and blind so a judge can't favour a prompt it
recognises. Nothing here runs unless a person passes ``--judge`` and ``--allow-spend``.
"""

from __future__ import annotations

import asyncio
import json
import random
from contextlib import aclosing

from .lexicon import words_of

RUBRIC = {
    "originality": {
        "1": "Any song could have this film; you have seen it many times.",
        "3": "One idea you have not seen, among familiar ones.",
        "5": "The film could only be this one, and it surprised you.",
    },
    "song_specificity": {
        "1": "Nothing in it depends on this song.",
        "3": "Sections are followed, but the words and turns of the song are not.",
        "5": "A change in the song causes every change on screen.",
    },
    "cliche_density": {
        "1": "Stock images throughout.",
        "3": "A few stock images, some of them earned.",
        "5": "None, or used against their meaning.",
    },
    "shot_variety": {
        "1": "One scale and one kind of shot, repeated.",
        "3": "Some variety, but neighbours often repeat each other.",
        "5": "Every shot does a job its neighbours do not.",
    },
}


class SpendNotAllowed(ValueError):
    pass


def require_spend(judge: str | None, allow_spend: bool) -> None:
    if judge and not allow_spend:
        raise SpendNotAllowed("a judge costs money; pass --allow-spend to say you know")


def _prompt() -> str:
    lines = ["Score this film plan from 1 to 5 on each scale. Reply with JSON only."]
    for name, anchors in RUBRIC.items():
        lines.append(f"{name}: " + "; ".join(f"{key} = {text}" for key, text in anchors.items()))
    lines.append('Add "sentence": the one thing you would tell its writer.')
    return "\n".join(lines)


async def _ask(llm, system: str, text: str) -> tuple[str, dict]:
    from mp3_to_videoclip.director.llm import TextDelta
    from mp3_to_videoclip.director.providers.base import Usage

    reply = ""
    used = {"prompt_tokens": 0, "completion_tokens": 0}
    async with aclosing(llm.stream([{"role": "user", "content": text}], system=system)) as stream:
        async for event in stream:
            if isinstance(event, TextDelta):
                reply += event.text
            elif isinstance(event, Usage):
                used = {
                    "prompt_tokens": event.prompt_tokens,
                    "completion_tokens": event.completion_tokens,
                }
    return reply, used


def _json_in(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the judge did not answer in JSON")
    return json.loads(text[start : end + 1])


def score(llm, treatments: dict, board: dict) -> dict:
    """One run against the rubric, with what the judge cost in tokens."""
    reply, used = asyncio.run(_ask(llm, _prompt(), words_of(treatments, board)))
    value = _json_in(reply)
    for name in RUBRIC:
        if not 1 <= float(value[name]) <= 5:
            raise ValueError(f"the judge scored {name} outside 1 to 5")
    return {"scores": {name: value[name] for name in RUBRIC}, "sentence": value.get("sentence", ""), "usage": used}  # fmt: skip


def blind_pair(llm, first: dict, second: dict, *, seed: int = 0) -> dict:
    """Two runs of one fixture, order shuffled. The judge sees neither hash nor model."""
    pair = [("first", first), ("second", second)]
    random.Random(seed).shuffle(pair)
    text = "\n\n".join(
        f"Film {label}:\n{words_of(run['treatments'], run['board'])}"
        for label, (_, run) in zip("AB", pair, strict=True)
    )
    system = (
        'Which film plan is better? Reply with JSON only: {"prefer": "A" or "B", "sentence": why}.'
    )
    reply, used = asyncio.run(_ask(llm, system, text))
    value = _json_in(reply)
    if value.get("prefer") not in ("A", "B"):
        raise ValueError("the judge did not choose A or B")
    return {
        "prefer": pair[0 if value["prefer"] == "A" else 1][0],
        "sentence": value.get("sentence", ""),
        "usage": used,
    }
