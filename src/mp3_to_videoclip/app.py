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
from .api.errors import error_code, error_payload
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
from .jobs.watch import ProjectWatcher
from .storage import ProjectBusy

MUTATING = ("POST", "PUT", "PATCH", "DELETE")
#: How long the SSE stream waits for an event before it sends a heartbeat.
HEARTBEAT_SECONDS = 15.0
#: The stream checks for a closed tab at least this often.
DISCONNECT_POLL_SECONDS = 2.0


def _projects_dir(app: FastAPI) -> Path:
    return Path(getattr(app.state, "projects_dir", "projects"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner = JobRunner(projects_dir=_projects_dir(app))
    await runner.start()
    app.state.runner = runner
    watcher = ProjectWatcher(_projects_dir(app), runner.bus)
    app.state.watcher = watcher
    await watcher.start()
    yield
    close_gateways()
    await watcher.stop()
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


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _host_port(host: str) -> int | None:
    if host.startswith("["):  # [::1]:8000
        _, _, rest = host.partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    else:
        _, _, port = host.partition(":")
    return int(port) if port.isdigit() else None


def _changed_project(path: str) -> tuple[str | None, bool]:
    """The production slug a mutating request touched, and whether the library did."""
    parts = [part for part in path.split("/") if part]
    if parts[:2] != ["api", "projects"]:
        return None, False
    if len(parts) == 2:
        return None, True  # a new production
    slug = parts[2]
    # Renaming, archiving or deleting a film changes the library card too.
    library = len(parts) == 3 or (len(parts) >= 4 and parts[3] in ("archive", "settings"))
    return slug, library


class StudioGuard:
    """Loopback + same-origin guard, and change notices for every write.

    After a mutating request under ``/api/projects`` finishes with a 2xx status,
    publish ``project.changed`` so every open tab and view reloads that film.
    The notice is sent once the response body is complete, so a streamed
    director turn announces its changes when it ends.
    """

    def __init__(self, app):
        self.app = app

    async def _reject(self, send, detail: str, code: str, status: int) -> None:
        body = json.dumps(error_payload(detail, code)).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        host_header = (_header(scope, b"host") or "").lower()
        host = host_header.split(":")[0] if not host_header.startswith("[") else host_header
        if host.startswith("["):
            host = host[1 : host.index("]")] if "]" in host else host
        if host not in ("127.0.0.1", "localhost", "", "::1"):
            await self._reject(send, "loopback only", "loopback_only", 403)
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if method in MUTATING:
            origin = _header(scope, b"origin")
            if origin is not None and not _origin_allowed(origin, _host_port(host_header)):
                await self._reject(send, "origin not allowed", "origin_not_allowed", 403)
                return
            content_type = (_header(scope, b"content-type") or "").split(";")[0].strip().lower()
            is_upload = method == "POST" and path.rstrip("/") == "/api/projects"
            if (
                not (
                    is_upload
                    and content_type in ("audio/mpeg", "audio/mp3", "application/octet-stream")
                )
                and content_type != "application/json"
            ):
                await self._reject(send, "JSON required", "json_required", 415)
                return
        if method not in MUTATING or not path.startswith("/api/projects"):
            await self.app(scope, receive, send)
            return

        status = {"code": 500}

        async def tracking_send(message):
            if message["type"] == "http.response.start":
                status["code"] = message.get("status", 500)
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                if 200 <= status["code"] < 300:
                    self._announce(scope, path)

        await self.app(scope, receive, tracking_send)

    @staticmethod
    def _announce(scope, path: str) -> None:
        app = scope.get("app")
        state = getattr(app, "state", None)
        runner = getattr(state, "runner", None)
        if runner is None:
            return
        slug, library = _changed_project(path)
        if slug:
            watcher = getattr(state, "watcher", None)
            if watcher is not None:
                try:
                    watcher.absorb(slug)
                except Exception:  # noqa: BLE001 - a notice never fails a saved write
                    pass
            part = path.split("/")[4:5]
            artifact = part[0] if part else None
            artifact = {
                "proof-shots": "brief",
                "music-notes": "track",
                "music-mode": "track",
                "analyze": "track",
                "graphics-review": "graphics",
            }.get(artifact, artifact)
            runner.bus.publish(
                "project.changed",
                {"project": slug, "source": "request", "artifact": artifact},
            )
        if library:
            runner.bus.publish("library.changed", {"source": "request"})


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

    @app.exception_handler(ProjectBusy)
    async def project_busy(_request: Request, exc: ProjectBusy):
        return JSONResponse(error_payload(str(exc), "project_busy"), status_code=409)

    @app.get("/api/events")
    async def events(request: Request):
        runner: JobRunner = request.app.state.runner
        queue = runner.bus.subscribe()

        async def stream():
            # ``retry`` tells the browser how soon to reconnect after a drop.
            yield {"event": "hello", "data": json.dumps({"ok": True}), "retry": 2000}
            loop = asyncio.get_running_loop()
            quiet_since = loop.time()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        # Short wait so a disconnected tab releases the stream promptly.
                        msg = await asyncio.wait_for(queue.get(), timeout=DISCONNECT_POLL_SECONDS)
                    except TimeoutError:
                        if loop.time() - quiet_since >= HEARTBEAT_SECONDS:
                            quiet_since = loop.time()
                            yield {"event": "heartbeat", "data": "{}"}
                        continue
                    quiet_since = loop.time()
                    # sse-starlette stringifies a dict as a Python repr, which
                    # is not JSON. The browser store parses JSON, so encode it.
                    yield {
                        "id": str(msg.get("id", "")),
                        "event": msg["event"],
                        "data": json.dumps(msg["payload"], default=str),
                    }
            finally:
                runner.bus.unsubscribe(queue)

        return EventSourceResponse(
            stream(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=False,
        allow_methods=[],
        allow_headers=[],
    )
    # Pure ASGI (not ``@app.middleware("http")``): BaseHTTPMiddleware wraps every
    # response in a memory stream, which delays and can stall the SSE stream and
    # the director's NDJSON stream behind it.
    app.add_middleware(StudioGuard)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "read_only": False, "review_only": True}

    frontend = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app
