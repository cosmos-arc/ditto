"""DI 容器工厂."""

from dishka import (
    AsyncContainer,
    Container,
    Provider,
    make_async_container,
    make_container,
)

from .core import get_core_providers
from .datahub import get_datahub_providers
from .infra import get_infra_providers
from .port import get_port_providers

__all__ = ["make_app_container", "make_async_app_container"]


def _get_base_providers() -> tuple[Provider, ...]:
    """获取所有 Provider（按层级组装）."""
    return (
        *get_infra_providers(),  # Infrastructure 层
        *get_core_providers(),  # Core 层
        *get_datahub_providers(),  # DataHub 层
        *get_port_providers(),  # Port 层
    )


def make_app_container() -> Container:
    """创建同步容器."""
    return make_container(*_get_base_providers())


def make_async_app_container() -> AsyncContainer:
    """创建异步容器."""
    return make_async_container(*_get_base_providers())
