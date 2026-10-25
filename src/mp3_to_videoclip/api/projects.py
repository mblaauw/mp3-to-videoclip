"""Projects: list, open, create from an upload id, read-only archive view."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import archive

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _projects_dir(request: Request) -> Path:
    return Path(getattr(request.app.state, "projects_dir", "projects"))


class ProjectSummary(BaseModel):
    slug: str
    title: str
    duration: float | None = None
    archived: bool = False
    render: str | None = None
    still_count: int = 0


@router.get("", response_model=list[ProjectSummary])
async def list_projects(request: Request):
    root = _projects_dir(request)
    if not root.is_dir():
        return []
    result: list[ProjectSummary] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not (entry / "project.json").is_file():
            continue
        if archive.is_archived(entry):
            film = archive.read(entry)
            result.append(
                ProjectSummary(
                    slug=film.slug,
                    title=film.title,
                    duration=film.duration,
                    archived=True,
                    render=str(film.render) if film.render else None,
                    still_count=len(film.stills),
                )
            )
            continue
        try:
            project = P.load_project(entry)
            result.append(
                ProjectSummary(
                    slug=project.slug,
                    title=project.title,
                    duration=project.duration,
                    archived=False,
                )
            )
        except Exception:
            continue
    return result


@router.get("/{slug}")
async def get_project(slug: str, request: Request, verify: bool = False):
    root = _projects_dir(request) / slug
    if not root.is_dir() or not (root / "project.json").is_file():
        raise HTTPException(status_code=404, detail="project not found")
    if archive.is_archived(root):
        film = archive.read(root)
        return {
            "slug": film.slug,
            "title": film.title,
            "duration": film.duration,
            "archived": True,
            "render": str(film.render) if film.render else None,
            "stills": [str(p) for p in film.stills],
        }
    project = P.load_project(root)
    from mp3_to_videoclip.storage import read_json

    board_path = root / "work" / "storyboard.json"
    board = P.load_board(root) if board_path.is_file() else None
    assets_path = root / "work" / "assets.json"
    assets = read_json(assets_path) if assets_path.is_file() else {}
    approvals_path = root / "work" / "approvals.json"
    approvals = read_json(approvals_path) if approvals_path.is_file() else {}
    result = {
        "slug": project.slug,
        "title": project.title,
        "duration": project.duration,
        "fps": project.fps,
        "width": project.width,
        "height": project.height,
        "music_mode": project.music_mode,
        "archived": False,
        "shots": len(board.shots) if board is not None else 0,
        "stills": sum(
            1
            for entry in assets.values()
            if isinstance(entry, dict) and entry.get("selected") is not None
        ),
        "approvals": sorted(approvals) if isinstance(approvals, dict) else [],
    }
    # Full verification re-hashes every selected still; ask for it explicitly.
    if verify:
        result["status"] = P.status(root)
    return result
