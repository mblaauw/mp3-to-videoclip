"""Paid director tools estimate, authorize and only then queue work.

The services are faked here: this test owns the money ordering, not the provider.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path

from api_support import add_assets, make_api_project
from PIL import Image

from mp3_to_videoclip import production as P
from mp3_to_videoclip import services
from mp3_to_videoclip.director import tools
from mp3_to_videoclip.storage import digest, read_json


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "projects" / "demo"
    (root / "work").mkdir(parents=True)
    (root / "media").mkdir()
    source = root / "media" / "song.mp3"
    source.write_bytes(b"x")
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "slug": "demo",
                "title": "Demo",
                "source": "media/song.mp3",
                "source_sha256": hashlib.sha256(b"x").hexdigest(),
                "duration": 60.0,
                "aspect": "16:9",
                "fps": 24,
                "width": 1920,
                "height": 1080,
                "budget": [{"at": "2026-10-25T00:00:00+00:00", "cap_usd": "5.00"}],
            }
        )
    )
    (root / "work" / "tasks.json").write_text("{}")
    return root


class FakeRunner:
    def __init__(self):
        self.submitted = []

    def submit(self, kind, project, factory):
        self.submitted.append((kind, project))
        return "job-1"


def _fake_estimate(reserve="2.00", uploads=False, tasks=3):
    return {
        "quote_id": "quote-1",
        "scope": "stills",
        "tasks": tasks,
        "reserve_usd": reserve,
        "cap_usd": "5.00",
        "uploads_required": uploads,
        "shot_ids": ["s001", "s002", "s003"],
    }


def test_generate_images_authorizes_before_queueing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    authorized = {}
    monkeypatch.setattr(services.generation, "estimate", lambda *a, **k: _fake_estimate())
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda root, quote_id, **kw: authorized.update(quote_id=quote_id, **kw) or {},
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "generate_images",
                {"slug": "demo", "shot_ids": ["s001", "s002", "s003"]},
                runner,
            )
        )
    )
    assert result["status"] == "queued"
    assert result["job_id"] == "job-1"
    assert authorized["quote_id"] == "quote-1"
    assert runner.submitted == [("images", "demo")]


def test_generate_images_stops_at_the_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.generation, "estimate", lambda *a, **k: _fake_estimate(reserve="9.00")
    )
    monkeypatch.setattr(
        services.generation,
        "authorize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not authorize")),
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch("generate_images", {"slug": "demo", "shot_ids": ["s001"]}, runner)
        )
    )
    assert result["needs_budget"] is True
    assert result["decision"]["suggested_usd"]
    assert runner.submitted == []


def test_reference_upload_needs_confirmation_before_queueing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.generation, "estimate", lambda *a, **k: _fake_estimate(uploads=True)
    )
    runner = FakeRunner()
    result = json.loads(
        asyncio.run(
            tools.dispatch("generate_images", {"slug": "demo", "shot_ids": ["s001"]}, runner)
        )
    )
    assert "needs_confirmation" in result
    assert runner.submitted == []


def test_transcription_never_uploads_audio_from_chat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    monkeypatch.setattr(
        services.transcription,
        "quote",
        lambda root, language=None: {"id": "quote-2", "reserve_total_usd": "0.05"},
    )
    runner = FakeRunner()
    result = json.loads(asyncio.run(tools.dispatch("transcribe_lyrics", {"slug": "demo"}, runner)))
    assert "needs_confirmation" in result
    assert runner.submitted == []


def test_tools_follow_the_configured_projects_directory(tmp_path, monkeypatch):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)
    root = _project(tmp_path)
    result = json.loads(
        asyncio.run(tools.dispatch("get_project", {"slug": "demo"}, projects_dir=root.parent))
    )
    assert result == {"slug": "demo", "title": "Demo", "duration": 60.0}


def test_update_brief_deep_merges_and_keeps_the_world(tmp_path):
    root = make_api_project(tmp_path)
    before = P.load_brief(root)
    assert before.creative is not None

    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_brief",
                {"slug": "production", "patch": {"creative": {"look": "NEW LOOK ONLY"}}},
                projects_dir=tmp_path,
            )
        )
    )

    after = P.load_brief(root)
    assert result["creative"]["look"] == "NEW LOOK ONLY"
    assert after.creative is not None
    assert after.creative.look == "NEW LOOK ONLY"
    assert after.creative.image_rules == before.creative.image_rules
    assert after.creative.scenes == before.creative.scenes
    assert after.creative.references == before.creative.references
    assert after.creative.proof_shot_ids == before.creative.proof_shot_ids
    assert after.direction == before.direction
    history = root / f"work/brief-history/{digest(before.model_dump())}.json"
    assert read_json(history) == before.model_dump()


def test_update_brief_rejects_an_invalid_patch_without_writing(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "brief.json")
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_brief",
                {
                    "slug": "production",
                    "patch": {"creative": {"scenes": [{"id": "broken"}]}},
                },
                projects_dir=tmp_path,
            )
        )
    )
    assert "error" in result
    assert read_json(root / "brief.json") == before


def test_update_brief_refuses_to_blank_a_required_text_field(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "brief.json")
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_brief",
                {"slug": "production", "patch": {"style": ""}},
                projects_dir=tmp_path,
            )
        )
    )
    assert "style cannot be blank" in result["error"]
    assert read_json(root / "brief.json") == before


def test_update_shots_validates_the_whole_board_before_writing(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "work" / "storyboard.json")
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_shots",
                {
                    "slug": "production",
                    "changes": [
                        {"id": "s001", "purpose": "A changed purpose"},
                        {"id": "s002", "duration_frames": 13},
                    ],
                },
                projects_dir=tmp_path,
            )
        )
    )
    assert "error" in result
    assert read_json(root / "work" / "storyboard.json") == before


def test_update_shots_rejects_unknown_fields_and_ids(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "work" / "storyboard.json")
    for change in (
        {"id": "s001", "nonsense": True},
        {"id": "s001", "framing": "huge"},
        {"id": "s001", "scene_id": "missing-scene"},
        {"id": "missing", "purpose": "Nowhere"},
    ):
        result = json.loads(
            asyncio.run(
                tools.dispatch(
                    "update_shots",
                    {"slug": "production", "changes": [change]},
                    projects_dir=tmp_path,
                )
            )
        )
        assert "error" in result, change
        assert read_json(root / "work" / "storyboard.json") == before


def test_update_shots_returns_changed_ids_and_writes_a_valid_board(tmp_path):
    root = make_api_project(tmp_path)
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_shots",
                {
                    "slug": "production",
                    "changes": [
                        {"id": "s001", "purpose": "A changed purpose"},
                        {"id": "s002", "camera": "hold"},
                    ],
                },
                projects_dir=tmp_path,
            )
        )
    )
    assert result["changed"] == ["s001", "s002"]
    assert result["storyboard"]["shots"][0]["purpose"] == "A changed purpose"
    assert result["storyboard"]["shots"][1]["camera"] == "hold"
    assert P.load_board(root).shots[0].purpose == "A changed purpose"


def test_get_images_returns_bounded_thumbnails_as_image_parts(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    result = asyncio.run(
        tools.dispatch(
            "get_images",
            {"slug": "production", "shot_ids": ["s001", "s002"]},
            projects_dir=tmp_path,
        )
    )
    assert isinstance(result, tools.ToolResult)
    assert len(result.images) == 2
    assert "base64" not in result.text
    payload = json.loads(result.text)
    assert payload["image_count"] == 2
    for data_url in result.images:
        assert data_url.startswith("data:image/jpeg;base64,")
        raw = base64.b64decode(data_url.split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as image:
            assert max(image.size) <= tools.THUMBNAIL_PIXELS


def test_get_images_refuses_more_than_eight_shots(tmp_path):
    make_api_project(tmp_path)
    result = asyncio.run(
        tools.dispatch(
            "get_images",
            {"slug": "production", "shot_ids": [f"s{index:03d}" for index in range(9)]},
            projects_dir=tmp_path,
        )
    )
    assert isinstance(result, tools.ToolResult)
    assert result.images == ()
    assert "at most 8" in json.loads(result.text)["error"]


def test_update_treatments_validates_and_writes_three_distinct_routes(tmp_path):
    root = make_api_project(tmp_path)
    payload = {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"Route {index}",
                "structure": structure,
                "logline": "A courier crosses the city with a record.",
                "why": "The measured chorus earns the arrival.",
                "world": "Night streets, practical light, one record.",
                "shape": ["open", "lose", "search", "arrive"],
                "signature_moment": "The label becomes a street lamp.",
                "risk": "The city may read as generic.",
            }
            for index, structure in enumerate(("narrative", "demonstration", "three reasons"))
        ]
    }
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {"slug": "production", **payload},
                projects_dir=tmp_path,
            )
        )
    )
    assert len(result["concepts"]) == 3
    assert read_json(root / "work/treatments.json")["concepts"][0]["id"] == "c0"

    duplicate = json.loads(json.dumps(payload))
    duplicate["concepts"][1]["structure"] = "narrative"
    failed = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {"slug": "production", **duplicate},
                projects_dir=tmp_path,
            )
        )
    )
    assert "different structures" in failed["error"]


def test_concept_limits_accept_long_fields_and_advertise_the_same_bound(tmp_path):
    payload = {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"Route {index}",
                "structure": structure,
                "logline": "A courier crosses the city with a record.",
                "why": "w" * 1200,
                "world": "d" * 1200,
                "shape": ["open", "lose", "search", "arrive"],
                "signature_moment": "The label becomes a street lamp.",
                "risk": "r" * 800,
            }
            for index, structure in enumerate(("narrative", "demonstration", "three reasons"))
        ]
    }
    saved = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {"slug": "production", **payload},
                projects_dir=tmp_path,
            )
        )
    )
    assert saved["concepts"][0]["why"] == "w" * 1200
    assert saved["concepts"][1]["risk"] == "r" * 800

    too_long = json.loads(json.dumps(payload))
    too_long["concepts"][0]["why"] = "w" * 1201
    failed = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {"slug": "production", **too_long},
                projects_dir=tmp_path,
            )
        )
    )
    assert "concepts.0.why" in failed["error"]
    assert "at most 1200 characters" in failed["error"]

    schema = next(tool for tool in tools.TOOLS if tool["function"]["name"] == "update_treatments")
    properties = schema["function"]["parameters"]["properties"]["concepts"]["items"]["properties"]
    limits = {
        "title": 120,
        "structure": 80,
        "logline": 300,
        "why": 1200,
        "world": 1200,
        "signature_moment": 300,
        "risk": 800,
    }
    assert {name: properties[name]["maxLength"] for name in limits} == limits
