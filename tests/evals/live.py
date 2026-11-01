"""One live evaluation run: a frozen fixture, a real model, a bundle the report can read.

This is the only part of the harness that calls a model, so it runs only by hand with
--authorized, spends no image money (stills are drawn locally), and works in a throwaway
projects folder. The bundle goes under tests/evals/runs/ and is not committed.

    uv run python -m tests.evals.live --fixture advert-30s --role writer --authorized
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from mp3_to_videoclip import edits, styles
from mp3_to_videoclip import production as P
from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director import prompts
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.director.llm import DirectorLLM
from mp3_to_videoclip.director.loop import run_turn
from mp3_to_videoclip.director.routing import route_for
from mp3_to_videoclip.domain import intake
from mp3_to_videoclip.storage import read_json, write_json

from . import checks
from .runner import RUNS

SLUG = "eval-fixture"
WRITER_ASK = (
    "Work from the brief and the measured music. First write three distinct concepts with "
    "update_treatments and choose the best. Then write the whole storyboard with "
    "write_storyboard, for this kind of film. Only use facts in the brief."
)
EDITOR_ASK = (
    "Cut the whole film from the storyboard and the measured music with update_edit. Write a "
    "feel for each section, and fix every hard finding in the report."
)


def _song(path: Path, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=110:duration={seconds}", "-ac", "2", str(path),
        ],
        check=True,
    )  # fmt: skip


def _project(projects: Path, fixture: dict) -> Path:
    """A real production for the fixture, with its measured music and intent."""
    song = projects.parent / "song.mp3"
    _song(song, float(fixture.get("source_duration") or fixture["duration"]))
    window = fixture.get("audio_window") or {}
    intake.create_from_upload(
        projects,
        song,
        title=SLUG,
        kind=fixture["kind"],
        music_mode=fixture["music_mode"],
        budget="1.00",
        intent=fixture.get("intent"),
        style_preset=styles.default_for(fixture["kind"]).id,
        length_seconds=(window["end"] - window["start"]) if window else None,
        window_start=window.get("start", 0.0),
        fade_in=window.get("fade_in", 0.0),
        fade_out=window.get("fade_out", 0.0),
    )
    root = projects / SLUG
    write_json(
        root / P.STAGE_FILES["analysis"],
        {**fixture["music"], "duration": fixture["duration"], "warnings": []},
    )
    project = P.load_project(root)
    write_json(
        root / P.STAGE_FILES["storyboard"],
        {
            "schema_version": 1,
            "aspect": project.aspect,
            "fps": project.fps,
            "total_frames": project.total_frames,
            "shots": [
                {
                    "id": "s001",
                    "start_frame": 0,
                    "duration_frames": project.total_frames,
                    "purpose": "TODO: approved story purpose",
                    "image_prompt": "TODO: compose this shot",
                }
            ],
        },
    )
    return root


async def _turn(root: Path, role: str, message: str, task: str, model: str) -> dict:
    route = route_for(effective_settings(), role)
    llm = DirectorLLM(route.base_url, route.key, route.model, kind=route.kind)
    project = P.load_project(root)
    stage = "storyboard" if role == "writer" else "film"
    bundle = prompts.assemble(
        root, stage, role=role, kind=project.kind, style_preset=project.style_preset, task=task
    )
    system = (
        bundle.text
        + "\n\n---\n\n"
        + build_context(SLUG, root.parent, stage=stage, context={}, task=bundle.task)
    )
    reply, tools = "", []
    async for event in run_turn(
        llm,
        root,
        SLUG,
        message,
        system,
        projects_dir=root.parent,
        prompt_meta=bundle.meta,
        role=role,
        provider=route.provider,
    ):
        if event.kind == "tool":
            tools.append(event.tool)
        elif event.kind == "text":
            reply += event.text or ""
        elif event.kind == "done" and (event.payload or {}).get("error"):
            reply += "\n[error] " + str(event.payload["error"])
    return {"meta": bundle.meta, "reply": reply, "tools": tools}


def _prepare_editor(root: Path, board_path: Path) -> None:
    """The Writer's board with drawn stand-ins, so an Editor run spends nothing on images."""
    write_json(root / P.STAGE_FILES["storyboard"], read_json(board_path))
    board = P.load_board(root)
    stills = checks.materialize_stills(
        {
            "stills": [
                {"shot_id": shot.id, "colors": ["#20242C", "#6C5A48"]}
                for shot in board.shots
                if shot.asset_shot_id is None
            ]
        },
        root / "assets" / "eval",
    )
    assets = {}
    owners = [shot.id for shot in board.shots if shot.asset_shot_id is None]
    for shot_id, still in zip(owners, stills, strict=True):
        assets[shot_id] = {
            "selected": 1,
            "versions": [
                {
                    "version": 1,
                    "path": still.relative_to(root).as_posix(),
                    "sha256": P.file_hash(still),
                    "input_hash": "eval",
                    "task_id": "eval",
                }
            ],
        }
    write_json(root / "work/assets.json", assets)
    edits.seed_edit(root)


def run(fixture_name: str, role: str, board: Path | None) -> Path:
    fixture = checks.fixture(fixture_name)
    settings = effective_settings()
    model = settings.writer_model if role == "writer" else settings.editor_model
    run_id = f"{fixture_name}-{role}-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    bundle = RUNS / run_id
    with tempfile.TemporaryDirectory(prefix="eval-live-") as scratch:
        projects = Path(scratch) / "projects"
        projects.mkdir()
        root = _project(projects, fixture)
        if role == "editor":
            if board is None:
                raise SystemExit("an editor run needs --board from a writer run")
            _prepare_editor(root, board)
        task, ask = ("storyboard", WRITER_ASK) if role == "writer" else ("edit", EDITOR_ASK)
        outcome = asyncio.run(_turn(root, role, ask, task, model))
        bundle.mkdir(parents=True)
        artifacts = {"storyboard": "storyboard.json"}
        shutil.copy(root / P.STAGE_FILES["storyboard"], bundle / "storyboard.json")
        if role == "writer":
            treatments = root / "work/treatments.json"
            if treatments.is_file():
                shutil.copy(treatments, bundle / "treatments.json")
            artifacts["treatments"] = "treatments.json"
        else:
            edit = root / "work/edit.json"
            if edit.is_file():
                shutil.copy(edit, bundle / "edit.json")
            artifacts["edit"] = "edit.json"
    (bundle / "meta.json").write_text(
        json.dumps(
            {
                "fixture": fixture_name,
                "role": role,
                "model": model,
                "created_at": datetime.now(UTC).isoformat(),
                "prompt": outcome["meta"],
                "artifacts": artifacts,
                "reply": outcome["reply"],
                "tools": outcome["tools"],
            },
            indent=2,
        )
    )
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--role", choices=("writer", "editor"), required=True)
    parser.add_argument("--board", type=Path, help="a writer run's storyboard.json")
    parser.add_argument(
        "--authorized", action="store_true", help="the owner approved this live call"
    )
    args = parser.parse_args()
    if not args.authorized:
        raise SystemExit(
            "this calls a live model; pass --authorized once the owner has approved it"
        )
    print(run(args.fixture, args.role, args.board))


if __name__ == "__main__":
    main()
