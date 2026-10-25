"""FastAPI application factory for the Studio.

Phase 2 skeleton: a health check, the static frontend mount and the loopback/Origin
guards from D8. Routers and the job runner land in the following commits; the
interim ``serve.py`` stays available until the frontend replaces it.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .api.budget import router as budget_router
from .api.director import router as director_router
from .api.film import router as film_router
from .api.images import router as images_router
from .api.jobs import router as jobs_router
from .api.projects import router as projects_router
from .api.settings import router as settings_router
from .api.story import router as story_router
from .api.storyboard import router as storyboard_router
from .api.track import router as track_router
from .jobs import JobRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner = JobRunner()
    await runner.start()
    app.state.runner = runner
    yield
    await runner.stop()


def create_app(projects_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="mp3-to-videoclip Studio", lifespan=lifespan)
    if projects_dir is not None:
        app.state.projects_dir = str(projects_dir)
    app.include_router(projects_router)
    app.include_router(settings_router)
    app.include_router(track_router)
    app.include_router(story_router)
    app.include_router(storyboard_router)
    app.include_router(images_router)
    app.include_router(film_router)
    app.include_router(budget_router)
    app.include_router(director_router)
    app.include_router(jobs_router)

    @app.get("/api/events")
    async def events(request: Request):
        runner: JobRunner = request.app.state.runner
        queue = runner.bus.subscribe()

        async def stream():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=10.0)
                        yield {"event": msg["event"], "data": msg["payload"]}
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": {}}
            finally:
                runner.bus.unsubscribe(queue)

        return EventSourceResponse(stream())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=[],
        allow_headers=[],
    )

    @app.middleware("http")
    async def loopback_and_origin(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost", ""):
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin is not None and origin not in (
                "http://127.0.0.1:8000",
                "http://localhost:8000",
            ):
                return JSONResponse({"detail": "origin not allowed"}, status_code=403)
            if (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                return JSONResponse({"detail": "JSON required"}, status_code=415)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "read_only": False, "review_only": True}

    frontend = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app
