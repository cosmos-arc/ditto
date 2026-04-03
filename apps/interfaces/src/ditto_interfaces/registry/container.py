"""DI 容器工厂."""

from dishka import (
    AsyncContainer,
    Container,
    Provider,
    make_async_container,
    make_container,
)
from ditto_app.providers import get_app_providers
from ditto_data.di import get_data_providers

from .infra import get_infra_providers

__all__ = ["make_app_container", "make_async_app_container"]


def _get_base_providers() -> tuple[Provider, ...]:
    """获取所有 Provider（按层级组装）."""
    return (
        *get_infra_providers(),  # Infrastructure 层
        *get_data_providers(),  # Data 层（含原 Core + Data DQ）
        *get_app_providers(),  # App 层
    )


def make_app_container() -> Container:
    """创建同步容器."""
    return make_container(*_get_base_providers())


def make_async_app_container() -> AsyncContainer:
    """创建异步容器."""
    return make_async_container(*_get_base_providers())
