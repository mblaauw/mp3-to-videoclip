"""Shared helpers for the API routers."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, Request

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def valid_slug(slug: str) -> bool:
    """A production folder name, never a path fragment."""
    return isinstance(slug, str) and bool(_SLUG.fullmatch(slug))


def project_root(request: Request, slug: str) -> Path:
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="project not found")
    root = Path(getattr(request.app.state, "projects_dir", "projects")) / slug
    if not root.is_dir() or not (root / "project.json").is_file():
        raise HTTPException(status_code=404, detail="project not found")
    from mp3_to_videoclip.domain import archive

    if archive.is_archived(root):
        raise HTTPException(status_code=409, detail="archived production is read-only")
    return root
