"""Every blocked state names the fix. No key, no money, no call off this computer."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from mp3_to_videoclip.storage import read_json, write_json

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stays_local")]


def test_film_without_a_storyboard_shows_one_card(page: Page, studio):
    (studio.root / "work/storyboard.json").unlink()
    page.goto(studio.film("film"))
    expect(page.get_by_text("This film has no storyboard yet").first).to_be_visible()
    text = page.locator("body").inner_text()
    assert "[Errno" not in text
    assert ".json" not in text
    expect(page.locator(".toast.error")).to_have_count(0)
    page.locator(".ui-state").get_by_role("button", name="Go to Storyboard").click()
    expect(page).to_have_url(studio.film("storyboard"))


def test_an_unconfirmed_permission_names_who_and_goes_to_the_card(page: Page, studio):
    brief = read_json(studio.root / "brief.json")
    reference = brief["creative"]["references"][0]
    reference["permission_confirmed"] = False
    write_json(studio.root / "brief.json", brief)
    page.goto(studio.film("story"))
    bar = page.locator(".next-bar")
    expect(bar).to_contain_text(f"Confirm permission for {reference['id']}")
    bar.get_by_role("button", name="Go to World").click()
    expect(page.locator('.story-parts [aria-pressed="true"]')).to_contain_text("World")


def test_unfinished_shots_are_counted_filtered_and_never_say_todo(page: Page, studio):
    studio.unfinish_shots(2)
    studio.approve("brief")
    page.goto(studio.film("storyboard"))
    bar = page.locator(".next-bar")
    expect(bar).to_contain_text("2 shots still need a job and a prompt")
    expect(page.locator(".shot-card")).to_have_count(4)
    bar.get_by_role("button", name="Show them").click()
    expect(page.locator(".shot-card")).to_have_count(2)
    expect(page.locator(".needs-pill")).to_have_count(2)
    assert "TODO" not in page.locator("body").inner_text()


def test_pictures_with_no_runware_key_say_so_and_open_settings(page: Page, studio):
    studio.approve("brief", "storyboard")
    page.goto(studio.film("images"))
    page.locator(".next-bar").get_by_role("button", name="style still").click()
    toast = page.locator(".toast.error").first
    expect(toast).to_contain_text("Runware key")
    toast.get_by_role("button", name="Open settings").click()
    expect(page.get_by_role("dialog")).to_be_visible()


def test_a_missing_renderer_shows_its_card_above_the_viewer(page: Page, studio):
    page.route(
        "**/api/setup",
        lambda route: route.fulfill(
            json={
                "node": True,
                "npm": True,
                "chrome": True,
                "ffmpeg": True,
                "ffprobe": True,
                "renderer": False,
                "frontend": True,
            }
        ),
    )
    page.goto(studio.film("film"))
    card = page.locator(".card.setup")
    expect(card).to_be_visible()
    assert card.bounding_box()["height"] > 60


def test_the_picture_gets_its_share_of_a_short_tablet(page: Page, studio):
    studio.approve("brief", "storyboard")
    # With the renderer present, as on any film being worked on: CI's browser job has none.
    tools = dict.fromkeys(
        ("node", "npm", "chrome", "ffmpeg", "ffprobe", "renderer", "frontend"), True
    )
    page.route("**/api/setup", lambda route: route.fulfill(json=tools))
    page.set_viewport_size({"width": 1024, "height": 700})
    page.goto(studio.film("film"))
    # The page lays out in steps as the film loads, so wait for the height it settles at.
    page.wait_for_function(
        "(document.querySelector('.film-viewer')?.getBoundingClientRect().height ?? 0) >= 250"
    )
