"""Studio index: cheap scanning, honest stage states, static read-only output."""

from pathlib import Path

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip import budget, studio
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import read_json, write_json


def two_projects(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    make_root(projects)
    make_root(projects, name="second")
    return projects


def test_scan_lists_projects_and_ignores_other_folders(tmp_path):
    projects = two_projects(tmp_path)
    (projects / "not-a-production").mkdir()
    (projects / "not-a-production" / "readme.txt").write_text("x")
    entries = studio.scan(projects)
    assert [entry["slug"] for entry in sorted(entries, key=lambda e: e["slug"])] == [
        "production",
        "second",
    ]


def test_scan_project_returns_none_without_project_json(tmp_path):
    (tmp_path / "empty").mkdir()
    assert studio.scan_project(tmp_path / "empty") is None


def test_image_stages_are_recorded_not_hashed(tmp_path, monkeypatch):
    """An index must never read gigabytes of stills to draw a card."""
    root = make_root(tmp_path)
    approve_through_proof(root)
    make_root(tmp_path, name="second")

    real = studio.file_hash

    def guarded(path):
        text = str(path)
        for heavy in ("/assets/", "/renders/", "/previews/", "/work/reviews/"):
            if heavy in text:
                raise AssertionError(f"studio hashed media bytes: {text}")
        return real(path)

    monkeypatch.setattr(studio, "file_hash", guarded)
    entries = studio.scan(tmp_path)
    assert entries
    stages = next(entry for entry in entries if entry["slug"] == "production")["stages"]
    assert stages["proof"] in ("recorded", "missing")
    assert stages["stills"] in ("recorded", "missing")
    assert stages["storyboard"] == "approved"


def test_hashed_stage_turns_stale_after_an_edit(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    make_root(tmp_path, name="second")
    entry = studio.scan_project(root)
    assert entry["stages"]["storyboard"] == "approved"
    brief = read_json(root / "brief.json")
    brief["direction"] += " (edited)"
    write_json(root / "brief.json", brief)
    entry = studio.scan_project(root)
    assert entry["stages"]["brief"] == "stale"
    assert any("stale approval: brief" in text for _, text in entry["blockers"])


def test_missing_budget_is_a_blocker_until_one_is_recorded(tmp_path):
    root = make_root(tmp_path)
    entry = studio.scan_project(root)
    assert any(text == "no spending cap recorded" for _, text in entry["blockers"])
    budget.set_budget(root, "5.00", "test cap")
    entry = studio.scan_project(root)
    assert not any(text == "no spending cap recorded" for _, text in entry["blockers"])
    assert entry["spend"]["cap_usd"] == "5.00"


def test_page_is_versioned_static_and_never_overwrites(tmp_path):
    projects = two_projects(tmp_path)
    first = studio.build_studio(projects)
    second = studio.build_studio(projects)
    assert first["page"].endswith("studio-v001.html")
    assert second["page"].endswith("studio-v002.html")
    with pytest.raises(ValueError, match="never overwritten"):
        studio.build_studio(projects, name="studio-v001.html")
    with pytest.raises(ValueError, match="safe lowercase"):
        studio.build_studio(projects, name="../x.html")


def test_page_is_self_contained_and_links_only_local_artifacts(tmp_path):
    projects = two_projects(tmp_path)
    root = projects / "production"
    result = studio.build_studio(projects)
    page = Path(result["page"])
    document = page.read_text()
    assert "http://" not in document and "https://" not in document
    assert "data:image" not in document
    assert "<script src" not in document
    assert "uv run clip status" in document
    # A dashboard link appears only once that artifact exists.
    assert "work/dashboard" not in document or root.name in document
    assert result["productions"] == 2
    sidecar = read_json(page.with_suffix(".json"))
    assert sidecar["html_sha256"] == result["html_sha256"]
    assert sidecar["next_steps"]["production"] in {
        "analysis approval",
        "events approval",
        "brief approval",
        "storyboard approval",
        "proof approval",
        "preview approval",
        "stills approval",
        "graphics approval",
        "render",
        "final export",
        "delivered",
    }


def test_titles_and_paths_are_escaped(tmp_path):
    projects = two_projects(tmp_path)
    config = read_json(projects / "production" / "project.json")
    config["title"] = "<script>alert('x')</script> & co"
    write_json(projects / "production" / "project.json", config)
    result = studio.build_studio(projects)
    document = Path(result["page"]).read_text()
    assert "<script>alert" not in document
    assert "&lt;script&gt;alert" in document


def test_cli_studio_command_works_without_a_project_argument(tmp_path, monkeypatch):
    projects = two_projects(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = execute(parser().parse_args(["studio", "--projects-dir", str(projects)]))
    assert result["productions"] == 2
    assert (tmp_path / "studio" / "studio-v001.html").is_file()
    assert Path(result["page"]) == tmp_path / "studio" / "studio-v001.html"


def test_scan_survives_a_corrupt_artifact(tmp_path):
    projects = two_projects(tmp_path)
    (projects / "production" / "work" / "approvals.json").write_text("{not json")
    entries = studio.scan(projects)
    assert len(entries) == 2
    assert next(entry for entry in entries if entry["slug"] == "production")["shots"] >= 1


def test_actions_are_commands_or_links_never_silent_writes(tmp_path):
    projects = two_projects(tmp_path)
    studio.build_studio(projects)
    entries = studio.scan(projects)
    for entry in entries:
        assert entry["actions"]
        for action in entry["actions"]:
            assert action["label"] and action["reason"]
            assert action.get("href") or action.get("command")
            if action.get("command"):
                assert action["command"].startswith("uv run clip ")
                # Commands are templates: they must ask for a decision, not assert one.
                assert "'<" in action["command"] or action["id"] in {
                    "status",
                    "review-stills",
                    "reconcile",
                    "plan",
                }


def test_missing_budget_produces_a_cap_action(tmp_path):
    projects = two_projects(tmp_path)
    entry = next(item for item in studio.scan(projects) if item["slug"] == "production")
    budget_action = next(item for item in entry["actions"] if item["id"] == "budget")
    assert "--cap 5.00" in budget_action["command"]
    assert budget_action["needs_input"] is True
    budget.set_budget(projects / "production", "5.00", "test")
    entry = next(item for item in studio.scan(projects) if item["slug"] == "production")
    assert not any(item["id"] == "budget" for item in entry["actions"])


def test_next_gate_action_names_the_stage_and_project(tmp_path):
    projects = two_projects(tmp_path)
    root = projects / "production"
    budget.set_budget(root, "5.00", "test")
    approve_through_proof(root)
    entry = studio.scan_project(root)
    stage = entry["next_step"].split(" ")[0]
    action = next(item for item in entry["actions"] if item["id"] == f"approve-{stage}")
    assert action["command"].startswith("uv run clip approve projects/production ")
    assert action["needs_input"] is True


def test_rejected_stills_surface_a_review_action(tmp_path):
    projects = two_projects(tmp_path)
    root = projects / "production"
    budget.set_budget(root, "5.00", "test")
    approve_through_proof(root)
    from mp3_to_videoclip.storage import write_json as _write

    _write(
        root / "work/reviews.json",
        [{"shot_id": "s001", "version": 1, "verdict": "reject", "sha256": "x", "input_hash": "y"}],
    )
    entry = studio.scan_project(root)
    action = next(item for item in entry["actions"] if item["id"] == "review-stills")
    assert "--stage stills" in action["command"]
    assert "1 rejected" in action["reason"]
