"""The Sound stage in a real browser: a cue, its price refused without a key, the bar's word."""

from __future__ import annotations

import re

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stays_local")]


def test_a_silent_cue_is_counted_and_its_price_needs_a_key(page: Page, studio):
    saved = httpx.put(
        f"{studio.api}/sound",
        json={
            "cues": [
                {
                    "id": "hit",
                    "kind": "effect",
                    "prompt": "a door closing",
                    "start": {"frame": 0},
                    "end": {"frame": 24},
                }
            ]
        },  # fmt: skip
    )
    assert saved.status_code == 200, saved.text
    page.goto(studio.film("sound"))
    expect(page.get_by_role("heading", name="Sound")).to_be_visible()
    expect(page.locator(".sound-stage h2").first).to_contain_text("1 cue, 1 silent")
    expect(page.locator(".next-bar")).to_contain_text("1 of 1 cue has no sound yet")
    expect(page.locator(".cue-band")).to_have_count(1)
    page.locator("#cue-hit").get_by_role("button", name="Make this sound").click()
    toast = page.locator(".toast.error").first
    expect(toast).to_contain_text("Runware key")
    toast.get_by_role("button", name="Open settings").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    assert "[Errno" not in page.locator("body").inner_text()


def test_a_placed_cue_shows_its_places_on_the_spine_and_a_click_offers_an_effect(
    page: Page, studio
):
    saved = httpx.put(
        f"{studio.api}/sound",
        json={
            "cues": [
                {
                    "id": "tick",
                    "kind": "effect",
                    "prompt": "a clock tick",
                    "start": {"frame": 0},
                    "end": {"frame": -1},
                    "places": {"every": 1.0},
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    page.goto(studio.film("sound"))
    expect(page.get_by_role("heading", name="Sound")).to_be_visible()
    expect(page.locator(".map-playhead").first).to_be_visible()
    places = page.locator(".cue-place")
    assert places.count() >= 2
    row = page.locator("#cue-tick")
    expect(row).to_contain_text("every 1 s")
    expect(row).to_contain_text("a clock tick")
    row.locator(".cue-row-main").click()
    inspector = page.get_by_role("complementary", name="Cue tick")
    expect(inspector.get_by_role("radio", name="Every few seconds")).to_have_attribute(
        "aria-checked", "true"
    )
    expect(inspector.get_by_label("From kind")).to_have_value("frame")
    page.locator(".map-track.lane-cues.ambience").click(position={"x": 40, "y": 10})
    expect(page.get_by_role("button", name=re.compile(r"^Add an effect at"))).to_be_visible()


def test_a_cue_edited_in_the_inspector_saves_itself(page: Page, studio):
    saved = httpx.put(
        f"{studio.api}/sound",
        json={
            "cues": [
                {
                    "id": "rain",
                    "kind": "ambience",
                    "prompt": "rain",
                    "start": {"frame": 0},
                    "end": {"frame": -1},
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    page.goto(studio.film("sound"))
    page.get_by_role("button", name=re.compile(r"^rain, ambience")).click()
    inspector = page.get_by_role("complementary", name="Cue rain")
    inspector.get_by_label("What rain sounds like").fill("soft rain on a tin roof ")
    inspector.get_by_role("radio", name="At a moment").click()
    expect(page.locator(".save-state")).to_contain_text("Saved")
    cue = httpx.get(f"{studio.api}/sound").json()["cues"][0]
    assert cue["prompt"] == "soft rain on a tin roof"
    assert cue["start"] == cue["end"] == {"frame": 0}
    # The words on screen keep the space the owner typed; the saved cue is trimmed.
    expect(inspector.get_by_label("What rain sounds like")).to_have_value(
        "soft rain on a tin roof "
    )
    expect(page.locator("#cue-rain")).to_contain_text("at 0:00.0")
