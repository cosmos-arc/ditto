"""Ingestion 集成测试配置."""

import pytest

# 集成测试串行执行，避免全局状态污染
pytestmark = pytest.mark.serial


@pytest.fixture(autouse=True)
def reset_observability_state() -> None:
    """在每个测试前重置观察性系统状态，避免测试隔离问题."""
    from ditto_foundation import reset_for_testing

    reset_for_testing()
