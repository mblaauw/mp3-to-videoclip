"""FastAPI application factory for the Studio.

Phase 2 skeleton: a health check, the static frontend mount and the loopback/Origin
guards from D8. Routers and the job runner land in the following commits; the
interim ``serve.py`` stays available until the frontend replaces it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app(projects_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="mp3-to-videoclip Studio", lifespan=lifespan)

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
