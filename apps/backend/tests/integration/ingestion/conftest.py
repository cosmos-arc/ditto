"""Ingestion 集成测试配置."""

import pytest

# serial 由根 layering 规则按 tests/integration 目录赋予；conftest 的
# pytestmark 声明从不生效，已删除该 no-op（#330 B1）。


@pytest.fixture(autouse=True)
def reset_observability_state() -> None:
    """在每个测试前重置观察性系统状态，避免测试隔离问题."""
    from ditto_platform.foundation import reset_for_testing

    reset_for_testing()
