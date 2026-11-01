"""A whole Director turn in a browser, through the real SDK, to a provider on this computer."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from mp3_to_videoclip import budget, config, services
from mp3_to_videoclip.storage import read_json

pytestmark = [pytest.mark.e2e, pytest.mark.usefixtures("stays_local")]


def _chunk(delta=None, usage=None, finish=None):
    choices = [{"index": 0, "delta": delta, "finish_reason": finish}] if delta is not None else []
    return {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": choices,
        "usage": usage,
    }


class FakeProvider:
    """Answers each chat completion with the next scripted stream, and keeps what it was sent."""

    def __init__(self, *streams):
        self.streams = list(streams)
        self.requests: list[dict] = []
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["content-length"])
                provider.requests.append(json.loads(self.rfile.read(length)))
                body = "".join(f"data: {json.dumps(c)}\n\n" for c in provider.streams.pop(0))
                body += "data: [DONE]\n\n"
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def _use(provider: FakeProvider) -> None:
    config.save_settings(
        config.Settings(
            llm_api_key="fake",
            llm_base_url=provider.url,
            roles={"writer": {"provider": "direct", "model": "local-model"}},
        )
    )


def _ask(page: Page, studio, text: str) -> None:
    page.goto(studio.film("story"))
    composer = page.locator(".director textarea")
    # The rail may open by itself once the page has loaded; a click then would close it.
    try:
        composer.wait_for(state="visible", timeout=3000)
    except PlaywrightTimeoutError:
        page.get_by_role("button", name="Director").first.click()
    composer.fill(text)
    composer.press("Enter")


def test_an_answer_shows_what_it_used_and_the_api_gets_a_clean_request(page: Page, studio):
    provider = FakeProvider(
        [
            _chunk({"content": "Here is a thought."}),
            _chunk(usage={"prompt_tokens": 1932, "completion_tokens": 410, "total_tokens": 2342}),
        ],
        [_chunk({"content": "And another."})],
    )
    _use(provider)
    _ask(page, studio, "What do you think?")
    expect(page.locator(".msg-usage").first).to_contain_text("1,932 in · 410 out · no price known")
    sent = provider.requests[0]
    assert sent["model"] == "local-model"
    assert sent["stream_options"] == {"include_usage": True}
    assert sent["messages"][-1] == {"role": "user", "content": "What do you think?"}
    assert sent["messages"][0]["role"] == "system"
    # A second turn sends the first back with none of the log's own fields, which real APIs refuse.
    composer = page.locator(".director textarea")
    expect(composer).to_be_enabled()
    composer.fill("And now?")
    composer.press("Enter")
    expect(page.locator(".msg-usage").last).to_contain_text("Tokens not reported")
    history = provider.requests[1]["messages"][1:]
    assert history == [
        {"role": "user", "content": "What do you think?"},
        {"role": "assistant", "content": "Here is a thought."},
        {"role": "user", "content": "And now?"},
    ]
    assert studio.root.joinpath("work/model-usage.jsonl").read_text().count("\n") == 2


def test_the_director_prices_stills_and_only_the_owners_click_buys(page: Page, studio, monkeypatch):
    def estimate(*args, **kwargs):
        return {
            "quote_id": "q1",
            "tasks": 3,
            "reserve_usd": "0.15",
            "uploads_required": False,
            "shot_ids": ["s001"],
            "scope": "stills",
            "cap_usd": "5.00",
        }

    monkeypatch.setattr(services.generation, "estimate", estimate)
    budget.set_budget(studio.root, "5.00", "test budget")
    arguments = json.dumps({"slug": studio.root.name, "shot_ids": ["s001"]})
    call = {
        "index": 0,
        "id": "c1",
        "type": "function",
        "function": {"name": "generate_images", "arguments": arguments},
    }
    provider = FakeProvider(
        [_chunk({"tool_calls": [call]})],
        [_chunk({"content": "Priced them for you."})],
    )
    _use(provider)
    bought = []
    page.route(
        "**/images/generate",
        lambda route: (
            bought.append(route.request.post_data_json),
            route.fulfill(json={"job_id": "j1", "tasks": 3}),
        ),
    )
    _ask(page, studio, "Make the stills.")
    button = page.get_by_role("button", name="Buy 3 stills · $0.15")
    expect(button).to_be_visible()
    assert bought == []
    assert read_json(studio.root / "work/tasks.json") == {}
    button.click()
    expect(page.get_by_role("button", name="Started")).to_be_visible()
    assert bought[0]["quote_id"] == "q1"


def test_a_role_with_no_key_says_so_and_nothing_else_answers(page: Page, studio):
    config.save_settings(config.Settings(llm_api_key="go-key", writer_model="openai/gpt-6.1-sol"))
    _ask(page, studio, "Hello?")
    expect(page.locator(".director-error")).to_contain_text("key")
