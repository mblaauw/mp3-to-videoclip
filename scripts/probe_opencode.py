"""T1 Writer/Editor probe through the OpenCode gateway. Not a test.

A live run spends model tokens, so it refuses unless both ``--yes`` and
``PROBE_ALLOW_SPEND=1`` are present. It writes only to the project copy passed
on the command line; production folders are refused.

    PROBE_ALLOW_SPEND=1 uv run python scripts/probe_opencode.py \
      --project .opencode/scratch/t1/probe-project --yes

Each role must call ``clipstudio_get_project``, call ``clipstudio_get_images``
(two selected stills), call its write tool and finish without an error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mp3_to_videoclip import production as P
from mp3_to_videoclip.director.opencode import (
    EDITOR_MODEL,
    WRITER_MODEL,
    OpenCodeGateway,
    run_gateway_turn,
)

REPO = Path(__file__).resolve().parents[1]


def _refuse_production(path: Path) -> bool:
    for name in ("projects", "backups", "archive"):
        root = (REPO / name).resolve()
        if path == root or root in path.parents:
            return True
    return False


def _shot_ids(root: Path, count: int = 2) -> list[str]:
    board = P.load_board(root)
    ids = [shot.id for shot in board.shots]
    resolved = {item.shot.id for item in P.resolved_assets(root, ids)}
    return [shot_id for shot_id in ids if shot_id in resolved][:count]


def _prompt(role: str, slug: str, shots: list[str], stamp: str) -> str:
    write = (
        f'call clipstudio_update_brief with {{"slug":"{slug}","patch":'
        f'{{"treatment":"T1 writer probe {stamp}"}}}}'
        if role == "writer"
        else f'call clipstudio_update_shots with {{"slug":"{slug}","changes":'
        f'[{{"id":"{shots[0]}","purpose":"T1 editor probe {stamp}"}}]}}'
    )
    return (
        f"T1 probe on production {slug}. Work in this order and do not skip a step:\n"
        f'1. call clipstudio_get_project with {{"slug":"{slug}"}}\n'
        f'2. call clipstudio_get_images with {{"slug":"{slug}","shot_ids":{json.dumps(shots)}}}\n'
        f"3. {write}\n"
        "4. Reply with one sentence naming the tools you used."
    )


async def probe(
    *,
    project: Path,
    role: str,
    model: str,
    binary: str,
    workspace: Path,
    stamp: str,
) -> bool:
    slug = project.name
    gateway = OpenCodeGateway(
        binary=binary,
        workspace=workspace,
        projects_dir=project.parent,
        writer_model=model,
        editor_model=model,
    )
    await gateway.start()
    client = gateway.client()
    try:
        if not await client.model_available(model):
            print(f"{role}: model {model} is not in /api/model")
            return False
        shots = _shot_ids(project)
        if len(shots) < 2:
            print(f"{role}: need two stills with selected versions; found {len(shots)}")
            return False
        tool_events = []
        text = ""
        error = None
        async for event in run_gateway_turn(
            client,
            project,
            slug,
            role,
            _prompt(role, slug, shots, stamp),
            f"T1 probe. Production {slug}.",
            model=model,
        ):
            if event.kind == "text":
                text += event.text
            elif event.kind == "tool":
                tool_events.append(event)
                print(f"  tool {event.tool}: {event.result[:120]}")
            elif event.kind == "done":
                error = event.payload.get("error")
        names = {event.tool for event in tool_events if event.result}
        failed = [event.tool for event in tool_events if '"error"' in event.result]
        expected = {"clipstudio_get_project", "clipstudio_get_images"}
        expected.add("clipstudio_update_brief" if role == "writer" else "clipstudio_update_shots")
        missing = expected - names
        print(f"{role}: {text.strip()[:300]}")
        print(
            f"{role}: tools={sorted(names)} missing={sorted(missing)} failed={failed} error={error}"
        )
        return not missing and not error and not failed
    finally:
        await client.aclose()
        gateway.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="T1 OpenCode Writer/Editor probe")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--opencode-bin", default="opencode")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / ".local/share/mp3-to-videoclip/probe-opencode",
    )
    parser.add_argument("--writer-model", default=WRITER_MODEL)
    parser.add_argument("--editor-model", default=EDITOR_MODEL)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not args.yes or os.environ.get("PROBE_ALLOW_SPEND") != "1":
        print("Refusing to spend model tokens. Pass --yes and set PROBE_ALLOW_SPEND=1.")
        return 2
    project = args.project.resolve()
    if _refuse_production(project):
        print("Refusing to write inside projects/, backups/ or archive/; pass a copy.")
        return 2
    if not (project / "project.json").is_file():
        print(f"No project.json in {project}")
        return 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    writer = asyncio.run(
        probe(
            project=project,
            role="writer",
            model=args.writer_model,
            binary=args.opencode_bin,
            workspace=args.workspace,
            stamp=stamp,
        )
    )
    editor = asyncio.run(
        probe(
            project=project,
            role="editor",
            model=args.editor_model,
            binary=args.opencode_bin,
            workspace=args.workspace,
            stamp=stamp,
        )
    )
    return 0 if writer and editor else 1


if __name__ == "__main__":
    raise SystemExit(main())
