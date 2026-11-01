"""The panel in a real browser, with no key, on a throwaway folder. Nothing is spent."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


@pytest.fixture
def panel(page: Page, studio, stays_local):
    page.goto(studio.url + "/")
    page.get_by_role("button", name="Settings").first.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    return dialog


def _tab(dialog, name: str):
    dialog.get_by_role("navigation").get_by_role("button", name=name).click()


def test_the_checklist_names_what_is_missing_and_focuses_each_field(page: Page, panel):
    missing = panel.get_by_role("region", name="What is missing to make a film")
    expect(missing).to_contain_text("Writer key")
    expect(missing).to_contain_text("Runware key")
    missing.get_by_role("button", name="Runware key").click()
    expect(panel.locator("#key-runware")).to_be_focused()


def test_a_model_chosen_through_other_saves_and_reset_restores_it(page: Page, panel):
    field = panel.get_by_label("Writer model")
    field.select_option(label="Other…")
    typed = panel.get_by_label("Writer model")
    typed.fill("my-own-model")
    typed.blur()
    expect(panel.locator(".save-state.saved").first).to_contain_text("Saved")
    panel.get_by_role("button", name="Reset to recommended").click()
    expect(panel.get_by_label("Writer model")).to_have_value("gpt-6.1-sol")


def test_elevenlabs_voices_appear_only_with_a_key(page: Page, panel):
    _tab(panel, "Voices")
    expect(panel.get_by_label("Default voice")).to_have_value("English_Magnetic_Male_2")
    expect(
        panel.get_by_label("Voice provider").locator("option", has_text="ElevenLabs")
    ).to_have_count(0)
    _tab(panel, "Keys")
    key = panel.locator("#key-elevenlabs")
    key.fill("fake-key")
    key.blur()
    expect(panel.locator("#key-elevenlabs")).to_have_attribute(
        "placeholder", "Stored. Leave empty to keep it"
    )
    _tab(panel, "Voices")
    expect(
        panel.get_by_label("Voice provider").locator("option", has_text="ElevenLabs")
    ).to_have_count(1)


def test_a_test_on_an_empty_key_row_asks_for_the_key(page: Page, panel):
    _tab(panel, "Keys")
    row = panel.locator(".settings-field", has=page.locator("#key-runware"))
    row.get_by_role("button", name="Test").click()
    expect(row).to_contain_text("Add a Runware key first.")


def test_search_finds_a_field_on_another_tab(page: Page, panel):
    panel.get_by_label("Search settings").fill("reserve per still")
    expect(panel.get_by_label("Reserve per still")).to_be_visible()
    expect(panel.get_by_label("Writer model")).to_have_count(0)


def test_a_cache_clear_asks_first_then_removes_only_that_folder(page: Page, panel, studio):
    chunk = studio.root / "work/remotion-chunks/one.mp4"
    chunk.parent.mkdir(parents=True)
    chunk.write_bytes(b"x" * 2048)
    kept = studio.root / "work/tasks.json"
    before = kept.read_bytes()
    _tab(panel, "This computer")
    row = panel.locator(".settings-field", has_text="Finished render chunks")
    row.get_by_role("button", name="Clear", exact=True).click()
    assert chunk.exists()
    row.get_by_role("button", name="Clear 2 KB").click()
    expect(row).to_contain_text("Cleared 2 KB")
    assert not chunk.exists()
    assert kept.read_bytes() == before


def test_the_tab_rail_fits_a_phone(page: Page, panel):
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    box = panel.get_by_label("Writer model").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390
