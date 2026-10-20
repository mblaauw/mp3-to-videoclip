"""Standing prompt contracts, not proof of musical/visual quality or live routing."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "opencode.json").read_text())
REFERENCE = ".opencode/skills/clip-music-director/references/music-first-direction.md"


@pytest.mark.parametrize("name", list(CONFIG["agents"]))
def test_each_role_explicitly_reads_the_shared_music_first_contract(name):
    assert REFERENCE in CONFIG["agents"][name]["system"]
    assert (ROOT / REFERENCE).is_file()


def test_single_existing_lead_gets_early_music_and_post_input():
    assert CONFIG["default_agent"] == "film-director"
    assert len(CONFIG["agents"]) == 7
    lead = CONFIG["agents"]["film-director"]["system"]
    for phrase in (
        "narrative is optional",
        "Before storyboard lock and image generation",
        "music-editor and post-editor",
        "sequence treatment into the existing brief",
        "provisional",
        "proof-only full-song preview",
        "only you write canonical",
    ):
        assert phrase.lower() in lead.lower(), phrase


def test_writer_and_critic_do_not_require_narrative_in_other_modes():
    writer = CONFIG["agents"]["short-film-writer"]["system"]
    critic = CONFIG["agents"]["visual-critic"]["system"]
    assert "Narrative is optional" in writer
    assert "For narrative directions" in writer
    assert "otherwise visual progression" in critic
    assert "never reject abstraction for lacking a protagonist" in critic


def test_post_editor_co_designs_instead_of_arriving_after_image_generation():
    post = CONFIG["agents"]["post-editor"]["system"]
    for phrase in (
        "BEFORE storyboard lock and image generation",
        "attention plans",
        "typography",
        "deliberate holds",
        "proof-only full-song preview",
    ):
        assert phrase in post
    board = (ROOT / ".opencode/skills/clip-storyboard/SKILL.md").read_text()
    assert "planned later by `post-editor`" not in board
    assert "Snap the proposal" not in board
    assert "visual or musical function" in board
    assert "Action/reaction pairs" in board and "when interactions require" in board
    assert "Each cut introduces **new information**" not in board
    edit = (ROOT / ".opencode/skills/clip-edit-graphics/SKILL.md").read_text()
    assert "**One slow push or pull per shot**" not in edit


def test_shared_contract_protects_evidence_spend_and_actual_song_sequence_review():
    text = (ROOT / REFERENCE).read_text()
    for phrase in (
        "supplied style/lyric intent",
        "Candidate BPM does not establish meter",
        "attention plan",
        "not a defect",
        "anticipation/counterpoint",
        "No automatic 3–4 paid candidates",
        "Grade/grain",
        "Depth/parallax",
        "narrative causality only where applicable",
        "dense and contrasting passages",
        "proof-only full-song",
        "composited locally",
        "user-owned",
    ):
        assert phrase in text, phrase
    for name in CONFIG["agents"]:
        assert name in text
    for file in ("AGENTS.md", "LOOP.md"):
        assert REFERENCE in (ROOT / file).read_text()
