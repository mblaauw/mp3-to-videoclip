"""Shared helpers for the API routers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request


def project_root(request: Request, slug: str) -> Path:
    root = Path(getattr(request.app.state, "projects_dir", "projects")) / slug
    if not root.is_dir() or not (root / "project.json").is_file():
        raise HTTPException(status_code=404, detail="project not found")
    from mp3_to_videoclip.domain import archive

    if archive.is_archived(root):
        raise HTTPException(status_code=409, detail="archived production is read-only")
    return root
