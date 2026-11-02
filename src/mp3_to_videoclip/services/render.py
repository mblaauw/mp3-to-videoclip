"""Render service: Remotion preview, base, titles review and final."""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import captions, depth, operations
from mp3_to_videoclip import production as P
from mp3_to_videoclip.remotion import WORKING_CAPTURE
from mp3_to_videoclip.remotion import render_base as _render
from mp3_to_videoclip.storage import file_hash, read_snapshot, write_json


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
    if P.load_project(root).spine == "soundtrack":
        # What was measured when the mix was made, so the delivery checklist can say it.
        from mp3_to_videoclip.production import soundtrack

        report["soundtrack"] = soundtrack.receipt(root)


@operations.progress_scope(stage="base-render")
def render_base(root: Path, output: Path | None = None) -> dict:
    """Render the selected stills without graphics; this is never delivery."""
    P.require_approval(root, "stills")
    depth.ensure_for_render(root)
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
        P.film_audio(root, project),
        output,
        root / "work",
        brand=brand,
        capture=WORKING_CAPTURE,
        reuse_chunks=True,
    )
    report["delivery_ready"] = False
    _stamp(root, output, report, "base", provenance)
    # Titles are reviewed from stills of the film itself (check_titles), so a
    # base no longer prepares or replaces the titles review.
    _write_report(output, report)
    return report


#: The streaming norm, applied only to the kinds whose sound is ours to change.
LOUDNESS = {"target_lufs": -14.0, "true_peak": -1.0}
LOUDNESS_KINDS = ("promo", "advert")
FINAL_CAPTURES = {"png": None, "jpeg90": {"format": "jpeg", "quality": 90}}


def loudness_refusal(project) -> str | None:
    """Why this film's sound stays as it is, or ``None`` when it may be normalised."""
    if project.kind in LOUDNESS_KINDS:
        return None
    if project.spine == "soundtrack":
        return "A story film's mix already sets its own loudness."
    return "A music video's master is the mix, so it is never normalised."


def final_options(project, options: dict | None) -> dict:
    """The render arguments for a final's choices. Refuses what this film may not have."""
    options = options or {}
    unknown = set(options) - {"sample_rate", "loudness", "capture"}
    if unknown:
        raise ValueError(f"unknown final options: {', '.join(sorted(unknown))}")
    capture = options.get("capture", "png")
    if capture not in FINAL_CAPTURES:
        raise ValueError("a final's capture is png or jpeg90")
    rate = options.get("sample_rate")
    if rate not in (None, 48000):
        raise ValueError("a final keeps its source rate or uses 48000")
    audio: dict = {}
    if rate:
        audio["sample_rate"] = rate
    if options.get("loudness"):
        refusal = loudness_refusal(project)
        if refusal:
            raise ValueError(refusal)
        audio["loudness"] = LOUDNESS
    result: dict = {"final_capture": capture}
    if FINAL_CAPTURES[capture]:
        result["capture"] = FINAL_CAPTURES[capture]
    if audio:
        result["audio_delivery"] = audio
    return result


def _render_arguments(choices: dict) -> dict:
    return {key: value for key, value in choices.items() if key != "final_capture"}


def _titled_final_inputs(root: Path, project, review: dict) -> dict:
    """Everything the titled final draws, read in the caller's snapshot.

    The titles must hash to the reviewed ones, so the final draws exactly what
    was inspected.
    """
    from mp3_to_videoclip import titles
    from mp3_to_videoclip.storage import digest

    payload = titles.render_input(root)
    if digest(payload) != review["titles_hash"]:
        raise ValueError("the planned titles changed after review; check the titles again")
    return {
        "titles": payload,
        "shots": P.resolved_assets(root),
        "brand": P.load_brand(root),
        "provenance": _provenance(root, "final", graphics=True),
    }


def _render_titled_final(
    root: Path,
    project,
    directory: Path,
    output: Path | None,
    review: dict,
    inputs: dict,
    choices: dict,
) -> dict:
    """One Remotion pass: the reviewed pictures with the reviewed titles drawn in."""
    output = output or _next_output(directory, f"{project.slug}-final")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _render(
        project,
        inputs["shots"],
        P.film_audio(root, project, strict=True),
        output,
        root / "work",
        brand=inputs["brand"],
        titles=inputs["titles"],
        **_render_arguments(choices),
    )
    report["delivery_ready"] = True
    report["final_capture"] = choices["final_capture"]
    report["graphics_review_method"] = review["method"]
    report["captions"] = captions.sidecars_for(root, output, project)
    _stamp(root, output, report, "final", inputs["provenance"])
    _write_report(output, report)
    return report


def check_titles(root: Path) -> dict:
    """Prepare the titles review: stills of the real film with its titles, no base."""
    from mp3_to_videoclip.signature import prepare_titles_review

    P.require_approval(root, "stills")
    project = P.load_project(root)
    if not P.requires_signature(root, project):
        raise ValueError("this film has no intro or credits to check")
    return prepare_titles_review(root, project)


@operations.progress_scope(stage="final-render")
def render_final(root: Path, output: Path | None = None, options: dict | None = None) -> dict:
    """Render delivery: compose approved graphics over the reviewed base."""
    # The full-stills decision is the last human gate before a delivery render.
    P.require_approval(root, "stills")
    depth.ensure_for_render(root)
    project = P.load_project(root)
    choices = final_options(project, options)
    directory = root / "renders"
    directory.mkdir(parents=True, exist_ok=True)

    if P.requires_signature(root, project):
        from mp3_to_videoclip.signature import COMPOSITION_METHOD, OLD_REVIEW, validate_review

        # Both the approval record and the reviewed bytes must still match.
        with read_snapshot(root):
            P.require_approval(root, "graphics")
            review = validate_review(root, project)
            if review.get("method") != COMPOSITION_METHOD:
                raise ValueError(OLD_REVIEW)
            inputs = _titled_final_inputs(root, project, review)
        return _render_titled_final(root, project, directory, output, review, inputs, choices)

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
        P.film_audio(root, project, strict=True),
        output,
        root / "work",
        brand=brand,
        **_render_arguments(choices),
    )
    report["delivery_ready"] = True
    report["final_capture"] = choices["final_capture"]
    report["captions"] = captions.sidecars_for(root, output, project)
    _stamp(root, output, report, "final", provenance)
    _write_report(output, report)
    return report


def _latest_current_final(root: Path) -> Path | None:
    from mp3_to_videoclip.domain.exports import describe

    directory = root / "renders"
    if not directory.is_dir():
        return None
    finals = sorted(
        (path for path in directory.glob("*-final-v*.mp4")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in finals:
        facts = describe(root, "renders", path.name)
        if facts["classification"] == "final" and facts["current"]:
            return path
    return None


def variant_source(root: Path, aspect) -> Path:
    """The current final a version would come from, or why there can be none yet."""
    from mp3_to_videoclip import reframe

    if aspect not in reframe.ASPECTS:
        raise ValueError("a version comes in 9:16 or 1:1")
    project = P.load_project(root)
    if project.width * 16 == project.height * 9 and aspect == "9:16":
        raise ValueError("this film is already 9:16")
    if project.width == project.height and aspect == "1:1":
        raise ValueError("this film is already square")
    final = _latest_current_final(root)
    if final is None:
        raise ValueError("render the final first: a version comes from the current final")
    return final


def _reframe_shots(shots: list, canvas: tuple[int, int]) -> dict:
    """Place every still on its anchor, and say which were guessed or will look soft."""
    from PIL import Image

    from mp3_to_videoclip import reframe, shotkinds

    centred, soft = [], []
    for rs in shots:
        if rs.shot.asset_shot_id is None and shotkinds.is_local(rs.shot):
            continue
        with Image.open(rs.image) as image:
            size = image.size
        anchor = list(rs.edit.motion.anchor) if rs.edit is not None else [0.5, 0.5]
        place = reframe.position(anchor, size, canvas)
        rs.reframe = {"x": place["x"], "y": place["y"]}
        if anchor == [0.5, 0.5]:
            centred.append(rs.shot.id)
        if reframe.is_soft(size, canvas):
            soft.append(rs.shot.id)
    return {"centred": centred, "soft": soft}


@operations.progress_scope(stage="final-render")
def render_variant(root: Path, aspect: str, output: Path | None = None) -> dict:
    """The same cut on another canvas. Not an approval: its inputs are approved and current."""
    from mp3_to_videoclip import reframe, titles

    final = variant_source(root, aspect)
    P.require_approval(root, "stills")
    depth.ensure_for_render(root)
    project = P.load_project(root)
    signature = P.requires_signature(root, project)
    canvas = reframe.canvas_for(project.width, project.height, aspect)
    label = aspect.replace(":", "x")
    directory = root / "renders"
    output = output or _next_output(directory, f"{project.slug}-final-{label}")
    with read_snapshot(root):
        shots = P.resolved_assets(root, canvas=canvas)
        drawn = (
            titles.render_input(root) if signature and titles.has_layout_for(root, aspect) else None
        )
        provenance = _provenance(root, "final", graphics=signature)
    placed = _reframe_shots(shots, canvas)
    report = _render(
        project.model_copy(update={"width": canvas[0], "height": canvas[1]}),
        shots,
        P.film_audio(root, project, strict=True),
        output,
        root / "work",
        titles=drawn,
    )
    report["delivery_ready"] = True
    report["variant_of"] = {"name": final.name, "sha256": file_hash(final), "aspect": aspect}
    report["reframe"] = placed
    if signature and drawn is None:
        report["titles_note"] = "This film's titles have no layout for this shape, so it has none."
    report["captions"] = captions.sidecars_for(root, output, project)
    _stamp(root, output, report, "final", provenance)
    _write_report(output, report)
    return report


#: Previews are for watching with the music, at half size. Bases and finals are untouched.
PREVIEW_SIZES = {"16:9": (960, 540), "9:16": (540, 960)}


@operations.progress_scope(stage="preview-render")
def render_preview(root: Path, output: Path | None = None) -> dict:
    """Marked preview plus the exact review report the preview approval binds."""
    project = P.load_project(root)
    directory = root / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    output = output or _next_output(directory, f"{project.slug}-preview")
    depth.ensure_for_render(root)
    with read_snapshot(root):
        project = P.load_project(root)
        shots, placeholders = P.preview_assets(root)
        brand = P.load_brand(root)
        provenance = _provenance(root, "preview")
    width, height = PREVIEW_SIZES.get(project.aspect, (project.width, project.height))
    report = _render(
        project.model_copy(update={"width": width, "height": height}),
        shots,
        P.film_audio(root, project),
        output,
        root / "work",
        preview_banner=True,
        preview_placeholders=tuple(placeholders),
        brand=brand,
        capture=WORKING_CAPTURE,
        reuse_chunks=True,
    )
    report["delivery_ready"] = False
    _stamp(root, output, report, "preview", provenance)
    if placeholders or not report["current"]:
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
