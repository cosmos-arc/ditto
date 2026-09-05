"""错误处理中间件."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any, Final, Protocol

from ditto_kernel.exceptions import DataError, DittoError, IdentifierError
from ditto_platform.foundation import Metrics, get_trace_id, logger, span
from ditto_platform.foundation.observability.tracing import SpanKind, StatusCode
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import APIError
from .models.common import ErrorResponse

REQUEST_ID_HEADER: Final = "X-Request-ID"
TRACE_ID_HEADER: Final = "X-Trace-ID"
_UNMATCHED_ROUTE: Final = "unmatched"
_CLIENT_CLOSED_REQUEST_STATUS: Final = 499
_OTHER_HTTP_METHOD: Final = "_OTHER"
_STANDARD_HTTP_METHODS: Final = frozenset(
    {
        "CONNECT",
        "DELETE",
        "GET",
        "HEAD",
        "OPTIONS",
        "PATCH",
        "POST",
        "PUT",
        "TRACE",
    }
)


def configure_exception_handlers(app: FastAPI) -> None:
    """Install the shared runtime and contract error-envelope boundary."""
    app.add_exception_handler(DataError, data_error_handler)
    app.add_exception_handler(DittoError, ditto_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)


class _MutableSpan(Protocol):
    """Span operations needed after FastAPI resolves the route template."""

    def update_name(self, name: str) -> None:
        """Replace the provisional operation name."""
        ...

    def set_attribute(self, key: str, value: str | int) -> None:
        """Attach one bounded attribute."""
        ...

    def set_status(self, status: StatusCode) -> None:
        """Attach the OpenTelemetry terminal status."""
        ...

    def record_exception(self, error: BaseException) -> None:
        """Record one handled exception."""
        ...


def _request_id(request: Request) -> str:
    """Accept only canonical UUID request IDs; replace every other value."""
    candidate = request.headers.get(REQUEST_ID_HEADER)
    if candidate is not None:
        try:
            parsed = uuid.UUID(candidate)
        except ValueError:
            pass
        else:
            if str(parsed) == candidate:
                return candidate
    return str(uuid.uuid4())


def _route_template(scope: Scope) -> str:
    """Return a router-owned template and never an attacker-controlled raw path."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else _UNMATCHED_ROUTE


def _bounded_http_method(raw_method: str) -> str:
    """Map arbitrary request tokens into one finite aggregation dimension."""
    normalized = raw_method.upper()
    if normalized in _STANDARD_HTTP_METHODS:
        return normalized
    return _OTHER_HTTP_METHOD


def _trace_id(request: Request) -> str | None:
    """Read the request trace identifier without requiring middleware in unit tests."""
    value = getattr(request.state, "trace_id", None)
    return value if isinstance(value, str) and value else None


def _set_correlation_headers(
    message: Message,
    *,
    request_id: str,
    trace_id: str,
) -> None:
    """Attach correlation headers to an ASGI response-start message."""
    headers = MutableHeaders(scope=message)
    headers[REQUEST_ID_HEADER] = request_id
    if trace_id:
        headers[TRACE_ID_HEADER] = trace_id


def _record_http_completion(
    *,
    scope: Scope,
    method: str,
    status_code: int,
    outcome: str,
    started_at: float,
    request_span: _MutableSpan,
    monotonic: Callable[[], float],
) -> None:
    """Emit the one terminal log, counter, histogram, and span update."""
    route = _route_template(scope)
    duration = monotonic() - started_at
    metric_attributes: dict[str, Any] = {
        "method": method,
        "route": route,
        "status_code": status_code,
    }
    Metrics.api_requests.add(1, metric_attributes)
    Metrics.api_duration.record(duration, metric_attributes)
    request_span.update_name(f"{method} {route}")
    request_span.set_attribute("http.route", route)
    request_span.set_attribute("http.response.status_code", status_code)
    request_span.set_attribute("ditto.http.outcome", outcome)
    if outcome in {"error", "cancelled"}:
        request_span.set_status(StatusCode.ERROR)
    logger.info(
        "HTTP request completed",
        event="http_request_completed",
        method=method,
        route=route,
        status_code=status_code,
        duration_ms=duration * 1000,
        outcome=outcome,
    )


class HTTPObservabilityMiddleware:
    """Pure ASGI correlation middleware, including streamed response completion."""

    def __init__(
        self,
        app: ASGIApp,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._app = app
        self._monotonic = monotonic

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Observe one ASGI request and pass non-HTTP scopes through unchanged."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        method = _bounded_http_method(request.method)
        request_id = _request_id(request)
        request.state.request_id = request_id
        started_at = self._monotonic()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response_started = False
        outcome = "error"

        with span(
            f"HTTP {method}",
            kind=SpanKind.SERVER,
            **{
                "http.request.method": method,
                "ditto.request_id": request_id,
            },
        ) as request_span:
            trace_id = get_trace_id()
            request.state.trace_id = trace_id or None

            async def send_observed(message: Message) -> None:
                nonlocal response_started, status_code
                if message["type"] == "http.response.start":
                    response_started = True
                    status_code = message["status"]
                    _set_correlation_headers(
                        message,
                        request_id=request_id,
                        trace_id=trace_id,
                    )
                await send(message)

            with logger.contextualize(
                request_id=request_id,
                trace_id=trace_id or None,
            ):
                logger.info(
                    "HTTP request started",
                    event="http_request_started",
                    method=method,
                )
                try:
                    await self._app(scope, receive, send_observed)
                    outcome = (
                        "success"
                        if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
                        else "error"
                    )
                except asyncio.CancelledError:
                    status_code = _CLIENT_CLOSED_REQUEST_STATUS
                    outcome = "cancelled"
                    raise
                except Exception as error:
                    if not response_started:
                        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                    outcome = "error"
                    if response_started:
                        raise
                    request_span.record_exception(error)
                    response = await general_exception_handler(request, error)
                    await response(scope, receive, send_observed)
                finally:
                    _record_http_completion(
                        scope=scope,
                        method=method,
                        status_code=status_code,
                        outcome=outcome,
                        started_at=started_at,
                        request_span=request_span,
                        monotonic=self._monotonic,
                    )


def create_error_response(params: ErrorResponse) -> JSONResponse:
    """创建标准化的错误响应."""
    if params.timestamp is None:
        params.timestamp = time.time()

    content: dict[str, Any] = {
        "success": False,
        "error": params.error,
        "status_code": params.status_code,
        "timestamp": params.timestamp,
    }

    if params.detail:
        content["detail"] = params.detail

    if params.error_code:
        content["error_code"] = params.error_code

    if params.request_id:
        content["request_id"] = params.request_id

    return JSONResponse(
        status_code=params.status_code,
        content=content,
    )


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 API 层异常（APIError 及其子类）。"""
    if not isinstance(exc, APIError):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)
    is_server_error = exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
    log_level = logger.error if is_server_error else logger.warning
    log_level(
        "API error occurred",
        error=exc.message,
        error_code=exc.error_code,
        status_code=exc.status_code,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=exc.status_code,
            error=exc.__class__.__name__,
            detail=exc.message,
            error_code=exc.error_code,
            request_id=request_id,
        )
    )


def _map_data_error_status(exc: DataError) -> int:
    """将 DataError 子类映射为 HTTP 状态码."""
    if isinstance(exc, IdentifierError):
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_422_UNPROCESSABLE_ENTITY


async def data_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 Data 域异常（DataError 及其子类），映射为精细 HTTP 响应."""
    if not isinstance(exc, DataError):
        return await ditto_error_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)
    http_status = _map_data_error_status(exc)
    is_server_error = http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR
    log_level = logger.error if is_server_error else logger.warning
    log_level(
        "Data error occurred",
        error=str(exc),
        error_type=exc.__class__.__name__,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=http_status,
            error=exc.__class__.__name__,
            detail=str(exc),
            error_code=exc.__class__.__name__,
            request_id=request_id,
        )
    )


async def ditto_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 DittoError 域异常（非 APIError、非 DataError 的 DittoError 子类）."""
    # APIError 子类有独立的 status_code，走专用 handler
    if isinstance(exc, APIError):
        return await api_error_handler(request, exc)

    if not isinstance(exc, DittoError):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)
    error_msg = str(exc)
    error_code = getattr(exc, "error_code", None) or exc.__class__.__name__
    logger.error(
        "Ditto error occurred",
        error=error_msg,
        error_code=error_code,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=exc.__class__.__name__,
            detail=error_msg,
            error_code=error_code,
            request_id=request_id,
        )
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 HTTP 异常."""
    if not isinstance(exc, StarletteHTTPException):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)
    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    response = create_error_response(
        ErrorResponse(
            status_code=exc.status_code,
            error="HTTP_ERROR",
            detail=str(exc.detail),
            request_id=request_id,
        )
    )
    if exc.headers is not None:
        response.headers.update(exc.headers)
    return response


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """处理请求验证异常."""
    if not isinstance(exc, RequestValidationError):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)

    # 格式化验证错误
    errors: list[dict[str, object]] = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Request validation failed",
        errors=errors,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error="VALIDATION_ERROR",
            detail="Invalid request parameters",
            request_id=request_id,
        )
    )


async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """处理通用异常."""
    request_id = getattr(request.state, "request_id", None)
    trace_id = _trace_id(request)

    # 记录异常堆栈
    logger.exception(
        "Unhandled exception occurred",
        error=str(exc),
        error_type=exc.__class__.__name__,
        path=request.url.path,
        method=_bounded_http_method(request.method),
        request_id=request_id,
        trace_id=trace_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="INTERNAL_SERVER_ERROR",
            detail="An unexpected error occurred",
            request_id=request_id,
        )
    )
