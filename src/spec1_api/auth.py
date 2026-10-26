# @domain:   machine
# @module:   auth
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""Optional API-key authentication middleware for spec1_api.

Enabled by setting ``SPEC1_API_KEY`` in the environment.  When set, every
request that is *not* on the excluded paths must supply the key via one of:

- HTTP header ``X-API-Key: <key>``
- Query parameter ``?api_key=<key>``

If the key is wrong a ``403 Forbidden`` is returned.
If ``SPEC1_API_KEY`` is unset the middleware is a no-op (open access).

Excluded paths (no key required):
- ``/health``
- ``/metrics``
- ``/`` (UI root)
- ``/docs``, ``/redoc``, ``/openapi.json``
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that never require authentication
_PUBLIC_PATHS = frozenset({
    "/",
    "/desk/legislative",      # page shell only; its data calls carry the key
    "/desk/legislative/",
    "/health",
    "/metrics",
    "/metrics/json",
    "/docs",
    "/redoc",
    "/openapi.json",
})

# Prefix exemptions (e.g. static assets)
_PUBLIC_PREFIXES = ("/static/",)


def _get_configured_key() -> Optional[str]:
    """Return the configured API key, or None if auth is disabled."""
    key = os.environ.get("SPEC1_API_KEY", "").strip()
    return key if key else None


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces API-key authentication.

    The middleware is a no-op when ``SPEC1_API_KEY`` is not set.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        required_key = _get_configured_key()

        # Auth disabled — pass through
        if required_key is None:
            return await call_next(request)

        path = request.url.path

        # Public paths — pass through
        if path in _PUBLIC_PATHS:
            return await call_next(request)
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Check header first, then query param
        supplied = (
            request.headers.get("X-API-Key")
            or request.query_params.get("api_key")
        )

        if supplied == required_key:
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={"detail": "Invalid or missing API key"},
        )
