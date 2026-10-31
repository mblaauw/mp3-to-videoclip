"""A hung render fails instead of waiting forever, and settings survive any value."""

from __future__ import annotations

import stat

from mp3_to_videoclip import config, signature


def test_settings_survive_quotes_and_backslashes_and_stay_private(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    saved = config.Settings(llm_api_key='a"b\\c', opencode_bin="C:\\tools\\opencode")
    config.save_settings(saved)
    loaded = config.load_settings()
    assert loaded.llm_api_key == 'a"b\\c'
    assert loaded.opencode_bin == "C:\\tools\\opencode"
    assert loaded.brand_name == saved.brand_name
    assert stat.S_IMODE(config.settings_path().stat().st_mode) == 0o600


def test_a_new_film_uses_the_brand_settings():
    brand = signature.film_brand("Solo act", "")
    spec = signature.draft_spec("Song", brand)
    assert spec["intro"]["names"] == "SOLO ACT"
    assert spec["credits"]["lockup"] == "A SOLO ACT PRODUCTION"
    assert spec["brand"] == {"name": "SOLO ACT", "partner": ""}


def test_the_original_pair_leaves_a_film_spec_as_it_was():
    assert signature.film_brand("MAHA KALA", "VJDJ69") is None
    assert signature.film_brand("", "anyone") is None
    assert "brand" not in signature.draft_spec("Song")
    assert signature.draft_spec("Song")["intro"]["names"] == signature.NAMES


def test_old_settings_files_with_removed_fields_still_load():
    assert config.Settings(remotion_dir="x", ffmpeg_path="y", default_credit_roles=["z"])
