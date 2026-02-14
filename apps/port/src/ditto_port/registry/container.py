"""DI 容器工厂."""

from dishka import (
    AsyncContainer,
    Container,
    Provider,
    make_async_container,
    make_container,
)

from .config import ConfigProvider
from .core import CoreProvider
from .datahub import DataHubProvider
from .sources import DataSourcesProvider

__all__ = ["make_app_container", "make_async_app_container"]


def _get_base_providers() -> tuple[Provider, ...]:
    """获取基础 Provider 列表."""
    return (
        ConfigProvider(),
        CoreProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )


def make_app_container() -> Container:
    """创建同步容器."""
    return make_container(*_get_base_providers())


def make_async_app_container() -> AsyncContainer:
    """创建异步容器."""
    return make_async_container(*_get_base_providers())
