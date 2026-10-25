"""Guided flow: late credits, no mandatory preview, durable revision requests."""

import json
import urllib.error
import urllib.request

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import flow, human_actions, serve, signature
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import digest, read_json, write_json


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


def test_guided_next_step_skips_agent_owned_music_stages(tmp_path):
    from mp3_to_videoclip import studio

    guided = guided_root(tmp_path / "guided")
    v2 = make_root(tmp_path / "v2")
    assert studio.scan_project(guided)["next_step"] == "brief approval"
    assert studio.scan_project(v2)["next_step"] == "analysis approval"


def test_save_credits_is_late_bound_and_can_prefill_new_productions(tmp_path):
    root = guided_root(tmp_path)
    value = spec(root)
    brief_hash = P.stage_hash(root, "brief")
    result = human_actions.save_credits(
        root,
        {
            "expected_spec_hash": digest(value),
            "title": "Creative",
            "cards": [["Director", "A Person"], ["Editor", "Another Person"]],
            "confirmed": True,
            "note": "Confirmed factual roles",
            "use_as_template": True,
        },
    )
    assert result["spec"]["credit_roles_confirmed"] is True
    assert P.stage_hash(root, "brief") == brief_hash
    assert signature.credits_template(root.parent) == [
        ["Director", "A Person"],
        ["Editor", "Another Person"],
    ]
    with pytest.raises(human_actions.ActionError) as stale:
        human_actions.save_credits(
            root,
            {
                "expected_spec_hash": digest(value),
                "title": "Creative",
                "cards": [["Director", "Changed"]],
                "confirmed": True,
                "note": "stale",
            },
        )
    assert stale.value.status == 409

    v2 = make_root(tmp_path / "v2")
    with pytest.raises(human_actions.ActionError) as legacy:
        human_actions.save_credits(
            v2,
            {
                "expected_spec_hash": "a" * 64,
                "title": "Creative",
                "cards": [],
                "confirmed": True,
                "note": "legacy",
            },
        )
    assert legacy.value.status == 409


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


def test_guided_story_approval_is_atomic_and_hash_bound(tmp_path):
    root = guided_root(tmp_path)
    review = human_actions.review_story(root)
    result = human_actions.approve_story(
        root,
        {
            "expected_hash": review["combined_hash"],
            "note": "I reviewed and agree to the story and board",
            "confirmed": True,
        },
    )
    assert result["approved"] == ["brief", "storyboard"]
    assert read_json(root / "work/approvals.json")["storyboard"]["via"] == "studio"

    # A hash taken before the board changed must be refused without writing.
    stale = guided_root(tmp_path / "stale")
    old = human_actions.review_story(stale)
    board = read_json(stale / P.STAGE_FILES["storyboard"])
    board["shots"][0]["image_prompt"] = ""
    write_json(stale / P.STAGE_FILES["storyboard"], board)
    before = (stale / "work/approvals.json").read_bytes()
    with pytest.raises(human_actions.ActionError) as changed:
        human_actions.approve_story(
            stale,
            {
                "expected_hash": old["combined_hash"],
                "note": "stale board review",
                "confirmed": True,
            },
        )
    assert changed.value.status == 409
    assert (stale / "work/approvals.json").read_bytes() == before

    # A fresh hash can still fail validation on the second gate; roll back both.
    broken = guided_root(tmp_path / "broken")
    board = read_json(broken / P.STAGE_FILES["storyboard"])
    board["shots"][0]["image_prompt"] = ""
    write_json(broken / P.STAGE_FILES["storyboard"], board)
    current = human_actions.review_story(broken)
    before = (broken / "work/approvals.json").read_bytes()
    with pytest.raises(ValueError):
        human_actions.approve_story(
            broken,
            {
                "expected_hash": current["combined_hash"],
                "note": "changed story",
                "confirmed": True,
            },
        )
    assert (broken / "work/approvals.json").read_bytes() == before


def test_recorded_v2_story_keeps_separate_decisions(tmp_path):
    root = make_root(tmp_path)
    approve_music_and_events(root)
    review = human_actions.review_story(root)
    with pytest.raises(human_actions.ActionError) as refused:
        human_actions.approve_story(
            root,
            {
                "expected_hash": review["combined_hash"],
                "note": "one click is not the v2 path",
                "confirmed": True,
            },
        )
    assert refused.value.status == 409
    assert read_json(root / "work/approvals.json").get("storyboard") is None


def test_shot_review_is_bound_to_version_and_bytes(tmp_path):
    from test_creative_production import record_stills

    root = make_root(tmp_path)
    record_stills(root, ["s001"])
    assets = read_json(root / "work/assets.json")["s001"]["versions"][0]
    result = human_actions.record_shot_review(
        root,
        {
            "shot_id": "s001",
            "version": assets["version"],
            "sha256": assets["sha256"],
            "verdict": "accept",
            "note": "Inspected this exact image",
            "confirmed": True,
        },
    )
    assert result["review"]["verdict"] == "accept"
    with pytest.raises(human_actions.ActionError) as stale:
        human_actions.record_shot_review(
            root,
            {
                "shot_id": "s001",
                "version": assets["version"],
                "sha256": "b" * 64,
                "verdict": "accept",
                "note": "stale bytes",
                "confirmed": True,
            },
        )
    assert stale.value.status == 409


def test_alias_shot_review_resolves_the_shared_asset_owner(tmp_path):
    from test_creative_production import record_stills

    root = make_root(tmp_path)
    record_stills(root, ["s001"])
    board = read_json(root / P.STAGE_FILES["storyboard"])
    board["shots"][1]["asset_shot_id"] = "s001"
    write_json(root / P.STAGE_FILES["storyboard"], board)
    assets = read_json(root / "work/assets.json")["s001"]["versions"][0]
    result = human_actions.record_shot_review(
        root,
        {
            "shot_id": "s002",
            "version": assets["version"],
            "sha256": assets["sha256"],
            "verdict": "accept",
            "note": "Alias points at the inspected shared asset",
            "confirmed": True,
        },
    )
    assert result["review"]["shot_id"] == "s001"
    assert result["review"]["verdict"] == "accept"


def _post(base, path, body, *, capability="human"):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Origin": base.rstrip("/"),
            "X-Studio-Token": "read",
            "X-Studio-Action": capability,
        },
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def test_guided_http_routes_need_capability_and_never_spend(tmp_path):
    root = guided_root(tmp_path)
    projects = root.parent
    server, url, thread = serve.start_in_thread(projects, token="read")
    server.action_token = "human"
    base = url.split("?")[0]
    try:
        status, _ = _post(
            base,
            "api/project/production/credits",
            {
                "expected_spec_hash": "a" * 64,
                "title": "Creative",
                "cards": [],
                "confirmed": True,
                "note": "x",
            },
            capability="",
        )
        assert status == 401
        status, _ = _post(base, "api/project/production/unknown", {}, capability="human")
        assert status == 405
        assert read_json(root / "work/tasks.json") == {}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
