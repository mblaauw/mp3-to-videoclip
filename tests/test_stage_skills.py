"""Stage routing/reference integrity, without loading or executing upstream tools."""

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mp3_to_videoclip import profiles

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".opencode/skills"
STAGES = (
    "clip-music-analysis",
    "clip-story",
    "clip-storyboard",
    "clip-art-direction",
    "clip-image-prompts",
    "clip-image-production",
    "clip-visual-review",
    "clip-edit-graphics",
    "clip-delivery",
)


@pytest.mark.parametrize("name", ("clip-music-director", *STAGES))
def test_stage_skill_frontmatter_contracts_and_local_links(name):
    path = SKILLS / name / "SKILL.md"
    text = path.read_text()
    assert text.startswith("---\n")
    front, body = text.split("---", 2)[1:]
    assert re.search(rf"^name: {name}$", front, re.M)
    assert re.search(r"^description: .{20,}", front, re.M)
    assert len(body.splitlines()) <= 120  # Keep task guidance small; details go in references.
    for token in re.findall(r"`([^`\n]+)`", text):
        if token.endswith(".md") and (token.startswith("../") or token.startswith("references/")):
            assert (path.parent / token).is_file(), (name, token)
    if name != "clip-music-director":
        assert "Inputs" in body and "gate" in body.lower()


def test_feedback_and_renderer_references_exist_and_are_linked():
    pairs = (
        ("clip-music-director", "references/crew-feedback-loop.md"),
        ("clip-story", "references/story-feedback.md"),
        ("clip-storyboard", "references/board-feedback.md"),
        ("clip-visual-review", "references/critic-modes.md"),
        ("clip-edit-graphics", "references/remotion-motion.md"),
    )
    for skill, reference in pairs:
        path = SKILLS / skill / reference
        assert path.is_file(), (skill, reference)
        assert f"`{reference}`" in (SKILLS / skill / "SKILL.md").read_text(), (skill, reference)


def test_stage_skills_keep_the_remotion_primary_ffmpeg_legacy_split():
    editor = (SKILLS / "clip-edit-graphics/SKILL.md").read_text()
    assert "Remotion" in editor and "FFmpeg" in editor
    assert "deliberate hold" in editor.lower()
    assert "glitches" in editor
    # Movement is chosen per purpose; the forbidden defaults are named, not implied.
    assert "AI character animation" in editor
    assert "per-beat" in editor
    assert "opt-in" in editor
    motion = (SKILLS / "clip-edit-graphics/references/remotion-motion.md").read_text()
    assert "primary visual renderer" in motion and "opt-in" in motion
    assert "no paid call" in motion, "post design is local and never buys AI motion"
    assert (
        "designs movement"
        in (SKILLS / "clip-edit-graphics/references/motion-and-grade.md").read_text()
    )
    director = (SKILLS / "clip-music-director/SKILL.md").read_text()
    assert "Remotion" in director
    assert "six specialists" in director


def test_edit_skill_keeps_playback_a_checkpoint_not_sampled_evidence():
    editor = (SKILLS / "clip-edit-graphics/SKILL.md").read_text()
    assert "continuous" in editor and "playback with audio" in editor
    assert "sampled" in editor.lower() and "signal checks" in editor
    assert "not watching" in editor.replace("**", "")
    assert "unwatched" in editor, "a delegated proxy preview is never a pass"


def test_critic_reference_fixes_report_shape_and_coverage_honesty():
    modes = (SKILLS / "clip-visual-review/references/critic-modes.md").read_text()
    for mode in ("story", "board", "pixels"):
        assert mode in modes, mode
    for field in ("evidence", "consequence", "proposed fix", "severity"):
        assert field in modes, field
    assert "text review" in modes
    assert "pixel inspection" in modes
    assert "the files it actually opened" in modes
    assert "never report an unseen file as reviewed" in modes
    for coverage in ("inspected", "unreadable", "not reviewed"):
        assert coverage in modes, coverage
    assert "hard ceiling" in modes and "15" in modes
    assert re.search(r"6[–-]8", modes), "the practical batch stays below the ceiling"
    critic = (SKILLS / "clip-visual-review/SKILL.md").read_text()
    assert "text-only" in critic and "15 image occurrences" in critic


def test_feedback_lane_references_give_each_draft_owner_one_revision():
    story = (SKILLS / "clip-story/references/story-feedback.md").read_text()
    assert "independent" in story and "bounded revision" in story
    assert "short-film-writer" in story and "visual-critic" in story and "music-editor" in story
    assert "default second revision" in story
    board = (SKILLS / "clip-storyboard/references/board-feedback.md").read_text()
    assert "independent" in board and "bounded revision" in board
    assert "visual-director" in board and "visual-critic" in board and "post-editor" in board
    loop = (SKILLS / "clip-music-director/references/crew-feedback-loop.md").read_text()
    assert "seven roles" in loop
    assert "only dispatcher" in loop, "the director alone dispatches, approves and spends"


def test_router_covers_all_stages_and_actual_dependency_loop():
    text = (SKILLS / "clip-music-director/SKILL.md").read_text()
    assert all(f"`{name}`" in text for name in STAGES)
    lowered = text.lower()
    # Ordering is a contract, not a fixed wording: story before brief approval,
    # board before storyboard approval, preview before the stills quote.
    for word in ("brief", "storyboard", "preview", "approval"):
        assert word in lowered
    assert lowered.count("approval") >= 3


def test_original_skills_visible_but_vendor_and_pinned_recipes_ignored():
    if not shutil.which("git"):
        pytest.skip("git is needed to check ignore routing")
    for name in ("clip-music-director", *STAGES):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", str(SKILLS / name / "SKILL.md")],
            cwd=ROOT,
            capture_output=True,
        )
        assert result.returncode == 1, name
    for path in (".opencode/vendor/future.txt", ".opencode/skills/runware-run/SKILL.md"):
        assert (
            subprocess.run(
                ["git", "check-ignore", "--no-index", path], cwd=ROOT, capture_output=True
            ).returncode
            == 0
        )


def _literals(path):
    """Module-level literal assignments, ignoring computed ones like Path resolvers."""
    values = {}
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = value
    return values


def test_bootstrap_selects_only_still_recipes_and_archives_motion():
    assert not (ROOT / "scripts/bootstrap_skills.py").exists(), "one bootstrap command only"
    constants = _literals(ROOT / "scripts/bootstrap_production.py")
    assert set(constants["SELECTED"]) == {
        "runware-run",
        "runware-models",
        "runware-prompting",
        "photoreal-stills",
        "character-consistency",
    }
    assert set(constants["ARCHIVED"]) == {"animate-image", "cinematic-video"}
    config = json.loads((ROOT / "opencode.json").read_text())
    for name in constants["ARCHIVED"]:
        matching = [
            r
            for r in config["permissions"]
            if r["action"] == "skill" and r["resource"] in ("*", name)
        ]
        assert matching[-1]["effect"] == "deny"
    assert "runware" in config["mcp"]["servers"]


def _recipe_copy(name, archived):
    """Locate a pinned recipe copy; deselected ones live in the ignored archive."""
    if archived:
        assert not (SKILLS / name).exists(), f"{name} must not be an active skill"
        return ROOT / "backups/unused-motion-skills" / name
    return SKILLS / name


def test_pinned_recipe_bytes_match_vendor_when_present():
    vendor = ROOT / ".opencode/vendor/runware-skills/skills"
    if not vendor.is_dir():
        pytest.skip("pinned external recipes are an optional local installation")
    for name, archived in (
        ("runware-run", False),
        ("runware-models", False),
        ("runware-prompting", False),
        ("photoreal-stills", False),
        ("character-consistency", False),
        ("animate-image", True),
        ("cinematic-video", True),
    ):
        installed = _recipe_copy(name, archived)
        if not installed.is_dir():
            continue
        for path in installed.rglob("*"):
            if path.is_file():
                assert (
                    path.read_bytes() == (vendor / name / path.relative_to(installed)).read_bytes()
                )


def test_style_has_both_artists_and_no_test_scene_contamination():
    assert "Alex Ross" in profiles.DEFAULT_STYLE and "Gabriele Dell'Otto" in profiles.DEFAULT_STYLE
    assert "photograph" in profiles.DEFAULT_STYLE and "brush" in profiles.DEFAULT_STYLE
    assert not any(
        s in profiles.DEFAULT_STYLE.lower()
        for s in ("rooftop", "rain streak", "overcoat", "f/2", "50mm")
    )
    assert profiles.DEFAULT_MAX_CORRECTIONS == 1
    story = (SKILLS / "clip-story/references/treatment-template.md").read_text()
    assert all(
        word in story
        for word in ("Central question", "Obstacle", "Choice and cost", "Turn", "Payoff")
    )
    board = (SKILLS / "clip-storyboard/references/shot-contract.md").read_text()
    assert all(word in board for word in ("must_show", "framing", "event_ids", "duration_frames"))
