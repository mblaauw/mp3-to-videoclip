"""The Writer/Editor prompt suite is assembled, versioned and budgeted."""

from __future__ import annotations

import json
from pathlib import Path

from api_support import make_api_project

from mp3_to_videoclip.api.director import _system_prompt
from mp3_to_videoclip.director import prompts
from mp3_to_videoclip.storage import read_json, write_json


def _bundle(root: Path, stage: str, role: str = "writer", task: str | None = None):
    return prompts.assemble(
        root,
        stage,
        role=role,
        kind="advert",
        style_preset="clean-photographic-v1",
        task=task,
    )


def test_assembly_order_versions_and_hash(tmp_path):
    root = make_api_project(tmp_path)
    bundle = _bundle(root, "story")
    assert bundle.task == "brief"
    assert bundle.meta["hash"] == prompts.digest(bundle.text)
    assert bundle.meta["words"] <= 2000
    assert all(isinstance(item["version"], int) for item in bundle.meta["files"])
    assert bundle.meta["files"][0]["path"] == "writer/system.md"
    text = bundle.text
    order = [
        "# Writer",
        "# The five truth rules",
        "# Advert",
        "## Style preset",
        "# W1",
        "## Example",
    ]
    positions = [text.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_a_protected_style_preset_states_the_core_rule(tmp_path):
    root = make_api_project(tmp_path)
    protected = prompts.assemble(
        root,
        "story",
        role="writer",
        kind="music_video",
        style_preset="photographic-painted-v2",
        task="brief",
    ).text
    assert "This preset core is protected" in protected
    assert "switch Story \u2192 Look to Custom" in protected

    ordinary = prompts.assemble(
        root,
        "story",
        role="writer",
        kind="music_video",
        style_preset="clean-photographic-v1",
        task="brief",
    ).text
    assert "This preset core is protected" not in ordinary


def test_every_writer_task_is_under_the_word_budget(tmp_path):
    root = make_api_project(tmp_path)
    for task in prompts.TASKS["writer"]:
        for kind in ("music_video", "promo", "advert"):
            for style in ("photographic-painted-v2", "clean-photographic-v1"):
                bundle = prompts.assemble(
                    root,
                    "story",
                    role="writer",
                    kind=kind,
                    style_preset=style,
                    task=task,
                )
                assert bundle.meta["words"] <= 2000, (
                    f"{task}/{kind}/{style} is {bundle.meta['words']} words"
                )
                assert bundle.meta["hash"]


def test_story_task_routing_follows_the_artifacts(tmp_path):
    root = make_api_project(tmp_path)
    project = read_json(root / "project.json")
    project["kind"] = "advert"
    write_json(root / "project.json", project)
    assert prompts.select_task(root, "story", "writer") == "brief"

    brief = read_json(root / "brief.json")
    brief["intent"] = {
        "kind": "advert",
        "objective": "launch the single",
        "audience": "listeners",
        "message": "out now",
        "cta": {"text": "Buy"},
    }
    write_json(root / "brief.json", brief)
    assert prompts.select_task(root, "story", "writer") == "concepts"

    concepts = {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"route {index}",
                "structure": structure,
                "logline": "a line",
                "why": "it fits",
                "world": "a world",
                "shape": ["a", "b", "c", "d"],
                "signature_moment": "one image",
                "risk": "a risk",
            }
            for index, structure in enumerate(("narrative", "demonstration", "three reasons"))
        ]
    }
    write_json(root / "work/treatments.json", concepts)
    assert prompts.select_task(root, "story", "writer") == "concepts"

    concepts["chosen_id"] = "c2"
    write_json(root / "work/treatments.json", concepts)
    assert prompts.select_task(root, "story", "writer") == "script_ad"

    brief["treatment"] = "the chosen route"
    brief["script"] = [
        {"time_range": "0–3 s", "picture": "the hook", "text": "", "music": "first accent"}
    ]
    write_json(root / "brief.json", brief)
    assert prompts.select_task(root, "story", "writer") == "profile"

    brief["creative"]["profile_version"] = 1
    write_json(root / "brief.json", brief)
    assert prompts.select_task(root, "story", "writer") == "revise"


def test_stage_and_role_routing_is_deterministic(tmp_path):
    root = make_api_project(tmp_path)
    assert prompts.role_for_stage("track") == "editor"
    assert prompts.role_for_stage("film") == "editor"
    assert prompts.role_for_stage("story") == "writer"
    assert prompts.select_task(root, "track", "editor") == "music"
    assert prompts.select_task(root, "storyboard", "writer") == "storyboard"
    assert prompts.select_task(root, "storyboard", "editor") == "notes"
    assert prompts.select_task(root, "images", "writer") == "prompts"
    assert prompts.select_task(root, "film", "editor") == "edit"

    assets = read_json(root / "work/assets.json")
    assets["s001"] = {"versions": [{"version": 1}], "selected": 1}
    write_json(root / "work/assets.json", assets)
    assert prompts.select_task(root, "images", "writer") == "review"


def test_editor_prompts_do_not_include_the_writer_style_block(tmp_path):
    root = make_api_project(tmp_path)
    bundle = _bundle(root, "film", role="editor", task="edit")
    assert "## Style preset" not in bundle.text
    assert "# Editor" in bundle.text
    assert "# E3" in bundle.text


def test_unknown_stage_preview_is_a_real_writer_prompt():
    text = _system_prompt("polish")
    assert "# Writer" in text
    assert "# The five truth rules" in text
    assert "# W7" in text


def test_stored_versions_are_json_metadata(tmp_path):
    root = make_api_project(tmp_path)
    bundle = _bundle(root, "storyboard")
    json.dumps(bundle.meta)
    assert bundle.meta["task"] == "storyboard"
    assert bundle.meta["kind"] == "advert"


def test_artifact_writes_record_the_current_prompt_revision(tmp_path):
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip import promptlog

    root = make_api_project(tmp_path)
    promptlog.remember(
        root, {"hash": "abc123", "files": [{"path": "writer/brief.md", "version": 2}]}
    )
    P.update_brief(root, {"treatment": "A recorded revision"})
    lines = (root / promptlog.HISTORY).read_text().splitlines()
    entry = json.loads(lines[-1])
    assert entry["artifact"] == "brief"
    assert entry["hash"] == "abc123"
    assert entry["files"][0]["version"] == 2
