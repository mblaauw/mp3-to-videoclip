"""Depth runs on a fake worker here: layers, caching, and refusing to render flat."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from api_support import add_assets, api_client, make_api_project
from PIL import Image

from mp3_to_videoclip import chunks, depth, edits, remotion
from mp3_to_videoclip import production as P
from mp3_to_videoclip.models import EditDecisionList, FilmLook, Grade
from mp3_to_videoclip.storage import file_hash, read_json


def _still(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), (120, 80, 40)).save(path, "JPEG")
    return path


def _map(path: Path) -> Path:
    # The right half is near.
    values = np.zeros((90, 160), dtype=np.uint8)
    values[:, 80:] = 255
    Image.fromarray(values, mode="L").save(path)
    return path


@pytest.fixture(autouse=True)
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DEPTH_TOOLS", str(tmp_path / "tools"))


def test_three_layers_far_is_the_whole_still_and_near_is_only_what_is_near(tmp_path):
    root = tmp_path / "film"
    still = _still(root / "assets/s001/v001.jpg")
    layers = depth.make_layers(root, still, _map(tmp_path / "d.png"))
    folder = layers["folder"]
    far = np.asarray(Image.open(folder / "far.png"))
    near = np.asarray(Image.open(folder / "near.png"))
    assert (far[..., 3] == 255).all()
    assert near[45, 150, 3] == 255 and near[45, 10, 3] == 0
    assert 0 < near[45, 80, 3] < 255 or 0 < near[45, 79, 3] < 255, "a soft edge"
    assert folder.is_relative_to(root / "work/depth")


def test_layers_are_made_once_and_a_damaged_set_does_not_count(tmp_path):
    root = tmp_path / "film"
    still = _still(root / "assets/s001/v001.jpg")
    first = depth.make_layers(root, still, _map(tmp_path / "d.png"))
    stamp = (first["folder"] / "near.png").stat().st_mtime_ns
    depth.make_layers(root, still, tmp_path / "does-not-exist.png")
    assert (first["folder"] / "near.png").stat().st_mtime_ns == stamp
    (first["folder"] / "near.png").write_bytes(b"damaged")
    assert depth.layer_set(root, still) is None


def test_the_still_itself_is_never_touched(tmp_path):
    root = tmp_path / "film"
    still = _still(root / "assets/s001/v001.jpg")
    before = file_hash(still)
    depth.make_layers(root, still, _map(tmp_path / "d.png"))
    assert file_hash(still) == before
    assert list((root / "assets").rglob("*.png")) == []


def test_tools_not_set_up_means_no_map(tmp_path):
    still = _still(tmp_path / "a.jpg")
    assert depth.status()["ready"] is False
    with pytest.raises(ValueError, match="set up the depth tools"):
        depth.depth_map(still)


def test_a_map_is_kept_per_still_and_never_made_twice(tmp_path, monkeypatch):
    still = _still(tmp_path / "a.jpg")
    calls = []

    def fake_run(argv):
        calls.append(argv)
        _map(Path(argv[-1]))

    monkeypatch.setattr(depth, "_run", fake_run)
    monkeypatch.setattr(depth, "status", lambda: {"ready": True})
    first = depth.depth_map(still)
    assert depth.depth_map(still) == first
    assert len(calls) == 1
    assert first.is_file()


def test_running_makes_only_what_is_missing(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    monkeypatch.setattr(depth, "depth_map", lambda still: _map(tmp_path / "d.png"))
    assert depth.coverage(root)["with_depth"] == 0
    made = depth.run(root)["made"]
    assert made >= 1
    assert depth.run(root)["made"] == 0
    state = depth.coverage(root)
    assert state["with_depth"] == state["stills"]


def _edit_with_depth(root, amount=0.5):
    edit = edits.seed_edit(root)
    updated = edit.model_copy(update={"grade": Grade(look=FilmLook(depth=amount))})
    return edits.save_edit(root, updated)


def _compile(root, tmp_path):
    work = root / "work"
    assets = work / "remotion-assets"
    assets.mkdir(parents=True, exist_ok=True)
    return remotion.compile_shots(P.resolved_assets(root), work, assets)


def test_a_film_with_depth_refuses_to_render_flat_and_names_the_stills(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    _edit_with_depth(root)
    with pytest.raises(ValueError, match="run depth for .* stills first: s001"):
        _compile(root, tmp_path)


def test_layers_enter_the_compiled_shot_and_the_chunk_key(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    plain = _compile(root, tmp_path)
    assert "depth" not in plain[0]
    monkeypatch.setattr(depth, "depth_map", lambda still: _map(tmp_path / "d.png"))
    depth.run(root)
    _edit_with_depth(root)
    compiled = _compile(root, tmp_path)
    assert set(compiled[0]["depth"]) == {"far", "mid", "near", "model"}
    assert (root / "work/remotion-assets" / compiled[0]["depth"]["near"]).is_file()
    selected = remotion.selected_asset_root(compiled, root / "work/remotion-assets")
    assert (selected / compiled[0]["depth"]["near"]).is_file()
    flat = chunks.film_chunks({"shots": [{**compiled[0], "depth": None}]}, (96, 54), 24, "r")
    deep = chunks.film_chunks({"shots": [compiled[0]]}, (96, 54), 24, "r")
    assert flat[0].key != deep[0].key


def test_a_flat_shot_skips_its_layers(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    edit = _edit_with_depth(root)
    first = edit.shots[0].model_copy(update={"depth": False})
    others = edit.shots[1:]
    monkeypatch.setattr(depth, "depth_map", lambda still: _map(tmp_path / "d.png"))
    depth.run(root)
    edits.save_edit(root, edit.model_copy(update={"shots": [first, *others]}))
    compiled = _compile(root, tmp_path)
    assert "depth" not in compiled[0]


def test_a_film_with_no_depth_serialises_exactly_as_before():
    assert "depth" not in FilmLook(grain=0.2).model_dump()
    assert FilmLook(depth=0.3).model_dump()["depth"] == 0.3
    edit = EditDecisionList.model_json_schema()
    assert edit
    from mp3_to_videoclip.models import EditShot

    shot = EditShot(shot_id="s001", start_frame=0, duration_frames=10)
    assert "depth" not in shot.model_dump()
    assert shot.model_copy(update={"depth": False}).model_dump()["depth"] is False


def test_the_routes(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    with api_client(tmp_path) as client:
        base = f"/api/projects/{root.name}"
        state = client.get(f"{base}/depth").json()
        assert state["with_depth"] == 0
        assert state["tools"]["ready"] is False
        refused = client.post(f"{base}/depth/run", json={})
        assert refused.status_code == 409
        assert refused.json()["code"] == "depth_tools_missing"
        assert client.get(f"{base}/depth/nothing/near").status_code == 404
        assert client.get(f"{base}/depth/..%2f..%2f/near").status_code == 404
        assert client.get(f"{base}/depth/abc/secret").status_code == 404


def test_the_player_gets_layers_only_when_the_film_has_depth(tmp_path, monkeypatch):
    from mp3_to_videoclip.services.preview import player_input

    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    edits.seed_edit(root)
    assert "depth" not in player_input(root, root.name)["shots"][0]
    monkeypatch.setattr(depth, "depth_map", lambda still: _map(tmp_path / "d.png"))
    depth.run(root)
    _edit_with_depth(root)
    shot = player_input(root, root.name)["shots"][0]
    assert shot["depth"]["src"]["near"].startswith(f"/api/projects/{root.name}/depth/")
    assert read_json(root / "work/edit.json")
