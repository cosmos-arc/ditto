"""Command Handler Protocol 定义."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

__all__ = ["CommandHandler"]

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
