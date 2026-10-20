"""Context packs: exactly what a planning step is allowed to know.

A prompt is not context. This module assembles a small, labelled digest from admitted
artifacts, states what is unknown, and refuses to include anything the step did not ask
for. It is the boundary that keeps a model from inventing project state — and the thing
an eval can assert on before any model call exists.
"""

from __future__ import annotations

from pathlib import Path

from . import production as P
from .storage import file_hash, read_optional

CHARS_PER_TOKEN = 4


def build(root: Path, *, stage: str | None = None, shots: int = 0, include_prompts=False) -> dict:
    """Assemble a deterministic digest. ``shots=0`` means no shot detail at all."""
    root = Path(root)
    project = P.load_project(root)
    board = P.load_board(root)
    brief = P.load_brief(root)
    approvals = {}
    for name in (
        "analysis",
        "events",
        "brief",
        "storyboard",
        "proof",
        "preview",
        "stills",
        "graphics",
    ):
        try:
            current = P.stage_hash(root, name)
        except (OSError, ValueError, KeyError):
            approvals[name] = "unavailable"
            continue
        record = (
            (P.read_json(root / "work/approvals.json") or {}).get(name)
            if (root / "work/approvals.json").is_file()
            else None
        )
        approvals[name] = (
            "approved"
            if record and record.get("hash") == current
            else ("stale" if record else "missing")
        )

    selected = []
    for shot in board.shots[: max(0, shots)]:
        entry = {
            "id": shot.id,
            "start_frame": shot.start_frame,
            "seconds": round(shot.duration_frames / project.fps, 2),
            "purpose": shot.purpose,
            "framing": shot.framing,
            "camera": shot.camera,
            "transition": shot.transition or "cut",
            "must_show": shot.must_show,
        }
        if include_prompts:
            entry["image_prompt"] = shot.image_prompt
        selected.append(entry)

    music_path = root / "work/music.json"
    music = read_optional(music_path, {})
    unknowns = []
    if music_path.is_file() and not music:
        unknowns.append(
            "music.json exists but could not be read; no tempo or section claim is safe"
        )
    if not (root / "work/music-grid.json").is_file():
        unknowns.append("no approved meter/bar grid: do not state BPM, bars or downbeats as fact")
    if not (root / "work/lyrics.json").is_file():
        unknowns.append("no reviewed lyric timestamps")
    unknowns.append("continuous playback is unverified unless this project recorded a watch")
    unknown_stages = [name for name, state in approvals.items() if state != "approved"]
    if unknown_stages:
        unknowns.append(f"stages not current: {', '.join(unknown_stages)}")

    pack = {
        "schema_version": 1,
        "production": {
            "slug": project.slug,
            "title": project.title,
            "duration": project.duration,
            "fps": project.fps,
            "aspect": project.aspect,
            "frames": project.total_frames,
            "shots": len(board.shots),
        },
        "stage_requested": stage,
        "direction": brief.direction,
        "approvals": approvals,
        "budget": {
            "cap_usd": (P.read_json(root / "work/production-budget.json") or {}).get("cap_usd")
            if (root / "work/production-budget.json").is_file()
            else None,
        },
        "music": {
            "tempo_estimate": music.get("estimated_tempo_bpm"),
            "beats": len(music.get("beats") or []),
            "basis": "measured estimate; not meter or downbeat",
        },
        "shots": selected,
        "unknowns": unknowns,
        "sources": {
            "brief": file_hash(root / "brief.json"),
            "storyboard": file_hash(root / "work/storyboard.json"),
        },
        "limits": (
            "A digest, not the artifacts. Quote hashes when a decision depends on exact bytes; "
            "never infer a fact that is absent here."
        ),
    }
    pack["estimated_tokens"] = len(render(pack)) // CHARS_PER_TOKEN
    return pack


def render(pack: dict) -> str:
    """Compact text form for a model turn, with provenance kept visible."""
    lines = [
        f"PRODUCTION {pack['production']['slug']} — {pack['production']['title']}",
        f"{pack['production']['seconds'] if 'seconds' in pack['production'] else round(pack['production']['duration'], 2)}s · "
        f"{pack['production']['shots']} shots · {pack['production']['fps']}fps · {pack['production']['aspect']}",
        f"DIRECTION {pack['direction']}",
        "APPROVALS " + ", ".join(f"{stage}={state}" for stage, state in pack["approvals"].items()),
        f"TEMPO {pack['music']['tempo_estimate']} (measured estimate; no meter claimed)",
    ]
    for shot in pack["shots"]:
        lines.append(
            f"SHOT {shot['id']} @{shot['start_frame']} {shot['seconds']}s "
            f"{shot['framing']} / {shot['camera']} / {shot['transition']}: {shot['purpose']}"
        )
    lines.append("UNKNOWNS: " + "; ".join(pack["unknowns"]))
    lines.append("LIMITS: " + pack["limits"])
    return "\n".join(lines)
