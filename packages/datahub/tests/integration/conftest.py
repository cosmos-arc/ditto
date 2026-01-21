"""Pytest configuration for integration tests.

这个文件为 tests/integration/ 目录下的所有测试自动添加 @pytest.mark.integration marker。
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def ensure_sqlite_cleanup() -> Generator[None, None, None]:
    """确保 SQLite 连接在测试后正确关闭（Windows 兼容）。

    Windows 文件锁机制更严格，SQLite 连接未正确关闭会导致临时文件无法删除。
    通过强制垃圾回收确保连接在测试间被释放。
    """
    yield
    import gc

    gc.collect()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """为 integration 目录下的所有测试自动添加 integration marker.

    Args:
        items: pytest 收集到的所有测试项
    """
    for item in items:
        # 检查测试文件是否在 integration 目录下且没有 integration marker
        is_integration_path = "/integration/" in str(
            item.fspath
        ) or "\\integration\\" in str(item.fspath)
        has_integration_marker = "integration" in [
            mark.name for mark in item.iter_markers()
        ]

        if is_integration_path and not has_integration_marker:
            item.add_marker(pytest.mark.integration)
