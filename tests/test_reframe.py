"""A version of another shape: arithmetic, and that a film of its own shape is untouched."""

from __future__ import annotations

import pytest
from api_support import add_assets, make_api_project
from test_clips import make_clip  # noqa: F401
from test_creative_production import approve_prerequisites

from mp3_to_videoclip import production as P
from mp3_to_videoclip import reframe, remotion, services
from mp3_to_videoclip.storage import write_json


def test_a_canvas_keeps_the_short_side_and_stays_even():
    assert reframe.canvas_for(1920, 1080, "9:16") == (1080, 1920)
    assert reframe.canvas_for(1920, 1080, "1:1") == (1080, 1080)
    width, height = reframe.canvas_for(1366, 768, "9:16")
    assert width == 768 and height % 2 == 0
    with pytest.raises(ValueError):
        reframe.canvas_for(1920, 1080, "4:3")


def test_the_middle_stays_the_middle_and_an_anchor_moves_the_crop():
    source, canvas = (1920, 1080), (1080, 1920)
    assert reframe.position([0.5, 0.5], source, canvas)["x"] == 50.0
    assert reframe.position([0.5, 0.5], source, canvas)["y"] == 50.0
    left = reframe.position([0.0, 0.5], source, canvas)
    right = reframe.position([1.0, 0.5], source, canvas)
    assert left["x"] == 0.0 and right["x"] == 100.0
    assert (
        reframe.position([0.25, 0.5], source, canvas)["x"]
        < 50
        < reframe.position([0.75, 0.5], source, canvas)["x"]
    )
    assert left["kept"] == pytest.approx(0.316, abs=0.001)


def test_an_anchor_near_the_edge_never_shows_past_the_picture():
    place = reframe.position([0.05, 0.5], (1920, 1080), (1080, 1920))
    assert place["x"] == 0.0


def test_a_portrait_still_on_a_square_crops_the_other_way():
    place = reframe.position([0.5, 0.2], (1080, 1920), (1080, 1080))
    assert place["x"] == 50.0
    assert 0 <= place["y"] < 50


def test_softness_is_about_enlargement():
    assert reframe.is_soft((1376, 768), (1080, 1920))
    assert not reframe.is_soft((2752, 1536), (1080, 1920))


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    write_json(root / "work/tasks.json", {})
    approve_prerequisites(root)
    return root


def test_nothing_is_named_for_a_film_of_its_own_shape(film, tmp_path):
    assets = tmp_path / "staged"
    assets.mkdir()
    compiled = remotion.compile_shots(P.resolved_assets(film, ["s001"]), film / "work", assets)
    assert "reframe" not in compiled[0]
    assert "reframe" not in services.preview.player_input(film, film.name)["shots"][0]


def test_the_player_shows_the_version_with_its_canvas_and_anchors(film):
    payload = services.preview.player_input(film, film.name, "1:1")
    project = P.load_project(film)
    side = min(project.width, project.height)
    assert (payload["width"], payload["height"]) == (side, side)
    assert payload["shots"][0]["reframe"]["x"] == 50.0


def test_a_version_needs_a_current_final_and_a_new_shape(film):
    with pytest.raises(ValueError, match="render the final first"):
        services.render.variant_source(film, "9:16")
    with pytest.raises(ValueError, match="9:16 or 1:1"):
        services.render.variant_source(film, "4:3")


def test_a_card_is_drawn_for_the_shape_it_appears_in(film):
    from PIL import Image

    board = P.load_board(film)
    data = board.model_dump()
    data["shots"][0].update(kind="date_card", text=["1880"])
    data["shots"][0].pop("image_prompt", None)
    write_json(film / "work/storyboard.json", data)
    path = P.local_plate_path(film, "s001", (540, 960))
    with Image.open(path) as image:
        assert image.size == (540, 960)
