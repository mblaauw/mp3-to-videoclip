"""The catalogue loads with no network, and a refresh never invents or overwrites a price."""

from __future__ import annotations

import json

import httpx
import pytest

from mp3_to_videoclip import catalog
from mp3_to_videoclip.config import Settings


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    target = tmp_path / "catalog-cache"
    monkeypatch.setenv(catalog.CACHE_ENV, str(target))
    return target


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_network(request):
    raise AssertionError(f"unexpected call to {request.url}")


def test_it_loads_with_no_cache_and_no_network():
    loaded = catalog.load()
    assert {provider.id for provider in loaded.providers} >= {"openai", "runware", "elevenlabs"}
    recommended = {role: m.id for m in loaded.models for role in m.recommended}
    assert recommended == {
        "writer": "gpt-6.1-sol",
        "critic": "gpt-6.1-sol",
        "editor": "deepseek-v4.1-flash",
        "pictures": "google-nano-banana-2-1",
        "upscaler": "real-esrgan",
        "narrator": "minimax-speech-2-8",
    }
    assert next(v for v in loaded.voices if v.recommended).id == "English_Magnetic_Male_2"


def test_every_stated_price_has_a_source_and_a_date():
    for model in catalog.load().models:
        if model.price is not None:
            assert model.price_source.startswith("https://")
            assert model.price_checked


def test_a_refresh_adds_listed_models_without_a_price(cache):
    def handler(request):
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200, json={"data": [{"id": "gpt-6.1-sol"}, {"id": "new-model", "price": "1"}]}
        )

    settings = Settings(llm_api_key="k", llm_base_url="https://example.test/v1")
    report = catalog.refresh("openai", settings, client=_client(handler))
    assert report["added"] == ["new-model"]
    assert report["listed"] == 2
    models = {m.id: m for m in catalog.load().models if m.provider == "openai"}
    assert models["new-model"].source == "listed"
    assert models["new-model"].price is None
    assert models["gpt-6.1-sol"].source == "static"


def test_a_cached_entry_cannot_state_or_overwrite_a_price(cache):
    cache.mkdir()
    (cache / "runware.json").write_text(
        json.dumps(
            {
                "models": [
                    {"id": "minimax-speech-2-8", "price": {"amount": "99", "unit": "1k_chars"}},
                    {"id": "other", "price": {"amount": "99", "unit": "image"}},
                ]
            }
        )
    )
    models = {m.id: m for m in catalog.load().models}
    assert models["minimax-speech-2-8"].price.amount == "0.10"
    assert models["other"].price is None


def test_a_runware_refresh_is_public_and_needs_no_key():
    def handler(request):
        assert "authorization" not in request.headers
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={"info": {"x-status": "live", "x-pricing": {"rates": [{"display": "$1 each"}]}}},
        )

    report = catalog.refresh("runware", Settings(), client=_client(handler))
    assert report["added"] == []
    model = next(m for m in catalog.load().models if m.id == "google-nano-banana-2-1")
    assert (model.status, model.published_price) == ("live", "$1 each")
    assert model.price.amount == "0.034"


def test_a_damaged_cache_only_loses_what_it_added(cache):
    cache.mkdir()
    (cache / "openai.json").write_text("{not json")
    (cache / "gemini.json").write_text(json.dumps({"models": [{"nope": 1}, "x"]}))
    assert {m.id for m in catalog.load().models} == {m.id for m in catalog._static().models}


def test_elevenlabs_is_absent_until_there_is_a_key():
    absent = catalog.public_view(Settings())
    assert "elevenlabs" not in {provider["id"] for provider in absent["providers"]}
    present = catalog.public_view(Settings(keys={"elevenlabs": "x"}))
    assert "elevenlabs" in {provider["id"] for provider in present["providers"]}


def test_elevenlabs_voices_list_with_their_free_preview():
    def handler(request):
        assert request.headers["xi-api-key"] == "x"
        return httpx.Response(
            200,
            json={"voices": [{"voice_id": "v1", "name": "One", "preview_url": "https://p.test/1"}]},
        )

    settings = Settings(keys={"elevenlabs": "x"})
    assert catalog.refresh("elevenlabs", settings, client=_client(handler))["added"] == ["v1"]
    voice = next(v for v in catalog.load().voices if v.id == "v1")
    assert voice.preview_url == "https://p.test/1"


def test_a_test_with_no_key_makes_no_call():
    result = catalog.test_provider("runware", Settings(), client=_client(_no_network))
    assert result["ok"] is False
    assert result["message"] == "Add a Runware key first."


@pytest.mark.parametrize(
    ("provider", "settings", "url", "header"),
    [
        ("opencode-go", {"keys": {"opencode_go": "s3"}}, "/models", "authorization"),
        ("anthropic", {"keys": {"anthropic": "s3"}}, "/v1/models", "x-api-key"),
        ("gemini", {"keys": {"gemini": "s3"}}, "/v1beta/models", "x-goog-api-key"),
        ("elevenlabs", {"keys": {"elevenlabs": "s3"}}, "/v1/user", "xi-api-key"),
    ],
)
def test_a_provider_test_is_one_free_get_and_keeps_its_result(provider, settings, url, header):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path.endswith(url)
        assert "s3" in request.headers[header]
        return httpx.Response(200, json={"data": [], "models": []})

    result = catalog.test_provider(provider, Settings(**settings), client=_client(handler))
    assert (result["ok"], result["message"]) == (True, "Works")
    view = catalog.public_view(Settings(**settings))
    row = next(item for item in view["providers"] if item["id"] == provider)
    assert row["ready"]["reachable"]["ok"] is True
    assert "s3" not in json.dumps(view)


def test_a_rejected_key_says_so_and_never_repeats_it():
    def handler(request):
        return httpx.Response(401, json={"error": "bad key s3"})

    settings = Settings(keys={"anthropic": "s3"})
    result = catalog.test_provider("anthropic", settings, client=_client(handler))
    assert (result["ok"], result["message"]) == (False, "Rejected")
    assert "s3" not in json.dumps(result)


def test_an_unknown_provider_is_refused():
    with pytest.raises(ValueError):
        catalog.test_provider("nope", Settings(), client=_client(_no_network))
