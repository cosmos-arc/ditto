"""
Stage 数据合约 — TradingOrchestrator 内部阶段间数据流.

AlphaOutput: Alpha 决策输出（信号、评分、排名）
PortfolioOutput: 组合构建输出（目标权重）
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = [
    "AlphaOutput",
    "PortfolioOutput",
]


def _validate_columns(
    df: pl.DataFrame,
    required: frozenset[str],
    name: str,
) -> None:
    """校验 DataFrame 包含必需列，否则抛出 ValueError."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} 缺少必需列: {missing}")


_ALPHA_REQUIRED: frozenset[str] = frozenset({"instrument_id", "score", "rank"})
_PORTFOLIO_REQUIRED: frozenset[str] = frozenset({"instrument_id", "target_weight"})


@dataclass(frozen=True, kw_only=True)
class AlphaOutput:
    """
    Alpha 决策输出 — 策略信号与排名.

    Attributes:
        signals: polars DataFrame，必需列: instrument_id, score, rank

    """

    signals: pl.DataFrame

    def __post_init__(self) -> None:
        """校验 signals 列完整性."""
        _validate_columns(self.signals, _ALPHA_REQUIRED, "AlphaOutput.signals")


@dataclass(frozen=True, kw_only=True)
class PortfolioOutput:
    """
    组合构建输出 — 目标权重.

    Attributes:
        targets: polars DataFrame，必需列: instrument_id, target_weight

    """

    targets: pl.DataFrame

    def __post_init__(self) -> None:
        """校验 targets 列完整性."""
        _validate_columns(self.targets, _PORTFOLIO_REQUIRED, "PortfolioOutput.targets")
