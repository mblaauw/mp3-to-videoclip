"""Heard seconds, the publish copy and its checks, thumbnails beside a real final, the release."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets
from test_delivery import _final
from test_first_cut import _film

from mp3_to_videoclip import budget, delivery, edits, publish, signature, watched
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


def _stamped_final(root: Path, name="production-final-v001.mp4", seconds=4) -> Path:
    """A real small MP4 whose report says what a delivered final's says."""
    film = _final(root, name, seconds=seconds)
    report = read_json(film.with_suffix(".json"))
    report.update(
        input_hash=signature.current_input_hash(root),
        delivery_ready=True,
        video={"frames": seconds * 24, "fps": 24},
    )
    write_json(film.with_suffix(".json"), report)
    return film


@pytest.fixture
def film(tmp_path):
    root = _film(tmp_path)
    add_assets(root)
    edits.save_edit(root, edits.seed_edit(root))
    P.update_brief(
        root,
        {
            "intent": {
                "kind": "promo",
                "objective": "Fill the room",
                "message": "Find the second heartbeat",
                "cta": {"text": "Enter After Dark", "url": "https://coolcat.example/after-dark"},
                "mandatories": ["Doors at 23:00", "Tickets $12"],
            }
        },  # fmt: skip
        owner=True,
    )
    return root


# ------------------------------------------------------------------ copy


def test_the_copy_is_checked_against_the_brief(film):
    root = film
    good = {"titles": ["Cool Cat After Dark"], "description": "Doors at 23:00. Tickets $12. coolcat.example/after-dark", "tags": ["jazz", "amsterdam"]}  # fmt: skip
    assert publish.check_copy(root, good) == []
    assert publish.check_copy(root, {"titles": [], "description": ""}) == ["One to 3 titles."]
    bad_link = publish.check_copy(root, {"titles": ["x"], "description": "See https://elsewhere.example/tickets"})  # fmt: skip
    assert bad_link == [
        "The link https://elsewhere.example/tickets is not the brief's call to action."
    ]
    bad_price = publish.check_copy(
        root, {"titles": ["x"], "description": "Only $9 tonight, 50% off"}
    )
    assert bad_price == [
        "The figure $9 is not in the brief or the script.",
        "The figure 50% is not in the brief or the script.",
    ]
    with pytest.raises(ValueError, match="not the brief's call to action"):
        publish.set_copy(root, {"titles": ["x"], "description": "https://elsewhere.example"})
    saved = publish.set_copy(root, good)
    assert saved["copy"]["titles"] == ["Cool Cat After Dark"] and saved["copy"]["by"] == "owner"
    publish.set_copy(root, {**good, "titles": ["Another"]}, by="writer")
    assert len(list((root / "work/publish-history").glob("copy-*.json"))) == 1


# ------------------------------------------------------------------ thumbnails, presets, plan


def test_three_thumbnails_are_drawn_beside_the_final_and_one_is_chosen(film):
    root = film
    final = _stamped_final(root)
    rows = publish.thumbnails(root, final, title="Cool Cat After Dark")
    assert 1 <= len(rows) <= 3
    for row in rows:
        path = final.parent / row["name"]
        assert path.is_file() and row["bytes"] <= publish.THUMB_BYTES
        assert row["name"].startswith("production-final-v001.thumb-f")
        from PIL import Image

        with Image.open(path) as image:
            assert image.size == publish.THUMB_SIZE
    assert publish.listing(final) == rows
    # Made again, nothing is rewritten.
    before = {row["name"]: row["sha256"] for row in rows}
    assert {row["name"]: row["sha256"] for row in publish.thumbnails(root, final)} == before
    with pytest.raises(ValueError, match="choose one of"):
        publish.choose_thumbnail(root, final, "nope.jpg")
    chosen = publish.choose_thumbnail(root, final, rows[0]["name"])
    assert chosen["thumbnail"]["final"] == final.name
    assert set(delivery.listing(final)) >= {row["name"] for row in rows}


def test_a_new_film_starts_on_the_presets_settings_name(film, tmp_path, monkeypatch):
    from mp3_to_videoclip import config

    monkeypatch.setattr(config, "settings_path", lambda: tmp_path / "settings.toml")
    root = film
    assert publish.read(root)["presets"] == ["youtube"]
    config.save_settings(config.Settings(new_films={"presets": ["shorts", "tiktok", "shorts"]}))
    assert publish.read(root)["presets"] == ["shorts"]
    # An empty or unknown choice falls back; a film that chose keeps its choice.
    config.save_settings(config.Settings(new_films={"presets": ["tiktok"]}))
    assert publish.read(root)["presets"] == ["youtube"]
    publish.set_presets(root, ["square"])
    config.save_settings(config.Settings(new_films={"presets": ["reels"]}))
    assert publish.read(root)["presets"] == ["square"]


def test_presets_and_the_plan_name_what_is_missing(film):
    root = film
    assert publish.plan(root, None)[0]["missing"] == ["a verified final"]
    final = _stamped_final(root)
    with pytest.raises(ValueError, match="presets are some of"):
        publish.set_presets(root, ["tiktok"])
    publish.set_presets(root, ["youtube", "shorts", "youtube"])
    assert publish.read(root)["presets"] == ["youtube", "shorts"]
    rows = {row["id"]: row for row in publish.plan(root, final)}
    assert rows["youtube"]["has"] == [final.name]
    assert rows["youtube"]["missing"] == [
        "the chapters (Film, Make the package)",
        "the captions (Film, Make the package)",
    ]
    assert rows["shorts"]["missing"] == ["the 9:16 version (Film, Render 9:16)"]
    delivery.make_package(root, final)
    rows = {row["id"]: row for row in publish.plan(root, final)}
    assert rows["youtube"]["missing"] == []


# ------------------------------------------------------------------ the checklist and the release


def test_the_release_waits_for_the_ear_the_copy_and_the_thumbnail(film):
    root = film
    facts = publish.checklist(root)
    assert facts["final"] is None and facts["can_release"] is False
    assert facts["lines"][0]["detail"] == "Render the final on Film first."
    final = _stamped_final(root)
    facts = publish.checklist(root)
    assert facts["final"] == final.name
    states = {line["id"]: line["state"] for line in facts["lines"]}
    assert states["final"] == "done" and states["heard"] == "you" and states["rights"] == "done"
    assert states["money"] == "done"
    with pytest.raises(ValueError, match="not ready to release"):
        publish.release(root)
    watched.record(root, f"renders/{final.name}", [0, 1, 2, 3])
    publish.set_copy(root, {"titles": ["Cool Cat After Dark"], "description": "Doors at 23:00."})
    publish.thumbnails(root, final)
    publish.choose_thumbnail(root, final, publish.listing(final)[0]["name"])
    facts = publish.checklist(root)
    assert facts["can_release"] is True and facts["outstanding"] == []
    manifest = publish.release(root, note="first release")
    assert manifest["final"] == final.name and manifest["note"] == "first release"
    assert set(manifest["files"]) >= {final.name, publish.read(root)["thumbnail"]["name"]}
    assert (final.parent / "production-final-v001.publish.json").is_file()
    assert publish.read(root)["released"]["final"] == final.name
    assert publish.view(root)["released"]["final"] == final.name
    # A paid task still out blocks a release.
    budget.set_budget(root, "5.00", "test")
    write_json(root / "work/tasks.json", {"t1": {"uuid": "t1", "kind": "images", "status": "submitted", "reserve_usd": "0.05"}})  # fmt: skip
    assert "No paid task still out" in publish.checklist(root)["outstanding"]
