"""
Ditto FastAPI 主应用.

量化系统的REST API服务器入口点
"""

# Standard library imports
import os
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Third-party imports
import uvicorn

# Local imports - using editable packages
# 使用新的 observability 模块
from ditto_foundation.observability import Mode, init, logger, shutdown
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ditto_server.exceptions import DittoException
from ditto_server.middleware import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

# Initialize project root
project_root = Path(__file__).parent.parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Ditto API server")
    try:
        # Initialize observability with environment-specific config
        env = os.getenv("DITTO_ENV", "development")
        log_level = "DEBUG" if env == "development" else "INFO"
        log_dir = str(project_root / "logs")

        # 使用新的 observability init
        init(
            service_name="ditto-server",
            environment=env,
            log_level=log_level,
            log_dir=log_dir,
            mode=Mode.DEVELOPMENT if env == "development" else Mode.PRODUCTION,
        )

        logger.info("Observability configured", environment=env)
        yield
    except Exception as e:
        logger.exception("Failed to initialize application", error=str(e))
        raise
    finally:
        # Shutdown
        logger.info("Shutting down Ditto API server")
        shutdown()


# 创建FastAPI应用实例
app = FastAPI(
    title="Ditto Quant API",
    description="量化投资系统API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log incoming requests and outgoing responses."""
    # Generate unique request ID
    request_id = str(uuid.uuid4())

    # Get start time
    start_time = time.time()

    # Log request
    logger.info(
        f"{request.method} {request.url.path}",
        event="request",
        method=request.method,
        path=request.url.path,
        request_id=request_id,
    )

    # Process request
    try:
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code}",
            event="response",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )

        return response

    except Exception as e:
        # Log error
        duration_ms = (time.time() - start_time) * 1000
        logger.exception(
            "Request processing error",
            event="error",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )

        # Return error response
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request_id,
                "duration_ms": duration_ms,
            },
        )


@app.get("/")
async def root() -> dict[str, str]:
    """根路径."""
    logger.info("Root endpoint accessed")
    return {"message": "Ditto Quant API", "version": "0.1.0"}


@app.get("/healthz")
async def health_check() -> dict[str, Any]:
    """健康检查端点."""
    logger.debug("Health check endpoint accessed")
    return {"status": "ok", "service": "ditto-api", "timestamp": time.time()}


@app.get("/api/v1/status")
async def get_status() -> dict[str, Any]:
    """获取系统状态."""
    logger.info("Status endpoint accessed")
    return {
        "status": "running",
        "version": "0.1.0",
        "environment": os.getenv("DITTO_ENV", "development"),
        "features": {
            "data_collection": True,
            "data_validation": True,
            "backtest": False,
            "trading": False,
        },
        "observability": {
            "level": (
                "DEBUG"
                if os.getenv("DITTO_ENV", "development") == "development"
                else "INFO"
            ),
            "structured": True,
        },
    }


@app.get("/api/v1/logs/test")
async def test_logging() -> dict[str, str]:
    """测试日志记录功能."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}


# 注册异常处理器
app.add_exception_handler(DittoException, general_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
