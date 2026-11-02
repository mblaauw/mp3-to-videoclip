"""Story film templates: the beats a script fills, and what each beat asks for.

The code table is authoritative for ids, budgets and rules. The Writer's prose lives in
``director/prompts/structures/<id>.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Beat:
    id: str
    label: str
    seconds: float
    rule: str = ""
    #: Where the picture sits against the voice: ahead of the first word, or past the last.
    lead_picture: bool = False
    hold_after: bool = False


@dataclass(frozen=True)
class Structure:
    id: str
    label: str
    beats: tuple[Beat, ...]


STRUCTURES = {
    "five-beat-2m": Structure(
        "five-beat-2m",
        "Five beats",
        (
            Beat("hook", "Hook", 8, "Image before the first word.", lead_picture=True),
            Beat("world", "World", 27, "Establish the place and who is speaking."),
            Beat("develop", "Develop", 40, "Complicate what the hook promised."),
            Beat(
                "reveal",
                "Reveal",
                30,
                "Hold on the image after the sentence ends.",
                hold_after=True,
            ),  # fmt: skip
            Beat("payoff", "Payoff", 15, "Leave one thing behind."),
        ),
    ),
    "place-across-time": Structure(
        "place-across-time",
        "One place across time",
        tuple(
            Beat(
                f"era-{n}",
                f"Era {n}",
                24,
                "One framing: a constant and a change.",
                lead_picture=n == 1,
            )  # fmt: skip
            for n in range(1, 6)
        ),
    ),
    "essay": Structure(
        "essay",
        "Essay",
        (
            Beat(
                "question",
                "Question",
                15,
                "Ask something the viewer wants answered.",
                lead_picture=True,
            ),  # fmt: skip
            Beat("evidence", "Evidence", 60, "Each line shows, it does not assert."),
            Beat("turn", "Turn", 25, "The evidence says something unexpected.", hold_after=True),
            Beat("answer", "Answer", 20, "Answer less than was asked."),
        ),
    ),
    "fable": Structure(
        "fable",
        "Fable",
        (
            Beat("once", "Once", 20, "A place, a creature, a want.", lead_picture=True),
            Beat("trial", "Trial", 60, "Three attempts, each costing more."),
            Beat("cost", "Cost", 25, "What it took.", hold_after=True),
            Beat("moral", "Moral", 15, "Never state it outright."),
        ),
    ),
}
DEFAULT = "five-beat-2m"


def get(structure_id: str) -> Structure:
    try:
        return STRUCTURES[structure_id]
    except KeyError as exc:
        raise ValueError(f"unknown story structure {structure_id!r}") from exc


def instance(structure_id: str, length: float) -> dict:
    """The template at this film's length: budgets scale together and keep their shape."""
    structure = get(structure_id)
    total = sum(beat.seconds for beat in structure.beats)
    scale = length / total if length > 0 else 1.0
    return {
        "structure": structure.id,
        "label": structure.label,
        "length": length,
        "beats": [
            {
                "id": beat.id,
                "label": beat.label,
                "budget": round(beat.seconds * scale, 2),
                "rule": beat.rule,
                "lead_picture": beat.lead_picture,
                "hold_after": beat.hold_after,
            }
            for beat in structure.beats
        ],
    }


def public() -> list[dict]:
    return [
        {"id": item.id, "label": item.label, "length": sum(b.seconds for b in item.beats)}
        for item in STRUCTURES.values()
    ]
