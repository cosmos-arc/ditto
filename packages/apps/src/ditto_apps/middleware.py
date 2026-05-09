"""错误处理中间件."""

from __future__ import annotations

import time
from typing import Any

from ditto_kernel.exceptions import DataError, DittoError, IdentifierError
from ditto_platform.foundation import logger
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.errors import APIError
from .models.common import ErrorResponse


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
    is_server_error = exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
    log_level = logger.error if is_server_error else logger.warning
    log_level(
        "API error occurred",
        error=exc.message,
        error_code=exc.error_code,
        status_code=exc.status_code,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
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
    http_status = _map_data_error_status(exc)
    is_server_error = http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR
    log_level = logger.error if is_server_error else logger.warning
    log_level(
        "Data error occurred",
        error=str(exc),
        error_type=exc.__class__.__name__,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
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
    error_msg = str(exc)
    error_code = getattr(exc, "error_code", None) or exc.__class__.__name__
    logger.error(
        "Ditto error occurred",
        error=error_msg,
        error_code=error_code,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
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
    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=exc.status_code,
            error="HTTP_ERROR",
            detail=str(exc.detail),
            request_id=request_id,
        )
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """处理请求验证异常."""
    if not isinstance(exc, RequestValidationError):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)

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
        method=request.method,
        request_id=request_id,
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

    # 记录异常堆栈
    logger.exception(
        "Unhandled exception occurred",
        error=str(exc),
        error_type=exc.__class__.__name__,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
    )

    return create_error_response(
        ErrorResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="INTERNAL_SERVER_ERROR",
            detail="An unexpected error occurred",
            request_id=request_id,
        )
    )
