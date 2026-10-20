"""Opt-in layout validation/cache evidence; no providers or assumed pixel proof."""

import copy

import pytest

from mp3_to_videoclip import graphics


def test_layout_absent_leaves_legacy_element_content_unchanged():
    spec = {"intro": {"names": "A ◆ B"}}
    assert graphics.element_content("card", spec, {"card": ["MUSIC", "A"]}) == {
        "card": ["MUSIC", "A"],
        "design": graphics.resolve_design(spec),
    }


@pytest.mark.parametrize(
    "layout",
    [
        None,
        {},
        [],
        {"kind": "wrong"},
        {"kind": "compact-v1", "x": 0.4},
        {"kind": "compact-v1", "identity_switch_frame": 59},
        {"kind": "compact-v1", "identity_switch_frame": 59, "handoff_frames": 0},
        {"kind": "compact-v1", "identity_switch_frame": True, "handoff_frames": 1},
    ],
)
def test_invalid_layout_controls_fail(layout):
    with pytest.raises(graphics.ComposeError):
        graphics.validate_layout({"renderer": "remotion", "layout": layout})


def test_compact_cannot_silently_fall_back_to_pillow():
    with pytest.raises(graphics.ComposeError, match="requires Remotion"):
        graphics.validate_layout({"renderer": "pillow", "layout": {"kind": "compact-v1"}})


def test_compact_layout_and_name_changes_bind_role_cache_content():
    spec = {"renderer": "remotion", "layout": {"kind": "compact-v1"}, "intro": {"names": "A ◆ B"}}
    part = {"card": ["MUSIC", "A"]}
    before = graphics.element_content("card", spec, part)
    changed = copy.deepcopy(spec)
    changed["intro"]["names"] = "B ◆ A"
    assert before != graphics.element_content("card", changed, part)
    changed = copy.deepcopy(spec)
    changed["layout"].update(identity_switch_frame=59, handoff_frames=8)
    assert before != graphics.element_content("card", changed, part)
    assert (
        graphics.element_content(
            "caption", spec, {"caption": {"text": "Hello", "style": "caption"}}
        )["layout"]["kind"]
        == "compact-v1"
    )
