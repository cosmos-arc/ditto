"""
Ditto FastAPI 主应用.

量化系统的REST API服务器入口点
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol, TypeVar, cast

# Third-party imports
import granian
import orjson

# Local imports - using editable packages
from dishka.integrations.fastapi import setup_dishka
from ditto_platform.foundation import (
    ConfigInitCoordinator,
    ConfigInitError,
    InitScope,
    Metrics,
    Settings,
    get_environment,
    logger,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ditto_apps.api.app_metadata import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    BuildMetadata,
    generate_stable_operation_id,
    openapi_license_info,
    openapi_servers,
)
from ditto_apps.api.cors import configure_cors, configure_origin_guard
from ditto_apps.api.maturity import OPENAPI_TAGS
from ditto_apps.api.routes.system import (
    get_status,
    health_check,
    readiness_check,
    root,
)
from ditto_apps.config.runtime import RuntimePaths
from ditto_apps.middleware import (
    HTTPObservabilityMiddleware,
    configure_exception_handlers,
)
from ditto_apps.openapi_contract import (
    canonical_contract_sha256,
    configure_openapi,
    register_application_routes,
    standard_error_responses,
)
from ditto_apps.registry.container import make_async_app_container
from ditto_apps.registry.infra.config import data_store_settings_type
from ditto_apps.registry.infra.observability import ObservabilityLifecycle

T = TypeVar("T")


_generate_stable_operation_id = generate_stable_operation_id
ditto_version = APP_VERSION

__all__ = ["app", "get_status", "health_check", "readiness_check", "root"]


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
    app.state.runtime_initialized = False

    # 从 app.state 获取容器（由 setup_dishka 设置）
    container = app.state.dishka_container
    typed_container = cast(AsyncContainerProtocol, container)

    try:
        # 生命周期型 provider 不会被 Dishka 隐式实例化；HTTP 服务必须显式
        # 启动它，确保首个请求前 tracing/metrics/kernel bridge 已就绪。
        await typed_container.get(ObservabilityLifecycle)
        runtime_paths = await typed_container.get(RuntimePaths)
        app.state.runtime_paths = runtime_paths

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
        runtime_paths.cache_root.mkdir(parents=True, exist_ok=True)
        app.state.build_metadata = BuildMetadata.from_environment(
            generated_contract_sha256=canonical_contract_sha256(),
            production=app.state.settings.is_production,
        )
        app.state.runtime_initialized = True

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
        app.state.runtime_initialized = False
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
    openapi_tags=OPENAPI_TAGS,
    servers=openapi_servers(),
    license_info=openapi_license_info(),
    lifespan=lifespan,
    generate_unique_id_function=_generate_stable_operation_id,
    responses=standard_error_responses(),
    default_response_class=ORJSONResponse,  # 使用 orjson 提升性能
)

configure_openapi(app)

# 在应用启动前设置 dishka（必须在 lifespan 之外）
# 这样中间件可以在应用启动前添加
container = make_async_app_container()
setup_dishka(container=container, app=app)

_env = get_environment()
register_application_routes(app, include_debug=not _env.is_production)


# The guard is innermost so denied browser requests still receive correlation,
# bounded metrics, a root span, and one terminal log from the HTTP boundary.
configure_origin_guard(app)
app.add_middleware(HTTPObservabilityMiddleware)

# CORS is outermost so allowed Web origins can read structured error responses;
# its origin guard rejects disallowed browser requests before route execution.
configure_cors(app, origin_guard_already_installed=True)


# 注册与纯契约工厂一致的异常响应边界。
configure_exception_handlers(app)


if __name__ == "__main__":
    from granian.constants import Interfaces

    granian.Granian(
        "ditto_apps.main:app",
        address="127.0.0.1:8000",
        interface=Interfaces.ASGI,  # FastAPI 需要 ASGI 接口
    ).serve()
