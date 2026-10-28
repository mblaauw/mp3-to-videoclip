"""Read-only, conservative interpretation of render sidecars."""

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import digest, file_hash, read_json, snapshot_read


def input_metadata_hash(root: Path) -> str:
    """Cheap change detector; never read all source/still/movie bytes in a list."""
    paths = [root / "project.json", root / "brief.json", root / "brand.json"]
    paths += [
        root / "work" / name
        for name in (
            "storyboard.json",
            "assets.json",
            "edit.json",
            "graphics-spec.json",
            "lyrics.json",
            "events.json",
        )
    ]
    values = {str(path.relative_to(root)): read_json(path) for path in paths if path.is_file()}
    if "project.json" in values:
        values["project.json"].pop("budget", None)
    return digest(values)


@snapshot_read
def _current_input_hash(root: Path) -> str:
    from mp3_to_videoclip.signature import current_input_hash

    return current_input_hash(root)


def describe(root: Path, directory: str, name: str) -> dict:
    output = root / directory / name
    result = {
        "kind": directory,
        "name": name,
        "classification": "unknown",
        "verified": False,
        "current": False,
        "delivery_ready": False,
        "reason": "Missing or invalid render report",
    }
    try:
        report = read_json(output.with_suffix(".json"))
        if not isinstance(report, dict) or Path(report.get("output", "")).name != name:
            return result
        kind = report.get("render_kind")
        if kind is None:
            # Historical service bases have an explicit non-delivery verdict.
            if report.get("verified") is True and report.get("delivery_ready") is False:
                kind = "base"
            elif report.get("verified") is True and report.get("delivery_ready") is True:
                kind = "final"
        if kind not in ("base", "preview", "final") or report.get("verified") is not True:
            return result
        expected = report.get("final_output_sha256") or report.get("output_sha256")
        if expected and file_hash(output) != expected:
            result["reason"] = "Output content differs from render report"
            return result
        if kind == "final" and not expected:
            return result
        result.update(classification=kind, verified=True, current=True, reason=None)
        if kind == "final" and report.get("input_hash"):
            try:
                current_input = _current_input_hash(root)
            except (OSError, ValueError, KeyError, TypeError):
                current_input = None
            if report["input_hash"] != current_input:
                result.update(current=False, reason="Render inputs have changed")
        elif kind == "final":
            result.update(current=False, reason="Current render inputs cannot be verified")
        if report.get("input_metadata_hash") and report[
            "input_metadata_hash"
        ] != input_metadata_hash(root):
            result.update(current=False, reason="Render inputs have changed")
        graphics_provenance = report.get("graphics_approval_hash")
        signature_required = kind == "final" and P.requires_signature(root)
        if signature_required and (
            not isinstance(graphics_provenance, str) or not graphics_provenance.strip()
        ):
            result.update(current=False, reason="Graphics provenance cannot be verified")
        elif graphics_provenance:
            try:
                graphics_hash = P.stage_hash(root, "graphics")
            except (OSError, ValueError, KeyError, TypeError):
                graphics_hash = None
            if graphics_provenance != graphics_hash:
                result.update(current=False, reason="Graphics approval has changed")
        if report.get("current") is False:
            result.update(current=False, reason="Inputs changed during rendering")
        result["delivery_ready"] = (
            kind == "final" and result["current"] and report.get("delivery_ready") is True
        )
    except (OSError, ValueError, KeyError, TypeError):
        result.update(classification="unknown", verified=False, current=False, delivery_ready=False)
    return result
