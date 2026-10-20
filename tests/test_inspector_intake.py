"""Static inspector and intake pages: useful controls, zero hidden writes."""

import re
from pathlib import Path

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip import inspector, intake
from mp3_to_videoclip.storage import read_json, write_json


def approve_real_assets(root):
    """Give one shot a couple of versions so the inspector has something to show."""
    approve_through_proof(root)
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.storage import digest

    shot = P.load_board(root).shots[0]
    assets = read_json(root / "work/assets.json")
    first = assets[shot.id]["versions"][0]
    second = root / f"assets/{shot.id}/v002-second.png"
    from PIL import Image

    second.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (192, 108), (40, 60, 90)).save(second)
    P.record_asset(root, shot.id, 2, second, digest(P.image_spec(root, shot)), "local:test")
    assets = read_json(root / "work/assets.json")
    assets[shot.id]["selected"] = 2
    write_json(root / "work/assets.json", assets)
    write_json(
        root / "work/reviews.json",
        [
            {**first, "shot_id": shot.id, "verdict": "reject", "note": "first attempt"},
            {
                "shot_id": shot.id,
                "version": 2,
                "sha256": assets[shot.id]["versions"][1]["sha256"],
                "input_hash": assets[shot.id]["versions"][1]["input_hash"],
                "verdict": "accept",
                "note": "second attempt",
            },
        ],
    )
    return shot


def test_shot_inspector_shows_versions_verdicts_and_contract(tmp_path):
    root = make_root(tmp_path)
    shot = approve_real_assets(root)
    result = inspector.build_inspector(root, shot.id)
    page = root / result["page"]
    assert page.is_file()
    document = page.read_text()
    assert shot.id in document
    assert "ACCEPT" in document.upper() and "REJECT" in document.upper()
    assert "must show" in document
    assert "compiled prompt" in document.lower()
    assert "data:image/jpeg;base64" in document
    assert "window.__SHOT__" in document
    assert result["versions"] == 2 and result["selected"] == 2
    assert "records nothing" in result["warning"]


def test_inspector_controls_compose_commands_and_never_write(tmp_path):
    root = make_root(tmp_path)
    shot = approve_real_assets(root)
    before = {path: path.stat().st_mtime for path in (root / "work").rglob("*.json")}
    document = (root / inspector.build_inspector(root, shot.id)["page"]).read_text()
    # The page composes the validated commands; it does not embed approvals.
    assert "clip shot-edit" in document
    assert "clip adopt" in document
    assert "clip review" in document
    assert "timings" in document or "Timing" in document
    assert "stale" in document
    after = {path: path.stat().st_mtime for path in (root / "work").rglob("*.json")}
    for path, stamp in before.items():
        if path.name.startswith(shot.id) or path.name == "index":
            continue
        assert after[path] == stamp, f"inspector wrote {path}"


def test_inspector_index_lists_every_shot(tmp_path):
    root = make_root(tmp_path)
    result = inspector.build_inspector(root)
    page = root / result["page"]
    document = page.read_text()
    shots = read_json(root / "work/storyboard.json")["shots"]
    assert result["shots"] == len(shots)
    for shot in shots:
        assert shot["id"] in document
    assert "clip inspect projects/" in document


def test_inspector_refuses_unknown_shot_and_versions_pages(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(ValueError, match="unknown shot"):
        inspector.build_inspector(root, "nope")
    first = inspector.build_inspector(root, "s001")
    second = inspector.build_inspector(root, "s001")
    assert first["page"].endswith("v001.html")
    assert second["page"].endswith("v002.html")


def test_intake_emits_commands_and_refuses_impossible_ones(tmp_path):
    result = intake.build_intake(output_dir=tmp_path / "studio")
    page = Path(result["page"])
    document = page.read_text()
    assert result["emits"] == ["clip init", "clip budget"]
    assert "uv run clip init" in document and "uv run clip budget" in document
    assert "MAHA KALA" in document and "VJDJ69" in document
    # Client-side refusals exist for every rule the kernel enforces.
    for phrase in (
        "source MP3 path is required",
        "a film title is required",
        "slug must be lowercase",
        "MUSIC credit is required",
        "FILM DIRECTION credit is required",
        "positive spending cap",
        "16:9 only",
    ):
        assert phrase in document, phrase
    assert "never writes" in document.lower()


def test_intake_never_writes_outside_its_page(tmp_path):
    target = tmp_path / "studio"
    intake.build_intake(output_dir=target)
    assert sorted(path.name for path in target.iterdir()) == [
        "intake-v001.html",
        "intake-v001.json",
    ]


def test_intake_name_guard_and_versioning(tmp_path):
    target = tmp_path / "studio"
    first = intake.build_intake(output_dir=target)
    second = intake.build_intake(output_dir=target)
    assert Path(first["page"]).name == "intake-v001.html"
    assert Path(second["page"]).name == "intake-v002.html"
    with pytest.raises(ValueError, match="never overwritten"):
        intake.build_intake(output_dir=target, name="intake-v001.html")
    with pytest.raises(ValueError, match="safe lowercase"):
        intake.build_intake(output_dir=target, name="../x.html")


def test_intake_page_is_self_contained(tmp_path):
    document = Path(intake.build_intake(output_dir=tmp_path / "studio")["page"]).read_text()
    assert "http://" not in document and "https://" not in document
    assert "<script src" not in document and "<link" not in document
    assert not re.search(r"fetch\(", document)
