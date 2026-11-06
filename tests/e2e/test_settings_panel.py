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
    expect(panel.get_by_label("Writer model")).to_have_value("gpt-6-luna")


def test_elevenlabs_voices_appear_only_with_a_key(page: Page, panel):
    _tab(panel, "Voices")
    expect(panel.get_by_label("Default voice")).to_have_value("English_magnetic_voiced_man")
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


@pytest.mark.parametrize("width", [390, 320])
def test_no_field_is_cut_off_on_a_phone(page: Page, panel, width):
    page.set_viewport_size({"width": width, "height": 844})
    for name in (
        "Roles",
        "Voices",
        "Pictures",
        "Keys",
        "New films",
        "This computer",
        "Costs",
    ):
        _tab(panel, name)
        expect(panel.locator(".settings-section").first).to_be_visible()
        widest = page.evaluate(
            """() => Math.max(...[...document.querySelectorAll(
                '.settings-body input, .settings-body select, .settings-body button'
            )].map((item) => item.getBoundingClientRect().right))"""
        )
        assert widest <= width, f"{name} reaches {widest} on a {width} px screen"


def test_the_sounds_tab_names_the_models_with_their_prices(page: Page, panel):
    _tab(panel, "Sounds")
    expect(panel.get_by_label("Music model")).to_have_value("ace-step-v1-5-xl-turbo")
    expect(panel.get_by_label("Effects model")).to_have_value("mirelo-sfx-1-5")
    expect(panel).to_contain_text("$0.0009 per run")
    expect(panel).to_contain_text("$0.00025 per second")
    panel.get_by_label("Music model").select_option("minimax-music-2-6")
    expect(panel.locator(".save-state.saved").first).to_contain_text("Saved")
    expect(panel).to_contain_text("$0.15 per clip")
    panel.get_by_role("button", name="Reset to recommended").click()
    expect(panel.get_by_label("Music model")).to_have_value("ace-step-v1-5-xl-turbo")


def test_a_new_film_starts_where_the_presets_say(page: Page, panel):
    _tab(panel, "New films")
    group = panel.get_by_role("group", name="Presets a new film starts with")
    expect(group.get_by_role("button", name="YouTube (16:9)")).to_have_attribute(
        "aria-pressed", "true"
    )
    group.get_by_role("button", name="YouTube Shorts (9:16)").click()
    expect(group.get_by_role("button", name="YouTube Shorts (9:16)")).to_have_attribute(
        "aria-pressed", "true"
    )
    # The last preset cannot be taken away: a film must go somewhere.
    group.get_by_role("button", name="YouTube (16:9)").click()
    group.get_by_role("button", name="YouTube Shorts (9:16)").click()
    expect(group.get_by_role("button", name="YouTube Shorts (9:16)")).to_have_attribute(
        "aria-pressed", "true"
    )


def test_this_computer_says_where_things_are(page: Page, panel, studio):
    _tab(panel, "This computer")
    expect(panel).to_contain_text("World library")
    expect(panel).to_contain_text("0 entries, 0 series")
    expect(panel).to_contain_text(str(studio.root.parent))
    expect(panel).to_contain_text("settings.toml")
