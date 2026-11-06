"""The Sound stage in a real browser: a cue, its price refused without a key, the bar's word."""

from __future__ import annotations

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
