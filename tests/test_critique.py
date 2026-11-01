"""The Critic: frames of the real render, notes outside every gate, and no way to change a film."""

from __future__ import annotations

import asyncio
import json
import subprocess

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import critique
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import opencode, prompts, tools


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    (root / "renders").mkdir(exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
            "-i", "testsrc=size=320x180:rate=24:duration=2",
            str(root / "renders" / "production-final-v001.mp4"),
        ],
        check=True,
    )  # fmt: skip
    return root


def _dispatch(tmp_path, name, **arguments):
    return asyncio.run(
        tools.dispatch(name, {"slug": "production", **arguments}, projects_dir=tmp_path)
    )


def test_the_critic_sees_frames_of_the_newest_render(tmp_path, film):
    result = _dispatch(tmp_path, "get_film_frames", frames=[0, 24])
    assert len(result.images) == 2
    assert result.images[0].startswith("data:image/jpeg;base64,")
    text = json.loads(result.text)
    assert text["render"] == "production-final-v001.mp4"
    assert [item["seconds"] for item in text["frames"]] == [0.0, 1.0]


def test_a_frame_request_is_bounded_and_needs_a_render(tmp_path):
    root = make_api_project(tmp_path)
    assert (
        "no render" in json.loads(_dispatch(tmp_path, "get_film_frames", frames=[0]).text)["error"]
    )
    with pytest.raises(ValueError, match="at most"):
        critique.film_frames(root, list(range(9)), 24)
    with pytest.raises(ValueError, match="whole film frames"):
        critique.film_frames(root, [1.5], 24)


def test_notes_are_saved_bound_to_the_render_and_validated(film):
    entry = critique.save(
        film,
        "It lands, but the middle is mechanical.",
        [
            {
                "severity": "must_fix",
                "note": "The name is misspelled.",
                "shot_id": "s001",
                "frame": 12,
            }
        ],
        24,
    )
    assert entry["render"] == "production-final-v001.mp4"
    assert len(entry["render_sha256"]) == 64
    assert critique.latest(film)["notes"][0]["frame"] == 12
    with pytest.raises(ValueError, match="severity"):
        critique.save(film, "Fine.", [{"severity": "terrible", "note": "x"}], 24)
    with pytest.raises(ValueError, match="verdict"):
        critique.save(film, " ", [], 24)
    with pytest.raises(ValueError, match="at most"):
        critique.save(film, "Fine.", [{"severity": "consider", "note": "x"}] * 13, 24)


def test_a_review_opens_and_closes_no_gate(film):
    before = {
        path: path.read_bytes() for path in [film / "brief.json", film / "work/storyboard.json"]
    }
    hash_before = P.stage_hash(film, "storyboard")
    critique.save(film, "A review.", [], 24)
    assert P.stage_hash(film, "storyboard") == hash_before
    assert {path: path.read_bytes() for path in before} == before


def test_a_note_says_when_the_cut_has_moved_on(film):
    from mp3_to_videoclip import edits

    edits.seed_edit(film)
    critique.save(film, "A review.", [], 24)
    assert critique.latest(film)["current"] is True
    values = edits.load_edit(film).model_dump(by_alias=True)
    values["notes"] = "Changed."
    edits.save_edit(film, values)
    assert critique.latest(film)["current"] is False


def test_the_critic_can_only_read_and_leave_notes(tmp_path):
    offered = {tool["function"]["name"] for tool in tools.tools_for("critic")}
    assert offered == tools.CRITIC_TOOLS
    assert all(name.startswith("get_") or name == "save_critique" for name in offered), (
        "the Critic must have no tool that changes a film"
    )
    config = opencode.gateway_config(projects_dir=tmp_path, python="/usr/bin/python3")
    rules = config["agents"]["critic"]["permissions"]
    assert {"action": "clipstudio_*", "resource": "*", "effect": "deny"} in rules
    assert {"action": "clipstudio_save_critique", "resource": "*", "effect": "allow"} in rules
    assert not any(rule["action"] == "clipstudio_update_shots" for rule in rules)
    assert len(tools.tools_for("writer")) > len(offered)


def test_the_critics_prompt_is_assembled_and_its_task_is_the_review(tmp_path):
    root = make_api_project(tmp_path)
    bundle = prompts.assemble(root, "film", role="critic")
    assert bundle.task == "review"
    assert "get_film_frames" in bundle.text
    assert {"path": "critic/review.md", "version": 1} in bundle.meta["files"]


def test_the_critique_route_reports_nothing_until_there_is_a_review(tmp_path, film):
    with api_client(tmp_path) as client:
        base = "/api/projects/production"
        assert client.get(f"{base}/critique").json() == {"critique": None}
        critique.save(film, "A review.", [], 24)
        assert client.get(f"{base}/critique").json()["critique"]["verdict"] == "A review."
        assert client.get(f"{base}/director/model", params={"role": "critic"}).status_code == 200
        assert client.get(f"{base}/chat", params={"role": "critic"}).status_code == 200


def test_every_review_starts_a_fresh_session(tmp_path):
    root = make_api_project(tmp_path)
    opencode.write_json(
        opencode.session_path(root),
        {
            "critic": {"id": "ses_a", "model": "m", "agent": "critic", "warm": True},
            "editor": {"id": "ses_b", "model": "m", "agent": "editor", "warm": True},
        },
    )
    assert opencode.load_session(root, "critic", "m") is None
    assert opencode.load_session(root, "editor", "m")["id"] == "ses_b"
