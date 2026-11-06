"""The chat route's context check: every stage the prompt suite answers on is accepted."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from mp3_to_videoclip.api.director import _context
from mp3_to_videoclip.director import prompts


@pytest.mark.parametrize("stage", sorted(prompts.STAGE_ROLE))
def test_every_stage_with_a_role_is_a_valid_context(stage):
    assert _context({"context": {"stage": stage, "time": 1.5}}) == {"stage": stage, "time": 1.5}


def test_the_new_stages_reach_the_writer():
    for stage in ("sound", "publish", "script"):
        assert prompts.role_for_stage(stage) == "writer"
        assert _context({"context": {"stage": stage}}) == {"stage": stage}


def test_a_stage_the_suite_does_not_know_is_refused():
    with pytest.raises(HTTPException) as caught:
        _context({"context": {"stage": "nowhere"}})
    assert caught.value.detail == "context stage is invalid"
