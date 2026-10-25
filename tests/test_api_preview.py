"""The live Player payload: resolved renderer fields, URLs and honest placeholders."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_api_project(tmp_path)


@pytest.fixture
def client(tmp_path: Path, project: Path):
    with api_client(tmp_path) as value:
        yield value


def test_preview_input_carries_renderer_fields_and_local_urls(client, project):
    add_assets(project)
    data = client.get("/api/projects/production/preview").json()
    assert data["available"] is True
    assert data["fps"] == 24
    assert data["width"] == 192
    assert data["durationInFrames"] == 48
    assert data["audio"] == "/api/projects/production/audio"
    assert len(data["shots"]) == 4
    first = data["shots"][0]
    assert first["image"].endswith(".jpg")
    assert first["src"] == "/api/projects/production/images/s001/1"
    assert first["still_current"] is True
    assert first["start_frame"] == 0 and first["duration_frames"] == 12
    assert data["preview_placeholders"] == []
    assert data["stale_shots"] == []
    assert client.get(first["src"]).status_code == 200


def test_preview_input_marks_missing_and_stale_stills_without_losing_the_span(client, project):
    add_assets(project)
    assets = read_json(project / "work" / "assets.json")
    assets["s002"]["selected"] = 99
    write_json(project / "work" / "assets.json", assets)
    brief = read_json(project / "brief.json")
    brief["creative"]["look"] = brief["creative"]["look"] + " with more grain"
    write_json(project / "brief.json", brief)

    data = client.get("/api/projects/production/preview").json()
    by_id = {shot["id"]: shot for shot in data["shots"]}
    assert by_id["s002"]["src"] is None
    assert by_id["s002"]["image"] == "missing-still.jpg"
    assert by_id["s002"]["duration_frames"] == 12
    assert data["preview_placeholders"] == ["s002"]
    assert set(data["stale_shots"]) == {"s001", "s003", "s004"}
    assert by_id["s001"]["still_current"] is False


def test_preview_input_preserves_camera_effects_and_transition(client, project):
    add_assets(project)
    board = read_json(project / P.STAGE_FILES["storyboard"])
    board["shots"][0]["dissolve_frames"] = 2
    board["shots"][0]["transition"] = "wipe_left"
    board["shots"][0]["post_effects"] = {"contrast": 1.1, "vignette": 0.12}
    board["shots"][0]["camera_path"] = {
        "start": {"zoom": 1, "x": 0.5, "y": 0.5},
        "end": {"zoom": 1.08, "x": 0.8, "y": 0.5},
        "easing": "smoothstep",
    }
    write_json(project / P.STAGE_FILES["storyboard"], board)

    first = client.get("/api/projects/production/preview").json()["shots"][0]
    assert first["dissolve_frames"] == 2
    assert first["transition"] == "wipe_left"
    assert first["post_effects"] == {
        "contrast": 1.1,
        "saturation": 1,
        "brightness": 1,
        "vignette": 0.12,
    }
    assert first["camera_path"]["easing"] == "smoothstep"


def test_preview_input_is_unavailable_before_a_storyboard(client, project):
    (project / P.STAGE_FILES["storyboard"]).unlink()
    data = client.get("/api/projects/production/preview").json()
    assert data["available"] is False
    assert "storyboard" in data["reason"].lower()
