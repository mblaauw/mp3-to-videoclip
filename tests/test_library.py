"""The world library: promoted out of a film, adopted into another, a series that recurs."""

from __future__ import annotations

import pytest
from api_support import add_assets, make_api_project
from test_creative_production import jpeg

from mp3_to_videoclip import library
from mp3_to_videoclip import production as P
from mp3_to_videoclip.references import import_reference
from mp3_to_videoclip.storage import file_hash, read_json


@pytest.fixture
def films(tmp_path):
    """Two films and an empty library beside them."""
    first = make_api_project(tmp_path / "projects", "first")
    second = make_api_project(tmp_path / "projects", "second")
    lib = tmp_path / "library"
    # A permitted character with a reference still, as the Characters card would make one.
    face = import_reference(first, jpeg(tmp_path / "face.jpg"), note="owner", permission_confirmed=True)  # fmt: skip
    P.update_brief(
        first,
        {
            "characters": [
                {
                    "id": "curator",
                    "identity": "a curator in 2300",
                    "permission_confirmed": True,
                    "references": [face["path"]],
                }
            ]
        },  # fmt: skip
        owner=True,
    )
    return first, second, lib


def test_the_library_sits_beside_projects_unless_named(tmp_path, monkeypatch):
    monkeypatch.delenv(library.ENV, raising=False)
    assert library.library_dir(tmp_path / "projects") == tmp_path / "library"
    monkeypatch.setenv(library.ENV, str(tmp_path / "elsewhere"))
    assert library.library_dir(tmp_path / "projects") == tmp_path / "elsewhere"


def test_promoting_copies_bytes_and_never_moves_or_overwrites(films):
    first, _, lib = films
    before = {p.relative_to(first).as_posix(): file_hash(p) for p in (first / "media/references").iterdir()}  # fmt: skip
    entry = library.promote(first, lib, "character", "curator", label="The curator")
    assert entry["key"] == "character:curator" and entry["version"] == 1
    assert entry["from"]["slug"] == "first" and entry["label"] == "The curator"
    copied = list((lib / "references").iterdir())
    assert len(copied) == 1 and file_hash(copied[0]) == copied[0].name.split(".")[0]
    after = {p.relative_to(first).as_posix(): file_hash(p) for p in (first / "media/references").iterdir()}  # fmt: skip
    assert after == before  # the film was only read
    # The same content again is the same entry; other content is a new version.
    assert library.promote(first, lib, "character", "curator") == entry
    P.update_brief(first, {"characters": [{"id": "curator", "identity": "a curator in 2300, older now", "permission_confirmed": True}]}, owner=True)  # fmt: skip
    second = library.promote(first, lib, "character", "curator")
    assert second["version"] == 2 and len(read_json(lib / "world.json")["entries"]) == 2
    assert [e["version"] for e in library.entries(lib)] == [2]
    with pytest.raises(ValueError, match="no character"):
        library.promote(first, lib, "character", "nobody")
    with pytest.raises(ValueError, match="not prop"):
        library.promote(first, lib, "prop", "lamp")


def test_a_place_a_narrator_and_a_look_are_promoted_from_the_profile(films):
    first, _, lib = films
    place = library.promote(first, lib, "place", "street")
    assert place["payload"]["scene"]["reference_ids"] == ["lamp"]
    assert [r["id"] for r in place["payload"]["references"]] == ["lamp"]
    assert len(place["files"]) == 1
    look = library.promote(first, lib, "look", "house")
    assert look["payload"]["look"].startswith("LOOK:") and look["payload"]["avoid"] == [
        "AVOID-TEXT"
    ]
    with pytest.raises(ValueError, match="no narrator"):
        library.promote(first, lib, "narrator", "voice")
    brief = P.load_brief(first)
    creative = brief.creative.model_dump()
    creative["narrator"] = {"persona": "a curator", "era": "2300"}
    P.update_brief(first, {"creative": creative}, owner=True)
    narrator = library.promote(first, lib, "narrator", "voice")
    assert narrator["payload"]["persona"] == "a curator"
    assert {e["kind"] for e in library.entries(lib)} == {"place", "look", "narrator"}
    assert [e["kind"] for e in library.entries(lib, "look")] == ["look"]


def test_adopting_writes_the_brief_as_the_owner_and_keeps_permission(films):
    first, second, lib = films
    library.promote(first, lib, "character", "curator")
    library.promote(first, lib, "place", "street")
    P.approve(second, "brief", "owner approved before")
    result = library.adopt(second, lib, "character:curator")
    assert result["changed"] == ["characters"] and result["skipped_files"] == []
    brief = P.load_brief(second)
    curator = next(c for c in brief.characters if c.id == "curator")
    assert curator.permission_confirmed is True and len(curator.references) == 1
    imported = second / curator.references[0]
    assert imported.is_file() and imported.parent.name == "references"
    # The story is no longer approved: the owner has to look again.
    with pytest.raises(ValueError, match="needs current user approval"):
        P.require_approval(second, "brief")
    placed = library.adopt(second, lib, "place:street")
    assert "creative.scenes" in placed["changed"]
    scenes = {s.id: s for s in P.load_brief(second).creative.scenes}
    assert scenes["street"].reference_ids == ["lamp"]
    # Adopting the same thing again changes nothing more and is not an error.
    library.adopt(second, lib, "place:street")
    assert len(P.load_brief(second).creative.scenes) == len(scenes)
    with pytest.raises(ValueError, match="no entry"):
        library.adopt(second, lib, "character:nobody")


def test_an_unpermitted_character_travels_without_its_pictures(films):
    first, second, lib = films
    P.update_brief(first, {"characters": [{"id": "curator", "identity": "a curator", "permission_confirmed": False}]}, owner=True)  # fmt: skip
    entry = library.promote(first, lib, "character", "curator")
    assert entry["files"] == {}
    result = library.adopt(second, lib, "character:curator")
    curator = next(c for c in P.load_brief(second).characters if c.id == "curator")
    assert curator.permission_confirmed is False and curator.references == []
    assert result["skipped_files"] == []


def test_a_look_adopted_sets_the_preset_too(films):
    first, second, lib = films
    project = read_json(first / "project.json")
    project["style_preset"] = "clean-photographic-v1"
    from mp3_to_videoclip.storage import write_json

    write_json(first / "project.json", project)
    library.promote(first, lib, "look", "house")
    result = library.adopt(second, lib, "look:house")
    assert "project.style_preset" in result["changed"]
    assert P.load_project(second).style_preset == "clean-photographic-v1"
    assert P.load_brief(second).creative.look.startswith("LOOK:")


def test_a_series_keeps_its_bible_episodes_and_recurring_cast(films, tmp_path):
    first, second, lib = films
    with pytest.raises(ValueError, match="needs a title"):
        library.write_series(lib, {"id": "museum"})
    with pytest.raises(ValueError, match="no entry"):
        library.write_series(lib, {"id": "museum", "title": "The Museum", "recurring": ["character:curator"]})  # fmt: skip
    library.promote(first, lib, "character", "curator")
    series = library.write_series(lib, {"id": "museum", "title": "The Museum of Tomorrow", "bible": "A curator in 2300.", "recurring": ["character:curator"]})  # fmt: skip
    assert series["episodes"] == [] and library.list_series(lib)[0]["id"] == "museum"
    library.add_episode(lib, "museum", "first", 1, "The House Key")
    with pytest.raises(ValueError, match="already exists"):
        library.add_episode(lib, "museum", "other", 1, "Twice")
    assert library.add_episode(lib, "museum", "first", 1, "The House Key")["episodes"] == library.read_series(lib, "museum")["episodes"]  # fmt: skip
    joined = library.join_series(second, lib, "museum", 2)
    assert joined["adopted"] == ["character:curator"]
    assert [ep["number"] for ep in library.read_series(lib, "museum")["episodes"]] == [1, 2]
    assert any(c.id == "curator" for c in P.load_brief(second).characters)
    # A change keeps the episodes; the bible is the owner's text.
    kept = library.write_series(
        lib, {"id": "museum", "title": "The Museum of Tomorrow", "bible": "Longer."}
    )
    assert len(kept["episodes"]) == 2 and kept["recurring"] == ["character:curator"]
    lines = library.series_context(lib, tmp_path / "projects", "museum", "second")
    assert lines[0].startswith("- Series: The Museum of Tomorrow")
    assert any(line.startswith("- Episode 1, The House Key: TREATMENT-SECRET") for line in lines)
    assert not any("Episode 2" in line for line in lines)
    assert library.series_context(lib, tmp_path / "projects", "nope", "x") == ["- Series nope: not in the library."]  # fmt: skip


def test_a_still_from_another_film_is_a_copy_with_its_provenance(films, tmp_path):
    first, second, lib = films
    add_assets(first)
    row = library.bring_still(second, tmp_path / "projects", "first", "s001", 2)
    path = second / row["path"]
    assert path.is_file() and path.parent == second / "media/uploads"
    assert file_hash(path) == row["sha256"] == row["path"].split("/")[-1].split(".")[0]
    assert read_json(second / "work/provenance.json")[0]["from"] == {"slug": "first", "shot_id": "s001", "version": 2}  # fmt: skip
    # Twice is once.
    library.bring_still(second, tmp_path / "projects", "first", "s001", 2)
    assert len(read_json(second / "work/provenance.json")) == 1
    with pytest.raises(ValueError, match="no still"):
        library.bring_still(second, tmp_path / "projects", "first", "s001", 9)
    with pytest.raises(ValueError, match="no film"):
        library.bring_still(second, tmp_path / "projects", "third", "s001", 1)
    # The source film was only read.
    assert (first / "work/provenance.json").exists() is False


def test_a_film_without_a_series_keeps_its_bytes_and_one_with_is_told_what_came_before(films, tmp_path, monkeypatch):  # fmt: skip
    from mp3_to_videoclip.director.context import build_context
    from mp3_to_videoclip.models import Project

    first, second, lib = films
    stored = read_json(second / "project.json")
    assert "series" not in stored
    assert "series" not in Project.model_validate(stored).model_dump()
    before = P.stage_hash(second, "brief")
    library.promote(first, lib, "character", "curator")
    library.write_series(lib, {"id": "museum", "title": "The Museum", "bible": "A curator explains.", "recurring": ["character:curator"]})  # fmt: skip
    library.add_episode(lib, "museum", "first", 1, "The House Key")
    monkeypatch.setenv(library.ENV, str(lib))
    project = Project.model_validate({**stored, "series": {"id": "museum", "episode": 2}})
    from mp3_to_videoclip.storage import write_json

    write_json(second / "project.json", project.model_dump())
    assert read_json(second / "project.json")["series"] == {"id": "museum", "episode": 2}
    # The series field is outside every hash: the brief approval does not move.
    assert P.stage_hash(second, "brief") == before
    snapshot = build_context("second", tmp_path / "projects", stage="story", task="revise")
    assert "## Series (episode 2)" in snapshot
    assert "- Bible: A curator explains." in snapshot
    assert "- Episode 1, The House Key: TREATMENT-SECRET" in snapshot


def test_intake_with_a_series_adopts_the_cast_and_lists_the_episode(films, tmp_path, monkeypatch):
    from mp3_to_videoclip.domain import intake

    first, _, lib = films
    library.promote(first, lib, "character", "curator")
    library.write_series(lib, {"id": "museum", "title": "The Museum", "recurring": ["character:curator"]})  # fmt: skip
    created = intake.create_from_upload(
        tmp_path / "projects",
        None,
        title="002 The Lamp",
        kind="narrative",
        intent={"kind": "narrative", "fictional": True, "structure": "five-beat-2m"},
        length_seconds=120,
        series={"id": "museum", "episode": 2},
    )
    root = created["root"]
    assert P.load_project(root).series.model_dump() == {"id": "museum", "episode": 2}
    joined = library.join_series(root, lib, "museum", 2)
    assert joined["adopted"] == ["character:curator"]
    assert [c.id for c in P.load_brief(root).characters] == ["curator"]
    assert [ep["slug"] for ep in library.read_series(lib, "museum")["episodes"]] == [root.name]
