"""Schema 2 keeps every value an old file held, and the old names still answer."""

from __future__ import annotations

import stat
import tomllib

import pytest

from mp3_to_videoclip import config

V1 = """[settings]
runware_api_key = "rw-secret"
gateway = "opencode"
opencode_bin = "/opt/opencode"
writer_model = "openai/gpt-6.1-sol"
editor_model = "openrouter/deep/seek"
opencode_workspace = "/work"
llm_base_url = "https://example.test/v1"
llm_api_key = "llm-secret"
llm_model = "bare-model"
brand_name = "Owner"
brand_partner = "Partner"
default_budget_usd = 7.5
image_reserve_usd = 0.08
default_credit_roles = ["director"]
remotion_dir = ""
ffmpeg_path = ""
"""
EFFECTIVE = {
    "runware_api_key": "rw-secret",
    "gateway": "opencode",
    "opencode_bin": "/opt/opencode",
    "writer_model": "openai/gpt-6.1-sol",
    "editor_model": "openrouter/deep/seek",
    # A file without this name got the default, and still does.
    "critic_model": "openai/gpt-6.1-sol",
    "opencode_workspace": "/work",
    "llm_base_url": "https://example.test/v1",
    "llm_api_key": "llm-secret",
    "llm_model": "bare-model",
    "brand_name": "Owner",
    "brand_partner": "Partner",
    "default_budget_usd": 7.5,
    "image_reserve_usd": 0.08,
}


@pytest.fixture
def path(tmp_path, monkeypatch):
    target = tmp_path / "settings.toml"
    monkeypatch.setattr(config, "settings_path", lambda: target)
    return target


def _effective(settings: config.Settings) -> dict:
    return {name: getattr(settings, name) for name in EFFECTIVE}


def test_an_old_file_loads_to_the_same_values(path):
    path.write_text(V1)
    loaded = config.load_settings()
    assert _effective(loaded) == EFFECTIVE
    assert loaded.new_films.credit_roles == ["director"]
    assert loaded.roles.editor.provider == "openrouter"
    assert loaded.roles.editor.model == "deep/seek"


def test_a_fresh_install_keeps_todays_defaults(path):
    assert _effective(config.Settings()) | {"gateway": "x"} == {
        "runware_api_key": "",
        "gateway": "x",
        "opencode_bin": "opencode",
        "writer_model": "openai/gpt-6.1-sol",
        "editor_model": "opencode-go/deepseek-v4.1-flash",
        "critic_model": "openai/gpt-6.1-sol",
        "opencode_workspace": "",
        "llm_base_url": "https://opencode.ai/inference/go/openai/v1",
        "llm_api_key": "",
        "llm_model": "deepseek-v4.1-flash",
        "brand_name": "MAHA KALA",
        "brand_partner": "VJDJ69",
        "default_budget_usd": 5.0,
        "image_reserve_usd": 0.05,
    }
    assert config.Settings().gateway == "direct"


def test_the_first_save_keeps_the_old_file_once_and_private(path):
    path.write_text(V1)
    config.save_settings(config.load_settings())
    backup = path.with_name("settings.toml.v1.bak")
    assert backup.read_text() == V1
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert _effective(config.load_settings()) == EFFECTIVE

    path.write_text(V1.replace("Owner", "Changed"))
    config.save_settings(config.load_settings())
    assert backup.read_text() == V1, "only the first old file is the backup"


def test_a_new_file_gets_no_backup(path):
    config.save_settings(config.Settings())
    config.save_settings(config.Settings())
    assert not path.with_name("settings.toml.v1.bak").exists()


def test_a_save_round_trip_is_byte_stable_and_private(path):
    path.write_text(V1)
    config.save_settings(config.load_settings())
    first = path.read_bytes()
    config.save_settings(config.load_settings())
    assert path.read_bytes() == first
    assert tomllib.loads(first.decode())["schema_version"] == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_nested_choices_survive_a_round_trip(path):
    settings = config.Settings(
        roles={"writer": {"provider": "anthropic", "model": "m", "thinking": "high"}},
        voices={"favourites": ["a", "b"]},
        pictures={"image_model_by_look": {"look-v1": "model-x"}},
        prices={"model-x": "0.02"},
        new_films={"brand": {"palette": ["#000000"]}},
    )
    config.save_settings(settings)
    assert config.load_settings() == settings
    assert config.load_settings().writer_model == "anthropic/m"


def test_a_flat_name_cannot_be_assigned(path):
    with pytest.raises((AttributeError, ValueError)):
        config.Settings().brand_name = "x"


def test_the_file_wins_over_the_environment(path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-eleven")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic")
    config.save_settings(config.Settings(keys={"anthropic": "file-anthropic"}))
    effective = config.effective_settings()
    assert effective.keys.elevenlabs == "env-eleven"
    assert effective.keys.anthropic == "file-anthropic"
