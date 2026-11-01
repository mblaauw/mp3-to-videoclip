"""A redo that corrects the still it was given, where the model can take one. All fakes."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_support import add_assets, make_api_project
from test_creative_production import approve_prerequisites
from utils_image_schema import image_schema, jpeg_at

from mp3_to_videoclip import budget
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import read_json, write_json


class Fake:
    def __init__(self, **options):
        self.options = options
        self.submitted = []

    def schema(self, slug):
        return image_schema(**self.options)

    def reference_image(self, path):
        self.sent = getattr(self, "sent", []) + [Path(path).name]
        return "data:image/jpeg;base64,AAAA"

    def submit(self, request):
        self.submitted.append(request)
        return {"taskUUID": request["taskUUID"], "imageURL": "https://x.test/a.jpg", "cost": 0.04}

    def download(self, url, path):
        jpeg_at(Path(path))

    def close(self):
        pass


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    write_json(root / "work/tasks.json", {})
    budget.set_budget(root, "5.00", "test budget")
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved shots")
    return root


def _quote(root, client, note="Open her hand."):
    return G.quote_images(
        root, "proof", "0.05", ids=["s001"], client=client, edit_from={"s001": 1}, edit_note=note
    )


def test_the_still_goes_first_and_the_note_leads_the_prompt(film):
    quote = _quote(film, Fake())
    task = quote["tasks"][0]
    still = read_json(film / "work/assets.json")["s001"]["versions"][0]
    assert task["references"][0] == {"path": still["path"], "sha256": still["sha256"]}
    assert task["request"]["positivePrompt"].startswith("Edit the first supplied image")
    assert "Open her hand." in task["request"]["positivePrompt"]
    assert task["edit_of"] == 1
    assert G.quote_uploads_required(quote)
    assert "edit_unavailable" not in quote


def test_a_bought_edit_is_a_new_version_of_the_same_prompt_and_says_of_what(film):
    client = Fake()
    quote = _quote(film, client)
    G.authorize(
        film,
        quote["id"],
        quote["reserve_total_usd"],
        "owner",
        via="studio",
        review_confirmed=True,
        uploads_confirmed=True,
    )
    G.generate(film, quote["id"], client=client)
    assert client.sent[0] == Path(read_json(film / "work/assets.json")["s001"]["versions"][0]["path"]).name  # fmt: skip
    versions = read_json(film / "work/assets.json")["s001"]["versions"]
    assert versions[1]["edit_of"] == 1
    assert versions[1]["input_hash"] == versions[0]["input_hash"]
    assert "edit_of" not in versions[0]


def test_a_model_that_cannot_take_a_still_says_so_and_makes_it_again(film):
    quote = _quote(film, Fake(references=False))
    task = quote["tasks"][0]
    assert "cannot edit" in quote["edit_unavailable"]
    assert "edit_of" not in task
    assert not task["request"]["positivePrompt"].startswith("Edit the first")


def test_an_edit_needs_a_note_and_a_real_version(film):
    with pytest.raises(ValueError, match="what should change"):
        _quote(film, Fake(), note="  ")
    with pytest.raises(ValueError, match="no version 9"):
        G.quote_images(
            film, "proof", "0.05", ids=["s001"], client=Fake(),
            edit_from={"s001": 9}, edit_note="x",
        )  # fmt: skip
