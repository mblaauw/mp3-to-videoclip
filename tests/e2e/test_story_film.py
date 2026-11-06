"""A story film in a browser: no song, a pasted script, a silent draft and a beat sheet."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

SCRIPT = "\n".join(
    [
        "hook: This is a key. We have never found the door.",
        "world: Our museum keeps what your century left behind.",
        "develop: People carried these every day, and locked each other out.",
        "reveal: Nobody remembers what they were keeping safe.",
        "payoff: We keep it polished anyway.",
    ]
)


def _make(page: Page, studio) -> str:
    made = page.request.post(
        f"{studio.url}/api/projects",
        params={"title": "The Last House Key", "kind": "narrative", "fictional": "true"},
        headers={"Content-Type": "application/json"},
    )
    assert made.ok, made.text()
    return made.json()["slug"]


def test_new_film_offers_a_story_film_with_no_file(page: Page, studio):
    page.goto(f"{studio.url}/#/")
    page.get_by_role("button", name="New film").first.click()
    create = page.get_by_role("button", name="Create film")
    page.get_by_label("Title", exact=True).fill("The Last House Key")
    expect(create).to_be_disabled()
    page.get_by_role("button", name="Story film").click()
    expect(create).to_be_enabled()
    expect(page.get_by_role("complementary", name="At a glance")).to_contain_text("Five beats")
    create.click()
    expect(page.get_by_role("navigation", name="Stages").get_by_text("Script")).to_be_visible()
    expect(page.get_by_role("navigation", name="Stages").get_by_text("Track")).to_have_count(0)


def test_a_pasted_script_shows_its_budgets_and_a_draft_plays(page: Page, studio):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    slug = _make(page, studio)
    page.goto(f"{studio.url}/#/{slug}/script")
    expect(page.get_by_text("8 s estimated").or_(page.get_by_text("of 8 s"))).to_be_visible()
    page.get_by_label("Paste the script").fill(SCRIPT)
    page.get_by_role("button", name="Save these lines").click()
    expect(page.get_by_label("Words of l001")).to_have_value(
        "This is a key. We have never found the door."
    )
    page.get_by_role("button", name="Hear a draft").click()
    audio = page.locator(".script-main audio").first
    expect(audio).to_be_visible()
    expect(page.get_by_text("0 of 5 lines have a voice")).to_be_visible()
    duration = audio.evaluate(
        "el => new Promise(ok => el.readyState ? ok(el.duration) : "
        "el.addEventListener('loadedmetadata', () => ok(el.duration)))"
    )
    assert duration > 10
    audio.evaluate("el => { el.currentTime = 0.5; el.dispatchEvent(new Event('timeupdate')); }")
    expect(page.locator(".script-caption")).to_contain_text("This is a key")
    assert errors == []


def test_an_edited_line_saves_and_moves_the_estimate(page: Page, studio):
    slug = _make(page, studio)
    page.goto(f"{studio.url}/#/{slug}/script")
    page.get_by_label("Paste the script").fill(SCRIPT)
    page.get_by_role("button", name="Save these lines").click()
    words = page.get_by_label("Words of l001")
    expect(words).to_be_visible()
    words.fill("A key.")
    words.blur()
    expect(page.locator(".script-line").first).to_contain_text("0.9 s estimate")
