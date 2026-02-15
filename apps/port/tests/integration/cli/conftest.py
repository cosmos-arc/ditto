"""CLI 集成测试配置.

覆盖父级 conftest.py 中的 reset_observability fixture，
避免与 CliRunner 的 I/O 捕获机制冲突。
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    # 空操作：覆盖父级 fixture，不做任何事


@pytest.fixture(autouse=True)
def isolate_loguru_for_cli() -> Generator[None, None, None]:
    """在 CLI 测试中完全隔离 loguru。

    根因：loguru 的 stdout handler 与 CliRunner 的 I/O 捕获冲突，
          在测试结束时会触发 "I/O operation on closed file"。

    策略：
    1. 测试开始前：保存原始 handlers，然后移除所有 handler
    2. 添加静默 handler（level="CRITICAL"）
    3. 测试结束后：恢复原始 handlers
    """
    from loguru import logger as _logger

    # 保存原始 handlers
    original_handlers = _logger._core.handlers.copy()  # type: ignore[attr-defined]

    # 移除所有现有 handlers
    _logger.remove()

    # 添加静默 handler（仅记录 CRITICAL 级别，几乎不输出）
    _logger.add(
        lambda _: None,  # 静默 sink
        level="CRITICAL",
        format="{message}",
    )

    yield

    # 恢复原始配置
    _logger.remove()
    for _handler_id, handler in original_handlers.items():
        _logger.add(
            handler._sink,  # type: ignore[attr-defined]
            level=handler.level,
            format=handler.format,
            filter=handler.filter,
            colorize=handler.colorize,
            serialize=handler.serialize,
            backtrace=handler.backtrace,
            diagnose=handler.diagnose,
            enqueue=handler.enqueue,
            catch=handler.catch,
        )
