"""FastAPI application factory for the Studio.

One loopback process owns the library, the five stages, the director, the job
runner and the static frontend. The engine stays importable without this layer.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from .api.approvals import router as approvals_router
from .api.budget import router as budget_router
from .api.director import close_gateways
from .api.director import router as director_router
from .api.film import router as film_router
from .api.images import router as images_router
from .api.jobs import router as jobs_router
from .api.projects import router as projects_router
from .api.ratings import router as ratings_router
from .api.settings import router as settings_router
from .api.setup import router as setup_router
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
    close_gateways()
    await runner.stop()


def _origin_allowed(origin: str, port: int | None) -> bool:
    """Loopback origins only, on this server's port or the Vite dev port."""
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        return False
    return parsed.port in (5173, 8000) or parsed.port == port


def create_app(projects_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="mp3-to-videoclip Studio", lifespan=lifespan)
    if projects_dir is not None:
        app.state.projects_dir = str(projects_dir)
    app.include_router(projects_router)
    app.include_router(settings_router)
    app.include_router(setup_router)
    app.include_router(track_router)
    app.include_router(story_router)
    app.include_router(storyboard_router)
    app.include_router(images_router)
    app.include_router(film_router)
    app.include_router(budget_router)
    app.include_router(approvals_router)
    app.include_router(ratings_router)
    app.include_router(director_router)
    app.include_router(jobs_router)

    @app.get("/api/events")
    async def events(request: Request):
        runner: JobRunner = request.app.state.runner
        queue = runner.bus.subscribe()

        async def stream():
            yield {"event": "hello", "data": {"ok": True}}
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        # Short wait so a disconnected tab releases the stream promptly;
                        # the heartbeat also keeps local proxies from timing out.
                        msg = await asyncio.wait_for(queue.get(), timeout=2.0)
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
            if origin is not None and not _origin_allowed(origin, request.url.port):
                return JSONResponse({"detail": "origin not allowed"}, status_code=403)
            content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/api/projects"
            if (
                not (
                    is_upload
                    and content_type in ("audio/mpeg", "audio/mp3", "application/octet-stream")
                )
                and content_type != "application/json"
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
