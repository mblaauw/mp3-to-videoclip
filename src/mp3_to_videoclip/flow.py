"""Guided creative-flow policy for new productions.

New productions use a simpler human flow: music is analysed for creative use,
the story and storyboard are agreed together, a small style check is approved,
the full image set is reviewed, and credits are confirmed at the end.

The policy marker lives in ``work/guided-flow.json`` and carries the production's
source hash and slug. A marker copied from another production is ignored, so a
stray file cannot silently change a recorded v2 project's hashes or credit rules.
A marker written for this exact production is an explicit policy decision.
Productions without a matching marker keep their recorded v2 gates exactly,
including the mandatory watched preview and the signature digest inside the brief
approval.
"""

from __future__ import annotations

from pathlib import Path

from .storage import read_optional, write_json

FILE = "work/guided-flow.json"
VERSION = 1


def _project_identity(root: Path) -> tuple[str | None, str | None]:
    project = read_optional(Path(root) / "project.json")
    if not isinstance(project, dict):
        return None, None
    source = project.get("source_sha256")
    slug = project.get("slug")
    return (
        source if isinstance(source, str) and source else None,
        slug if isinstance(slug, str) and slug else None,
    )


def settings(root: Path) -> dict:
    value = read_optional(Path(root) / FILE)
    source, slug = _project_identity(root)
    guided = (
        isinstance(value, dict)
        and value.get("version") == VERSION
        and source is not None
        and slug is not None
        and value.get("source_sha256") == source
        and value.get("slug") == slug
    )
    return {
        "guided": guided,
        "preview_gate": not guided,
        "late_credits": guided,
    }


def guided(root: Path) -> bool:
    return settings(root)["guided"]


def mark(root: Path, *, force: bool = False) -> dict:
    """Record the guided policy for this exact production.

    Refuses to convert a production that already has recorded decisions unless
    the caller explicitly forces it: adding the marker changes the brief hash and
    the full-stills gate, so it is a migration, never a casual edit.
    """
    approvals = read_optional(Path(root) / "work/approvals.json") or {}
    if approvals and not force:
        raise ValueError(
            "this production already has recorded decisions; guided policy is for "
            "new productions (pass force=True only for an explicit migration)"
        )
    source, slug = _project_identity(root)
    value = {"version": VERSION, "source_sha256": source, "slug": slug}
    write_json(Path(root) / FILE, value)
    return value
