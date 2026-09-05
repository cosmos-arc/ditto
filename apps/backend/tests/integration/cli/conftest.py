"""CLI 集成测试配置.

覆盖父级 conftest.py 中的 reset_observability fixture，
避免与 CliRunner 的 I/O 捕获机制冲突。
"""

import logging
from collections.abc import Generator
from io import StringIO

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def isolate_stdlib_logging_for_cli() -> Generator[None]:
    """Prevent pytest live logging from replacing CliRunner's captured streams."""
    previous_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(previous_level)


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    # 空操作：覆盖父级 fixture，不做任何事


@pytest.fixture(autouse=True)
def isolate_loguru_for_cli() -> Generator[None]:
    """CLI 测试中隔离 loguru，使用公共 API 避免私有依赖.

    根因：loguru 的 stdout handler 与 CliRunner 的 I/O 捕获冲突，
          在测试结束时会触发 "I/O operation on closed file"。

    策略：测试期间将日志输出到内存 buffer，测试结束后丢弃。
    """
    # 移除所有现有 handlers（公共 API）
    logger.remove()

    # 添加静默 sink（仅记录 CRITICAL）
    handler_id = logger.add(
        StringIO(),
        level="CRITICAL",
        format="{message}",
    )

    yield

    # 移除测试 handler
    logger.remove(handler_id)
