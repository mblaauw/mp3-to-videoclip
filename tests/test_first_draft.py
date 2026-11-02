"""One authorised click to a draft, and what a draft may and may not approve. All fakes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from api_support import api_client, make_api_project
from test_creative_production import approve_prerequisites

from mp3_to_videoclip import production as P
from mp3_to_videoclip.services import first_draft
from mp3_to_videoclip.storage import read_json, write_json


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    brief = read_json(root / "brief.json")
    brief["characters"] = [
        {"id": "ana", "identity": "A tall adult woman.", "permission_confirmed": False}
    ]
    write_json(root / "brief.json", brief)
    return root


def test_the_plan_splits_the_ceiling_in_two():
    plan = first_draft.plan()
    assert plan["ceiling_usd"] == "1.00" and plan["stills"] == 3
    assert float(plan["stills_usd"]) + float(plan["model_usd"]) == 1.0


def test_an_invented_character_is_confirmed_and_a_named_one_stops_it(film, monkeypatch):
    first_draft.confirm_invented_cast(film)
    assert read_json(film / "brief.json")["characters"][0]["permission_confirmed"] is True
    brief = read_json(film / "brief.json")
    brief["characters"][0]["permission_confirmed"] = False
    write_json(film / "brief.json", brief)
    monkeypatch.setattr(first_draft, "_names_to_protect", lambda _: {"ana"})
    with pytest.raises(first_draft.DraftStopped, match="Confirm ana"):
        first_draft.confirm_invented_cast(film)


def test_a_character_with_a_reference_stops_it(film):
    brief = read_json(film / "brief.json")
    brief["characters"][0]["references"] = ["media/ana.png"]
    write_json(film / "brief.json", brief)
    with pytest.raises(first_draft.DraftStopped, match="Confirm ana"):
        first_draft.confirm_invented_cast(film)


def test_the_allowance_stops_the_next_turn(film):
    write_path = film / "work/model-usage.jsonl"
    write_path.write_text(json.dumps({"prompt_tokens": 400_000, "completion_tokens": 0}) + "\n")
    with pytest.raises(first_draft.DraftStopped, match="allowance"):
        first_draft._check_allowance(film, 0)
    first_draft._check_allowance(film, 1)


def test_a_priced_model_stops_at_the_dollars_too(film):
    (film / "work/model-usage.jsonl").write_text(json.dumps({"cost_usd": "0.80"}) + "\n")
    with pytest.raises(first_draft.DraftStopped, match="allowance"):
        first_draft._check_allowance(film, 0)


def _approved(root):
    approve_prerequisites(root)
    return root


def test_a_draft_may_approve_three_stages_and_no_others(tmp_path):
    root = _approved(make_api_project(tmp_path))
    P.approve(root, "storyboard", "draft", via="draft", drafted_by={"job_id": "j"})
    record = read_json(root / "work/approvals.json")["storyboard"]
    assert record["via"] == "draft" and record["drafted_by"] == {"job_id": "j"}
    P.require_approval(root, "storyboard")
    assert first_draft.drafted_stages(root) == ["storyboard"]
    for stage in ("stills", "preview", "graphics"):
        with pytest.raises(ValueError, match="may only approve"):
            P.approve(root, stage, "draft", via="draft")


def test_the_owner_cannot_build_on_a_draft_until_it_is_theirs(tmp_path):
    root = _approved(make_api_project(tmp_path))
    P.approve(root, "storyboard", "draft", via="draft")
    with pytest.raises(ValueError, match="still a draft"):
        P.approve(root, "stills", "owner")
    P.approve(root, "storyboard", "mine")
    assert "via" not in read_json(root / "work/approvals.json")["storyboard"]
    assert first_draft.drafted_stages(root) == []


def test_a_story_film_is_not_drafted(tmp_path):
    from test_story_film import make_film

    result = asyncio.run(first_draft.run(make_film(tmp_path)))
    assert "script" in result["stopped"]


def test_no_key_stops_at_the_first_turn_and_spends_nothing(film):
    result = asyncio.run(first_draft.run(film))
    assert "no key" in result["stopped"]
    assert result["done"] == []
    assert read_json(film / "work/tasks.json") == {}


def test_the_route_needs_the_sentence_about_the_cast(tmp_path):
    root = make_api_project(tmp_path)
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}/first-draft"
        assert client.get(base).json()["ceiling_usd"] == "1.00"
        assert client.post(base, json={}).status_code == 400
    assert Path(root).is_dir()
