"""Artifact ratings bind to the prompt revision and exact bytes."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip import promptlog, ratings


def _remember(root: Path, *, suffix: str = "one"):
    promptlog.remember(
        root,
        {
            "hash": f"prompt-{suffix}",
            "files": [{"path": "writer/brief.md", "version": 3}],
            "role": "writer",
            "task": "brief",
            "words": 120,
        },
    )


def test_rating_binds_prompt_revision_and_artifact_bytes(tmp_path):
    root = make_api_project(tmp_path)
    _remember(root, suffix="alpha")
    P.update_brief(root, {"treatment": "A rated treatment"})
    entry = ratings.add(root, "brief", "up", "clearer than the last one")
    assert entry["prompt_hash"] == "prompt-alpha"
    assert entry["prompt_files"] == [{"path": "writer/brief.md", "version": 3}]
    assert entry["artifact_hash"]
    summary = ratings.summary(root, "brief")
    assert summary["available"] is True
    assert summary["latest"]["rating"] == "up"
    assert summary["stale"] is False
    assert summary["prompt"]["hash"] == "prompt-alpha"

    # A later artifact write leaves the old rating visible but stale.
    P.update_brief(root, {"treatment": "A different treatment"})
    assert ratings.summary(root, "brief")["stale"] is True


def test_rating_store_is_append_only_and_rejects_bad_input(tmp_path):
    root = make_api_project(tmp_path)
    _remember(root)
    ratings.add(root, "brief", "down", "too vague")
    ratings.add(root, "brief", "up", "fixed")
    values = ratings.load(root, "brief")
    assert [value["rating"] for value in values] == ["down", "up"]
    assert ratings.summary(root, "brief")["latest"]["note"] == "fixed"

    with pytest.raises(ValueError, match="unknown artifact"):
        ratings.add(root, "music", "up")
    with pytest.raises(ValueError, match="rating must be"):
        ratings.add(root, "brief", "maybe")
    with pytest.raises(ValueError, match="does not exist"):
        ratings.add(root, "treatments", "up")


def test_ratings_api_round_trip_and_prompt_grouping(tmp_path):
    root = make_api_project(tmp_path)
    _remember(root, suffix="api")
    P.update_brief(root, {"treatment": "API rated"})
    client = api_client(tmp_path)
    before = client.get("/api/projects/production/ratings?artifact=brief").json()
    assert before["available"] is True
    assert before["latest"] is None

    saved = client.post(
        "/api/projects/production/ratings",
        json={"artifact": "brief", "rating": "up", "note": "keep this direction"},
    )
    assert saved.status_code == 200
    assert saved.json()["summary"]["latest"]["prompt_hash"] == "prompt-api"

    all_values = client.get("/api/projects/production/ratings").json()
    assert {item["artifact"] for item in all_values["artifacts"]} == set(ratings.ARTIFACTS)
    grouped = ratings.prompt_versions(root)
    assert "prompt-api" in grouped
    assert grouped["prompt-api"]["ratings"][0]["rating"] == "up"


def test_rating_without_prompt_history_is_unbound(tmp_path):
    root = make_api_project(tmp_path)
    # make_api_project writes a brief without a recorded prompt turn.
    entry = ratings.add(root, "brief", "up")
    assert entry["prompt_hash"] is None
    assert ratings.summary(root, "brief")["prompt"]["hash"] is None
