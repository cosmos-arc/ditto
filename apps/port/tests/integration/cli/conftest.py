"""CLI 集成测试配置.

覆盖父级 conftest.py 中的 reset_observability fixture，
避免与 CliRunner 的 I/O 捕获机制冲突。
"""

import pytest


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    # 空操作：覆盖父级 fixture，不做任何事


@pytest.fixture(autouse=True)
def disable_stdout_logging():
    """在每个 CLI 测试前禁用 stdout 日志输出.

    解决 CliRunner I/O 错误：
    - loguru 的 stdout handler 可能在测试结束时导致 I/O 错误
    - 在测试开始前移除所有 handler
    """
    from loguru import logger as _logger

    # 移除默认 handler（包括 stdout）
    _logger.remove()
    # 测试结束后不恢复，让下一个测试重新配置
