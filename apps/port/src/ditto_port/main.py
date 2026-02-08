"""
Ditto FastAPI 主应用.

量化系统的REST API服务器入口点
"""

# Standard library imports
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

# Third-party imports
import granian
import orjson

# Local imports - using editable packages
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from ditto_datahub import register_datahub_providers
from ditto_datahub.config import DataRootConfig
from ditto_foundation.config.initializer import ConfigInitCoordinator, InitScope
from ditto_foundation.config.settings import Settings
from ditto_foundation.observability import M, logger
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ditto_port.exceptions import DittoException
from ditto_port.middleware import (
    ditto_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from ditto_port.registry import (
    ConfigProvider,
    CoreProvider,
    DataHubProvider,
    DataSourcesProvider,
    DomainServiceProvider,
)

# Initialize project root
project_root = Path(__file__).parent.parent.parent.parent

T = TypeVar("T")


class AsyncContainerProtocol(Protocol):
    """简化版容器协议（屏蔽未标注的第三方类型）。"""

    async def get(self, dependency_type: type[T]) -> T:
        """获取依赖实例。"""
        ...

    async def close(self) -> None:
        """关闭容器并释放资源。"""
        ...


class ORJSONResponse(JSONResponse):
    """
    使用 orjson 的 FastAPI 响应类.

    性能提升：
    - 序列化：4.5-11.5x 更快
    - 反序列化：2-5x 更快
    - 内存占用：更小
    """

    def render(self, content: Any) -> bytes:
        """使用 orjson 序列化内容."""
        # 记录序列化指标
        start_time = time.monotonic()

        # 使用 orjson 序列化
        result = orjson.dumps(content)

        # 记录序列化耗时
        duration = time.monotonic() - start_time
        M.json_serialize_duration.record(duration)
        M.json_bytes_total.add(len(result))

        return result


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager（使用 dishka 容器）.

    容器负责：
    - Observability 初始化/关闭
    - SQLitePool 创建/关闭
    - DataHub 创建
    """
    logger.info("Starting Ditto API server", event="server_start")

    # 创建容器（在 try 块之前，避免未绑定问题）
    container = make_async_container(
        ConfigProvider(),
        CoreProvider(),
        DomainServiceProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
    typed_container = cast(AsyncContainerProtocol, container)

    try:
        # 集成到 FastAPI
        setup_dishka(container=container, app=app)

        # 初始化配置（静默自动初始化）
        logger.info("Initializing configuration", event="config_init_start")
        coordinator: ConfigInitCoordinator = await typed_container.get(
            ConfigInitCoordinator
        )
        data_root_config: DataRootConfig = await typed_container.get(DataRootConfig)
        register_datahub_providers(coordinator)
        coordinator.initialize(
            scope=InitScope.STARTUP,
            data_root=data_root_config.data_root,
        )
        logger.info(
            "Configuration initialized",
            event="config_init_complete",
            data_root=str(data_root_config.data_root),
        )

        app.state.settings = await typed_container.get(Settings)

        yield
    except Exception as e:
        logger.exception(
            "Failed to initialize application",
            event="server_init_failed",
            error=str(e),
        )
        raise
    finally:
        # 关闭容器（自动清理所有资源）
        logger.info("Shutting down Ditto API server", event="server_shutdown")
        await typed_container.close()


# 创建FastAPI应用实例
app = FastAPI(
    title="Ditto Quant API",
    description="量化投资系统API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,  # 使用 orjson 提升性能
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

    except Exception:
        # Re-raise exception to let FastAPI exception handlers process it
        raise


@app.get("/")
async def root() -> dict[str, str]:
    """根路径."""
    logger.info("Root endpoint accessed")
    return {"message": "Ditto Quant API", "version": "0.1.0"}


@app.get("/healthz")
async def health_check() -> dict[str, Any]:
    """健康检查端点."""
    logger.debug("Health check endpoint accessed", event="health_check")
    return {
        "status": "ok",
        "service": "ditto-api",
        "timestamp": time.time(),
        "features": {
            "prefect": True,  # Prefect flows available
            "observability": True,
        },
    }


@app.get("/api/v1/status")
async def get_status(request: Request) -> dict[str, Any]:
    """获取系统状态."""
    logger.info("Status endpoint accessed")
    return {
        "status": "running",
        "version": "0.1.0",
        "environment": request.app.state.settings.system.environment.value,
        "features": {
            "data_collection": True,
            "data_validation": True,
            "backtest": False,
            "trading": False,
        },
        "observability": {
            "level": request.app.state.settings.observability.log_level,
            "structured": True,
        },
    }


@app.get("/api/v1/logs/test")
async def generate_test_logs() -> dict[str, str]:
    """测试日志记录功能."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}


# 注册异常处理器
app.add_exception_handler(DittoException, ditto_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


if __name__ == "__main__":
    granian.Granian(
        "main:app",
        address="0.0.0.0:8000",
        reload=True,
    ).serve()
