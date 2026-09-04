"""
Ditto FastAPI 主应用.

量化系统的REST API服务器入口点
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, TypeVar, cast

# Third-party imports
import granian
import orjson

# Local imports - using editable packages
from dishka.integrations.fastapi import setup_dishka
from ditto_kernel.exceptions import DataError, DittoError
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    ConfigInitError,
    InitScope,
    Metrics,
    Settings,
    get_environment,
    logger,
)
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ditto_apps.api.app_metadata import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    generate_stable_operation_id,
)
from ditto_apps.api.routes.system import (
    get_status,
    health_check,
    root,
)
from ditto_apps.middleware import (
    data_error_handler,
    ditto_error_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from ditto_apps.openapi_contract import configure_openapi, register_application_routes
from ditto_apps.registry.container import make_async_app_container
from ditto_apps.registry.infra.config import data_store_settings_type

# Initialize project root
project_root = Path(__file__).parent.parent.parent.parent

T = TypeVar("T")


_generate_stable_operation_id = generate_stable_operation_id
ditto_version = APP_VERSION

__all__ = ["app", "get_status", "health_check", "root"]


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

    def render(self, content: object) -> bytes:
        """使用 orjson 序列化内容."""
        # 记录序列化指标
        start_time = time.monotonic()

        # 使用 orjson 序列化
        result = orjson.dumps(content)

        # 记录序列化耗时
        duration = time.monotonic() - start_time
        Metrics.json_serialize_duration.record(duration)
        Metrics.json_bytes_total.add(len(result))

        return result


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Application lifespan manager（使用 dishka 容器）.

    容器负责：
    - Observability 初始化/关闭
    - SQLitePool 创建/关闭
    - Data 初始化

    注意：dishka 中间件在应用创建后立即设置，而不是在 lifespan 中。
    """
    logger.info("Starting Ditto API server", event="server_start")

    # 从 app.state 获取容器（由 setup_dishka 设置）
    container = app.state.dishka_container
    typed_container = cast(AsyncContainerProtocol, container)

    try:
        # 初始化配置（fail-fast 模式）
        logger.info("Initializing configuration", event="config_init_start")
        coordinator: ConfigInitCoordinator = await typed_container.get(
            ConfigInitCoordinator
        )
        data_store_settings = await typed_container.get(data_store_settings_type())
        # Providers 已经在容器中注册，无需手动注册
        try:
            coordinator.initialize(
                scope=InitScope.STARTUP,
                data_root=data_store_settings.data_root,
            )
        except ConfigInitError as e:
            logger.error(
                "Startup initialization failed",
                event="config_init_failed",
                failed_providers=e.failed_providers,
                details=e.details,
            )
            raise SystemExit(1) from e
        logger.info(
            "Configuration initialized",
            event="config_init_complete",
            data_root=str(data_store_settings.data_root),
        )

        app.state.settings = await typed_container.get(Settings)

        yield
    except SystemExit:
        raise
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
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=ditto_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    generate_unique_id_function=_generate_stable_operation_id,
    default_response_class=ORJSONResponse,  # 使用 orjson 提升性能
)

configure_openapi(app)

# 在应用启动前设置 dishka（必须在 lifespan 之外）
# 这样中间件可以在应用启动前添加
container = make_async_app_container()
setup_dishka(container=container, app=app)

# 配置 CORS（环境感知）
_env = get_environment()
if _env.is_production:
    _cors_raw = os.environ.get("CORS_ORIGINS", "")
    _cors_origins: list[str] = (
        [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
    )
else:
    _cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_application_routes(app, include_debug=not _env.is_production)


# Request logging middleware
@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log incoming requests and outgoing responses."""
    # Generate unique request ID
    request_id = str(uuid.uuid4())

    # 存储到 request.state，供异常处理器使用
    request.state.request_id = request_id

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


# 注册异常处理器（顺序：从具体到通用）


app.add_exception_handler(DataError, data_error_handler)
app.add_exception_handler(DittoError, ditto_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


if __name__ == "__main__":
    from granian.constants import Interfaces

    granian.Granian(
        "ditto_apps.main:app",
        address="127.0.0.1:8000",
        interface=Interfaces.ASGI,  # FastAPI 需要 ASGI 接口
    ).serve()
