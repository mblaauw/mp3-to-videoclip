"""Sheets and plates are bought like stills and bound only on the owner's click. All fakes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from api_support import make_api_project
from utils_image_schema import image_schema, jpeg_at

from mp3_to_videoclip import budget, sheets
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.storage import file_hash, read_json


class Fake:
    def __init__(self, *, pending=False):
        self.pending = pending
        self.submitted = []

    def schema(self, slug):
        return image_schema()

    def submit(self, request):
        self.submitted.append(request)
        uuid = request["taskUUID"]
        return {"taskUUID": uuid} if self.pending else {"taskUUID": uuid, "imageURL": "https://x.test/a.jpg", "cost": 0.04}  # fmt: skip

    def recover(self, uuid):
        return {"taskUUID": uuid, "imageURL": "https://x.test/a.jpg", "cost": 0.04}

    def download(self, url, path):
        jpeg_at(Path(path))

    def close(self):
        pass


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    P.update_brief(
        root,
        {
            "characters": [
                {"id": "ana", "identity": "A tall adult woman.", "permission_confirmed": True},
                {"id": "ben", "identity": "A short adult man.", "permission_confirmed": False},
            ],
            "creative": {
                "look": "Plain.",
                "scenes": [{"id": "barn", "description": "A red barn at noon."}],
            },  # fmt: skip
        },
        owner=True,
    )
    budget.set_budget(root, "5.00", "test budget")
    return root


def _bought(root, entry="ana", client=None):
    client = client or Fake()
    quote = sheets.quote_sheet(root, entry, client=client)
    G.authorize(root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    return quote, sheets.generate_sheet(root, quote["id"], client=client)


def test_a_quote_spends_nothing_and_says_where_the_sheet_will_live(film):
    quote = sheets.quote_sheet(film, "ana", client=Fake())
    task = quote["tasks"][0]
    assert quote["reserve_total_usd"] == "0.05"
    assert task["shot_id"] == "sheet:ana"
    assert task["relative"] == "work/sheets/ana/v001.jpg"
    assert "A tall adult woman." in task["request"]["positivePrompt"]
    assert "Plain." in task["request"]["positivePrompt"]
    assert read_json(film / "work/tasks.json") == {}


def test_nothing_is_bought_without_authorization(film):
    quote = sheets.quote_sheet(film, "ana", client=Fake())
    client = Fake()
    with pytest.raises(ValueError, match="authorization"):
        sheets.generate_sheet(film, quote["id"], client=client)
    assert client.submitted == []


def test_someone_without_permission_gets_no_sheet(film):
    with pytest.raises(ValueError, match="permission"):
        sheets.quote_sheet(film, "ben", client=Fake())


def test_buying_journals_before_it_asks_and_records_the_reported_cost(film):
    class Watching(Fake):
        def submit(self, request):
            task = read_json(film / "work/tasks.json")[request["taskUUID"]]
            assert task["status"] == "submitted" and task["reserve_usd"] == "0.05"
            return super().submit(request)

    quote, result = _bought(film, client=Watching())
    assert result["done"] == ["sheet:ana"]
    journal = read_json(film / "work/tasks.json")[quote["tasks"][0]["uuid"]]
    assert journal["kind"] == "sheet" and journal["cost_usd"] == "0.04"
    entry = read_json(film / "work/assets.json")["sheet:ana"]
    assert entry["selected"] == 1
    assert entry["versions"][0]["path"] == "work/sheets/ana/v001.jpg"


def test_a_lost_answer_is_recovered_and_never_bought_twice(film):
    client = Fake(pending=True)
    quote, result = _bought(film, client=client)
    assert result["pending"] == ["sheet:ana"]
    uuid = quote["tasks"][0]["uuid"]
    with pytest.raises(ValueError, match="recover"):
        sheets.generate_sheet(film, quote["id"], client=client)
    with pytest.raises(ValueError, match="unresolved"):
        sheets.quote_sheet(film, "ana", client=client)
    assert len(client.submitted) == 1
    assert G.recover(film, uuid, client=client) is True
    assert (film / "work/sheets/ana/v001.jpg").is_file()


def test_a_world_that_changed_after_the_quote_refuses_before_spending(film):
    client = Fake()
    quote = sheets.quote_sheet(film, "ana", client=client)
    G.authorize(film, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True)  # fmt: skip
    characters = read_json(film / "brief.json")["characters"]
    characters[0]["identity"] = "Someone else."
    P.update_brief(film, {"characters": characters}, owner=True)
    with pytest.raises(ValueError, match="changed since the quote"):
        sheets.generate_sheet(film, quote["id"], client=client)
    assert client.submitted == []
    assert read_json(film / "work/tasks.json") == {}


def test_a_new_sheet_keeps_the_old_one_and_goes_on_show(film):
    _bought(film)
    first = file_hash(film / "work/sheets/ana/v001.jpg")
    _bought(film)
    assert file_hash(film / "work/sheets/ana/v001.jpg") == first
    entry = read_json(film / "work/assets.json")["sheet:ana"]
    assert [v["version"] for v in entry["versions"]] == [1, 2]
    assert entry["selected"] == 2


def test_using_a_sheet_binds_it_and_only_on_that_click(film):
    _bought(film)
    assert read_json(film / "brief.json")["characters"][0]["references"] == []
    brief = sheets.use_as_reference(film, "ana", 1)
    path = brief.characters[0].references[0]
    assert path.startswith("media/references/")
    assert sheets.use_as_reference(film, "ana", 1).characters[0].references == [path]


def test_a_plate_becomes_a_reference_of_its_place(film):
    _bought(film, "barn")
    brief = sheets.use_as_reference(film, "barn", 1)
    reference = brief.creative.references[-1]
    assert reference.kind == "sheet" and reference.permission_confirmed
    assert brief.creative.scenes[0].reference_ids == [reference.id]


def test_sheets_never_count_as_stills(film):
    _bought(film)
    # A board that drops every shot is not told a sheet must stay on it.
    assert "sheet:ana" in read_json(film / "work/assets.json")
    assert prompts.select_task(film, "images", "writer") == "prompts"
    assert sheets.view(film)["ana"] == {"kind": "character", "version": 1, "current": True}
    assert "sheet:ana: the sheet" in build_context(film.name, film.parent, task="prompts")


def test_the_writer_can_look_at_a_sheet_a_reference_and_a_character(film):
    _bought(film)
    sheets.use_as_reference(film, "ana", 1)
    reference = read_json(film / "brief.json")["creative"]["references"][0]["id"]
    result = asyncio.run(
        tools.dispatch(
            "get_images",
            {"slug": film.name, "shot_ids": ["sheet:ana", "character:ana", reference, "sheet:ben"]},
            projects_dir=film.parent,
        )
    )
    payload = json.loads(result.text)
    assert payload["image_count"] == 3
    assert [item["id"] for item in payload["images"]] == ["sheet:ana", "character:ana", reference]
    assert "sheet:ben" in payload["errors"][0]
