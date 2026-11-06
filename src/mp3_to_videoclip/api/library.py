"""The world library and its series: promoted out of films, adopted into them."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from mp3_to_videoclip import library
from mp3_to_videoclip.api._helpers import project_root, valid_slug
from mp3_to_videoclip.storage import project_lock

router = APIRouter(prefix="/api", tags=["library"])

_FILE = re.compile(r"^[0-9a-f]{64}\.(?:png|jpg|jpeg|webp)$")


def _projects_dir(request: Request) -> Path:
    return Path(getattr(request.app.state, "projects_dir", "projects"))


def library_dir_for(request: Request) -> Path:
    """Where this app's world library is: the flag, the environment, or beside the productions."""
    named = getattr(request.app.state, "library_dir", None)
    return Path(named) if named else library.library_dir(_projects_dir(request))


_lib = library_dir_for


def _public(entry: dict) -> dict:
    files = list(entry.get("files", {}).values())
    return {
        "key": entry["key"],
        "kind": entry["kind"],
        "id": entry["id"],
        "version": entry["version"],
        "label": entry["label"],
        "from": entry["from"],
        "summary": _summary(entry),
        "thumbnail": f"/api/library/references/{files[0]}" if files else None,
        "files": len(files),
    }


def _summary(entry: dict) -> str:
    payload = entry.get("payload") or {}
    if entry["kind"] == "character":
        return str(payload.get("identity") or payload.get("description") or "")[:160]
    if entry["kind"] == "place":
        return str((payload.get("scene") or {}).get("description") or "")[:160]
    if entry["kind"] == "narrator":
        return str(payload.get("persona") or "")[:160]
    return str(payload.get("look") or "")[:160]


def _view(lib: Path) -> dict:
    return {
        "entries": [_public(entry) for entry in library.entries(lib)],
        "series": library.list_series(lib),
    }


@router.get("/library")
def get_library(request: Request):
    return _view(_lib(request))


@router.get("/library/references/{name}")
def get_library_reference(name: str, request: Request):
    if not _FILE.fullmatch(name):
        raise HTTPException(status_code=404, detail="unknown library file")
    path = _lib(request) / library.REFERENCES / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="library file is missing")
    return FileResponse(path)


@router.post("/library/promote")
def promote(request: Request, payload: dict):
    """Copy one thing a film settled into the library. The film is only read."""
    slug = payload.get("slug")
    if not valid_slug(slug):
        raise HTTPException(status_code=404, detail="project not found")
    root = project_root(request, slug)
    entry = library.promote(
        root,
        _lib(request),
        str(payload.get("kind")),
        str(payload.get("id")),
        label=str(payload.get("label") or ""),  # fmt: skip
    )
    return {"entry": _public(entry), **_view(_lib(request))}


@router.get("/library/series/{series_id}")
def get_series(series_id: str, request: Request):
    return library.read_series(_lib(request), series_id)


@router.put("/library/series/{series_id}")
def put_series(series_id: str, request: Request, payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="a series is an object")
    saved = library.write_series(_lib(request), {**payload, "id": series_id})
    return {"saved": saved, **_view(_lib(request))}


@router.post("/projects/{slug}/library/adopt")
def adopt(slug: str, request: Request, payload: dict):
    """Write a library entry into this film's brief as the owner; the story needs approving again."""
    root = project_root(request, slug)
    key = payload.get("key")
    if not isinstance(key, str) or ":" not in key:
        raise HTTPException(status_code=400, detail="name the entry to adopt, as kind:id")
    with project_lock(root):
        return library.adopt(root, _lib(request), key)


@router.post("/projects/{slug}/library/bring-still")
def bring_still(slug: str, request: Request, payload: dict):
    """A still from another film, copied here with its provenance, for an upload shot."""
    root = project_root(request, slug)
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise HTTPException(status_code=400, detail="version is a whole number")
    with project_lock(root):
        return library.bring_still(
            root,
            _projects_dir(request),
            str(payload.get("from_slug")),
            str(payload.get("shot_id")),
            version,  # fmt: skip
        )
