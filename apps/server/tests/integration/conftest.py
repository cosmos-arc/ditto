"""Pytest configuration for integration tests.

这个文件为 tests/integration/ 目录下的所有测试自动添加 @pytest.mark.integration marker。
"""

from collections.abc import Generator

import pytest
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(scope="session")
def prefect_test_session() -> Generator[None, None, None]:
    """Session 级别的 Prefect test harness。"""
    with prefect_test_harness():
        yield


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
