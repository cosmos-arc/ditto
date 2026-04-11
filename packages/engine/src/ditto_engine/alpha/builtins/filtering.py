"""FilteringStage + RiskLockFilter -- 条件过滤与风控锁定过滤."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.frame import FrameCol, validate_frame

__all__ = ["FilterCondition", "FilteringStage", "RiskLockFilter", "TrendFilterStage"]


@dataclass(frozen=True)
class FilterCondition:
    """
    单条过滤条件。

    Attributes:
        name: 过滤器名称（审计用）。
        column: 过滤依据列。
        min_value: 最小值（含）。
        max_value: 最大值（含）。
        exclude_nulls: True 表示排除 null 值。

    """

    name: str
    column: str
    min_value: float | None = None
    max_value: float | None = None
    exclude_nulls: bool = True


@dataclass(frozen=True)
class FilteringStage:
    """
    Filtering Stage -- 按条件过滤标的。

    多条条件为 AND 组合。

    Attributes:
        conditions: 过滤条件列表。空列表原样返回。

    """

    conditions: tuple[FilterCondition, ...] = ()

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """逐条件过滤 frame。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        if not self.conditions:
            return frame

        result = frame
        for cond in self.conditions:
            mask = pl.lit(True)
            if cond.min_value is not None:
                mask = mask & (pl.col(cond.column) >= cond.min_value)
            if cond.max_value is not None:
                mask = mask & (pl.col(cond.column) <= cond.max_value)
            if cond.exclude_nulls:
                mask = mask & pl.col(cond.column).is_not_null()
            result = result.filter(mask)
        return result


@dataclass(frozen=True)
class RiskLockFilter:
    """
    RiskLock 过滤器 -- 过滤被风控锁定的标的（R4）.

    从 ``context.risk_locked_instruments`` 读取锁定列表，
    锁定标的不进入 Pipeline 后续阶段，防止 same-day re-entry。
    """

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """过滤被锁定的标的，无锁定时原样返回。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        locked = context.risk_locked_instruments
        if not locked:
            return frame
        return frame.filter(
            ~pl.col("instrument_id").is_in(list(locked.keys())),
        )


@dataclass(frozen=True)
class TrendFilterStage:
    """
    趋势方向过滤 — 按信号阈值和方向过滤标的.

    Attributes:
        threshold: 过滤阈值。
        direction: 方向 (``"long"`` / ``"short"`` / ``"both"``)。
        signal_column: 信号列名。

    """

    threshold: float = 0.0
    direction: str = "long"
    signal_column: str = "signal_value"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """按方向和阈值过滤标的。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        col = pl.col(self.signal_column)

        if self.direction == "long":
            return frame.filter(col >= self.threshold)
        elif self.direction == "short":
            return frame.filter(col <= -self.threshold)
        else:  # "both"
            return frame.filter(col.abs() >= self.threshold)
