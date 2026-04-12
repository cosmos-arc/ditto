"""
App Command Contracts — 跨 CQRS 子模块共享的 Command DTO.

process 和 command 子模块都需要的 Command DTO 统一定义于此，
避免 process → command 的循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from ditto_engine.execution.reality.constants import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_MIN_COMMISSION,
)

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


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

_DEFAULT_STAMP_DUTY_RATE: float = 0.001
"""默认印花税税率(卖出千一) — A 股股票标准."""

_DEFAULT_SLIPPAGE_BPS: float = 1.0
"""默认滑点(bps)."""


@dataclass(frozen=True)
class CostConfig:
    """
    成本模型配置 — A 股标准费率默认值.

    默认值来源于 engine 层常量（commission_rate, commission_min）
    及 A 股标准费率（stamp_duty_rate, slippage_bps）。
    """

    commission_rate: float = DEFAULT_COMMISSION_RATE
    commission_min: float = DEFAULT_MIN_COMMISSION
    stamp_duty_rate: float = _DEFAULT_STAMP_DUTY_RATE
    slippage_bps: float = _DEFAULT_SLIPPAGE_BPS
    impact_model: str = "none"


__all__ = [
    "CheckDataQualityCommand",
    "CostConfig",
    "IngestDateCommand",
]
