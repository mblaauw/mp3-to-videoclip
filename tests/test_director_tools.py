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

import pytest
from api_support import add_assets, api_client, make_api_project
from PIL import Image

from mp3_to_videoclip import production as P
from mp3_to_videoclip import services
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.storage import digest, read_json, write_json


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

    def submit(self, kind, project, factory, *, blocking=False, render_kind=None):
        assert blocking is True
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


def _profile_payload(**overrides):
    payload = {
        "slug": "production",
        "characters": [
            {
                "id": "woman",
                "identity": "woman, early 30s, pale skin, green eyes, long blonde hair",
                "states": {
                    "dream": {"description": "hair loose, ivory linen, barefoot"},
                    "waking": {"description": "hair tied back, buttoned ivory linen"},
                },
                "default_state": "waking",
                "permission_confirmed": True,
            }
        ],
        "scenes": [{"id": "garden", "description": "A walled garden at first light, damp stone."}],
        "arc": [{"phase": "open", "intention": "distance"}],
        "image_rules": ["Single coherent frame."],
        "avoid": ["posed smiles"],
        "look": "A photorealistic 35mm still with visible skin texture, soft dawn light, "
        "a restrained palette and fine grain. Not CGI, not a glossy advert.",
    }
    payload.update(overrides)
    return payload


def test_set_creative_profile_writes_the_structured_profile(tmp_path):
    root = make_api_project(tmp_path)
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "set_creative_profile",
                _profile_payload(),
                projects_dir=tmp_path,
            )
        )
    )
    after = P.load_brief(root)
    assert result["creative"]["profile_version"] == 1
    assert after.creative.profile_version == 1
    assert [character.id for character in after.characters] == ["woman"]
    assert after.characters[0].states["dream"].description.startswith("hair loose")
    assert after.creative.scenes[0].id == "garden"
    assert after.creative.arc[0].phase == "open"
    assert after.creative.look.startswith("A photorealistic 35mm still")
    assert after.avoid == ["posed smiles"]


def test_set_creative_profile_enforces_the_writing_budget(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "brief.json")

    too_many_rules = json.loads(
        asyncio.run(
            tools.dispatch(
                "set_creative_profile",
                _profile_payload(image_rules=[f"Rule {index}" for index in range(7)]),
                projects_dir=tmp_path,
            )
        )
    )
    assert "at most 6" in too_many_rules["error"]

    long_look = json.loads(
        asyncio.run(
            tools.dispatch(
                "set_creative_profile",
                _profile_payload(look="word " * 181),
                projects_dir=tmp_path,
            )
        )
    )
    assert "180 words" in long_look["error"]
    assert read_json(root / "brief.json") == before


def test_set_creative_profile_keeps_the_protected_core_verbatim(tmp_path):
    from mp3_to_videoclip import profiles

    root = make_api_project(tmp_path)
    P.apply_intake(root, style_preset=profiles.STYLE_PRESET_ID)
    core = profiles.DEFAULT_STYLE
    accepted = json.loads(
        asyncio.run(
            tools.dispatch(
                "set_creative_profile",
                _profile_payload(look=core + "\n\nHard amber key light."),
                projects_dir=tmp_path,
            )
        )
    )
    assert "error" not in accepted
    assert P.load_brief(root).creative.look.startswith(core)

    before = read_json(root / "brief.json")
    rejected = json.loads(
        asyncio.run(
            tools.dispatch(
                "set_creative_profile",
                _profile_payload(look="A completely different look."),
                projects_dir=tmp_path,
            )
        )
    )
    assert "approved DEFAULT_STYLE core" in rejected["error"]
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
    assert "different structure" in failed["error"]


def test_concept_limits_accept_long_fields_and_advertise_the_same_bound(tmp_path):
    make_api_project(tmp_path)
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


def _route(index, structure, **fields):
    route = {
        "id": f"c{index}",
        "title": f"Route {index}",
        "structure": structure,
        "logline": "A line.",
        "why": "It fits.",
        "world": "A world.",
        "beats": [
            {"start": at * 10.0, "end": (at + 1) * 10.0, "label": f"Beat {at}", "text": "It moves."}
            for at in range(4)
        ],
        "signature_moment": "One image.",
        "risk": "A risk.",
    }
    return {**route, **fields}


@pytest.mark.parametrize("count", [1, 2, 3])
def test_a_film_holds_one_to_three_concepts(tmp_path, count):
    root = tmp_path / "p"
    root.mkdir()
    structures = ("narrative", "performance", "symbolic")
    routes = [_route(index, structures[index]) for index in range(count)]
    saved = P.update_treatments(root, {"concepts": routes})
    assert len(saved.concepts) == count
    assert saved.concepts[0].beats[0].label == "Beat 0"
    assert "shape" not in read_json(root / "work/treatments.json")["concepts"][0]


def test_concept_counts_and_structures_are_still_refused(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    with pytest.raises(ValueError, match="invalid"):
        P.update_treatments(root, {"concepts": []})
    four = [_route(index, f"structure {index}") for index in range(4)]
    with pytest.raises(ValueError, match="invalid"):
        P.update_treatments(root, {"concepts": four})
    same = [_route(0, "narrative"), _route(1, "Narrative")]
    with pytest.raises(ValueError, match="different structure"):
        P.update_treatments(root, {"concepts": same})


def test_concept_beats_must_be_ordered_and_inside_the_film(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    write_json(root / "project.json", {"duration": 35.0})
    with pytest.raises(ValueError, match="the film is 35.0 s"):
        P.update_treatments(root, {"concepts": [_route(0, "narrative")]})
    (root / "project.json").unlink()
    crossing = _route(0, "narrative")
    crossing["beats"][1]["start"] = 5.0
    with pytest.raises(ValueError, match="without overlapping"):
        P.update_treatments(root, {"concepts": [crossing]})
    backwards = _route(0, "narrative")
    backwards["beats"][0]["end"] = 0.0
    with pytest.raises(ValueError):
        P.update_treatments(root, {"concepts": [backwards]})


def test_an_empty_chosen_id_from_the_writer_means_no_choice(tmp_path):
    make_api_project(tmp_path)
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {
                    "slug": "production",
                    "concepts": [_route(0, "narrative", beats=[])],
                    "chosen_id": "",
                },
                projects_dir=tmp_path,
            )
        )
    )
    assert "error" in result  # no beats and no shape is still refused
    route = _route(0, "narrative", shape=["a", "b", "c", "d"], beats=[])
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "update_treatments",
                {"slug": "production", "concepts": [route], "chosen_id": ""},
                projects_dir=tmp_path,
            )
        )
    )
    assert result.get("chosen_id") is None and len(result["concepts"]) == 1


def test_older_concepts_with_free_text_shape_still_read_and_keep_their_form(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    old = [
        {key: value for key, value in _route(index, name).items() if key != "beats"}
        | {"shape": ["a", "b", "c", "d"]}
        for index, name in enumerate(("narrative", "performance", "symbolic"))
    ]
    write_json(
        root / "work/treatments.json", {"schema_version": 1, "concepts": old, "chosen_id": "c1"}
    )
    loaded = P.load_treatments(root)
    assert loaded.chosen_id == "c1" and loaded.concepts[0].shape == ["a", "b", "c", "d"]
    assert "beats" not in loaded.model_dump()["concepts"][0]


def test_a_film_length_passed_as_shot_length_is_refused_before_it_locks_the_board(tmp_path):
    root = make_api_project(tmp_path)
    (root / P.STAGE_FILES["storyboard"]).unlink(missing_ok=True)
    result = json.loads(
        asyncio.run(
            tools.dispatch(
                "create_storyboard",
                {"slug": "production", "seconds": 240},
                projects_dir=tmp_path,
            )
        )
    )
    assert "length of one shot" in result["error"]
    assert not (root / P.STAGE_FILES["storyboard"]).exists()


def _call(name, tmp_path, **arguments):
    return json.loads(
        asyncio.run(
            tools.dispatch(name, {"slug": "production", **arguments}, projects_dir=tmp_path)
        )
    )


def _character(character_id="keeper", **overrides):
    return {"id": character_id, "identity": "invented lighthouse keeper, 60s", **overrides}


def _store_permissions(root, *, value):
    """Write the gate directly: one stored character "hero" plus the fixture's references."""
    brief = read_json(root / "brief.json")
    brief["characters"] = [_character("hero")]
    for entry in [*brief["characters"], *brief["creative"]["references"]]:
        entry["permission_confirmed"] = value
    write_json(root / "brief.json", brief)


def test_the_writer_tool_schema_does_not_offer_the_permission_flag():
    assert "permission_confirmed" not in json.dumps(tools.TOOLS)


@pytest.mark.parametrize("claimed", [True, "true", 1])
def test_set_creative_profile_cannot_confirm_a_new_character(tmp_path, claimed):
    root = make_api_project(tmp_path)
    payload = _profile_payload(characters=[_character(permission_confirmed=claimed)])
    payload.pop("slug")
    result = _call("set_creative_profile", tmp_path, **payload)
    assert result["characters"][0]["permission_confirmed"] is False
    assert "keeper" in result["owner_must_confirm"]
    assert P.load_brief(root).characters[0].permission_confirmed is False


@pytest.mark.parametrize("claimed", [True, "true", 1])
def test_update_brief_cannot_confirm_a_new_character(tmp_path, claimed):
    root = make_api_project(tmp_path)
    result = _call(
        "update_brief",
        tmp_path,
        patch={"characters": [_character(permission_confirmed=claimed)]},
    )
    assert result["characters"][0]["permission_confirmed"] is False
    assert "keeper" in result["owner_must_confirm"]
    assert P.load_brief(root).characters[0].permission_confirmed is False


def test_update_brief_cannot_confirm_a_new_reference(tmp_path):
    root = make_api_project(tmp_path)
    existing = read_json(root / "brief.json")["creative"]["references"]
    added = {**existing[0], "id": "new-reference", "permission_confirmed": True}
    _call("update_brief", tmp_path, patch={"creative": {"references": [*existing, added]}})
    stored = {r.id: r.permission_confirmed for r in P.load_brief(root).creative.references}
    assert stored["new-reference"] is False
    assert stored[existing[0]["id"]] is True


def test_writer_tools_cannot_flip_a_stored_false_by_either_route(tmp_path):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=False)
    before = read_json(root / "brief.json")
    characters = [{**value, "permission_confirmed": True} for value in before["characters"]]
    references = [
        {**value, "permission_confirmed": True} for value in before["creative"]["references"]
    ]

    result = _call(
        "update_brief",
        tmp_path,
        patch={"characters": characters, "creative": {"references": references}},
    )
    assert "error" not in result
    assert read_json(root / "brief.json") == before

    payload = _profile_payload(characters=characters)
    payload.pop("slug")
    assert "error" not in _call("set_creative_profile", tmp_path, **payload)
    after = P.load_brief(root)
    assert [c.permission_confirmed for c in after.characters] == [False]
    assert [r.permission_confirmed for r in after.creative.references] == [False] * len(references)


@pytest.mark.parametrize("sent", [{}, {"permission_confirmed": False}])
def test_a_profile_rewrite_keeps_an_owner_confirmation(tmp_path, sent):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=True)
    before = P.load_brief(root)
    confirmed = before.characters[0]
    payload = _profile_payload(
        characters=[_character(confirmed.id, **sent), _character("newcomer")]
    )
    payload.pop("slug")
    result = _call("set_creative_profile", tmp_path, **payload)
    stored = {c.id: c.permission_confirmed for c in P.load_brief(root).characters}
    assert stored == {confirmed.id: True, "newcomer": False}
    assert result["owner_must_confirm"] == ["newcomer"]
    # Rewriting the profile leaves the references it does not own alone too.
    assert P.load_brief(root).creative.references == before.creative.references


def test_a_brief_patch_keeps_an_owner_confirmation(tmp_path):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=True)
    before = read_json(root / "brief.json")
    characters = [{**value, "permission_confirmed": False} for value in before["characters"]]
    result = _call("update_brief", tmp_path, patch={"characters": characters})
    assert "owner_must_confirm" not in result
    assert read_json(root / "brief.json") == before


def test_the_owner_confirms_and_revokes_through_the_studio_route(tmp_path):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=False)
    character = read_json(root / "brief.json")["characters"][0]
    client = api_client(tmp_path)
    url = "/api/projects/production/brief"

    confirmed = client.patch(
        url, json={"characters": [{**character, "permission_confirmed": True}]}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["characters"][0]["permission_confirmed"] is True
    assert P.load_brief(root).characters[0].permission_confirmed is True

    # What the owner confirmed then survives the Writer's next rewrite.
    payload = _profile_payload(characters=[_character(character["id"])])
    payload.pop("slug")
    _call("set_creative_profile", tmp_path, **payload)
    assert P.load_brief(root).characters[0].permission_confirmed is True

    revoked = client.patch(url, json={"characters": [{**character, "permission_confirmed": False}]})
    assert revoked.json()["characters"][0]["permission_confirmed"] is False
    assert P.load_brief(root).characters[0].permission_confirmed is False


def test_the_refusal_tells_the_writer_to_ask_the_owner(tmp_path):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=False)
    with pytest.raises(ValueError) as refused:
        P.approve(root, "brief", "user")
    message = str(refused.value)
    assert "permission to upload/depict hero is not confirmed" in message
    assert "Only the owner" in message
    assert "Characters card" in message
    assert "ask them" in message


def test_the_snapshot_names_who_is_waiting_for_the_owner(tmp_path):
    root = make_api_project(tmp_path)
    _store_permissions(root, value=True)
    assert "Owner must confirm" not in build_context("production", projects_dir=tmp_path)
    _store_permissions(root, value=False)
    assert "Owner must confirm permission for: hero" in build_context(
        "production", projects_dir=tmp_path
    )


def test_the_profile_prompt_no_longer_teaches_the_writer_to_set_the_flag(tmp_path):
    root = make_api_project(tmp_path)
    text = prompts.assemble(
        root,
        "story",
        role="writer",
        kind="music_video",
        style_preset="clean-photographic-v1",
        task="profile",
    ).text
    assert '"permission_confirmed": true' not in text
    assert "Do not send `permission_confirmed`" in text
