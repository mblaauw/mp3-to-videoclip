"""Render service: Remotion base/preview, FFmpeg graphics composite for delivery."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import operations
from mp3_to_videoclip import production as P
from mp3_to_videoclip.render import render as _render
from mp3_to_videoclip.storage import file_hash, inside, read_snapshot, write_json


def _next_output(directory: Path, prefix: str) -> Path:
    version = 1
    while (directory / f"{prefix}-v{version:03d}.mp4").exists():
        version += 1
    return directory / f"{prefix}-v{version:03d}.mp4"


def _write_report(output: Path, report: dict) -> Path:
    path = output.with_suffix(".json")
    write_json(path, report)
    return path


def _provenance(root: Path, kind: str, *, graphics: bool = False) -> dict:
    from mp3_to_videoclip.domain.exports import input_metadata_hash
    from mp3_to_videoclip.signature import current_input_hash

    with read_snapshot(root):
        value = {"input_metadata_hash": input_metadata_hash(root)}
        if kind != "preview":
            value["input_hash"] = current_input_hash(root)
        if graphics:
            value["graphics_approval_hash"] = P.stage_hash(root, "graphics")
        return value


def _stamp(root: Path, output: Path, report: dict, kind: str, provenance: dict) -> None:
    try:
        current = _provenance(root, kind, graphics="graphics_approval_hash" in provenance)
    except (OSError, ValueError, KeyError, TypeError):
        current = None

    report.update(provenance)
    report["render_kind"] = kind
    report["output"] = str(output)
    report["output_sha256"] = file_hash(output)
    report["current"] = current == provenance
    if not report["current"]:
        report["delivery_ready"] = False
    if kind == "final":
        report["final_output_sha256"] = report["output_sha256"]


@operations.progress_scope(stage="base-render")
def render_base(root: Path, output: Path | None = None) -> dict:
    """Render the selected stills without graphics; this is never delivery."""
    P.require_approval(root, "stills")
    project = P.load_project(root)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)
    output = output or _next_output(directory, f"{project.slug}-base")
    output.parent.mkdir(parents=True, exist_ok=True)
    with read_snapshot(root):
        project = P.load_project(root)
        shots = P.resolved_assets(root)
        brand = P.load_brand(root)
        provenance = _provenance(root, "base")
    report = _render(
        project,
        shots,
        P.render_audio(root, project),
        output,
        root / "work",
        brand=brand,
    )
    from mp3_to_videoclip.signature import prepare_review

    report["delivery_ready"] = False
    _stamp(root, output, report, "base", provenance)
    # Write the report before preparing the review: validate_review later reads
    # this sidecar to prove the base belongs to the current storyboard/stills.
    _write_report(output, report)
    if report["current"] and P.requires_signature(root, project):
        report["graphics_review"] = prepare_review(root, output, project)
        _write_report(output, report)
    return report


@operations.progress_scope(stage="final-render")
def render_final(root: Path, output: Path | None = None) -> dict:
    """Render delivery: compose approved graphics over the reviewed base."""
    # The full-stills decision is the last human gate before a delivery render.
    P.require_approval(root, "stills")
    project = P.load_project(root)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)

    if P.requires_signature(root, project):
        from mp3_to_videoclip.graphics import compose
        from mp3_to_videoclip.signature import validate_review

        # Both the approval record and the reviewed bytes must still match.
        with read_snapshot(root):
            P.require_approval(root, "graphics")
            review = validate_review(root, project)
            base = inside(root, review["base"])
            provenance = _provenance(root, "final", graphics=True)
        output = output or _next_output(directory, f"{project.slug}-final")
        report = compose(root, base, output)
        report["delivery_ready"] = True
        # compose already checked frames, identical audio and faststart.
        report["verified"] = True
        # The compositor versions an occupied destination. Its returned path is
        # authoritative; never certify or overwrite the old movie's sidecar.
        _stamp(root, Path(report["output"]), report, "final", provenance)
        _write_report(Path(report["output"]), report)
        return report

    # Projects without a signature have no separate graphics pass.
    output = output or _next_output(directory, f"{project.slug}-final")
    output.parent.mkdir(parents=True, exist_ok=True)
    with read_snapshot(root):
        project = P.load_project(root)
        shots = P.resolved_assets(root)
        brand = P.load_brand(root)
        provenance = _provenance(root, "final")
    report = _render(
        project,
        shots,
        P.render_audio(root, project),
        output,
        root / "work",
        brand=brand,
    )
    report["delivery_ready"] = True
    _stamp(root, output, report, "final", provenance)
    _write_report(output, report)
    return report


@operations.progress_scope(stage="preview-render")
def render_preview(root: Path, output: Path | None = None) -> dict:
    """Marked preview plus the exact review report the preview approval binds."""
    project = P.load_project(root)
    directory = root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    output = output or _next_output(directory, f"{project.slug}-preview")
    with read_snapshot(root):
        project = P.load_project(root)
        shots = P.resolved_assets(root)
        brand = P.load_brand(root)
        provenance = _provenance(root, "preview")
    report = _render(
        project,
        shots,
        P.render_audio(root, project),
        output,
        root / "work",
        preview_banner=True,
        brand=brand,
    )
    report["delivery_ready"] = False
    _stamp(root, output, report, "preview", provenance)
    if not report["current"]:
        report["approval_ready"] = False
        _write_report(output, report)
        return report
    review = write_preview_review(root, output, report)
    report["preview_review"] = str(
        (root / P.STAGE_FILES["preview"]).resolve().relative_to(root.resolve())
    )
    report["approval_ready"] = True
    report["review"] = review
    _write_report(output, report)
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
