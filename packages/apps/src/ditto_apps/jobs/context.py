"""Prefect 任务上下文管理（使用 dishka 同步容器）."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from ditto_apps.registry.container import make_app_container


@contextmanager
def create_prefect_host() -> Generator[Any]:
    """
    Prefect Host — 任务级容器生命周期管理.

    Yields:
        dishka 同步容器实例

    """
    container = make_app_container()
    try:
        yield container
    finally:
        container.close()
