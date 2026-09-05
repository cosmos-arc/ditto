"""FastAPI CORS composition."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from ditto_apps.config.runtime import resolve_cors_origins
from ditto_apps.middleware import create_error_response
from ditto_apps.models.common import ErrorResponse

__all__ = [
    "OriginGuardMiddleware",
    "configure_cors",
    "configure_origin_guard",
]


class OriginGuardMiddleware:
    """Reject browser origins outside the deployment allowlist before execution."""

    def __init__(self, app: ASGIApp, *, allowed_origins: Sequence[str]) -> None:
        self._app = app
        self._allowed_origins = frozenset(allowed_origins)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Allow non-browser clients, or exactly one explicitly allowed Origin."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        origins = [
            value.decode("latin-1")
            for name, value in scope.get("headers", ())
            if name.lower() == b"origin"
        ]
        if not origins:
            await self._app(scope, receive, send)
            return
        if len(origins) == 1 and origins[0] in self._allowed_origins:
            await self._app(scope, receive, send)
            return
        state = scope.get("state")
        request_id = state.get("request_id") if isinstance(state, dict) else None
        response = create_error_response(
            ErrorResponse(
                status_code=403,
                error="CORS_ORIGIN_DENIED",
                detail="Browser origin is not allowed",
                error_code="CORS_ORIGIN_DENIED",
                request_id=request_id if isinstance(request_id, str) else None,
            )
        )
        await response(scope, receive, send)


def configure_origin_guard(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Install the browser-origin execution guard at the current stack position."""
    app.add_middleware(
        OriginGuardMiddleware,
        allowed_origins=resolve_cors_origins(environ),
    )


def configure_cors(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
    origin_guard_already_installed: bool = False,
) -> None:
    """Install CORS using the exact deployment allowlist."""
    origins = resolve_cors_origins(environ)
    if not origin_guard_already_installed:
        configure_origin_guard(app, environ=environ)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )
