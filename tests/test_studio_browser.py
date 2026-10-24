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
def studio_page(tmp_path, browser, request):
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
    if getattr(request, "param", False):
        httpd.action_token = "browser-human-capability"
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    base = url.split("?")[0]
    app = base + "app?token=browser-test"
    yield page, app, root, second, db, audio
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


def choose_audio(page, audio):
    page.locator("#sourceFile").set_input_files(str(audio))
    page.wait_for_function("() => selectedSource && selectedSource.path")


def test_routes_reload_back_forward_and_keyboard_tabs(studio_page):
    page, app, *_ = studio_page
    select_project(page, app, tab="track")
    card = page.locator('#list a[data-slug="production"]')
    assert card.get_attribute("aria-current") == "page"
    page.locator("#tab-track").focus()
    page.keyboard.press("ArrowRight")
    page.wait_for_url("**#/production/story")
    playwright.expect(page.locator("#tab-story")).to_have_attribute("aria-selected", "true")
    page.reload()
    page.wait_for_selector("#view h2 >> text=Story & storyboard")
    assert page.locator("#tab-story").get_attribute("aria-selected") == "true"
    page.go_back()
    page.wait_for_function("() => location.hash.endsWith('/track')")
    page.go_forward()
    page.wait_for_function("() => location.hash.endsWith('/story')")
    page.locator('#list a[data-slug="second"]').focus()
    page.keyboard.press("Enter")
    page.wait_for_url("**#/second/story")
    playwright.expect(page.locator("#projectEyebrow")).to_contain_text("second")


def test_verified_card_and_project_history_agree_and_notes_are_visible(studio_page):
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
    page.wait_for_selector("#view h2 >> text=Style check")
    assert page.locator("#tab-style").get_attribute("data-state") == "stale"
    page.locator("#tab-project").click()
    page.wait_for_selector("#view h2 >> text=Project details")
    page.get_by_text("Decision history", exact=True).click()
    assert "Human rationale stays visible" in page.locator("#view").inner_text()


def test_thumbnails_and_board_inspection_use_the_served_project_identity(studio_page):
    page, app, *_ = studio_page
    select_project(page, app, tab="images")
    page.wait_for_function("() => document.querySelector('.still img').naturalWidth > 0")
    assert "/production/thumb/" in page.locator(".still img").first.get_attribute("src")
    page.locator("#tab-story").click()
    page.wait_for_selector("#view h2 >> text=Story & storyboard")
    page.get_by_text("Review all 4 shots", exact=True).click()
    page.get_by_role("button", name="Inspect shot s001", exact=True).click()
    page.wait_for_selector("#shotPanel >> text=Contract")
    assert page.locator("#tab-story").get_attribute("aria-selected") == "true"
    assert "Beat 0" in page.locator("#shotPanel").inner_text()


def test_create_opens_returned_project_without_reload(studio_page):
    page, app, root, _second, _db, audio = studio_page
    page.goto(app)
    page.locator("#newProduction").click()
    assert page.locator("#sourceFile").is_visible()
    assert page.locator("#src").count() == 0
    choose_audio(page, audio)
    assert page.locator("#cap").input_value() == ""
    page.locator("#setupNext").click()
    page.locator("#title").fill("Café — Browser Test!")
    page.locator("#setupNext").click()
    page.locator("#cap").fill("1.00")
    page.evaluate("window.testNoReload = 'present'")
    with page.expect_response(lambda r: "/api/create" in r.url) as response:
        page.locator("#create").click()
    assert response.value.status == 201, response.value.text()
    page.wait_for_url("**#/cafe-browser-test/**")
    page.wait_for_selector("#view h2 >> text=Story & storyboard")
    assert page.evaluate("window.testNoReload") == "present"
    assert "Café — Browser Test!" in page.locator("#detailTitle").inner_text()
    assert (
        read_json(root.parent / "cafe-browser-test/work/production-budget.json")["cap_usd"]
        == "1.00"
    )
    # The browser copy is temporary; the project keeps its own media/song.mp3.
    assert list((root.parent.parent / "studio/uploads").glob("*.mp3")) == []


def test_failed_copy_is_honest_and_command_stays_selectable(studio_page):
    page, app, *_ = studio_page
    select_project(page, app, tab="project")
    page.wait_for_selector("#view h2 >> text=Project details")
    page.evaluate(
        "Object.defineProperty(navigator, 'clipboard', {value: {writeText: async () => {throw new Error('denied')}}})"
    )
    page.get_by_text("Technical commands & local artifacts", exact=True).click()
    page.get_by_role("button", name="Copy command").first.click()
    page.wait_for_selector("text=Copy unavailable")
    assert "Copied" not in page.locator("#view").inner_text()
    assert page.locator("#view pre[tabindex='0']").count() > 0


def test_live_activity_marks_snapshot_dirty_outside_runs(studio_page):
    page, app, root, _second, db, *_ = studio_page
    select_project(page, app, tab="story")
    page.wait_for_function("() => activitySource && activitySource.readyState === 1")
    with spine.connect(db) as conn:
        spine.start_run(conn, intent="background local work", production=root.name)
    page.wait_for_selector("text=Studio activity detected")
    assert page.locator("#tab-story").get_attribute("aria-selected") == "true"
    assert page.locator("#view .callout").count() > 0


def test_auth_error_has_human_recovery_and_api_stays_json(studio_page):
    page, app, *_ = studio_page
    response = page.goto(app.split("?")[0])
    assert response.status == 401
    assert "Your Studio link needs a token" in page.locator("h1").inner_text()
    assert "uv run clip serve" in page.locator("main").inner_text()
    api = page.request.get(app.split("app?")[0] + "api/status")
    assert api.status == 401
    assert json.loads(api.text())["error"] == "token required"


def test_new_production_browses_for_a_file_without_preloading_songs(studio_page):
    page, app, _root, _second, _db, audio = studio_page
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(app)
    page.locator("#newProduction").click()
    assert page.locator("#sourceFile").is_visible()
    assert page.locator("#src").count() == 0
    assert page.locator("#sourceSearch").count() == 0
    assert page.locator("#setupNext").is_disabled()
    assert not any("/api/sources" in url for url in requests)

    page.locator("#sourceFile").set_input_files(
        [{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"not audio"}]
    )
    page.wait_for_selector("#sourceStatus >> text=Choose an MP3")
    assert page.locator("#setupNext").is_disabled()
    assert not any("/api/source?" in url for url in requests)

    page.locator("#sourceFile").set_input_files(str(audio))
    page.wait_for_function("() => selectedSource && selectedSource.path")
    assert page.locator("#setupNext").is_enabled()
    assert "track" in page.locator("#sourceStatus").inner_text()
    assert any("/api/source?name=track.mp3" in url for url in requests)
    assert not any("/api/sources" in url for url in requests)


def test_run_event_failure_has_a_working_retry(studio_page):
    page, app, root, _second, db, *_ = studio_page
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


def open_human_session(page, app):
    # A changed query forces a document load even when the test is already deep in
    # a project, so the action fragment is processed exactly once.
    page.goto(app + "&human-session=1#action=browser-human-capability")
    page.wait_for_selector("#humanStatus >> text=Human action session enabled")
    assert "action=" not in page.url
    page.locator('#list a[data-slug="production"]').click()
    page.wait_for_selector("#tabs:not([hidden])")
    page.locator("#tab-project").click()
    page.wait_for_selector("#view h2 >> text=Project details")
    page.get_by_role("button", name="Open advanced decision form").click()
    page.wait_for_selector("#humanApproval")


def open_quotes(page):
    page.locator("#tab-project").click()
    page.wait_for_selector("#view h2 >> text=Project details")
    page.get_by_role("button", name="Budget & quotes").click()
    page.wait_for_selector("#view >> text=Exact authority")


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_human_stage_confirmation_and_capability_bootstrap(studio_page):
    page, app, root, *_ = studio_page
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    open_human_session(page, app)
    page.locator("#approvalStage").select_option("analysis")
    page.get_by_role("button", name="Load current artifact").click()
    form = page.locator("#humanApproval form")
    form.locator("textarea").fill("A deliberate browser decision")
    form.locator('input[type="checkbox"]').first.check()
    form.get_by_role("button", name="Approve Music analysis", exact=True).click()
    page.wait_for_selector("#humanStatus >> text=Approved analysis for production")
    decision = read_json(root / "work/approvals.json")["analysis"]
    assert decision["note"] == "A deliberate browser decision"
    assert decision["via"] == "studio"
    assert not any("browser-human-capability" in url for url in requests)
    assert read_json(root / "work/tasks.json") == {}


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_human_stale_stage_refuses_and_requires_review_again(studio_page):
    page, app, root, *_ = studio_page
    open_human_session(page, app)
    page.locator("#approvalStage").select_option("analysis")
    page.get_by_role("button", name="Load current artifact").click()
    form = page.locator("#humanApproval form")
    form.locator("textarea").fill("Old snapshot must not approve")
    form.locator('input[type="checkbox"]').first.check()
    before = (root / "work/approvals.json").read_bytes()
    write_json(root / "work/music.json", {"duration": 2, "beats": [0.123]})
    form.get_by_role("button", name="Approve Music analysis", exact=True).click()
    page.wait_for_selector("#humanApproval >> text=Stage changed")
    assert form.get_by_role("button", name="Approve Music analysis", exact=True).is_disabled()
    assert (root / "work/approvals.json").read_bytes() == before


@pytest.mark.parametrize("studio_page", [True], indirect=True)
@pytest.mark.parametrize("amount", ["0.10", "0.0006"])
def test_human_quote_authorizes_exact_scope_without_execution(studio_page, amount):
    from test_studio_actions import quote

    from mp3_to_videoclip import budget

    page, app, root, *_ = studio_page
    budget.set_budget(root, "1.00", "test only")
    q = quote(root, reserve_total_usd=amount)
    open_human_session(page, app)
    open_quotes(page)
    page.wait_for_selector("#view >> text=Exact authority")
    page.locator("#view textarea").fill("Exactly this quote, no automatic generation")
    page.locator('#view input[type="checkbox"]').check()
    assert f"Exact authority: {amount} USD" in page.locator("#view").inner_text()
    page.get_by_role("button", name=f"Authorize {amount} USD", exact=True).click()
    page.wait_for_selector("text=Nothing was generated, uploaded or spent")
    auth = read_json(root / "work/authorizations.json")[q["id"]]
    assert auth["cap_usd"] == amount and auth["via"] == "studio"
    assert auth["review_confirmed"] is True
    assert read_json(root / "work/tasks.json") == {}


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_blocked_browser_storage_does_not_break_review_or_in_memory_session(studio_page):
    page, app, root, *_ = studio_page
    page.add_init_script(
        "Object.defineProperty(window, 'sessionStorage', {get(){throw new DOMException('blocked','SecurityError')}})"
    )
    open_human_session(page, app)
    assert "Storage is blocked" in page.locator("#humanStatus").inner_text()
    assert page.locator("#humanApproval").is_visible()
    page.locator("#approvalStage").select_option("analysis")
    page.get_by_role("button", name="Load current artifact").click()
    form = page.locator("#humanApproval form")
    form.locator("textarea").fill("Ephemeral test-session decision")
    form.locator('input[type="checkbox"]').first.check()
    form.get_by_role("button", name="Approve Music analysis", exact=True).click()
    page.wait_for_selector("#humanStatus >> text=Approved analysis for production")
    assert read_json(root / "work/approvals.json")["analysis"]["via"] == "studio"
    page.wait_for_url("**#/production/approvals")
    page.wait_for_selector("#view table")
    page.reload()
    page.wait_for_selector("#view table")
    assert page.locator("#humanApproval").count() == 0
    page.wait_for_selector("#humanStatus >> text=Read-only session")


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_failed_history_cleanup_discards_capability_and_clears_fragment(studio_page):
    page, app, *_ = studio_page
    page.add_init_script(
        "history.replaceState = () => {throw new DOMException('blocked','SecurityError')}"
    )
    page.goto(app + "#action=browser-human-capability")
    page.wait_for_url(app)
    page.wait_for_selector("#humanStatus >> text=Read-only session")
    assert "action=" not in page.url
    assert page.evaluate("actionCapability") == ""


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_quote_upload_confirmation_and_stale_conflict_are_visible(studio_page):
    from test_studio_actions import quote

    from mp3_to_videoclip import budget

    page, app, root, *_ = studio_page
    budget.set_budget(root, "1.00", "test")
    q = quote(root, kind="transcription", tasks=[], source_hash="a" * 64)
    open_human_session(page, app)
    open_quotes(page)
    page.locator("#view textarea").fill("Review old quote but no transfer yet")
    boxes = page.locator('#view input[type="checkbox"]')
    boxes.nth(0).check()
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    button = page.get_by_role("button", name="Authorize 0.10 USD", exact=True)
    button.click()
    assert boxes.nth(1).evaluate("box => box.validity.valueMissing")
    assert page.locator("#view form").evaluate("form => !form.checkValidity()")
    assert posts == []
    assert not (root / "work/authorizations.json").exists()
    boxes.nth(1).check()
    q["reserve_total_usd"] = "0.20"
    write_json(root / f"work/quotes/{q['id']}.json", q)
    button.click()
    page.wait_for_selector("#view >> text=Quote changed")
    assert button.is_disabled()
    assert not (root / "work/authorizations.json").exists()


@pytest.mark.parametrize("width", [390, 900, 1280])
def test_five_step_workspace_stays_above_the_fold_and_has_one_project_menu(studio_page, width):
    page, app, *_ = studio_page
    page.set_viewport_size({"width": width, "height": 900})
    select_project(page, app, tab="story")
    assert page.locator(".workflow-tabs .step").count() == 5
    assert page.locator("#tab-project").is_visible()
    assert "Overview" not in page.locator(".utility-tabs").inner_text()
    assert "Decisions" not in page.locator(".utility-tabs").inner_text()
    assert "Activity" not in page.locator(".utility-tabs").inner_text()
    assert "Story & storyboard" in page.locator("#view h2").inner_text()
    assert page.locator("#view .callout").count() >= 1
    assert page.locator("#detailTitle").bounding_box()["y"] < 450
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if width <= 1000:
        assert page.locator("aside").is_hidden()
        page.locator("#projectSwitch").select_option("second")
        page.wait_for_url("**#/second/story")
        playwright.expect(page.locator("#projectEyebrow")).to_contain_text("second")


def test_library_search_keeps_the_current_step_visible(studio_page):
    page, app, *_ = studio_page
    select_project(page, app, tab="story")
    assert page.locator("#list .tag").count() == 0
    page.locator("#projectSearch").fill("second")
    assert page.locator("#list .card").count() == 1
    page.locator("#list .card").click()
    page.wait_for_url("**#/second/story")
    page.locator("#projectSearch").fill("no-such-production")
    assert "No productions match" in page.locator("#list").inner_text()
    assert "Story & storyboard" in page.locator("#view h2").inner_text()


def test_track_and_story_are_readable_without_human_actions_or_writes(studio_page):
    page, app, root, *_ = studio_page
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    writes = []
    page.on("request", lambda r: writes.append(r.url) if r.method == "POST" else None)
    select_project(page, app, tab="track")
    assert "Measurements are estimates" in page.locator("#view").inner_text()
    assert "Reviewed line" in page.locator("#view").inner_text()
    assert not page.locator("#view .technical").first.get_attribute("open")
    page.locator("#tab-story").click()
    page.wait_for_selector("#view h3 >> text=Concept")
    assert "TREATMENT-SECRET" in page.locator("#view").inner_text()
    assert "LOOK: muted teal" in page.locator("#styleText").input_value()
    assert page.locator("#view pre:visible").count() == 0
    assert writes == []
    assert {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_workflow_route_failure_has_retry_and_late_response_cannot_replace_view(studio_page):
    page, app, *_ = studio_page
    page.route(
        "**/api/project/production/workflow?*",
        lambda route: route.fulfill(status=500, json={"error": "Review evidence unavailable"}),
    )
    page.goto(app + "#/production/story")
    page.wait_for_selector("#view [role=alert]")
    assert "Review evidence unavailable" in page.locator("#view").inner_text()
    page.unroute("**/api/project/production/workflow?*")
    page.get_by_role("button", name="Try again", exact=True).click()
    page.wait_for_selector("#view h3 >> text=Concept")
    pending = []

    def hold_first(route):
        if not pending:
            pending.append(route)
        else:
            route.continue_()

    page.route("**/api/project/production/workflow?*", hold_first)
    page.expose_function("heldWorkflowCount", lambda: len(pending))
    with page.expect_request("**/api/project/production/workflow?*"):
        page.locator("#tab-track").click()
    page.wait_for_function("async () => (await window.heldWorkflowCount()) === 1")
    page.locator("#tab-story").click()
    page.wait_for_selector("#view h2 >> text=Story & storyboard")
    try:
        pending[0].fulfill(
            json={"artifacts": {}, "music_mode": "vocal", "feedback": [], "flow": {}}
        )
    except Exception:
        pass
    page.wait_for_timeout(300)
    assert page.locator("#tab-story").get_attribute("aria-selected") == "true"
    assert "Story & storyboard" in page.locator("#view h2").inner_text()


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_style_and_images_expose_per_shot_human_review(studio_page):

    page, app, root, *_ = studio_page
    open_human_session(page, app)
    page.locator("#tab-style").click()
    page.wait_for_selector("#view h2 >> text=Style check")
    page.wait_for_selector(".still-cell")
    assert page.locator(".still-cell").count() == 3
    assert page.locator(".still-actions").first.is_visible()
    page.locator(".still-actions").first.get_by_role("button", name="Approve", exact=True).click()
    page.wait_for_selector(".still-actions >> text=Approved")
    reviews = read_json(root / "work/reviews.json")
    assert any(r["verdict"] == "accept" and r["reviewer"] == "studio" for r in reviews)
    page.locator("#tab-images").click()
    page.wait_for_selector("#view h2 >> text=Images")
    page.wait_for_selector(".still-cell")
    assert page.locator(".still-cell").count() == 4
    assert "Pacing preview" in page.locator("#view").inner_text()
    assert "review progress" in page.locator("#view").inner_text().lower()
    assert page.locator(".still-actions").first.is_visible()


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_story_feedback_request_and_composite_approval_are_separate_actions(studio_page):
    from mp3_to_videoclip import flow

    page, app, _root, second, _db, *_ = studio_page
    flow.mark(second)
    open_human_session(page, app)
    page.goto(app + "#/second/story")
    page.wait_for_selector("#view h2 >> text=Story & storyboard")
    feedback_form = page.locator("form", has=page.get_by_role("button", name="Request revision"))
    feedback_form.locator("textarea").first.fill("Make the middle section quieter.")
    feedback_form.locator('input[type="checkbox"]').check()
    feedback_form.get_by_role("button", name="Request revision").click()
    page.wait_for_selector("#view >> text=Saved. Your agent")
    assert (
        read_json(second / "work/feedback.json")[0]["message"] == "Make the middle section quieter."
    )

    approval = page.locator(
        "form", has=page.get_by_role("button", name="Approve story & storyboard")
    )
    approval.locator("textarea").fill("I agree to this story and board")
    approval.locator('input[type="checkbox"]').check()
    approval.get_by_role("button", name="Approve story & storyboard").click()
    page.wait_for_selector("#view h2 >> text=Style check")
    approvals = read_json(second / "work/approvals.json")
    assert approvals["brief"]["via"] == "studio"
    assert approvals["storyboard"]["via"] == "studio"
    assert read_json(second / "work/tasks.json") == {}


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_finish_credits_are_editable_only_for_guided_projects(studio_page):
    from mp3_to_videoclip import flow, signature

    page, app, root, second, _db, *_ = studio_page
    select_project(page, app, tab="finish")
    assert "predates guided credits" in page.locator("#view").inner_text()
    assert page.locator(".credit-row").count() == 0

    flow.mark(second)
    spec = signature.draft_spec("Creative")
    spec["renderer"] = "remotion"
    write_json(second / "work/graphics-spec.json", spec)
    open_human_session(page, app)
    page.goto(app + "#/second/finish")
    page.wait_for_selector("#view h2 >> text=Finish")
    page.wait_for_selector(".credit-row")
    row = page.locator(".credit-row").first
    inputs = row.locator("input")
    inputs.nth(0).fill("Director")
    inputs.nth(1).fill("A Person")
    form = page.locator("form", has=page.get_by_role("button", name="Save credits"))
    form.locator("textarea").fill("Confirmed factual roles for this film")
    form.locator('input[type="checkbox"]').nth(0).check()
    form.get_by_role("button", name="Save credits").click()
    page.wait_for_selector("#view >> text=Credits saved")
    saved = read_json(second / "work/graphics-spec.json")
    assert saved["credit_roles_confirmed"] is True
    assert saved["credits"]["cards"] == [["Director", "A Person"]]


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_canonical_music_and_character_fields_are_readable_in_decision_evidence(studio_page):
    page, app, root, *_ = studio_page
    music = read_json(root / "work/music.json")
    music["estimated_tempo_bpm"] = 123.45
    write_json(root / "work/music.json", music)
    brief = read_json(root / "brief.json")
    brief["characters"] = [
        {
            "id": "lead",
            "identity": "Unique test identity",
            "permission_confirmed": True,
            "default_state": "night",
            "states": {
                "night": {
                    "description": "Night wardrobe",
                    "attributes": {"coat": "Crimson test coat"},
                }
            },
        }
    ]
    write_json(root / "brief.json", brief)
    open_human_session(page, app)
    page.locator("#tab-track").click()
    page.wait_for_selector("#view dt >> text=Tempo estimate")
    assert "123.45" in page.locator("#view").inner_text()
    page.locator("#tab-story").click()
    page.wait_for_selector("#view h3 >> text=Concept")
    page.locator("summary", has_text="Visual arc, scenes and characters").click()
    page.wait_for_selector("#view h3 >> text=Characters")
    for text in ("Unique test identity", "Night wardrobe", "Crimson test coat"):
        assert text in page.locator("#view").inner_text()
    page.locator("#tab-project").click()
    page.wait_for_selector("#view h2 >> text=Project details")
    page.get_by_role("button", name="Open advanced decision form").click()
    page.wait_for_selector("#humanApproval")
    page.locator("#approvalStage").select_option("brief")
    page.get_by_role("button", name="Load current artifact", exact=True).click()
    page.wait_for_selector("#humanApproval h3 >> text=Characters")
    assert "Crimson test coat" in page.locator("#humanApproval").inner_text()
    page.locator("#approvalStage").select_option("analysis")
    page.get_by_role("button", name="Load current artifact", exact=True).click()
    page.wait_for_selector("#humanApproval dt >> text=Tempo estimate")
    assert "123.45" in page.locator("#humanApproval").inner_text()
    assert page.locator("#humanApproval pre:visible").count() == 0


@pytest.mark.parametrize("studio_page", [True], indirect=True)
def test_preview_playback_and_confirmation_target_the_bound_movie_not_the_newest(studio_page):
    import os

    from test_creative_production import write_preview_report

    page, app, root, *_ = studio_page
    report = write_preview_report(root, "previews/review-bound-v001.mp4")
    latest = root / "previews/newer-unbound-v002.mp4"
    latest.write_bytes(b"unbound available-set preview")
    newer = (root / report["movie"]).stat().st_mtime + 10
    os.utime(latest, (newer, newer))
    open_human_session(page, app)
    page.locator("#tab-images").click()
    page.wait_for_selector("#previewTarget")
    assert page.locator("#previewTarget").inner_text() == report["movie"]
    assert "newer-unbound-v002.mp4 · not the approval target" in page.locator("#view").inner_text()
    page.locator("#tab-project").click()
    page.wait_for_selector("#view h2 >> text=Project details")
    page.get_by_role("button", name="Open advanced decision form").click()
    page.wait_for_selector("#humanApproval")
    page.locator("#approvalStage").select_option("preview")
    page.get_by_role("button", name="Load current artifact", exact=True).click()
    page.wait_for_selector("#humanApproval form")
    confirmation = page.locator("#humanApproval .confirmation")
    assert report["movie"] in confirmation.inner_text()
    assert "newer-unbound" not in confirmation.inner_text()
    (root / report["movie"]).unlink()
    page.locator("#tab-images").click()
    page.wait_for_selector("#previewTarget")
    assert "This recorded movie is missing" in page.locator("#view").inner_text()
    assert "review binding cannot pass" in page.locator("#view").inner_text()


def test_setup_dialog_validates_steps_preserves_back_navigation_and_escape(studio_page):
    page, app, _root, _second, _db, audio = studio_page
    page.goto(app)
    page.locator("#newProduction").click()
    assert page.locator("#createDialog").is_visible()
    assert page.locator("#setupNext").is_disabled()
    choose_audio(page, audio)
    page.locator("#setupNext").click()
    playwright.expect(page.locator("#title")).to_be_focused()
    page.locator("#setupNext").click()
    assert page.locator("#title").evaluate("e => e.validity.valueMissing")
    page.locator("#title").fill("Draft title")
    page.locator("#aspect").select_option("9:16")
    assert "landscape-only" in page.locator("#aspectHelp").inner_text()
    page.locator("#setupNext").click()
    assert "Draft title" in page.locator("#setupSummary").inner_text()
    assert page.locator("#cap").input_value() == ""
    page.locator("#create").click()
    assert page.locator("#cap").evaluate("e => e.validity.valueMissing")
    page.locator("#setupBack").click()
    assert page.locator("#title").input_value() == "Draft title"
    page.keyboard.press("Escape")
    assert page.locator("#createDialog").is_hidden()
    playwright.expect(page.locator("#newProduction")).to_be_focused()


def test_setup_single_flight_and_failed_submit_offer_honest_recovery(studio_page):
    page, app, _root, _second, _db, audio = studio_page
    page.goto(app)
    page.locator("#newProduction").click()
    choose_audio(page, audio)
    page.locator("#setupNext").click()
    page.locator("#title").fill("Network test")
    page.locator("#setupNext").click()
    page.locator("#cap").fill("1.00")
    pending = []
    page.route("**/api/create?*", lambda route: pending.append(route))
    with page.expect_request("**/api/create?*"):
        page.locator("#create").click()
    assert page.locator("#create").is_disabled()
    page.evaluate(
        "document.querySelector('#createForm').dispatchEvent(new Event('submit',{cancelable:true}))"
    )
    assert len(pending) == 1
    pending[0].fulfill(status=500, json={"error": "Temporary setup error"})
    page.wait_for_selector("#msg >> text=Creation could not be confirmed")
    assert "Refresh the library before retrying" in page.locator("#msg").inner_text()
    assert page.locator("#title").input_value() == "Network test"
