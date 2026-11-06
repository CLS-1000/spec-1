"""spec1_api — FastAPI application factory."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from spec1_api import __version__
from spec1_api.routers import (
    brief,
    calibration,
    cycle,
    fara,
    health,
    intel,
    leads,
    psyop,
    signals,
    verdicts,
)
from spec1_api.routers import publication
from spec1_api.scheduler import maybe_run_on_start, start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

# In non-production environments, allow common local dev origins including
# "null" (the file:// origin). In production, read from SPEC1_CORS_ORIGINS
# (comma-separated) or default to an empty allowlist.
_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "null",  # file:// origin sent by browsers opening spec1_ui.html directly
]
_STATIC_DIR = Path(__file__).parent / "static"


def _build_cors_origins() -> list[str]:
    env = os.environ.get("SPEC1_ENVIRONMENT", "production")
    if env in ("development", "dev", "local"):
        return _DEV_ORIGINS
    raw = os.environ.get("SPEC1_CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _political_web_enabled() -> bool:
    """Whether to mount the Portland Political Web routes + viewer.

    Off by default — opt in with SPEC1_POLITICAL_WEB_ENABLED=true. Keeps the
    canonical API surface focused on the core intelligence cycle; the political
    web is an experimental side feature with its own data store.
    """
    return os.environ.get("SPEC1_POLITICAL_WEB_ENABLED", "").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — start/stop scheduler."""
    start_scheduler()
    maybe_run_on_start()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="SPEC-1 Intelligence API",
        description="Real-time OSINT intelligence engine API",
        version=__version__,
        lifespan=lifespan,
    )

    cors_origins = _build_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=bool(cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.get("/", include_in_schema=False)
    async def ui_root() -> FileResponse:
        """Serve the SPEC-1 UI."""
        path = _STATIC_DIR / "index.html"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="UI not found")
        return FileResponse(path, media_type="text/html")

    _API_V1 = "/api/v1"
    app.include_router(health.router, prefix=_API_V1)
    app.include_router(signals.router, prefix=_API_V1)
    app.include_router(intel.router, prefix=_API_V1)
    app.include_router(leads.router, prefix=_API_V1)
    app.include_router(brief.router, prefix=_API_V1)
    app.include_router(psyop.router, prefix=_API_V1)
    app.include_router(fara.router, prefix=_API_V1)
    app.include_router(cycle.router, prefix=_API_V1)
    app.include_router(verdicts.router, prefix=_API_V1)
    app.include_router(calibration.router, prefix=_API_V1)
    app.include_router(publication.router, prefix=_API_V1)

    if _political_web_enabled():
        from spec1_api.routers import ingest, nodes

        @app.get("/portland-web", include_in_schema=False)
        async def portland_web() -> FileResponse:
            """Serve the Portland Political Web force-graph visualization."""
            path = _STATIC_DIR / "portland_political_web.html"
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Portland Political Web not found")
            return FileResponse(path, media_type="text/html")

        app.include_router(nodes.router)
        app.include_router(ingest.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SPEC1_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SPEC1_API_PORT", "8000"))
    uvicorn.run("spec1_api.main:app", host=host, port=port, reload=False)
