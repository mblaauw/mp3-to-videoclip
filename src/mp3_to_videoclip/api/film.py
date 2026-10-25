"""Film stage: graphics spec, preview/final render, exports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from mp3_to_videoclip.api._helpers import project_root

router = APIRouter(prefix="/api/projects/{slug}", tags=["film"])


@router.get("/graphics")
async def get_graphics(slug: str, request: Request):
    root = project_root(request, slug)
    path = root / "work" / "graphics-spec.json"
    if not path.is_file():
        return {"available": False}
    from mp3_to_videoclip.storage import read_json

    return {"available": True, "spec": read_json(path)}


@router.post("/render")
async def render(slug: str, request: Request, payload: dict):
    root = project_root(request, slug)
    kind = payload.get("kind", "preview")
    if kind not in ("preview", "final"):
        raise HTTPException(status_code=400, detail="kind must be preview or final")
    runner = getattr(request.app.state, "runner", None)
    if runner is None:
        return {"error": "job runner unavailable"}
    import asyncio

    from mp3_to_videoclip import services

    async def work():
        fn = services.render.render_final if kind == "final" else services.render.render_preview
        return await asyncio.to_thread(fn, root)

    job_id = runner.submit("render", slug, work)
    return {"job_id": job_id, "kind": kind, "status": "queued"}


@router.get("/exports")
async def list_exports(slug: str, request: Request):
    root = project_root(request, slug)
    renders = root / "renders"
    if not renders.is_dir():
        return {"exports": []}
    return {"exports": [p.name for p in sorted(renders.glob("*.mp4"))]}
