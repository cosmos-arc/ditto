"""错误处理中间件."""

import time
from dataclasses import dataclass
from typing import Any

from ditto_foundation.observability import logger
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import DittoException


@dataclass
class ErrorResponseParams:
    """错误响应参数."""

    status_code: int
    error: str
    detail: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    timestamp: float | None = None


def create_error_response(params: ErrorResponseParams) -> JSONResponse:
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


async def ditto_exception_handler(
    request: Request,
    exc: Exception,  # Changed from DittoException to Exception
) -> JSONResponse:
    """处理 Ditto 自定义异常."""
    if not isinstance(exc, DittoException):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Ditto exception occurred",
        error=exc.message,
        error_code=exc.error_code,
        path=request.url.path,
        method=request.method,
        request_id=request_id,
    )

    return create_error_response(
        ErrorResponseParams(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=exc.__class__.__name__,
            detail=exc.message,
            error_code=exc.error_code,
            request_id=request_id,
        )
    )


async def http_exception_handler(
    request: Request,
    exc: Exception,  # Changed from StarletteHTTPException to Exception
) -> JSONResponse:
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
        ErrorResponseParams(
            status_code=exc.status_code,
            error="HTTP_ERROR",
            detail=str(exc.detail),
            request_id=request_id,
        )
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,  # Changed from RequestValidationError to Exception
) -> JSONResponse:
    """处理请求验证异常."""
    if not isinstance(exc, RequestValidationError):
        return await general_exception_handler(request, exc)

    request_id = getattr(request.state, "request_id", None)

    # 格式化验证错误
    errors = []
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
        ErrorResponseParams(
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
        ErrorResponseParams(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="INTERNAL_SERVER_ERROR",
            detail="An unexpected error occurred",
            request_id=request_id,
        )
    )
