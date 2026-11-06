"""The New film form: formats fill it, the titles follow the shape, the film keeps the answers."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from mp3_to_videoclip import config

pytestmark = pytest.mark.e2e


def _form(page: Page, studio):
    page.goto(f"{studio.url}/#/")
    page.get_by_role("button", name="New film").first.click()
    return page.get_by_label("Titles")


def _options(select) -> list[str]:
    return [text.strip() for text in select.locator("option").all_inner_texts()]


def test_a_fresh_install_starts_on_short_titles_and_portrait_loses_the_signature(
    page: Page, studio
):
    titles = _form(page, studio)
    expect(titles).to_have_value("title-v1")
    assert _options(titles) == ["25/40 signature", "Short title and end card", "None"]
    page.get_by_role("radio", name="9:16 portrait").click()
    assert _options(titles) == ["Short title and end card", "None"]


def test_a_kit_with_a_name_starts_on_the_signature(page: Page, studio):
    config.save_settings(config.Settings(brand_name="Ana"))
    titles = _form(page, studio)
    expect(titles).to_have_value("joint-v1")
    page.get_by_role("radio", name="9:16 portrait").click()
    expect(titles).to_have_value("title-v1")


def test_a_format_fills_the_form_and_says_when_it_was_adjusted(page: Page, studio):
    _form(page, studio)
    page.get_by_role("button", name="Promo").click()
    page.get_by_role("button", name="Release teaser, 30 s, 9:16").click()
    glance = page.get_by_role("complementary", name="At a glance")
    expect(glance).to_contain_text("Release teaser")
    expect(page.get_by_role("radio", name="30 s")).to_have_attribute("aria-checked", "true")
    expect(page.get_by_role("radio", name="9:16 portrait")).to_have_attribute(
        "aria-checked", "true"
    )
    expect(glance).to_contain_text("Release teaser")
    expect(page.get_by_label("Structure")).to_have_count(0)
    expect(page.get_by_role("checkbox", name="YouTube Shorts")).to_be_checked()
    expect(page.get_by_role("checkbox", name="Instagram Reels")).to_be_checked()
    expect(page.get_by_role("checkbox", name="YouTube", exact=True)).to_have_count(0)
    page.get_by_role("radio", name="1 min").click()
    expect(glance).to_contain_text("Adjusted from Release teaser")
    expect(glance).to_contain_text("Your own format")
    expect(page.get_by_role("button", name="Create film")).to_be_disabled()
    expect(glance).to_contain_text("Still needed: an MP3, a title, the one message.")
