"""Paid/local shot kinds, deterministic plates and legacy-safe serialization."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, make_api_project
from test_creative_production import jpeg

from mp3_to_videoclip import production as P
from mp3_to_videoclip import reviews, services, shotkinds
from mp3_to_videoclip.models import Shot
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def _shot(**values):
    base = {"id": "s900", "start_frame": 0, "duration_frames": 24, "purpose": "job"}
    return Shot(**base, **values)


def test_new_kind_fields_are_dropped_at_defaults():
    legacy = Shot(id="s001", start_frame=0, duration_frames=24, purpose="job", image_prompt="x")
    dumped = legacy.model_dump()
    for key in ("kind", "message", "text", "bridge", "product_ref", "panes", "asset"):
        assert key not in dumped
    assert dumped["image_prompt"] == "x"

    card = _shot(kind="card", text=["A line"])
    dumped = card.model_dump()
    assert dumped["kind"] == "card"
    assert dumped["text"] == ["A line"]
    assert "image_prompt" not in dumped


def test_legacy_artifacts_round_trip_without_new_fields(tmp_path):
    root = make_api_project(tmp_path)
    brief = read_json(root / "brief.json")
    board = read_json(root / "work" / "storyboard.json")
    assert P.load_brief(root).model_dump() == brief
    assert P.load_board(root).model_dump() == board
    assert "script" not in brief
    assert all("kind" not in shot for shot in board["shots"])


def test_paid_predicate_only_charges_generated_kinds():
    scene = _shot(image_prompt="x")
    product = _shot(kind="product", product_ref="media/product.jpg", image_prompt="x")
    uploaded_product = _shot(kind="product", asset="media/product.jpg")
    generated_bridge = _shot(
        kind="bridge",
        image_prompt="x",
        bridge={"mode": "generated", "match": {"type": "shape", "anchor": [0.5, 0.5]}},
    )
    designed_bridge = _shot(
        kind="bridge",
        message="turn",
        bridge={"mode": "designed", "match": {"type": "shape", "anchor": [0.5, 0.5]}},
    )
    card = _shot(kind="card", text=["hello"])
    upload = _shot(kind="upload", asset="media/photo.jpg")
    reprise = _shot(kind="reprise", asset_shot_id="s001")
    split = _shot(kind="split", panes=[{"shot_id": "s001"}, {"shot_id": "s002"}])
    logo = _shot(kind="logo", message="brand")
    end_card = _shot(kind="end_card", text=["Out now"])

    assert shotkinds.is_paid(scene)
    assert shotkinds.is_paid(product)
    assert not shotkinds.is_paid(uploaded_product)
    assert shotkinds.is_paid(generated_bridge)
    assert not shotkinds.is_paid(designed_bridge)
    for local in (card, upload, reprise, split, logo, end_card):
        assert shotkinds.is_local(local), local.kind


def test_kind_validation_refuses_an_incomplete_shot():
    with pytest.raises(ValueError, match="image prompt"):
        _shot()
    with pytest.raises(ValueError, match="message or on-screen text"):
        _shot(kind="card")
    with pytest.raises(ValueError, match="two or three panes"):
        _shot(kind="split", panes=[{"shot_id": "s001"}])
    with pytest.raises(ValueError, match="bridge plan"):
        _shot(kind="bridge", message="turn")
    with pytest.raises(ValueError, match="explicit match"):
        _shot(kind="bridge", message="turn", bridge={"mode": "designed"})
    with pytest.raises(ValueError, match="generated bridge"):
        _shot(
            kind="bridge",
            bridge={"mode": "generated", "match": {"type": "shape", "anchor": [0.5, 0.5]}},
        )
    with pytest.raises(ValueError, match="asset_shot_id"):
        _shot(kind="reprise")
    with pytest.raises(ValueError, match="upload"):
        _shot(kind="upload")
    with pytest.raises(ValueError, match="product_ref"):
        _shot(kind="product")


def _local_board(root: Path) -> list[dict]:
    return [
        {"id": "s002", "kind": "card", "message": "two years", "text": ["Two years of silence."]},
        {
            "id": "s003",
            "kind": "end_card",
            "message": "out now",
            "text": ["Out 14 Nov", "Pre-save now"],
        },
        {
            "id": "s004",
            "kind": "bridge",
            "message": "the turn",
            "bridge": {"mode": "designed", "match": {"type": "shape", "anchor": [0.5, 0.45]}},
        },
    ]


def test_local_kinds_render_deterministic_plates_and_skip_reviews(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    P.update_shots(root, _local_board(root))
    brief = read_json(root / "brief.json")
    brief["creative"]["proof_shot_ids"] = ["s001"]
    write_json(root / "brief.json", brief)

    first = P.resolved_assets(root, ["s002"])[0]
    second = P.resolved_assets(root, ["s002"])[0]
    assert Path(first.image).is_file()
    assert first.image == second.image
    assert first.image.endswith(".png")
    assert P.local_plate_path(root, "s002") == Path(first.image)
    assert P.local_plate_path(root, "s002").read_bytes() == Path(first.image).read_bytes()

    before = P.stage_hash(root, "proof")
    P.update_shots(root, [{"id": "s002", "text": ["A different line"]}])
    after = P.stage_hash(root, "proof")
    assert before != after

    reviews.require_accepted(root, ["s002", "s003", "s004"])


def test_proof_ids_and_generation_stay_paid_only(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    P.update_shots(root, _local_board(root))
    brief = read_json(root / "brief.json")
    brief["creative"]["proof_shot_ids"] = ["s001"]
    write_json(root / "brief.json", brief)
    board = P.load_board(root)
    assert P.proof_ids(board) == ["s001"]

    with pytest.raises(ValueError, match="local shot"):
        services.generation.estimate(root, ["s002"], scope="stills", reserve="0.05")


def test_split_upload_and_logo_render_local_plates(tmp_path):
    from PIL import Image

    root = make_api_project(tmp_path)
    add_assets(root)
    jpeg(root / "media/upload.jpg")
    jpeg(root / "media/logo.jpg")
    P.update_shots(
        root,
        [
            {
                "id": "s002",
                "kind": "split",
                "message": "before and after",
                "panes": [{"shot_id": "s001"}, {"shot_id": "s003"}],
            },
            {
                "id": "s003",
                "kind": "upload",
                "message": "the real place",
                "asset": "media/upload.jpg",
            },
            {
                "id": "s004",
                "kind": "logo",
                "message": "the label",
                "asset": "media/logo.jpg",
            },
        ],
    )
    brief = read_json(root / "brief.json")
    brief["creative"]["proof_shot_ids"] = ["s001"]
    write_json(root / "brief.json", brief)

    for shot_id in ("s002", "s003", "s004"):
        path = Path(P.resolved_assets(root, [shot_id])[0].image)
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == (192, 108)
    with pytest.raises(ValueError, match="not a local plate"):
        P.local_plate_path(root, "s001")


def test_generated_product_and_bridge_compile_their_own_spec(tmp_path):
    root = make_api_project(tmp_path)
    jpeg(root / "media/product.jpg")
    P.update_shots(
        root,
        [
            {
                "id": "s003",
                "kind": "product",
                "product_ref": "media/product.jpg",
                "image_prompt": "The supplied product on a wet night street",
            },
            {
                "id": "s004",
                "kind": "bridge",
                "image_prompt": "The round label becomes the moon",
                "bridge": {
                    "mode": "generated",
                    "match": {"type": "shape", "anchor": [0.5, 0.45], "note": "label to moon"},
                },
            },
        ],
    )
    board = P.load_board(root)
    product = next(shot for shot in board.shots if shot.id == "s003")
    bridge = next(shot for shot in board.shots if shot.id == "s004")
    assert shotkinds.is_paid(product) and shotkinds.is_paid(bridge)
    product_spec = P.image_spec(root, product)
    bridge_spec = P.image_spec(root, bridge)
    assert product_spec["kind"] == "product"
    assert any(ref["path"] == "media/product.jpg" for ref in product_spec["references"])
    assert "Product reference" in product_spec["positivePrompt"]
    assert bridge_spec["kind"] == "bridge"
    assert bridge_spec["bridge"]["mode"] == "generated"
    assert "Bridge match" in bridge_spec["positivePrompt"]
    assert product_spec["positivePrompt"] != bridge_spec["positivePrompt"]


def test_reprise_alias_keeps_working_without_a_kind(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    P.update_shots(root, [{"id": "s002", "asset_shot_id": "s001"}])
    board = P.load_board(root)
    alias = next(shot for shot in board.shots if shot.id == "s002")
    assert alias.kind == "scene"
    assert not shotkinds.is_paid(alias)
    assert P.image_spec(root, alias) == P.image_spec(
        root, next(shot for shot in board.shots if shot.id == "s001")
    )
    assert file_hash(Path(P.resolved_assets(root, ["s002"])[0].image)) == file_hash(
        Path(P.resolved_assets(root, ["s001"])[0].image)
    )
