"""
Universe 写路径 registry 上下文（apps 层边界收口）.

非 registry 代码不得直接导入 ``ditto_data`` barrels（架构测试强制）。
物化脚本等运维入口经本上下文获取 MetadataService 的 universe 域服务。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from ditto_data.services.metadata_service import MetadataService

from ditto_apps.registry.container import make_app_container

__all__ = ["create_universe_write_context"]


@contextmanager
def create_universe_write_context() -> Generator[MetadataService]:
    """Yield 容器托管的 MetadataService（universe CRUD 经 ``.universe`` 域）."""
    container = make_app_container()
    try:
        yield container.get(MetadataService)
    finally:
        container.close()
