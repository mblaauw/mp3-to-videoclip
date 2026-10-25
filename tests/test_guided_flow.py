"""Guided flow: late credits, no mandatory preview, durable revision requests."""

import json

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import flow, signature
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


def guided_root(tmp_path):
    root = make_root(tmp_path)
    project = read_json(root / "project.json")
    project["signature_required"] = True
    write_json(root / "project.json", project)
    flow.mark(root)
    return root


def spec(root, title="Creative", cards=None):
    value = signature.draft_spec(title)
    value["renderer"] = "remotion"
    value["design"] = "joint-v1"
    value["credits"]["cards"] = cards or []
    write_json(root / "work/graphics-spec.json", value)
    return value


def approve_music_and_events(root):
    P.approve(root, "analysis", "test analysis")
    if P.load_project(root).music_mode != "instrumental":
        P.approve(root, "lyrics", "test lyrics", True)
    if (root / P.STAGE_FILES["events"]).exists():
        P.approve(root, "events", "test events")


def test_guided_policy_is_a_separate_file_and_new_projects_get_it(tmp_path):
    root = make_root(tmp_path)
    assert flow.guided(root) is False
    flow.mark(root)
    assert flow.guided(root) is True
    marker = read_json(root / flow.FILE)
    assert marker["version"] == flow.VERSION
    assert marker["source_sha256"] == read_json(root / "project.json")["source_sha256"]
    # The policy stays out of project.json; only its own marker records it.
    assert "guided-flow" not in json.dumps(read_json(root / "project.json"))


def test_guided_marker_from_another_production_is_ignored(tmp_path):
    first = make_root(tmp_path / "first")
    second = make_root(tmp_path / "second")
    for root, slug in ((first, "first"), (second, "second")):
        project = read_json(root / "project.json")
        project["slug"] = slug
        write_json(root / "project.json", project)
    flow.mark(first)
    write_json(second / flow.FILE, read_json(first / flow.FILE))
    assert flow.guided(first) is True
    assert flow.guided(second) is False


def test_guided_marker_refuses_to_convert_recorded_decisions(tmp_path):
    root = make_root(tmp_path)
    approve_music_and_events(root)
    with pytest.raises(ValueError, match="already has recorded decisions"):
        flow.mark(root)
    assert flow.guided(root) is False


def test_guided_brief_does_not_hash_late_credits_but_v2_still_does(tmp_path):
    guided = guided_root(tmp_path / "guided")
    guide_spec = spec(guided, cards=[["Director", "One"]])
    before = P.stage_hash(guided, "brief")
    guide_spec["credits"]["cards"] = [["Director", "Two"]]
    write_json(guided / "work/graphics-spec.json", guide_spec)
    assert P.stage_hash(guided, "brief") == before

    v2 = make_root(tmp_path / "v2")
    project = read_json(v2 / "project.json")
    project["signature_required"] = True
    write_json(v2 / "project.json", project)
    old = spec(v2, cards=[["Director", "One"]])
    before = P.stage_hash(v2, "brief")
    old["credits"]["cards"] = [["Director", "Two"]]
    write_json(v2 / "work/graphics-spec.json", old)
    assert P.stage_hash(v2, "brief") != before


def test_guided_stills_gate_on_proof_while_v2_keeps_preview(tmp_path):
    guided = guided_root(tmp_path / "guided")
    v2 = make_root(tmp_path / "v2")
    assert P.effective_upstream(guided, "stills") == "proof"
    assert P.effective_upstream(v2, "stills") == "preview"


def test_guided_brief_approval_does_not_require_music_approvals(tmp_path):
    root = guided_root(tmp_path)
    spec(root)  # unconfirmed draft credits
    assert read_json(root / "work/approvals.json") == {}
    P.approve(root, "brief", "agreed story and style")
    P.approve(root, "storyboard", "agreed shots")
    saved = read_json(root / "work/approvals.json")
    assert saved["brief"]["hash"] and saved["storyboard"]["hash"]
    assert "analysis" not in saved
    assert "lyrics" not in saved


def test_recorded_v2_brief_still_requires_music_approvals(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(ValueError, match="analysis needs current user approval"):
        P.approve(root, "brief", "no music approvals recorded")


def test_new_production_prefills_style_and_credits_from_siblings(tmp_path):
    from test_native_size import init, synth_source

    projects = tmp_path / "projects"
    projects.mkdir()
    older = make_root(projects, name="older")
    brief = read_json(older / "brief.json")
    brief["creative"]["look"] = "CUSTOM-LOOK from the last film"
    write_json(older / "brief.json", brief)
    approve_music_and_events(older)
    P.approve(older, "brief", "approved older style")
    spec = signature.draft_spec("Older")
    spec["credits"]["cards"] = [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]]
    write_json(older / "work/graphics-spec.json", spec)

    new = projects / "new"
    init(new, synth_source(tmp_path), "--music-mode", "instrumental")
    assert P.load_brief(new).creative.look == "CUSTOM-LOOK from the last film"
    # A prefilled custom look must not claim the approved default preset, or the
    # new brief could never be approved.
    assert read_json(new / "project.json")["style_preset"] == "custom"
    project = P.load_project(new)
    write_json(new / "work/music.json", {"duration": project.duration, "beats": [0, 0.1]})
    brief = P.load_brief(new).model_copy(
        update={
            "direction": "Test direction",
            "style": "Test style",
            "treatment": "Test treatment",
        }
    )
    write_json(new / "brief.json", brief.model_dump())
    P.approve(new, "brief", "prefilled style is approvable")
    prefilled = read_json(new / "work/graphics-spec.json")
    assert prefilled["credits"]["cards"] == [["MUSIC", "MAHA KALA"], ["FILM DIRECTION", "VJDJ69"]]
    assert prefilled.get("credit_roles_confirmed") is not True
    assert flow.guided(new) is True
