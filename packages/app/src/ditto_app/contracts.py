"""
App Command Contracts — 跨 CQRS 子模块共享的 Command DTO.

process 和 command 子模块都需要的 Command DTO 统一定义于此，
避免 process → command 的循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl


@dataclass(frozen=True)
class IngestDateCommand:
    """单日入库命令."""

    dataset: str
    trade_date: date
    force: bool = False


@dataclass(frozen=True)
class CheckDataQualityCommand:
    """数据质量检查命令."""

    df: pl.DataFrame
    dataset: str
    context: dict[str, Any] | None = None


__all__ = ["CheckDataQualityCommand", "IngestDateCommand"]
