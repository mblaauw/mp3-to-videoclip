"""Reference runs from a scripted writer, so every page has a baseline at $0. No model is called.

``uv run python -m tests.evals.reference`` rewrites them. They show the checks working, not good
writing: a real run is compared against their numbers, never judged by them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .checks import fixture, load_fixtures

RUNS = Path(__file__).resolve().parent / "runs"
FPS = 24
FRAMINGS = ("wide", "detail", "medium", "close_up")
#: One small world per fixture: what the film is about, and the things in it.
WORLDS = {
    "advert-30s": ("a ceramic bottle", ("the glaze", "a hand", "white paper", "the pour", "a table", "its shadow")),
    "energetic-vocal": ("a brass band learning one song", ("a dented horn", "chalk marks", "a kitchen", "a bus stop", "the last rehearsal", "a borrowed coat")),
    "slow-instrumental": ("a house as the tide turns", ("the sea wall", "a wet step", "one lit room", "the tide line", "salt on glassware", "a door left open")),
    "bright-pastoral-120s": ("a harvest and one uncut row", ("a whetstone", "the field edge", "bread on a cloth", "a child's boots", "the uncut row", "a cart")),
}  # fmt: skip


def _treatments(subject: str) -> dict:
    routes = (
        ("Told in order", "narrative", f"One day of {subject}, each section later than the last."),
        ("Only the objects", "symbolic", f"{subject.capitalize()} told through what it leaves behind."),
    )  # fmt: skip
    return {
        "concepts": [
            {
                "id": f"c{index}",
                "title": title,
                "structure": structure,
                "logline": logline,
                "why": f"It shows {subject} changing instead of describing it.",
                "world": f"The ordinary places of {subject}, in plain daylight.",
                "signature_moment": f"The last image of {subject} changes how the first one reads.",
                "risk": "It only works if the small changes are visible at a glance.",
                "beats": [
                    {"start": 0, "end": 4, "label": "Opening", "text": "What is there at first."},
                    {"start": 4, "end": 8, "label": "Change", "text": "What the film changes."},
                    {"start": 8, "end": 12, "label": "Turn", "text": "What that costs."},
                    {"start": 12, "end": 16, "label": "Close", "text": "What is left behind."},
                ],
            }
            for index, (title, structure, logline) in enumerate(routes, start=1)
        ],
        "chosen_id": "c1",
    }


def _board(value: dict, things: tuple[str, ...]) -> dict:
    total = round(value["duration"] * FPS)
    count = max(6, min(12, round(value["duration"] / 5)))
    cuts = [round(total * index / count) for index in range(count + 1)]
    advert = value["kind"] == "advert"
    shots = []
    for index, (start, end) in enumerate(zip(cuts, cuts[1:], strict=False)):
        thing = things[index % len(things)]
        kind = "card" if advert and index in (1, count - 1) else "scene"
        shot = {
            "id": f"s{index + 1:03d}",
            "start_frame": start,
            "duration_frames": end - start,
            "kind": kind,
            "purpose": f"Show {thing} doing something it was not doing before",
            "message": f"{thing.capitalize()} has changed",
            "framing": FRAMINGS[index % len(FRAMINGS)],
            "scene_id": f"place-{index % 3}",
        }
        if kind == "scene":
            shot["image_prompt"] = (
                f"{thing.capitalize()} in plain daylight, seen from close to the ground."
            )
        else:
            shot["text"] = ["Made by hand"]
        shots.append(shot)
    return {"aspect": "16:9", "fps": FPS, "total_frames": total, "shots": shots}


def write_all(directory: Path = RUNS) -> list[Path]:
    made = []
    for value in load_fixtures():
        name = value["name"]
        subject, things = WORLDS[name]
        run = directory / f"reference-{name}"
        run.mkdir(parents=True, exist_ok=True)
        (run / "treatments.json").write_text(json.dumps(_treatments(subject), indent=2) + "\n")
        (run / "storyboard.json").write_text(json.dumps(_board(fixture(name), things), indent=2) + "\n")  # fmt: skip
        (run / "meta.json").write_text(
            json.dumps(
                {
                    "fixture": name,
                    "role": "writer",
                    "model": "scripted-reference",
                    "synthetic": True,
                    "created_at": "2026-11-01T00:00:00Z",
                    "prompt": {"hash": "reference", "files": [], "task": "storyboard"},
                },
                indent=2,
            )
            + "\n"
        )
        made.append(run)
    return made


if __name__ == "__main__":
    for path in write_all():
        print(path)
