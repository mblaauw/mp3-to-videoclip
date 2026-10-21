"""Real browser regressions; run with `uv run --with playwright pytest`.

The normal unit suite skips these when Playwright is absent. CI installs its
Chromium explicitly and runs this file separately. All projects are temporary;
no source media, existing production or provider is contacted.
"""

import json
import subprocess
from pathlib import Path

import pytest
from test_creative_production import approve_through_proof, make_root, record_stills

from mp3_to_videoclip import serve, spine, studio
from mp3_to_videoclip.storage import read_json, write_json

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as instance:
        chromium = instance.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def studio_page(tmp_path, browser):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    approve_through_proof(root)
    record_stills(root, ["s001", "s002"])
    second = make_root(projects, name="second")
    sources = tmp_path / "sources"
    sources.mkdir()
    audio = sources / "track.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=2", str(audio)],
        check=True,
    )
    write_json(
        sources / "track.json",
        {"title": "Test source", "isLiked": True, "metadata": {"duration": 2}},
    )
    db = tmp_path / "journal.sqlite3"
    httpd, url, thread = serve.start_in_thread(projects, db, token="browser-test")
    httpd.sources_dir = sources
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    base = url.split("?")[0]
    app = base + "app?token=browser-test"
    yield page, app, root, second, db
    page.unroute_all(behavior="ignoreErrors")
    page.close()
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)
    assert not errors, errors


def select_project(page, app, slug="production", tab="overview"):
    page.goto(app + f"#/{slug}/{tab}")
    page.wait_for_function(
        "() => document.querySelector('#view').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator("#view .empty[role=alert]").count() == 0


def test_routes_reload_back_forward_and_keyboard_tabs(studio_page):
    page, app, *_ = studio_page
    select_project(page, app)
    card = page.locator('#list a[data-slug="production"]')
    assert card.get_attribute("aria-current") == "page"
    page.locator("#tab-overview").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**#/production/stills")
    playwright.expect(page.locator("#tab-stills")).to_have_attribute("aria-selected", "true")
    page.reload()
    page.wait_for_selector(".still")
    assert page.locator("#tab-stills").get_attribute("aria-selected") == "true"
    page.go_back()
    page.wait_for_function("() => location.hash.endsWith('/overview')")
    page.go_forward()
    page.wait_for_function("() => location.hash.endsWith('/stills')")
    page.locator('#list a[data-slug="second"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_url("**#/second/overview")
    playwright.expect(page.locator("#detailTitle")).to_contain_text("second")


def test_verified_card_and_overview_agree_and_notes_are_visible(studio_page):
    page, app, root, *_ = studio_page
    # A deliberately stale proof must not stay green on the library card.
    approvals = read_json(root / "work/approvals.json")
    approvals["proof"]["hash"] = "old-hash"
    approvals["proof"]["note"] = "Human rationale stays visible"
    write_json(root / "work/approvals.json", approvals)
    page.goto(app)
    page.wait_for_selector("#list .card")
    card = page.locator('#list a[data-slug="production"]')
    assert "not checked" in card.inner_text()
    card.click()
    page.wait_for_selector("#view .decision")
    assert "Three-shot proof: stale" in card.inner_text()
    assert "Three-shot proof: stale" in page.locator("#view").inner_text()
    assert "Approve proof" in page.locator("#view").inner_text()
    page.locator("#tab-approvals").click()
    page.wait_for_selector("#view table")
    assert "Human rationale stays visible" in page.locator("#view").inner_text()
    assert page.locator("#view summary", has_text="Command and hashes").count() == 8


def test_thumbnails_and_board_inspection_use_the_served_project_identity(studio_page):
    page, app, *_ = studio_page
    select_project(page, app, tab="stills")
    page.wait_for_function("() => document.querySelector('.still img').naturalWidth > 0")
    assert "/production/thumb/" in page.locator(".still img").first.get_attribute("src")
    page.locator("#tab-board").click()
    page.get_by_role("button", name="Inspect shot s001", exact=True).click()
    page.wait_for_selector("#shotPanel >> text=Contract")
    assert page.locator("#tab-stills").get_attribute("aria-selected") == "true"
    assert "Beat 0" in page.locator("#shotPanel").inner_text()


def test_create_opens_returned_project_without_reload(studio_page):
    page, app, root, *_ = studio_page
    page.goto(app)
    page.locator("#newProduction summary").click()
    page.wait_for_function("() => document.querySelector('#src').options.length > 1")
    assert page.locator("#src option").nth(1).get_attribute("value") == "0"
    assert page.locator("#cap").input_value() == ""
    page.locator("#src").select_option("0")
    page.locator("#title").fill("Café — Browser Test!")
    page.locator("#cap").fill("1.00")
    page.evaluate("window.testNoReload = 'present'")
    with page.expect_response(lambda r: "/api/create" in r.url) as response:
        page.locator("#create").click()
    assert response.value.status == 201, response.value.text()
    page.wait_for_url("**#/cafe-browser-test/overview")
    page.wait_for_selector("#view .decision")
    assert page.evaluate("window.testNoReload") == "present"
    assert "Café — Browser Test!" in page.locator("#detailTitle").inner_text()
    assert (
        read_json(root.parent / "cafe-browser-test/work/production-budget.json")["cap_usd"]
        == "1.00"
    )


def test_failed_copy_is_honest_and_command_stays_selectable(studio_page):
    page, app, *_ = studio_page
    select_project(page, app)
    page.evaluate(
        "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async () => {throw new Error('denied')}}})"
    )
    page.get_by_role("button", name="Copy command").first.click()
    page.wait_for_selector("text=Copy unavailable")
    assert "Copied" not in page.locator("#view").inner_text()
    assert page.locator("#view pre[tabindex='0']").count() > 0


def test_live_activity_marks_snapshot_dirty_outside_runs(studio_page):
    page, app, root, _second, db = studio_page
    select_project(page, app)
    page.wait_for_function("() => activitySource && activitySource.readyState === 1")
    with spine.connect(db) as conn:
        spine.start_run(conn, intent="background local work", production=root.name)
    page.wait_for_selector("text=Studio activity detected")
    assert page.locator("#tab-overview").get_attribute("aria-selected") == "true"
    assert page.locator("#view .decision").count() > 0


@pytest.mark.parametrize("width", [390, 900, 1280])
def test_responsive_layout_and_targets(studio_page, width):
    page, app, *_ = studio_page
    page.set_viewport_size({"width": width, "height": 900})
    select_project(page, app)
    facts = page.evaluate(
        """() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          title: parseFloat(getComputedStyle(document.querySelector('#detailTitle')).fontSize),
          inputs: [...document.querySelectorAll('input,select')].every(e => parseFloat(getComputedStyle(e).fontSize) >= 16),
          tabs: [...document.querySelectorAll('.tab')].every(e => e.getBoundingClientRect().height >= 24),
          landmarks: !!document.querySelector('main') && !!document.querySelector('nav'),
        })"""
    )
    assert facts == {
        "overflow": False,
        "title": 22,
        "inputs": True,
        "tabs": True,
        "landmarks": True,
    }


def test_auth_error_has_human_recovery_and_api_stays_json(studio_page):
    page, app, *_ = studio_page
    response = page.goto(app.split("?")[0])
    assert response.status == 401
    assert "Your Studio link needs a token" in page.locator("h1").inner_text()
    assert "uv run clip serve" in page.locator("main").inner_text()
    api = page.request.get(app.split("app?")[0] + "api/status")
    assert api.status == 401
    assert json.loads(api.text())["error"] == "token required"


def test_source_search_blocks_creation_until_a_new_track_is_chosen(studio_page):
    page, app, *_ = studio_page
    page.goto(app)
    page.locator("#newProduction summary").click()
    page.wait_for_function("() => sourceTracks.length > 0")
    page.locator("#src").select_option("0")
    page.locator("#title").fill("Must not create")
    page.locator("#cap").fill("1.00")
    pending = []
    writes = []
    page.on("request", lambda request: writes.append(request) if request.method == "POST" else None)
    page.route("**/api/sources?q=delayed*", lambda route: pending.append(route))
    with page.expect_request("**/api/sources?q=delayed*"):
        page.locator("#sourceSearch").fill("delayed")
    assert page.locator("#src").is_disabled()
    assert page.locator("#create").is_disabled()
    page.evaluate(
        "document.querySelector('#createForm').dispatchEvent(new Event('submit', {cancelable:true}))"
    )
    assert writes == []
    pending[0].fulfill(json={"tracks": []})
    page.wait_for_function("() => !document.querySelector('#src').disabled")
    assert page.locator("#src").input_value() == ""
    assert page.locator("#create").is_disabled()


def test_run_event_failure_has_a_working_retry(studio_page):
    page, app, root, _second, db = studio_page
    with spine.connect(db) as conn:
        spine.start_run(conn, intent="show events", production=root.name)
    page.route(
        "**/api/events?*",
        lambda route: route.fulfill(status=500, json={"error": "Events unavailable"}),
    )
    page.goto(app + "#/production/runs")
    page.wait_for_selector("#log >> text=Events unavailable")
    page.unroute("**/api/events?*")
    page.locator("#log").get_by_role("button", name="Try again").click()
    page.wait_for_selector("#log >> text=run.started")


def test_malformed_route_cancels_a_pending_snapshot(studio_page):
    page, app, *_ = studio_page
    payload = page.request.get(
        app.split("app?")[0] + "api/project/production?token=browser-test"
    ).json()
    pending = []
    page.route("**/api/project/production?token=*", lambda route: pending.append(route))
    page.goto(app + "#/production/overview")
    page.wait_for_selector("text=Checking current project state")
    page.evaluate("location.hash = '#/%invalid/overview'")
    page.wait_for_selector("text=Invalid project link. Choose")
    with page.expect_response("**/api/project/production?token=*"):
        pending[0].fulfill(json=payload)
    playwright.expect(page.locator("#view")).to_contain_text("Invalid project link")
    assert page.locator("#view .decision").count() == 0


def test_static_studio_copy_failure_reveals_command(studio_page):
    page, _app, root, *_ = studio_page
    result = studio.build_studio(root.parent)
    page.goto(Path(result["page"]).as_uri())
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
    button = page.locator("[data-copy]").first
    target = button.get_attribute("data-copy")
    button.click()
    playwright.expect(button).to_contain_text("Copy unavailable")
    assert page.locator("#" + target).is_visible()


@pytest.mark.parametrize("width", [390, 1280])
def test_long_approval_notes_do_not_hide_other_fields(studio_page, width):
    page, app, root, *_ = studio_page
    approvals = read_json(root / "work/approvals.json")
    approvals["analysis"]["note"] = "A" * 1000
    write_json(root / "work/approvals.json", approvals)
    page.set_viewport_size({"width": width, "height": 900})
    select_project(page, app, tab="approvals")
    assert page.evaluate(
        "document.querySelector('.approval-table').scrollWidth <= document.querySelector('.scroll').clientWidth"
    )
    assert page.locator('.approval-table tbody td[data-label="Recorded at"]').first.is_visible()
