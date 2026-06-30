"""Small shared DTOs for backtest process helpers."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BacktestLineageConfig"]


@dataclass(frozen=True)
class BacktestLineageConfig:
    """Subset of backtest config needed for lineage asset identity."""

    strategy_id: str
    strategy_version: str
    start_date: str
    end_date: str
