"""Shared API fixtures: a real schema-3 project and no provider calls."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_creative_production import jpeg, make_root

from mp3_to_videoclip import flow
from mp3_to_videoclip import production as P
from mp3_to_videoclip.app import create_app
from mp3_to_videoclip.references import import_reference
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json


def make_api_project(tmp_path: Path, name: str = "production") -> Path:
    """make_root upgraded to schema 3 with a matching slug and imported references."""
    root = make_root(tmp_path, name=name)
    project = read_json(root / "project.json")
    project["schema_version"] = 3
    project["slug"] = name
    write_json(root / "project.json", project)
    flow.mark(root)
    brief = read_json(root / "brief.json")
    for ref in brief["creative"]["references"]:
        imported = import_reference(
            root, root / ref["path"], note="test-owned reference", permission_confirmed=True
        )
        ref["path"] = imported["path"]
    write_json(root / "brief.json", brief)
    return root


def api_client(projects_dir: Path) -> TestClient:
    return TestClient(create_app(projects_dir=projects_dir), base_url="http://127.0.0.1")


def add_assets(root: Path, versions: int = 2) -> None:
    """Fake image versions for every shot; only route wiring is under test."""
    assets = {}
    for shot in P.load_board(root).shots:
        entries = []
        for version in range(1, versions + 1):
            path = jpeg(root / f"assets/{shot.id}/v{version:03d}-fake.jpg")
            entries.append(
                {
                    "version": version,
                    "path": path.relative_to(root).as_posix(),
                    "sha256": file_hash(path),
                    "input_hash": digest(P.image_spec(root, shot)),
                    "task_id": f"task-{shot.id}-{version}",
                }
            )
        assets[shot.id] = {"versions": entries, "selected": 1}
    write_json(root / "work" / "assets.json", assets)
