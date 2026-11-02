"""Reviews of the old compositor's samples, for the CLI that can still make them."""

from __future__ import annotations

from pathlib import Path

from .. import operations
from ..graphics import implementation_revision
from ..signature import (
    REVIEW,
    SPEC,
    current_input_hash,
    validate_spec,
)
from ..storage import digest, file_hash, inside, read_json, write_json
from .graphics_compose import preflight_frames


def prepare_review(root: Path, base: Path, project) -> dict:
    resolved_spec = validate_spec(root, project)
    spec_hash, base_hash = digest(read_json(root / SPEC)), file_hash(base)
    # The implementation revision belongs in the key. The composited samples are a
    # function of the renderer's bytes as much as of the spec and the base, so
    # keying on spec+base alone reused preflights drawn by older code and handed
    # back composites that no longer matched what the renderer produces.
    revision = implementation_revision()
    resolved_hash = digest(resolved_spec)
    key = digest([spec_hash, resolved_hash, base_hash, revision])[:16]
    directory = root / "work/reviews" / f"signature-{key}"
    preflight = directory / "preflight.json"
    if not preflight.exists() or read_json(preflight).get("implementation_revision") != revision:
        operations.phase("sampling-graphics")
        report = preflight_frames(root, base, directory)
        preflight = Path(report["sidecar"])
    samples = {}
    for frame in read_json(preflight)["frames"]:
        path = Path(frame["image"])
        relative = (
            str(path.resolve().relative_to(root.resolve())) if path.is_absolute() else str(path)
        )
        samples[relative] = file_hash(inside(root, relative))
    value = {
        "base": str(base.relative_to(root)),
        "base_sha256": base_hash,
        "base_input_hash": current_input_hash(root),
        "spec_hash": spec_hash,
        "resolved_spec_hash": resolved_hash,
        "implementation_revision": revision,
        "preflight": str(preflight.relative_to(root)),
        "preflight_sha256": file_hash(preflight),
        "samples": samples,
        "warning": "Inspect the actual composited preflight samples in Studio, then approve graphics with the inspected attestation; this base is not final.",
    }
    write_json(root / REVIEW, value)
    operations.phase("awaiting-owner-review")
    return value


def validate_old_review(root: Path, project) -> dict:
    """A review made by the compositor, bound to the base it sampled. CLI only."""
    value = read_json(root / REVIEW)
    resolved_spec = validate_spec(root, project)
    if value["spec_hash"] != digest(read_json(root / SPEC)):
        raise ValueError("graphics spec changed; recreate preflight and renew graphics review")
    if value["base_sha256"] != file_hash(inside(root, value["base"])):
        raise ValueError("graphics base changed; recreate preflight and renew graphics review")
    base_report = read_json(inside(root, value["base"]).with_suffix(".json"))
    current = current_input_hash(root)
    if value.get("base_input_hash") != current or base_report.get("input_hash") != current:
        raise ValueError(
            "graphics base belongs to obsolete storyboard/stills inputs; render a current base and renew graphics review"
        )
    preflight = inside(root, value["preflight"])
    if value["preflight_sha256"] != file_hash(preflight):
        raise ValueError("graphics preflight changed; renew review")
    facts = read_json(preflight)
    revision = implementation_revision()
    if (
        value.get("implementation_revision") != revision
        or facts.get("implementation_revision") != revision
    ):
        raise ValueError(
            "graphics implementation changed; recreate preflight and renew graphics review"
        )
    if value.get("resolved_spec_hash") != digest(resolved_spec) or facts.get(
        "spec_sha256"
    ) != digest(resolved_spec):
        raise ValueError("graphics identity changed; recreate preflight and renew graphics review")
    if facts["base"]["sha256"] != value["base_sha256"]:
        raise ValueError("graphics preflight belongs to another base")
    if facts.get("truncated") or not facts.get("frames"):
        raise ValueError("graphics preflight must cover the complete signature")
    if len(value.get("samples", {})) != len(facts["frames"]):
        raise ValueError("graphics review must bind every sampled image")
    for relative, expected in value["samples"].items():
        if file_hash(inside(root, relative)) != expected:
            raise ValueError("graphics review sample changed; renew inspection")
    return value
