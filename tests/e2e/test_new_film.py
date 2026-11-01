"""The New film form offers the titles and the shape, and takes the signature away from 9:16."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from mp3_to_videoclip import config

pytestmark = pytest.mark.e2e


def _form(page: Page, studio):
    page.goto(f"{studio.url}/#/")
    page.get_by_role("button", name="New film").first.click()
    return page.get_by_label("Titles"), page.get_by_label("Shape")


def _options(select) -> list[str]:
    return [text.strip() for text in select.locator("option").all_inner_texts()]


def test_a_fresh_install_starts_on_short_titles_and_portrait_loses_the_signature(
    page: Page, studio
):
    titles, shape = _form(page, studio)
    expect(titles).to_have_value("title-v1")
    assert _options(titles) == ["25/40 signature", "Short title and end card", "None"]
    shape.select_option("9:16")
    assert _options(titles) == ["Short title and end card", "None"]


def test_a_kit_with_a_name_starts_on_the_signature(page: Page, studio):
    config.save_settings(config.Settings(brand_name="Ana"))
    titles, shape = _form(page, studio)
    expect(titles).to_have_value("joint-v1")
    shape.select_option("9:16")
    expect(titles).to_have_value("title-v1")
