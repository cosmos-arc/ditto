"""Pytest configuration for unit tests.

这个文件为单元测试禁用 Prefect API 服务器，提高测试性能。
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def no_api_server() -> Generator[None, None, None]:
    """禁用 API 服务器，加速单元测试.

    通过设置 PREFECT_API_URL=None，避免每个测试都启动独立的 API 服务器。
    这是 Prefect 官方推荐的单元测试优化方式。
    """
    import prefect.settings

    with prefect.settings.temporary_settings(
        updates={prefect.settings.PREFECT_API_URL: None}
    ):
        yield
