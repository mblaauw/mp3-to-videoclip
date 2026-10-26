"""Offline checks for the frozen T3 eval inputs.

The live Writer run is a separate, authorized step. These checks only validate
what a run returns: three distinct concept structures, a complete board, the
advert's local kinds and claims that trace back to the intent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

from mp3_to_videoclip import shotkinds
from mp3_to_videoclip.models import Storyboard, Treatments

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixtures() -> list[dict]:
    values = []
    for path in sorted(FIXTURES.glob("*.json")):
        value = json.loads(path.read_text())
        value["path"] = str(path)
        values.append(value)
    return values


def fixture(name: str) -> dict:
    return next(value for value in load_fixtures() if value["name"] == name)


def materialize_stills(value: dict, directory: Path) -> list[Path]:
    """Draw deterministic gradient stand-ins; no provider, no text in pixels."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, still in enumerate(value["stills"]):
        first = still["colors"][0].lstrip("#")
        second = still["colors"][1].lstrip("#")
        left = tuple(int(first[i : i + 2], 16) for i in (0, 2, 4))
        right = tuple(int(second[i : i + 2], 16) for i in (0, 2, 4))
        width, height = 512, 288
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for x in range(width):
            mix = x / max(1, width - 1)
            colour = tuple(round(left[i] * (1 - mix) + right[i] * mix) for i in range(3))
            for y in range(height):
                band = 0.92 + 0.08 * ((x + y + index * 17) % 23) / 22
                pixels[x, y] = tuple(min(255, round(channel * band)) for channel in colour)
        path = directory / f"{still['shot_id']}.png"
        image.save(path)
        paths.append(path)
    return paths


def concept_report(value: dict | Treatments) -> dict:
    if isinstance(value, Treatments):
        structures = [concept.structure.strip().casefold() for concept in value.concepts]
        count = len(value.concepts)
    else:
        concepts = value.get("concepts") if isinstance(value, dict) else []
        concepts = concepts if isinstance(concepts, list) else []
        structures = [
            str(concept.get("structure") or "").strip().casefold()
            for concept in concepts
            if isinstance(concept, dict)
        ]
        count = len(structures)
    return {
        "count": count,
        "distinct_structures": len(set(structures)),
        "ok": count == 3 and len(set(structures)) == 3,
    }


_TEXT_CARD = re.compile(r"^(?:card|end_card|logo)$")


def storyboard_report(value: dict | Storyboard, *, kind: str) -> dict:
    board = value if isinstance(value, Storyboard) else Storyboard.model_validate(value)
    issues: list[str] = []
    cursor = 0
    for shot in board.shots:
        if shot.start_frame != cursor:
            issues.append(f"{shot.id}: frame gap or overlap at {shot.start_frame}")
        cursor += shot.duration_frames
        if not shot.message.strip() and shot.kind != "scene":
            issues.append(f"{shot.id}: {shot.kind} needs a message")
        if _TEXT_CARD.match(shot.kind):
            for line in shot.text:
                if len(line.split()) > 7:
                    issues.append(f"{shot.id}: text line is longer than seven words")
        if shotkinds.is_paid(shot) and not shot.image_prompt.strip():
            issues.append(f"{shot.id}: generated shot has no image prompt")
    if cursor != board.total_frames:
        issues.append(f"board covers {cursor} of {board.total_frames} frames")
    non_scene = [shot.id for shot in board.shots if shot.kind != "scene"]
    if kind == "advert" and len(non_scene) < 2:
        issues.append("advert needs at least two non-scene kinds")
    return {
        "shots": len(board.shots),
        "non_scene": non_scene,
        "ok": not issues,
        "issues": issues,
    }


_DATE = re.compile(
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b",
    re.IGNORECASE,
)
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PRICE = re.compile(r"[$€£]\s?\d+(?:[.,]\d+)?")
_PERCENT = re.compile(r"\b\d+\s?%")


def claim_report(values: list[str], allowed: list[str]) -> dict:
    text = " ".join(values)
    supplied = " ".join(allowed).casefold()
    invented = []
    for pattern in (_DATE, _URL, _PRICE, _PERCENT):
        for match in pattern.findall(text):
            token = match.strip().rstrip(".,;:!?)").casefold()
            if token not in supplied:
                invented.append(match)
    return {"invented": sorted(set(invented)), "ok": not invented}


def report(fixture_value: dict, treatments: dict, board: dict) -> dict:
    concepts = concept_report(treatments)
    storyboard = storyboard_report(board, kind=fixture_value["kind"])
    values = [shot.get("message", "") for shot in board.get("shots", [])]
    values += [line for shot in board.get("shots", []) for line in shot.get("text", [])]
    values += [concept.get("title", "") for concept in treatments.get("concepts", [])]
    claims = claim_report(values, fixture_value.get("allowed_facts", []))
    return {
        "concepts": concepts,
        "storyboard": storyboard,
        "claims": claims,
        "ok": concepts["ok"] and storyboard["ok"] and claims["ok"],
    }


def edit_report(fixture_value: dict, board: dict, report_value: dict) -> dict:
    """Automatic Editor checks: schema/board coverage, hard report, claims, ad."""
    storyboard = storyboard_report(board, kind=fixture_value["kind"])
    issues = [f"board: {issue}" for issue in storyboard["issues"]]
    for finding in report_value.get("hard", []):
        issues.append(f"hard {finding.get('code')}: {finding.get('message')}")
    values = [shot.get("message", "") for shot in board.get("shots", [])]
    values += [line for shot in board.get("shots", []) for line in shot.get("text", [])]
    values += [line for shot in report_value.get("shots", []) for line in shot.get("text", [])]
    claims = claim_report(values, fixture_value.get("allowed_facts", []))
    if not claims["ok"]:
        issues.append("claims: " + ", ".join(claims["invented"]))
    ad = report_value.get("ad") or {"applicable": False, "checks": []}
    for check in ad.get("checks", []):
        if check.get("automatic", True) and not check.get("ok"):
            issues.append(f"ad {check.get('id')}: {check.get('message')}")
    return {
        "ok": not issues,
        "issues": issues,
        "storyboard": storyboard,
        "claims": claims,
        "hard": report_value.get("hard", []),
        "warnings": report_value.get("warnings", []),
        "counts": report_value.get("counts", {}),
        "techniques": report_value.get("techniques", []),
        "ad": ad,
    }
