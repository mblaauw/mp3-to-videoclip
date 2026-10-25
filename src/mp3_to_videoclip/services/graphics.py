"""Graphics: spec validation, window planning, Remotion overlay compositing."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip.graphics import (
    ComposeError,
    compose,
    load_spec,
    resolve_palette,
    validate_layout,
)

__all__ = [
    "ComposeError",
    "compose",
    "load_spec",
    "resolve_palette",
    "validate_layout",
    "spec_path",
]


def spec_path(root: Path) -> Path:
    return root / "work" / "graphics-spec.json"
