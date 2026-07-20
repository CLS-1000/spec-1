from __future__ import annotations

import os

from fastapi import FastAPI

from cls_congress.api.router import router


def create_app(api_prefix: str = "/api/v1") -> FastAPI:
    app = FastAPI(
        title="Congress Brief API",
        description="Federal legislative intelligence API built from the SPEC-1 congress domain module.",
        version="0.1.0",
    )
    app.include_router(router, prefix=api_prefix)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SPEC1_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SPEC1_API_PORT", "8000"))
    uvicorn.run("cls_congress.api.main:app", host=host, port=port, reload=False)
