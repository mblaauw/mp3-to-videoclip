"""Film's Captions control in a real browser. Nothing leaves this computer."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from mp3_to_videoclip import edits
from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.storage import write_json

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stays_local")]


def test_choosing_captions_draws_them_and_off_removes_them(page: Page, studio):
    studio.approve("brief", "storyboard")
    edits.seed_edit(studio.root)
    write_json(studio.root / "work/lyrics.json", {"lines": ["One line", "Another line"]})
    lyric_timing.save(
        studio.root,
        {
            "lines": [
                {"index": 0, "start": 0.5, "end": 1.5, "source": "tapped"},
                {"index": 1, "start": 2.0, "end": 3.0, "source": "tapped"},
            ]
        },
        60,
    )
    page.goto(studio.film("film"))
    control = page.locator(".caption-control")
    expect(control).to_contain_text("0 on the film")
    control.get_by_label("Captions").select_option(label="All sung lines")
    expect(control).to_contain_text("2 on the film")
    assert sum(len(shot.text) for shot in edits.load_edit(studio.root).shots) == 2
    control.get_by_label("Captions").select_option(label="Off")
    expect(control).to_contain_text("0 on the film")


def test_the_player_loads_the_films_embedded_typeface(page: Page, studio):
    studio.approve("brief", "storyboard")
    edit = edits.seed_edit(studio.root)
    grade = edit.grade.model_copy(update={"typeface": "fraunces"})
    edits.save_edit(studio.root, edit.model_copy(update={"grade": grade}))
    page.goto(studio.film("film"))
    page.wait_for_function(
        "[...document.fonts].some((face) => face.family.includes('Fraunces') && face.status === 'loaded')"
    )
