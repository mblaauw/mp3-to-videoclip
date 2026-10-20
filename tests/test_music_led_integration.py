from uuid import uuid4

import pytest
from test_creative_production import (
    approve_prerequisites,
    approve_through_proof,
    make_root,
    record_stills,
    write_preview_report,
)
from test_music_listening import listening_draft
from test_production import FakeRunware

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.branding import brand_hash
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import BrandPackage
from mp3_to_videoclip.storage import digest, read_json, write_json


def test_music_led_brief_does_not_depend_on_sparse_lyrics(tmp_path):
    root = make_root(tmp_path, music_mode="music-led")
    (root / "work/lyrics.json").unlink()
    P.approve(root, "analysis", "test user reviewed measurements")
    P.approve(root, "events", "test user reviewed events")
    P.approve(root, "brief", "test user selected music-led treatment")
    P.require_approval(root, "brief")
    assert "lyrics" not in read_json(root / "work/approvals.json")
    assert P.effective_upstream(root, "brief") == "analysis"


def test_reapproved_listening_change_keeps_old_brief_stale(tmp_path):
    root = make_root(tmp_path, music_mode="music-led", total_frames=96)
    project = P.load_project(root)
    value = {
        "source_sha256": project.source_sha256,
        "duration": project.duration,
        "model": "test",
        "task_uuid": str(uuid4()),
        "analysis_hash": digest(read_json(root / "work/music.json")),
        "draft": listening_draft(),
        "warning": "Unreviewed synthetic fixture",
    }
    write_json(root / "work/music-listening.json", value)
    P.approve(root, "analysis", "test user")
    P.approve(root, "events", "test user")
    P.approve(root, "listening", "test user")
    P.approve(root, "brief", "test user")
    original = P.stage_hash(root, "brief")
    value["draft"]["passages"][0]["groove"] = "User corrected groove"
    write_json(root / "work/music-listening.json", value)
    P.approve(root, "listening", "test user reviewed correction")
    assert P.stage_hash(root, "brief") != original
    with pytest.raises(ValueError, match="brief"):
        P.require_approval(root, "brief")


def test_reused_editorial_shot_uses_source_image_without_another_generation(tmp_path):
    root = make_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    board["shots"][2]["asset_shot_id"] = "s001"
    board["shots"][2]["camera"] = "pan_right"
    write_json(root / "work/storyboard.json", board)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved reusable coverage")
    fake = FakeRunware(root)
    quote = G.quote_images(root, "proof", "0.01", client=fake)
    assert {t["shot_id"] for t in quote["tasks"]} == {"s001", "s002", "s004"}
    record_stills(root, ["s001", "s002", "s004"])
    resolved = P.resolved_assets(root)
    assert len(resolved) == 4 and resolved[0].image == resolved[2].image
    assert resolved[2].shot.id == "s003" and resolved[2].shot.camera == "pan_right"
    assert P.image_spec(root, resolved[0].shot) == P.image_spec(root, resolved[2].shot)
    assert not fake.submissions


@pytest.mark.parametrize(
    "bindings",
    [
        {"s003": "s999"},
        {"s003": "s003"},
        {"s002": "s003", "s003": "s001"},
        {"s002": "s003", "s003": "s002"},
    ],
)
def test_asset_reuse_rejects_unknown_self_chain_and_cycle(tmp_path, bindings):
    root = make_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    for shot in board["shots"]:
        shot["asset_shot_id"] = bindings.get(shot["id"])
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="no chains/cycles"):
        P.load_board(root)


def test_brand_change_stales_review_but_not_image_inputs(tmp_path):
    root = make_root(tmp_path, total_frames=240)
    approve_through_proof(root)
    before = {s.id: digest(P.image_spec(root, s)) for s in P.load_board(root).shots}
    brand = BrandPackage(id="working-brand", duration_seconds=5)
    write_json(root / "brand.json", brand.model_dump())
    with pytest.raises(ValueError, match="brand"):
        P.require_approval(root, "brief")
    P.approve(root, "brand", "test user chose brand")
    P.approve(root, "brief", "test user reviewed brand integration")
    P.approve(root, "storyboard", "test user reviewed unchanged storyboard with brand")
    P.approve(root, "proof", "test user reviewed unchanged proof with brand")
    report = write_preview_report(root)
    with pytest.raises(ValueError, match="brand changed"):
        P.approve(root, "preview", "test user")
    report["brand_hash"] = brand_hash(root)
    write_json(root / "work/preview-review.json", report)
    P.approve(root, "preview", "test user reviewed branded movie")
    write_json(root / "brand.json", brand.model_copy(update={"version": 2}).model_dump())
    with pytest.raises(ValueError):
        P.require_approval(root, "preview")
    assert {s.id: digest(P.image_spec(root, s)) for s in P.load_board(root).shots} == before


def test_music_cli_modes_and_schema_are_available():
    assert (
        parser()
        .parse_args(
            ["init", "example", "--slug", "example", "--mp3", "x.mp3", "--music-mode", "music-led"]
        )
        .music_mode
        == "music-led"
    )
    assert parser().parse_args(["quote-music", "example"]).reserve == "0.05"
    assert execute(parser().parse_args(["schema", "brand"]))["type"] == "object"
    assert execute(parser().parse_args(["schema", "listening"]))["type"] == "object"
