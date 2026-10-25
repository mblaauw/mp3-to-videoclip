"""Render service: Remotion for preview and final, FFmpeg for probe/mux/verify."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.render import render as _render
from mp3_to_videoclip.storage import inside


def render_final(root: Path, output: Path | None = None) -> dict:
    """Render the selected stills to a versioned MP4 on the exact timeline."""
    project = P.load_project(root)
    shots = P.resolved_assets(root)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)
    if output is None:
        version = 1
        while (directory / f"{project.slug}-final-v{version:03d}.mp4").exists():
            version += 1
        output = directory / f"{project.slug}-final-v{version:03d}.mp4"
    return _render(
        project,
        shots,
        inside(root, project.source),
        output,
        root / "work",
    )


def render_preview(root: Path, output: Path | None = None) -> dict:
    """Low-resolution preview with a banner; not a delivery."""
    project = P.load_project(root)
    shots = P.resolved_assets(root)
    directory = root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    if output is None:
        version = 1
        while (directory / f"{project.slug}-preview-v{version:03d}.mp4").exists():
            version += 1
        output = directory / f"{project.slug}-preview-v{version:03d}.mp4"
    return _render(
        project,
        shots,
        inside(root, project.source),
        output,
        root / "work",
        preview_banner=True,
    )
