"""Every write says why and what it changed; the new tools read, or propose, and spend nothing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import captions, conversation, decisions, loop, tools
from mp3_to_videoclip.director.providers.base import TurnResult, Usage
from mp3_to_videoclip.storage import read_json


def call(root, name, *, require_reason=False, role="writer", **arguments):
    result = asyncio.run(
        tools.dispatch(
            name,
            {"slug": root.name, **arguments},
            projects_dir=root.parent,
            role=role,
            turn_id="t1",
            prompt_hash="p1",
            require_reason=require_reason,
        )
    )
    if isinstance(result, tools.ToolResult):
        return json.loads(result.text), result.images
    return json.loads(result)


def test_the_diff_names_fields_by_id():
    before = {"shots": [{"id": "s1", "image_prompt": "a"}, {"id": "s2", "image_prompt": "b"}]}
    after = {"shots": [{"id": "s2", "image_prompt": "b"}, {"id": "s1", "image_prompt": "c"}]}
    assert decisions.diff(before, after) == {"shots.s1.image_prompt": ("a", "c")}
    assert list(decisions.diff({"a": [1, 2]}, {"a": [1, 3]})) == ["a[1]"]
    assert decisions.diff({"a": 1}, {"a": 1}) == {}


def test_a_real_turns_write_without_a_reason_changes_nothing(tmp_path):
    root = make_api_project(tmp_path)
    before = read_json(root / "brief.json")
    refused = call(root, "update_brief", require_reason=True, patch={"treatment": "New."})
    assert "say why" in refused["error"]
    assert read_json(root / "brief.json") == before
    assert decisions.read(root) == []


def test_a_write_says_why_and_what_changed(tmp_path):
    root = make_api_project(tmp_path)
    done = call(
        root,
        "update_brief",
        require_reason=True,
        patch={"treatment": "New."},
        reason="the owner asked for a shorter story",
    )
    assert done["changed_fields"] == ["treatment"]
    assert done["reason"] == "the owner asked for a shorter story"
    row = decisions.read(root)[0]
    assert row["tool"] == "update_brief" and row["role"] == "writer" and row["turn_id"] == "t1"
    assert row["prompt_hash"] == "p1" and row["artifact"] == "brief.json"
    assert row["before_after"]["treatment"]["after"] == "New."
    assert decisions.find(root, done["decision_id"])["reason"] == row["reason"]


def test_a_large_result_comes_back_as_what_changed(tmp_path):
    root = make_api_project(tmp_path)
    long_story = "word " * 900
    done = call(
        root, "update_brief", require_reason=True, patch={"treatment": long_story}, reason="longer"
    )
    assert len(json.dumps(done)) < 2500
    assert done["changed_fields"] == ["treatment"]


def test_a_too_long_reason_is_refused(tmp_path):
    root = make_api_project(tmp_path)
    assert "300" in call(root, "update_brief", patch={"treatment": "x"}, reason="y" * 301)["error"]


def test_every_write_tool_requires_a_reason_in_its_schema():
    offered = {tool["function"]["name"]: tool["function"]["parameters"] for tool in tools.TOOLS}
    for name in decisions.WRITE_TOOLS:
        assert "reason" in offered[name]["required"], name


def test_the_tools_stay_under_seven_thousand_tokens():
    assert sum(len(json.dumps(tool)) for tool in tools.TOOLS) / 4 <= 7000


def test_the_shot_tools_are_typed_from_the_contract():
    offered = {tool["function"]["name"]: tool["function"]["parameters"] for tool in tools.TOOLS}
    shot = offered["update_shots"]["properties"]["changes"]["items"]["properties"]
    assert "image_prompt" in shot and "start_frame" not in shot
    edit = offered["update_edit_shots"]["properties"]["shots"]["items"]["properties"]
    assert {"motion", "accents", "shot_id"} <= set(edit) and "start_frame" not in edit
    assert "$ref" not in json.dumps(offered)
    assert "impulse" in json.dumps(edit["accents"])


def test_a_proposal_writes_nothing(tmp_path):
    root = make_api_project(tmp_path)
    before = (root / "work/storyboard.json").read_bytes()
    done = call(root, "propose_alternatives", target="shots.s001.image_prompt", options=["a", "b"])
    assert done["options"] == ["a", "b"]
    assert (root / "work/storyboard.json").read_bytes() == before
    assert "two or three" in call(root, "propose_alternatives", target="x", options=["a"])["error"]


def test_many_prompts_change_as_one_decision(tmp_path):
    root = make_api_project(tmp_path)
    board = P.load_board(root)
    ids = [shot.id for shot in board.shots if P.shotkinds.is_paid(shot)][:2] if hasattr(P, "shotkinds") else [board.shots[0].id]  # fmt: skip
    done = call(
        root,
        "batch_update_prompts",
        changes=[{"id": shot, "image_prompt": f"New {shot}"} for shot in ids],
        reason="a tighter frame throughout",
    )
    assert done["changed"]
    assert len(decisions.read(root)) == 1
    assert "exactly an id" in call(root, "batch_update_prompts", changes=[{"id": "s1"}])["error"]


def test_two_versions_compare_with_what_differed(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=2)
    value, images = call(root, "compare_versions", shot_id="s001", a=1, b=2)
    assert len(images) == 2
    assert value["a"] == 1
    assert "no version 9" in call(root, "compare_versions", shot_id="s001", a=1, b=9)["error"]


def test_preview_frames_need_a_preview(tmp_path):
    root = make_api_project(tmp_path)
    assert "no preview" in call(root, "get_preview_frames", seconds=[1])["error"]


def test_a_caption_is_cached_per_still_and_model(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    calls = []

    class Fake:
        def __init__(self, **options):
            pass

        async def stream(self, messages, tools=None, system=None):
            calls.append(messages)
            from mp3_to_videoclip.director.llm import TextDelta

            yield TextDelta(text="A hand holds a leaf.")
            yield Usage(prompt_tokens=10, completion_tokens=5)
            yield TurnResult(text="A hand holds a leaf.")

    monkeypatch.setattr(captions, "DirectorLLM", Fake)

    class Route:
        provider, kind, base_url, key, model = "x", "openai-compatible", None, "k", "m"

    first = asyncio.run(captions.describe(root, Route, "s1", "abc", "data:image/jpeg;base64,AA", "writer"))  # fmt: skip
    second = asyncio.run(captions.describe(root, Route, "s1", "abc", "data:image/jpeg;base64,AA", "writer"))  # fmt: skip
    assert first["caption"] == "A hand holds a leaf." and first["cached"] is False
    assert second["cached"] is True and len(calls) == 1
    assert "image_url" in json.dumps(calls[0])
    assert (root / "work/model-usage.jsonl").read_text().count("\n") == 1


def test_the_other_role_hears_what_was_said_and_why(tmp_path):
    root = make_api_project(tmp_path)
    conversation.append_message(root, {"role": "assistant", "content": "I tightened act two."}, agent="writer")  # fmt: skip
    call(root, "update_brief", patch={"treatment": "New."}, reason="too slow in the middle")
    block = decisions.handoff(root, "editor")
    assert block.startswith("## From the Writer")
    assert "I tightened act two." in block
    assert "too slow in the middle" in block
    assert decisions.handoff(root, "critic") == ""
    assert decisions.handoff(root, "writer") == ""


def test_a_long_film_keeps_its_reasons_in_the_summary():
    messages = [{"role": "user", "content": f"m{i}"} for i in range(400)]
    _, summary = conversation.compact_messages(messages, recorded_reasons=["update_brief: tighter"])
    assert "update_brief: tighter" in summary


def test_a_decision_can_be_read_back_over_the_api(tmp_path):
    root = make_api_project(tmp_path)
    done = call(root, "update_brief", patch={"treatment": "New."}, reason="why")
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}"
        assert client.get(f"{base}/decisions/{done['decision_id']}").json()["reason"] == "why"
        assert client.get(f"{base}/decisions/nope").status_code == 404
    assert Path(loop.__file__).is_file()
