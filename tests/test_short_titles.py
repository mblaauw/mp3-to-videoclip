"""Title packages: a spec without the key is the signature, untouched; short titles are new."""

from __future__ import annotations

import pytest
from test_signature_iteration import synth_source

from mp3_to_videoclip import config, graphics, production, signature, titles
from mp3_to_videoclip.storage import read_json


def _spec(**changes):
    spec = signature.draft_spec("Film", {"name": "ANA", "partner": ""}, package="title-v1")
    spec.update(changes)
    return spec


def test_a_short_film_opens_on_a_title_and_closes_on_an_end_card():
    windows, total = titles.plan_titles(_spec(), fps=24, duration=20.0)
    assert total == 480
    assert [(w["kind"], w["start_frame"], w["frames"]) for w in windows] == [
        ("title", 0, 72),
        ("end_card", 360, 120),
    ]


def test_no_opening_means_no_title_window():
    windows, _ = titles.plan_titles(_spec(intro_seconds=0.0), fps=24, duration=20.0)
    assert [w["kind"] for w in windows] == ["end_card"]


def test_no_end_card_means_no_closing_window():
    windows, _ = titles.plan_titles(_spec(credits_tail_seconds=0.0), fps=24, duration=20.0)
    assert [w["kind"] for w in windows] == ["title"]


def test_a_caption_can_start_at_the_first_frame_with_no_opening():
    caption = {"id": "c", "style": "caption", "text": "x", "start": 0.0, "end": 2.0}
    spec = _spec(intro_seconds=0.0, captions=[caption])
    windows, _ = titles.plan_titles(spec, fps=24, duration=20.0)
    assert windows[0]["kind"] == "caption"


def test_a_spec_without_a_package_plans_what_it_always_did():
    spec = {
        "intro_seconds": 25.0,
        "credits_tail_seconds": 40.0,
        "lockup_seconds": 4.0,
        "captions": [],
        "credits": {"cards": [["MUSIC", "A"]], "lockup": "X"},
    }
    windows, total = titles.plan_titles(spec, fps=24, duration=120.0)
    assert total == 2880
    assert [w["kind"] for w in windows] == ["intro", "card", "lockup"]
    assert windows[0]["frames"] == 600
    assert windows[1]["start_frame"] == 1920


def test_the_joint_draft_has_no_package_key():
    assert "package" not in signature.draft_spec("Film")
    assert signature.package_of(signature.draft_spec("Film")) == "joint-v1"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"intro_seconds": 6.0}, "at most 5"),
        ({"credits_tail_seconds": 11.0}, "at most 10"),
        ({"intro_seconds": 0.0, "credits_tail_seconds": 0.0}, "choose none"),
        ({"intro": {"title": ""}}, "needs a title"),
        ({"end_card": {"lockup": "", "lines": []}}, "nothing on it"),
        ({"end_card": {"lockup": "A", "lines": ["1", "2", "3", "4", "5"]}}, "at most 4"),
    ],
)
def test_short_titles_keep_their_own_rules(changes, message):
    with pytest.raises(ValueError, match=message):
        signature.check_short_titles(_spec(**changes))


def test_each_package_says_which_films_it_can_be_used_on():
    signature.require_package("title-v1", "9:16", 6.0)
    signature.require_package("none", "9:16", 6.0)
    with pytest.raises(ValueError, match="16:9"):
        signature.require_package("joint-v1", "9:16", 120.0)
    with pytest.raises(ValueError, match="65"):
        signature.require_package("joint-v1", "16:9", 30.0)
    with pytest.raises(ValueError, match="unknown"):
        signature.require_package("x", "16:9", 30.0)


def _settings(**brand):
    return config.Settings(new_films=config.NewFilms(brand=config.Brand(**brand)))


def test_the_default_follows_the_brand_kit():
    assert signature.default_package(_settings(), "music_video") == "title-v1"
    assert signature.default_package(_settings(name="Ana"), "music_video") == "joint-v1"
    assert signature.default_package(_settings(name="Ana"), "advert") == "none"
    off = config.Settings(new_films=config.NewFilms(signature_package=False))
    assert signature.default_package(off, "music_video") == "none"


def test_a_fresh_install_names_nobody(tmp_path):
    root = tmp_path / "film"
    production.init_project(root, synth_source(tmp_path), "film", title="Film")
    spec = read_json(root / "work/graphics-spec.json")
    assert spec["package"] == "title-v1"
    assert "brand" not in spec
    assert spec["credits_tail_seconds"] == 0.0
    assert read_json(root / "project.json")["signature_required"] is True
    assert "MAHA" not in str(spec)


def test_a_portrait_film_can_be_made_and_validates(tmp_path):
    root = tmp_path / "film"
    project = production.init_project(
        root, synth_source(tmp_path), "film", aspect="9:16", title="Film", titles="title-v1"
    )
    assert signature.validate_spec(root, project)["intro"]["title"] == "Film"
    assert graphics.load_spec(root)["package"] == "title-v1"


def test_a_film_with_no_titles_records_none_and_has_no_spec(tmp_path):
    root = tmp_path / "film"
    production.init_project(root, synth_source(tmp_path), "film", title="Film", titles="none")
    assert read_json(root / "project.json")["signature_required"] is False
    assert not (root / "work/graphics-spec.json").exists()


def test_a_kit_with_a_name_is_recorded_in_the_film(tmp_path):
    config.save_settings(_settings(name="Ana", partner="Ben"))
    root = tmp_path / "film"
    production.init_project(root, synth_source(tmp_path), "film", title="Film", titles="title-v1")
    spec = read_json(root / "work/graphics-spec.json")
    assert spec["brand"] == {"name": "ANA", "partner": "BEN"}
    assert spec["end_card"]["lockup"] == "A JOINT ANA & BEN PRODUCTION"


def test_a_film_with_something_to_close_on_gets_an_end_card():
    assert signature.draft_spec("F", {"name": "A", "partner": ""}, package="title-v1")["credits_tail_seconds"] == 5.0  # fmt: skip
    assert signature.draft_spec("F", None, package="title-v1")["credits_tail_seconds"] == 0.0


def test_the_credits_card_writes_end_card_lines_on_a_short_film(tmp_path):
    root = tmp_path / "film"
    production.init_project(root, synth_source(tmp_path), "film", title="Film", titles="title-v1")
    signature.save_credits(root, [["Music", "Ana"]])
    spec = read_json(root / "work/graphics-spec.json")
    assert spec["end_card"]["lines"] == ["Music: Ana"]
    assert spec["credits_tail_seconds"] == 5.0
    with pytest.raises(ValueError, match="at most 4"):
        signature.save_credits(root, [["a", str(i)] for i in range(5)])


def test_a_logo_must_be_an_svg_on_this_computer(tmp_path):
    svg = tmp_path / "logo.svg"
    svg.write_text("<svg/>")
    assert signature.logo_data(str(svg)).startswith("data:image/svg+xml;base64,")
    assert signature.logo_data(str(tmp_path / "missing.svg")) is None
    png = tmp_path / "logo.png"
    png.write_bytes(b"x")
    assert signature.logo_data(str(png)) is None
    assert signature.logo_data("") is None


def test_short_titles_reach_the_renderer_without_a_mark():
    from mp3_to_videoclip.remotion import title_assets

    spec = _spec()
    assets = title_assets(spec, graphics.resolve_palette(spec))
    assert assets["logo"] is None
    assert assets["palette"]["accent"] == "#ffffff"
