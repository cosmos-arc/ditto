"""FilteringStage + RiskLockFilter -- 条件过滤与风控锁定过滤."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame
from ditto_strategy.alpha.selection_evidence import (
    ExclusionEvidence,
    ExclusionReason,
    SelectionEvidenceSink,
)

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
    reason_code: ExclusionReason = ExclusionReason.CONDITION_NOT_MET
    message: str | None = None


@dataclass(frozen=True)
class FilteringStage:
    """
    Filtering Stage -- 按条件过滤标的。

    多条条件为 AND 组合。

    Attributes:
        conditions: 过滤条件列表。空列表原样返回。

    """

    conditions: tuple[FilterCondition, ...] = ()
    evidence_sink: SelectionEvidenceSink | None = None

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
            result = _filter_with_evidence(
                result,
                mask=mask,
                reason_column=cond.column,
                stage_name=cond.name,
                reason_code=cond.reason_code,
                message=cond.message,
                evidence_sink=self.evidence_sink,
            )
        return result


@dataclass(frozen=True)
class RiskLockFilter:
    """
    RiskLock 过滤器 -- 过滤被风控锁定的标的（R4）.

    从 ``context.risk_locked_instruments`` 读取锁定列表，
    锁定标的不进入 Pipeline 后续阶段，防止 same-day re-entry。
    """

    evidence_sink: SelectionEvidenceSink | None = None

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
        return _filter_with_evidence(
            frame,
            mask=~pl.col(FrameCol.INSTRUMENT_ID).is_in(list(locked.keys())),
            reason_column=None,
            stage_name="risk_lock",
            reason_code=ExclusionReason.RISK_LOCKED,
            message=None,
            evidence_sink=self.evidence_sink,
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
    evidence_sink: SelectionEvidenceSink | None = None

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """按方向和阈值过滤标的。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        col = pl.col(self.signal_column)

        if self.direction == "long":
            mask = col >= self.threshold
        elif self.direction == "short":
            mask = col <= -self.threshold
        else:  # "both"
            mask = col.abs() >= self.threshold
        return _filter_with_evidence(
            frame,
            mask=mask,
            reason_column=self.signal_column,
            stage_name="trend_filter",
            reason_code=ExclusionReason.TREND_THRESHOLD,
            message=None,
            evidence_sink=self.evidence_sink,
        )


def _filter_with_evidence(
    frame: pl.DataFrame,
    *,
    mask: pl.Expr,
    reason_column: str | None,
    stage_name: str,
    reason_code: ExclusionReason,
    message: str | None,
    evidence_sink: SelectionEvidenceSink | None,
) -> pl.DataFrame:
    """Apply one business filter and emit only rows first removed by it."""
    if evidence_sink is None:
        return frame.filter(mask)

    row_column = _unused_row_column(frame.columns)
    indexed = frame.with_row_index(row_column)
    filtered = indexed.filter(mask)
    excluded = indexed.join(filtered.select(row_column), on=row_column, how="anti")
    evidence_columns = [FrameCol.INSTRUMENT_ID]
    if reason_column is not None:
        evidence_columns.append(reason_column)
    for values in excluded.select(evidence_columns).iter_rows():
        instrument_id = values[0]
        is_missing = reason_column is not None and values[1] is None
        evidence_sink.emit(
            ExclusionEvidence(
                instrument_id=instrument_id,
                stage=stage_name,
                reason_code=(
                    ExclusionReason.MISSING_DATA if is_missing else reason_code
                ),
                message=message,
            ),
        )
    return filtered.drop(row_column)


def _unused_row_column(columns: list[str]) -> str:
    """Choose a temporary evidence row key without colliding with business data."""
    candidate = "_selection_evidence_row"
    while candidate in columns:
        candidate = f"_{candidate}"
    return candidate
