"""The Publish stage in a real browser: the release list reads the final and says what is heard."""

from __future__ import annotations

import pytest
from api_support import add_assets
from playwright.sync_api import Page, expect
from test_publish import _stamped_final

from mp3_to_videoclip import edits

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stays_local")]


def test_the_release_list_opens_on_the_final_and_measures_the_listening(page: Page, studio):
    add_assets(studio.root)
    edits.save_edit(studio.root, edits.seed_edit(studio.root))
    final = _stamped_final(studio.root)
    page.goto(studio.film("publish"))
    expect(page.get_by_role("heading", name="Publish")).to_be_visible()
    expect(page.locator(".publish-stage h2").first).to_contain_text(final.name)
    expect(page.get_by_text("0 of 4 seconds heard with the sound on.")).to_be_visible()
    expect(page.get_by_text("Heard start to finish with the sound on")).to_be_visible()
    expect(page.get_by_role("button", name="Mark as released")).to_be_disabled()
    page.get_by_role("button", name="Draw three candidates").click()
    expect(page.locator(".thumb-grid li").first).to_be_visible(timeout=30_000)
    page.locator(".thumb-grid button").first.click()
    expect(page.locator(".thumb-grid li.chosen")).to_have_count(1)
    assert "[Errno" not in page.locator("body").inner_text()
