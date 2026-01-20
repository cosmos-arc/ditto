"""Pytest configuration for unit tests.

这个文件为 tests/unit/ 目录下的所有测试自动添加 @pytest.mark.unit marker。
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """为 unit 目录下的所有测试自动添加 unit marker.

    Args:
        items: pytest 收集到的所有测试项
    """
    for item in items:
        # 检查测试文件是否在 unit 目录下且没有 unit marker
        is_unit_path = "/tests/unit/" in str(item.fspath) or "\\tests\\unit\\" in str(
            item.fspath
        )
        has_unit_marker = "unit" in [mark.name for mark in item.iter_markers()]

        if is_unit_path and not has_unit_marker:
            item.add_marker(pytest.mark.unit)
