"""FastAPI application factory for the Studio.

One loopback process owns the library, the five stages, the director, the job
runner and the static frontend. The engine stays importable without this layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.approvals import router as approvals_router
from .api.budget import router as budget_router
from .api.director import close_gateways
from .api.director import router as director_router
from .api.errors import error_code, error_payload, error_response
from .api.film import router as film_router
from .api.history import router as history_router
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


logger = logging.getLogger(__name__)


def create_app(projects_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="mp3-to-videoclip Studio", lifespan=lifespan)
    if projects_dir is not None:
        # Keep every API project root absolute. Asset paths are resolved before
        # indexing; a relative root makes path.relative_to(root) fail after a
        # paid result has already been fetched.
        app.state.projects_dir = str(Path(projects_dir).resolve())

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            error_payload(jsonable_encoder(exc.detail), error_code(exc)),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            error_payload(jsonable_encoder(exc.errors()), "validation_error"),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("unhandled API error on %s %s", request.method, request.url.path)
        return JSONResponse(error_payload("internal error", "internal_error"), status_code=500)

    app.include_router(projects_router)
    app.include_router(settings_router)
    app.include_router(setup_router)
    app.include_router(track_router)
    app.include_router(story_router)
    app.include_router(storyboard_router)
    app.include_router(images_router)
    app.include_router(film_router)
    app.include_router(history_router)
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
            yield {"event": "hello", "data": json.dumps({"ok": True})}
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        # Short wait so a disconnected tab releases the stream promptly;
                        # the heartbeat also keeps local proxies from timing out.
                        msg = await asyncio.wait_for(queue.get(), timeout=2.0)
                        # sse-starlette stringifies a dict as a Python repr, which
                        # is not JSON. The browser store parses JSON, so encode it.
                        yield {
                            "event": msg["event"],
                            "data": json.dumps(msg["payload"], default=str),
                        }
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": "{}"}
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
            return error_response("loopback only", "loopback_only", 403)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin is not None and not _origin_allowed(origin, request.url.port):
                return error_response("origin not allowed", "origin_not_allowed", 403)
            content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            is_upload = request.method == "POST" and request.url.path.rstrip("/") == "/api/projects"
            if (
                not (
                    is_upload
                    and content_type in ("audio/mpeg", "audio/mp3", "application/octet-stream")
                )
                and content_type != "application/json"
            ):
                return error_response("JSON required", "json_required", 415)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "read_only": False, "review_only": True}

    frontend = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app
