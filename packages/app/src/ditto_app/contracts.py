"""
App Command Contracts — 跨 CQRS 子模块共享的 Command DTO.

process 和 command 子模块都需要的 Command DTO 统一定义于此，
避免 process → command 的循环依赖。

query/command/process 共享的 ReadModel/Info DTO 也定义于此，
避免 command → query 或 process → query 的反向依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl
from ditto_data.models.strategy import StrategySpecRecord
from ditto_engine.execution.reality.constants import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_MIN_COMMISSION,
)
from ditto_kernel.enums import ImpactModel

REGIME_DEFAULT_LOOKBACK = 60
"""Regime detection minimum lookback days (MomentumIndicator, ts_mean, ts_std)."""


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
    impact_model: ImpactModel = ImpactModel.NONE


# ---------------------------------------------------------------------------
# Shared ReadModel DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySpecInfo:
    """App 层策略摘要 DTO — 切断 interfaces → data 直接依赖."""

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    version: int = 1
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""
    tags: tuple[str, ...] = ()


def to_spec_info(record: StrategySpecRecord) -> StrategySpecInfo:
    """将 Data Record 转换为 App DTO."""
    return StrategySpecInfo(
        strategy_id=record.strategy_id,
        name=record.name,
        spec_json=dict(record.spec_json),
        version=record.version,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        tags=record.tags,
    )


__all__ = [
    "CheckDataQualityCommand",
    "CostConfig",
    "IngestDateCommand",
    "StrategySpecInfo",
    "to_spec_info",
]
