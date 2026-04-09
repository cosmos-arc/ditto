"""App Command module — 单次写入操作，CQRS Command side."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from ditto_app.command.ingestion import (
    BackfillRangeCommand,
    IngestDateCommand,
    IngestRangeCommand,
)
from ditto_app.command.strategy import (
    RunBacktestCommand,
    RunStrategySliceCommand,
)

__all__ = [
    "BackfillRangeCommand",
    "CommandHandler",
    "IngestDateCommand",
    "IngestRangeCommand",
    "RunBacktestCommand",
    "RunStrategySliceCommand",
]

C_contra = TypeVar("C_contra", contravariant=True)


@runtime_checkable
class CommandHandler(Protocol[C_contra]):
    """
    Command handler Protocol — 处理单个 Command.

    .. note:: 当前无生产代码使用此 Protocol，计划在 CQRS Command
       路由完善后启用。
    """

    def handle(self, command: C_contra) -> object:
        """处理给定 command 并返回结果."""
        ...
