"""Projects: list, open, create from an upload id, read-only archive view."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import valid_slug
from mp3_to_videoclip.domain import archive
from mp3_to_videoclip.storage import read_json, read_optional

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
    error: str | None = None


@router.get("", response_model=list[ProjectSummary])
async def list_projects(request: Request):
    root = _projects_dir(request)
    if not root.is_dir():
        return []
    result: list[ProjectSummary] = []
    for entry in sorted(root.iterdir()):
        if (
            not entry.is_dir()
            or not valid_slug(entry.name)
            or not (entry / "project.json").is_file()
        ):
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
            assets_path = entry / "work" / "assets.json"
            assets = read_json(assets_path) if assets_path.is_file() else {}
            result.append(
                ProjectSummary(
                    # Routes are folder-based; never advertise an internal slug
                    # that does not open the production the card represents.
                    slug=entry.name,
                    title=project.title,
                    duration=project.duration,
                    archived=False,
                    still_count=sum(
                        1
                        for item in assets.values()
                        if isinstance(item, dict) and item.get("selected") is not None
                    ),
                )
            )
        except Exception:
            # A production the app cannot load must stay visible: silently
            # dropping it looks exactly like data loss.
            result.append(
                ProjectSummary(
                    slug=entry.name,
                    title=entry.name.replace("-", " ").title(),
                    archived=False,
                    error=(
                        "This production could not be loaded. Check project.json "
                        "and its source audio before opening it."
                    ),
                )
            )
    return result


@router.post("", status_code=201)
async def create_project(
    request: Request,
    title: str,
    filename: str,
    aspect: Literal["16:9", "9:16"] = "16:9",
    music_mode: Literal["vocal", "instrumental"] = "vocal",
    budget: str | None = None,
):
    """Upload one MP3, create a schema 3 production and queue local analysis."""
    from mp3_to_videoclip import services
    from mp3_to_videoclip.config import effective_settings
    from mp3_to_videoclip.domain import intake

    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ("audio/mpeg", "audio/mp3", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="upload an audio/mpeg file")
    name = Path(filename).name
    if not name.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="the source must be an MP3")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > intake.MAX_SOURCE_BYTES:
                raise HTTPException(status_code=413, detail="the MP3 is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content length") from exc
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the upload is empty")
    if len(data) > intake.MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="the MP3 is too large")

    cap = budget
    if cap is None:
        cap = f"{effective_settings().default_budget_usd:.2f}"
    projects_dir = _projects_dir(request)
    with tempfile.TemporaryDirectory(prefix="mp3-intake-") as temp:
        source = Path(temp) / "source.mp3"
        source.write_bytes(data)
        try:
            created = intake.create_from_upload(
                projects_dir,
                source,
                title=title,
                aspect=aspect,
                music_mode=music_mode,
                budget=cap,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = created["root"]
    project = P.load_project(root)
    job_id = None
    runner = getattr(request.app.state, "runner", None)
    if runner is not None:

        async def work():
            return await asyncio.to_thread(services.analysis.analyze_project, root)

        job_id = runner.submit("analysis", created["slug"], work)
    return {
        "slug": created["slug"],
        "title": project.title,
        "duration": project.duration,
        "analysis_job": job_id,
    }


@router.get("/{slug}")
async def get_project(slug: str, request: Request, verify: bool = False):
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="project not found")
    root = _projects_dir(request) / slug
    if not root.is_dir() or not (root / "project.json").is_file():
        raise HTTPException(status_code=404, detail="project not found")
    if not isinstance(read_optional(root / "project.json"), dict):
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
    board_path = root / "work" / "storyboard.json"
    board = P.load_board(root) if board_path.is_file() else None
    assets_path = root / "work" / "assets.json"
    assets = read_json(assets_path) if assets_path.is_file() else {}
    approvals_path = root / "work" / "approvals.json"
    approvals = read_json(approvals_path) if approvals_path.is_file() else {}
    result = {
        "slug": root.name,
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
