"""Python and the shared Remotion timing module must describe the same contract.

``renderers/remotion/src/timing.mjs`` is the renderer's pure frame authority and,
since Phase 5, also the browser Player's timing. This test loads the actual ESM
module with Node and compares its constants, bounds and allocation acceptance with
the Python models and renderer. It is skipped when Node is unavailable, the same
way a real render is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, get_args

import pytest

from mp3_to_videoclip import graphics, render
from mp3_to_videoclip.models import BrandPackage, PostEffects, Shot, Storyboard

TIMING = Path(__file__).resolve().parents[1] / "renderers/remotion/src/timing.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None or not TIMING.is_file(),
    reason="the shared timing module needs local Node",
)

_SCRIPT = """
import {pathToFileURL} from "node:url";
const timing = await import(pathToFileURL(process.argv[1]).href);
const payload = JSON.parse(process.argv[2]);
const allocations = payload.allocations.map((shots) => {
  try {
    const value = timing.allocateSpans(shots);
    return {
      ok: true,
      total: value.totalFrames,
      spans: value.spans.map((span) => ({
        id: span.id,
        start_frame: span.start_frame,
        duration_frames: span.duration_frames,
        handle: span.handle,
      })),
    };
  } catch (error) {
    return {ok: false, error: String(error.message)};
  }
});
const cameras = payload.cameras.map(([move, frames]) =>
  frames.map((frame) =>
    timing.cameraAtFrame({id: "probe", duration_frames: 24, handle: 0, camera: move}, frame),
  ),
);
console.log(JSON.stringify({
  constants: {
    ZOOM_RANGE: timing.ZOOM_RANGE,
    CAMERA_MOVES: timing.CAMERA_MOVES,
    INTRO_REFERENCE_SECONDS: timing.INTRO_REFERENCE_SECONDS,
    MIN_CAPTION_GAP: timing.MIN_CAPTION_GAP,
    SAFE_MARGIN: timing.SAFE_MARGIN,
    BRAND_PLATE_SECONDS: timing.BRAND_PLATE_SECONDS,
    BRAND_PLATE_FADE_SECONDS: timing.BRAND_PLATE_FADE_SECONDS,
  },
  ranges: timing.POST_EFFECT_RANGES,
  transitions: timing.TRANSITIONS,
  allocations,
  cameras,
}));
"""


def _run_node(payload: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", _SCRIPT, str(TIMING), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)


def _case(name: str, shots: list[dict], ok: bool) -> dict:
    return {"name": name, "shots": shots, "ok": ok}


def _shot(shot_id: str, start: int, duration: int, dissolve: int = 0) -> dict:
    value = {
        "id": shot_id,
        "image": f"{shot_id}.jpg",
        "start_frame": start,
        "duration_frames": duration,
        "camera": "hold",
    }
    if dissolve:
        value["dissolve_frames"] = dissolve
    return value


def _board(shots: list[dict]) -> Storyboard:
    total = sum(shot["duration_frames"] for shot in shots)
    return Storyboard.model_validate(
        {
            "aspect": "16:9",
            "fps": 24,
            "total_frames": total,
            "shots": [
                {
                    "id": shot["id"],
                    "start_frame": shot["start_frame"],
                    "duration_frames": shot["duration_frames"],
                    "dissolve_frames": shot.get("dissolve_frames", 0),
                    "purpose": f"parity {shot['id']}",
                    "image_prompt": "parity fixture",
                    "camera": shot["camera"],
                }
                for shot in shots
            ],
        }
    )


def _bounds(name: str) -> list[float]:
    field = PostEffects.model_fields[name]
    low = next(item.ge for item in field.metadata if hasattr(item, "ge"))
    high = next(item.le for item in field.metadata if hasattr(item, "le"))
    return [low, high]


CASES = [
    _case("contiguous with a dissolve", [_shot("a", 0, 6, 2), _shot("b", 6, 4)], True),
    _case("plain contiguous", [_shot("a", 0, 4), _shot("b", 4, 4)], True),
    _case("gap", [_shot("a", 0, 6), _shot("b", 7, 4)], False),
    _case("duplicate id", [_shot("a", 0, 4), _shot("a", 4, 4)], False),
    _case("trailing dissolve", [_shot("a", 0, 4, 2)], False),
    _case("dissolve too long", [_shot("a", 0, 3, 3), _shot("b", 3, 6)], False),
    _case("zero duration", [_shot("a", 0, 0), _shot("b", 0, 4)], False),
]

CAMERA_FRAMES = [0, 5, 23]


def test_the_shared_timing_module_agrees_with_python():
    observed = _run_node(
        {
            "allocations": [case["shots"] for case in CASES],
            "cameras": [[move, CAMERA_FRAMES] for move in render._MOVES],
        }
    )
    constants = observed["constants"]
    assert constants["ZOOM_RANGE"] == render.ZOOM_RANGE
    assert constants["CAMERA_MOVES"] == list(render._MOVES)
    assert constants["INTRO_REFERENCE_SECONDS"] == graphics.INTRO_REFERENCE_SECONDS
    assert constants["MIN_CAPTION_GAP"] == graphics.MIN_CAPTION_GAP
    assert constants["SAFE_MARGIN"] == graphics.SAFE_MARGIN
    assert constants["BRAND_PLATE_SECONDS"] == BrandPackage.model_fields["duration_seconds"].default
    assert constants["BRAND_PLATE_FADE_SECONDS"] == render.BRAND_PLATE_FADE_SECONDS

    assert observed["ranges"] == {name: _bounds(name) for name in PostEffects.model_fields}
    transitions = get_args(get_args(Shot.model_fields["transition"].annotation)[0])
    assert observed["transitions"] == list(transitions)


def test_allocation_acceptance_matches_the_python_storyboard():
    observed = _run_node({"allocations": [case["shots"] for case in CASES], "cameras": []})
    for case, result in zip(CASES, observed["allocations"], strict=True):
        try:
            board = _board(case["shots"])
        except ValueError:
            assert result["ok"] is False, case["name"]
            continue
        assert result["ok"] is True, (case["name"], result.get("error"))
        assert result["total"] == board.total_frames
        assert result["spans"] == [
            {
                "id": shot.id,
                "start_frame": shot.start_frame,
                "duration_frames": shot.duration_frames,
                "handle": shot.dissolve_frames,
            }
            for shot in board.shots
        ]


def test_legacy_camera_endpoints_match_the_python_zoom_range():
    observed = _run_node(
        {"allocations": [], "cameras": [[move, CAMERA_FRAMES] for move in render._MOVES]}
    )
    by_move = dict(zip(render._MOVES, observed["cameras"], strict=True))
    assert by_move["hold"][0] == {"zoom": 1, "x": 0.5, "y": 0.5}
    assert by_move["zoom_in"][-1]["zoom"] == pytest.approx(1 + render.ZOOM_RANGE)
    assert by_move["zoom_out"][-1]["zoom"] == pytest.approx(1)
    assert by_move["pan_left"][-1]["x"] == pytest.approx(0)
    assert by_move["pan_right"][-1]["x"] == pytest.approx(1)
    for move in render._MOVES:
        expression = render._zoompan(24, move)
        if move == "hold":
            assert "z='1'" in expression
        else:
            assert f"{render.ZOOM_RANGE}" in expression
