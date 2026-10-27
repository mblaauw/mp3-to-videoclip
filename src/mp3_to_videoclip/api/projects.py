"""Projects: list, open, create from an upload id, read-only archive view."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from mp3_to_videoclip import production as P
from mp3_to_videoclip.api._helpers import valid_slug
from mp3_to_videoclip.domain import archive, budget
from mp3_to_videoclip.storage import read_json, read_optional

router = APIRouter(prefix="/api/projects", tags=["projects"])

StageName = Literal["track", "story", "storyboard", "images", "film"]
StageWord = Literal["done", "you", "changed", "not_ready"]


def _projects_dir(request: Request) -> Path:
    return Path(getattr(request.app.state, "projects_dir", "projects"))


class ProjectSummary(BaseModel):
    slug: str
    title: str
    duration: float | None = None
    kind: str | None = None
    archived: bool = False
    render: str | None = None
    still_count: int = 0
    shots: int = 0
    error: str | None = None
    music_mode: str | None = None
    has_analysis: bool = False
    has_lyrics: bool = False
    signature_required: bool | None = None
    preview_required: bool = False
    poster_stills: list[str] = Field(default_factory=list)
    stage_states: dict[str, StageWord] = Field(default_factory=dict)
    next_step: StageName | None = None
    remaining_usd: str | None = None
    audio_url: str | None = None
    updated_at: str | None = None


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _has_lyrics_words(path: Path) -> bool:
    """A lyrics file only counts when it holds words, timed or plain."""
    if not path.is_file():
        return False
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and bool(value.get("segments") or value.get("lines"))


def _newest(paths: list[Path]) -> float:
    return max((_mtime(path) for path in paths), default=0.0)


def _changed_since(record: dict | None, paths: list[Path]) -> bool:
    """Cheap library signal: an artifact touched after its decision is changed."""
    if not isinstance(record, dict) or not record.get("at"):
        return False
    try:
        approved = datetime.fromisoformat(str(record["at"]))
    except ValueError:
        return False
    if approved.tzinfo is None:
        approved = approved.replace(tzinfo=UTC)
    return _newest(paths) > approved.timestamp() + 1


def _poster_stills(root: Path, slug: str, assets: dict) -> list[str]:
    """First four selected stills, addressed through the image route."""
    result: list[str] = []
    for owner, entry in assets.items():
        if not isinstance(entry, dict):
            continue
        chosen = next(
            (v for v in entry.get("versions", []) if v.get("version") == entry.get("selected")),
            None,
        )
        if not isinstance(chosen, dict) or not isinstance(chosen.get("path"), str):
            continue
        if not (root / chosen["path"]).is_file():
            continue
        result.append(f"/api/projects/{slug}/images/{owner}/{chosen['version']}")
        if len(result) == 4:
            break
    return result


def _stage_states(root: Path, project, approvals: dict) -> dict[str, str]:
    """Cheap stage words for the library.

    This deliberately does not re-hash every gate. It uses the recorded decision
    and artifact mtimes; the approval endpoints remain the authoritative check.
    """
    music_path = root / P.STAGE_FILES["analysis"]
    lyrics_path = root / P.STAGE_FILES["lyrics"]
    brief_path = root / P.STAGE_FILES["brief"]
    board_path = root / P.STAGE_FILES["storyboard"]
    assets_path = root / "work" / "assets.json"
    reviews_path = root / "work" / "reviews.json"

    track_ready = music_path.is_file() and (
        project.music_mode != "vocal"
        or (project.kind not in (None, "music_video"))
        or _has_lyrics_words(lyrics_path)
    )
    states: dict[str, str] = {"track": "done" if track_ready else "you"}

    if not brief_path.is_file():
        states["story"] = "not_ready"
    elif not isinstance(approvals.get("brief"), dict):
        states["story"] = "you"
    elif _changed_since(approvals.get("brief"), [brief_path]):
        states["story"] = "changed"
    else:
        states["story"] = "done"

    if not board_path.is_file():
        states["storyboard"] = "not_ready"
    elif not isinstance(approvals.get("storyboard"), dict):
        states["storyboard"] = "you"
    elif _changed_since(approvals.get("storyboard"), [board_path]):
        states["storyboard"] = "changed"
    else:
        states["storyboard"] = "done"

    if not board_path.is_file():
        states["images"] = "not_ready"
    elif isinstance(approvals.get("stills"), dict):
        if _changed_since(approvals.get("stills"), [assets_path, reviews_path]):
            states["images"] = "changed"
        else:
            states["images"] = "done"
    elif isinstance(approvals.get("proof"), dict):
        if _changed_since(approvals.get("proof"), [brief_path, assets_path, reviews_path]):
            states["images"] = "changed"
        else:
            states["images"] = "you"
    else:
        states["images"] = "you"

    finals = list((root / "renders").glob("*-final-*.mp4"))
    if finals:
        states["film"] = "done"
    elif states["images"] == "done":
        states["film"] = "you"
    else:
        states["film"] = "not_ready"

    return states


def _next_step(states: dict[str, str]) -> str | None:
    for stage in ("track", "story", "storyboard", "images", "film"):
        if states.get(stage) != "done":
            return stage
    return None


def _updated_at(root: Path, paths: list[Path]) -> str | None:
    newest = _newest(paths)
    if not newest:
        return None
    return datetime.fromtimestamp(newest, UTC).isoformat()


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
            poster = [
                f"/api/projects/{film.slug}/archive/stills/{index}"
                for index, _still in enumerate(film.stills[:4])
            ]
            media = [film.render] if film.render is not None else []
            result.append(
                ProjectSummary(
                    slug=film.slug,
                    title=film.title,
                    duration=film.duration,
                    archived=True,
                    render=film.render.name if film.render is not None else None,
                    still_count=len(film.stills),
                    shots=len(film.stills),
                    poster_stills=poster,
                    stage_states={
                        stage: "done"
                        for stage in (
                            "track",
                            "story",
                            "storyboard",
                            "images",
                            "film",
                        )
                    },
                    updated_at=_updated_at(entry, [*media, *film.stills]),
                )
            )
            continue
        try:
            project = P.load_project(entry)
            assets_path = entry / "work" / "assets.json"
            assets = read_json(assets_path) if assets_path.is_file() else {}
            approvals_path = entry / "work" / "approvals.json"
            approvals = read_json(approvals_path) if approvals_path.is_file() else {}
            states = _stage_states(entry, project, approvals)
            try:
                shots = len(P.load_board(entry).shots)
            except (OSError, ValueError):
                shots = 0
            try:
                remaining = budget.remaining(entry)
            except (OSError, ValueError):
                remaining = None
            try:
                signature_required = P.requires_signature(entry, project)
            except (OSError, ValueError):
                signature_required = None
            try:
                preview_required = P.effective_upstream(entry, "stills") == "preview"
            except (OSError, ValueError):
                preview_required = False
            result.append(
                ProjectSummary(
                    # Routes are folder-based; never advertise an internal slug
                    # that does not open the production the card represents.
                    slug=entry.name,
                    title=project.title,
                    duration=project.duration,
                    kind=project.kind,
                    archived=False,
                    still_count=sum(
                        1
                        for item in assets.values()
                        if isinstance(item, dict) and item.get("selected") is not None
                    ),
                    shots=shots,
                    music_mode=project.music_mode,
                    has_analysis=(entry / P.STAGE_FILES["analysis"]).is_file(),
                    has_lyrics=_has_lyrics_words(entry / P.STAGE_FILES["lyrics"]),
                    signature_required=signature_required,
                    preview_required=preview_required,
                    poster_stills=_poster_stills(entry, entry.name, assets),
                    stage_states=states,
                    next_step=_next_step(states),
                    remaining_usd=budget.fmt(remaining) if remaining is not None else None,
                    audio_url=(
                        f"/api/projects/{entry.name}/audio-excerpt"
                        if project.audio_window is not None
                        else f"/api/projects/{entry.name}/audio"
                    ),
                    updated_at=_updated_at(
                        entry,
                        [
                            entry / "project.json",
                            entry / P.STAGE_FILES["brief"],
                            entry / P.STAGE_FILES["storyboard"],
                            assets_path,
                            entry / "work" / "reviews.json",
                        ],
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
    kind: Literal["music_video", "promo", "advert"] = "music_video",
    style_preset: str | None = None,
    objective: str = "",
    message: str = "",
    audience: str = "",
    cta_text: str = "",
    cta_url: str = "",
    length_seconds: float | None = None,
    window_start: float = 0.0,
    fade_in: float = 0.0,
    fade_out: float = 1.5,
):
    """Upload one MP3, create a schema 3 production and queue local analysis."""
    from mp3_to_videoclip import services
    from mp3_to_videoclip.config import effective_settings
    from mp3_to_videoclip.domain import intake
    from mp3_to_videoclip.models import CallToAction, Intent

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
    intent = None
    if kind != "music_video" or any(
        (objective, message, audience, cta_text, cta_url, length_seconds)
    ):
        try:
            intent = Intent(
                kind=kind,
                objective=objective.strip(),
                audience=audience.strip(),
                message=message.strip(),
                cta=CallToAction(text=cta_text.strip(), url=cta_url.strip())
                if (cta_text.strip() or cta_url.strip())
                else None,
                length_seconds=int(length_seconds) if length_seconds is not None else None,
            ).model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
                kind=kind,
                intent=intent,
                style_preset=style_preset or None,
                length_seconds=length_seconds,
                window_start=window_start if kind != "music_video" else 0.0,
                fade_in=fade_in if kind != "music_video" else 0.0,
                fade_out=fade_out if kind != "music_video" else 0.0,
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

        job_id = runner.submit("analysis", created["slug"], work, blocking=True)
    return {
        "slug": created["slug"],
        "title": project.title,
        "kind": project.kind,
        "duration": project.duration,
        "source_duration": project.source_duration,
        "audio_window": (
            project.audio_window.model_dump() if project.audio_window is not None else None
        ),
        "signature_required": project.signature_required,
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
        "kind": project.kind,
        "duration": project.duration,
        "source_duration": project.source_duration or project.duration,
        "audio_window": (
            project.audio_window.model_dump() if project.audio_window is not None else None
        ),
        "style_preset": project.style_preset,
        "signature_required": project.signature_required,
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
