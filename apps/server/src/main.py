"""
Ditto FastAPI 主应用.

量化系统的REST API服务器入口点
"""

# Standard library imports
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

# Third-party imports
import uvicorn

# Local imports - using editable packages
from ditto_foundation.logging_config import (
    LogConfig,
    get_logger,
    request_logger,
    setup_logging,
)
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Initialize project root
project_root = Path(__file__).parent.parent.parent.parent

# Initialize logging
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Ditto API server")
    try:
        # Initialize logging with environment-specific config
        env = os.getenv("DITTO_ENV", "development")
        log_config = LogConfig(
            level="DEBUG" if env == "development" else "INFO",
            json_format=env == "production",
        )
        setup_logging(config=log_config, log_dir=project_root / "logs", env=env)
        logger.info("Logging configured", environment=env)
        yield
    except Exception as e:
        logger.exception("Failed to initialize application", error=str(e))
        raise
    finally:
        # Shutdown
        logger.info("Shutting down Ditto API server")


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
    call_next: Callable[[Request], Response],
) -> Response:
    """Log incoming requests and outgoing responses."""
    # Generate unique request ID
    request_id = str(uuid.uuid4())

    # Add request ID to response headers
    response = Response()
    response.headers["X-Request-ID"] = request_id

    # Get start time
    start_time = time.time()

    # Log request
    request_logger.log_request(
        method=request.method,
        path=request.url.path,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        request_id=request_id,
    )

    # Process request
    try:
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Add request ID to actual response
        response.headers["X-Request-ID"] = request_id

        # Log response
        request_logger.log_response(
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
        request_logger.log_error(
            method=request.method, path=request.url.path, error=e, request_id=request_id
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
async def root() -> dict:
    """根路径."""
    logger.info("Root endpoint accessed")
    return {"message": "Ditto Quant API", "version": "0.1.0"}


@app.get("/healthz")
async def health_check() -> dict:
    """健康检查端点."""
    logger.debug("Health check endpoint accessed")
    return {"status": "ok", "service": "ditto-api", "timestamp": time.time()}


@app.get("/api/v1/status")
async def get_status() -> dict:
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
        "logging": {
            "level": "DEBUG" if logger.logger.level == logging.DEBUG else "INFO",
            "structured": True,
        },
    }


@app.get("/api/v1/logs/test")
async def test_logging() -> dict:
    """测试日志记录功能."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
