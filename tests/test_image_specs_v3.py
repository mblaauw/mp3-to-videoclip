"""Compiler version 3: subject first, a look per section, a seed per shot."""

from __future__ import annotations

import hashlib

import pytest
from test_contract_golden import _brief, _project

from mp3_to_videoclip import generation, production
from mp3_to_videoclip.models import CreativeProfile, LookSection, Shot
from mp3_to_videoclip.production import image_specs

SECTIONS = [
    LookSection(id="v1", start=0, end=30, palette=["ochre", "#223344"], light="noon", lens="35 mm"),
    LookSection(id="c1", start=30, end=60, palette=["rust"], light="last light"),
]


def _shot(start=0, shot_id="s001"):
    return Shot(
        id=shot_id,
        start_frame=start,
        duration_frames=48,
        purpose="Let go",
        image_prompt="A hand lets go of the bottle.",
        framing="close_up",
        must_show=["the hand"],
    )


def _spec(tmp_path, version=3, *, sections=SECTIONS, shot=None):
    project = _project().model_copy(update={"prompt_version": version})
    brief = _brief()
    creative = (brief.creative or CreativeProfile()).model_copy(update={"sections": sections})
    brief = brief.model_copy(update={"creative": creative, "characters": []})
    return image_specs._creative_image_spec(tmp_path, project, brief, shot or _shot())


def test_version_3_puts_the_subject_first_and_the_look_after_it(tmp_path):
    lines = _spec(tmp_path, sections=[])["positivePrompt"].split("\n")
    look = _brief().creative.look
    assert lines[0] == "A hand lets go of the bottle."
    assert lines[1].startswith("Framing:")
    assert lines[2] == "Must show: the hand"
    assert "\n".join(lines).index(look) > "\n".join(lines).index("Must show: the hand")


def test_version_2_keeps_the_look_first_and_never_sees_a_section(tmp_path):
    spec = _spec(tmp_path, version=2)
    assert spec["positivePrompt"].startswith(_brief().creative.look)
    assert "Section look" not in spec["positivePrompt"]
    assert "avoid" not in spec


def test_the_section_holding_the_first_frame_gives_its_look(tmp_path):
    first = _spec(tmp_path)["positivePrompt"].split("\n")
    assert "Section look: palette ochre, #223344; light noon; lens 35 mm" in first
    assert first.index("Must show: the hand") < first.index(
        "Section look: palette ochre, #223344; light noon; lens 35 mm"
    )
    later = _spec(tmp_path, shot=_shot(start=24 * 30))["positivePrompt"]
    assert "Section look: palette rust; light last light" in later
    beyond = _spec(tmp_path, shot=_shot(start=24 * 70))["positivePrompt"]
    assert "Section look" not in beyond


def test_sections_only_change_a_profile_version_when_there_are_some():
    brief = _brief()
    before = image_specs.creative_profile_version(brief)
    empty = brief.model_copy(
        update={"creative": brief.creative.model_copy(update={"sections": []})}
    )
    assert image_specs.creative_profile_version(empty) == before
    assert "sections" not in brief.creative.model_dump()
    moved = brief.model_copy(
        update={"creative": brief.creative.model_copy(update={"sections": SECTIONS})}
    )
    assert image_specs.creative_profile_version(moved) != before


def test_sections_must_be_in_order_without_overlap():
    with pytest.raises(ValueError, match="in order"):
        CreativeProfile(sections=[SECTIONS[1], SECTIONS[0]])
    with pytest.raises(ValueError, match="end after"):
        LookSection(id="x", start=5, end=5, palette=["red"], light="noon")


def test_a_shots_seed_is_its_own_and_fits_the_model():
    assert image_specs.shot_seed(7, "s001") == image_specs.shot_seed(7, "s001")
    assert image_specs.shot_seed(7, "s001") != image_specs.shot_seed(7, "s002")
    raw = int(hashlib.sha256(b"7:s001").hexdigest()[:8], 16)
    assert image_specs.shot_seed(7, "s001") == raw % 2**31 <= 2147483647


def test_avoid_moves_to_the_models_own_field_only_when_it_has_one():
    spec = {"positivePrompt": "A hand.\nAvoid: text; logos", "avoid": ["text", "logos"]}
    assert generation._worded(spec, {"positivePrompt": {}}) == {
        "positivePrompt": "A hand.\nAvoid: text; logos"
    }
    assert generation._worded(spec, {"negativePrompt": {}}) == {
        "positivePrompt": "A hand.",
        "negativePrompt": "text; logos",
    }
    # A version 2 spec keeps its prose whatever the model offers.
    assert generation._worded(
        {"positivePrompt": "A hand.\nAvoid: text"}, {"negativePrompt": {}}
    ) == {"positivePrompt": "A hand.\nAvoid: text"}


def test_compile_order_names_each_version():
    assert production.compile_order(_project()) == "look-first"
    assert production.compile_order(_project().model_copy(update={"prompt_version": 3})) == "subject-first"  # fmt: skip
