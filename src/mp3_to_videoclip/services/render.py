"""Render service: Remotion base/preview, FFmpeg graphics composite for delivery."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.render import render as _render
from mp3_to_videoclip.storage import file_hash, inside, write_json


def _next_output(directory: Path, prefix: str) -> Path:
    version = 1
    while (directory / f"{prefix}-v{version:03d}.mp4").exists():
        version += 1
    return directory / f"{prefix}-v{version:03d}.mp4"


def _write_report(output: Path, report: dict) -> Path:
    path = output.with_suffix(".json")
    write_json(path, report)
    return path


def render_base(root: Path, output: Path | None = None) -> dict:
    """Render the selected stills without graphics; this is never delivery."""
    P.require_approval(root, "stills")
    project = P.load_project(root)
    shots = P.resolved_assets(root)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)
    output = output or _next_output(directory, f"{project.slug}-base")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _render(
        project,
        shots,
        P.render_audio(root, project),
        output,
        root / "work",
        brand=P.load_brand(root),
    )
    from mp3_to_videoclip.signature import current_input_hash, prepare_review

    report["input_hash"] = current_input_hash(root)
    report["delivery_ready"] = False
    # Write the report before preparing the review: validate_review later reads
    # this sidecar to prove the base belongs to the current storyboard/stills.
    _write_report(output, report)
    if P.requires_signature(root, project):
        report["graphics_review"] = prepare_review(root, output, project)
        _write_report(output, report)
    return report


def render_final(root: Path, output: Path | None = None) -> dict:
    """Render delivery: compose approved graphics over the reviewed base."""
    # The full-stills decision is the last human gate before a delivery render.
    P.require_approval(root, "stills")
    project = P.load_project(root)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)

    if P.requires_signature(root, project):
        from mp3_to_videoclip.graphics import compose
        from mp3_to_videoclip.signature import current_input_hash, validate_review

        # Both the approval record and the reviewed bytes must still match.
        P.require_approval(root, "graphics")
        review = validate_review(root, project)
        base = inside(root, review["base"])
        output = output or _next_output(directory, f"{project.slug}-final")
        report = compose(root, base, output)
        report["delivery_ready"] = True
        report["graphics_approval_hash"] = P.stage_hash(root, "graphics")
        report["input_hash"] = current_input_hash(root)
        _write_report(Path(report["output"]), report)
        return report

    # Projects without a signature have no separate graphics pass.
    output = output or _next_output(directory, f"{project.slug}-final")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _render(
        project,
        P.resolved_assets(root),
        P.render_audio(root, project),
        output,
        root / "work",
        brand=P.load_brand(root),
    )
    from mp3_to_videoclip.signature import current_input_hash

    report["delivery_ready"] = True
    report["input_hash"] = current_input_hash(root)
    _write_report(output, report)
    return report


def render_preview(root: Path, output: Path | None = None) -> dict:
    """Marked preview plus the exact review report the preview approval binds."""
    project = P.load_project(root)
    shots = P.resolved_assets(root)
    directory = root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    output = output or _next_output(directory, f"{project.slug}-preview")
    report = _render(
        project,
        shots,
        P.render_audio(root, project),
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
