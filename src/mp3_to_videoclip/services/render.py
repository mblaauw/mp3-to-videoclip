"""Render service: Remotion for preview and final, FFmpeg for probe/mux/verify."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.render import render as _render
from mp3_to_videoclip.storage import file_hash, inside, write_json


def render_final(root: Path, output: Path | None = None) -> dict:
    """Render the selected stills to a versioned MP4 on the exact timeline."""
    # The full-stills decision is the last human gate before a delivery render.
    P.require_approval(root, "stills")
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
        brand=P.load_brand(root),
    )


def render_preview(root: Path, output: Path | None = None) -> dict:
    """Marked preview plus the exact review report the preview approval binds."""
    project = P.load_project(root)
    shots = P.resolved_assets(root)
    directory = root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    if output is None:
        version = 1
        while (directory / f"{project.slug}-preview-v{version:03d}.mp4").exists():
            version += 1
        output = directory / f"{project.slug}-preview-v{version:03d}.mp4"
    report = _render(
        project,
        shots,
        inside(root, project.source),
        output,
        root / "work",
        preview_banner=True,
        brand=P.load_brand(root),
    )
    review = write_preview_review(root, output, report)
    report["preview_review"] = str(
        (root / P.STAGE_FILES["preview"]).resolve().relative_to(root.resolve())
    )
    report["approval_ready"] = True
    report["review"] = review
    return report


def write_preview_review(root: Path, output: Path, report: dict) -> dict:
    """Bind the reviewed movie bytes to the current storyboard, proof, brand and renderer.

    The GUI preview job owns this write so a rendered preview is immediately
    approvable. The CLI has the same contract in its own preview path.
    """
    movie = output.resolve()
    try:
        relative = movie.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("preview must stay inside the production") from exc
    value = {
        "movie": relative,
        "movie_sha256": file_hash(movie),
        "storyboard_hash": P.preview_board_hash(root),
        "proof_hash": P.stage_hash(root, "proof"),
        "brand_hash": P.brand_hash(root),
        "input_hash": report.get("input_hash"),
    }
    if report.get("renderer_revision"):
        value["renderer_revision"] = report["renderer_revision"]
    write_json(root / P.STAGE_FILES["preview"], value)
    return value
