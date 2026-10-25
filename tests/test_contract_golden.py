"""Byte-stable contract for the compiled prompt, the frame timing and the renderer request.

Phases 1-2 of the GUI rework move modules and delete whole generations of code.
These three outputs are what a silent refactor could change without any test
noticing: the image prompt that gets paid for, the exact integer-frame timing,
and the Remotion request JSON the renderer consumes.

Regenerate deliberately with ``UPDATE_GOLDEN=1 uv run pytest
tests/test_contract_golden.py`` and state the intended change in the commit.

Nothing here renders, probes audio or calls a provider.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from mp3_to_videoclip import production, profiles, remotion, timeline
from mp3_to_videoclip.models import (
    Brief,
    Character,
    CharacterState,
    CreativeProfile,
    ImageSettings,
    Project,
    Scene,
    Shot,
    Storyboard,
    VisualBeat,
)
from mp3_to_videoclip.storage import write_json

GOLDEN = Path(__file__).parent / "golden" / "contract.json"
FPS = 24
DURATION = 90.0
DURATIONS = (720, 960, 480)


def _project() -> Project:
    return Project(
        slug="contract",
        title="Contract fixture",
        source_sha256="",
        duration=DURATION,
        fps=FPS,
        width=1920,
        height=1080,
        music_mode="vocal",
        native_size=[1376, 768],
        workflow_version=2,
        prompt_version=2,
        style_preset=profiles.STYLE_PRESET_ID,
        image_model=profiles.DEFAULT_MODEL,
        image_settings=ImageSettings(thinkingLevel="high"),
        image_seed=7,
        renderer_backend="remotion",
    )


def _brief() -> Brief:
    return Brief(
        direction="Follow one woman through a wet street at night.",
        style="Photographic, cold, high contrast.",
        treatment="She walks; the street answers.",
        visual_rules=["One subject at a time"],
        avoid=["text", "logos"],
        characters=[
            Character(
                id="c1",
                identity="A tall woman with a red scarf and a shaved head",
                permission_confirmed=True,
                states={"rain": CharacterState(description="soaked wool coat")},
                default_state="rain",
            )
        ],
        creative=CreativeProfile(
            mode="narrative",
            look=profiles.DEFAULT_STYLE + "\n\nFixture-grade overcast palette.",
            image_rules=["No lettering anywhere in the frame"],
            arc=[VisualBeat(phase="open", intention="distance")],
            scenes=[Scene(id="street", description="Wet street at night, sodium light")],
            proof_shot_ids=["s002"],
        ),
    )


def _shot(shot_id: str, start: int, duration: int, **changes) -> Shot:
    values = {
        "id": shot_id,
        "start_frame": start,
        "duration_frames": duration,
        "purpose": "Test the timing contract",
        "image_prompt": f"Frame {shot_id} of the fixture sequence",
        "camera": "hold",
        "dissolve_frames": 0,
    }
    values.update(changes)
    return Shot(**values)


def _board(project: Project) -> Storyboard:
    cursor, shots = 0, []
    for shot_id, duration in zip(("s001", "s002", "s003"), DURATIONS, strict=True):
        changes = {"framing": "wide", "scene_id": "street", "character_ids": ["c1"]}
        if shot_id == "s002":
            changes |= {"dissolve_frames": 24, "framing": "close_up", "camera": "pan_left"}
        shots.append(_shot(shot_id, cursor, duration, **changes))
        cursor += duration
    return Storyboard(aspect="16:9", fps=FPS, total_frames=cursor, shots=shots)


def _write_project(root: Path, project: Project) -> Path:
    song = root / "media" / "song.mp3"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"contract fixture source; never loaded as audio")
    project = project.model_copy(
        update={"source_sha256": hashlib.sha256(song.read_bytes()).hexdigest()}
    )
    write_json(root / "project.json", project.model_dump())
    write_json(root / "brief.json", _brief().model_dump())
    write_json(root / "work" / "storyboard.json", _board(project).model_dump())
    return root


def _contract(root: Path) -> dict:
    project = production.load_project(root)
    board = production.load_board(root)
    frames = [0, 1, 719, 720, 1199, 1200, 1559, 2159]
    request = remotion.request(
        "base",
        root / "renders" / "base-v001.mp4",
        root / "work" / "assets",
        (project.width, project.height),
        project.fps,
        project.total_frames,
        {"shots": [{"id": shot.id, "frames": shot.duration_frames} for shot in board.shots]},
    )
    # Absolute paths must not leak into the pinned contract.
    request["output"] = "<output>"
    request["assetRoot"] = "<assets>"
    request["chrome"] = "<chrome>"
    return {
        "prompts": [production.image_spec(root, shot) for shot in board.shots],
        "timing": [timeline.label_at_frame(board, frame) for frame in frames],
        "remotion_request": request,
    }


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    return _write_project(tmp_path / "contract", _project())


def test_compiled_prompt_timing_and_renderer_request_are_unchanged(project_root, monkeypatch):
    monkeypatch.setenv("REMOTION_CHROME", "/chrome/contract")
    observed = _contract(project_root)
    if os.environ.get("UPDATE_GOLDEN"):
        write_json(GOLDEN, observed)
    golden = json.loads(GOLDEN.read_text())
    assert observed == golden


def test_the_fixture_actually_exercises_the_creative_compiler(project_root):
    """A vacuous golden would pass forever; assert the meaningful inputs are present."""
    spec = production.image_spec(project_root, production.load_board(project_root).shots[1])
    prompt = spec["positivePrompt"]
    assert profiles.DEFAULT_STYLE.splitlines()[0] in prompt
    assert "Wet street at night" in prompt
    assert "c1 state (rain): soaked wool coat" in prompt
    assert "Avoid: text; logos" in prompt
    assert spec["size"] == [1376, 768]
    assert spec["generation"]["model"] == profiles.DEFAULT_MODEL
    assert len(spec["profile_version"]) == 64
