"""Each Studio stage appends its own guide to the director's system prompt."""

from __future__ import annotations

from mp3_to_videoclip.api.director import STAGES, _system_prompt


def test_base_prompt_is_shared_and_each_stage_adds_its_guide():
    base = _system_prompt(None)
    assert "You are the director" in base
    for stage in STAGES:
        text = _system_prompt(stage)
        assert base in text
        assert len(text) > len(base) + 500, f"{stage} guide did not land"


def test_guides_carry_the_hard_rules_for_their_stage():
    assert "estimate" in _system_prompt("track").lower()
    assert "proof shots" in _system_prompt("story")
    assert "stable identity" in _system_prompt("storyboard")
    assert "no-text clause" in _system_prompt("images").lower()
    assert "silent tail" in _system_prompt("film")


def test_unknown_stage_gets_only_the_base_prompt():
    assert _system_prompt("polish") == _system_prompt(None)
