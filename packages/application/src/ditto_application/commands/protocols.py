"""Command Handler Protocol 定义."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

__all__ = ["CommandHandler"]

C_contra = TypeVar("C_contra", contravariant=True)


# runtime_checkable 允许 isinstance() 检查，用于 DI 容器路由。
# 注意：泛型 Protocol 的 runtime_checkable 仅检查方法是否存在，不检查参数类型。
@runtime_checkable
class CommandHandler(Protocol[C_contra]):
    """
    Command handler Protocol — CQRS 写入侧统一接口.

    所有 Command Handler（如 CheckDataQualityHandler、ReconcileSourcesHandler）
    均实现此 Protocol，由 AppCommandProvider 注册到 DI 容器。
    """

    def handle(self, command: C_contra) -> object:
        """处理给定 command 并返回结果."""
        ...
