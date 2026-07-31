"""ScoringStage -- 将 signal_value 转换为 score."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame
from ditto_strategy.alpha.selection_evidence import (
    FactorContributionEvidence,
    SelectionEvidenceSink,
)
from ditto_strategy.errors import StrategySpecError

__all__ = ["FactorScoreColumnBinding", "ScoringMethod", "ScoringStage"]


@dataclass(frozen=True, slots=True)
class FactorScoreColumnBinding:
    """Compiled factor columns and weight consumed by the scoring stage."""

    factor_id: str
    raw_column: str
    processed_column: str
    normalized_column: str
    weight: float

    def __post_init__(self) -> None:
        """Reject ambiguous or non-finite bindings at the strategy boundary."""
        for field_name in (
            "factor_id",
            "raw_column",
            "processed_column",
            "normalized_column",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty text")
        if isinstance(self.weight, bool):
            raise TypeError("weight must be a finite number")
        if not isfinite(float(self.weight)) or self.weight < 0:
            raise ValueError("weight must be a finite non-negative number")


class ScoringMethod(StrEnum):
    """评分方法。"""

    RAW = "raw"  # 直接使用 signal_value
    RANK = "rank"  # 百分位排名 (0-1)
    ZSCORE = "zscore"  # Z-score 标准化


@dataclass(frozen=True)
class ScoringStage:
    """
    Scoring Stage -- 将 signal_value 转换为 score。

    Attributes:
        method: 评分方法。
        ascending: True 表示 signal 值小的得分高（如波动率）。
        output_column: 输出列名。
        input_column: 输入列名。

    """

    method: ScoringMethod = ScoringMethod.RANK
    ascending: bool = False
    output_column: str = "score"
    input_column: str = "signal_value"
    factor_bindings: tuple[FactorScoreColumnBinding, ...] = ()
    evidence_sink: SelectionEvidenceSink | None = None

    def __post_init__(self) -> None:
        """Freeze the compiled factor binding surface as one exact tuple."""
        if type(self.factor_bindings) is not tuple or any(
            type(binding) is not FactorScoreColumnBinding
            for binding in self.factor_bindings
        ):
            raise TypeError("factor_bindings must contain exact compiled bindings")
        factor_ids = tuple(binding.factor_id for binding in self.factor_bindings)
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("factor_bindings must use unique factor_id values")
        if (
            self.evidence_sink is not None
            and self.factor_bindings
            and self.method is not ScoringMethod.RAW
        ):
            raise StrategySpecError(
                "factor contribution evidence requires additive raw scoring",
                details={
                    "reason": "non_additive_factor_evidence_scoring",
                    "scoring_method": self.method.value,
                },
            )

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """根据 method 转换 signal 为 score。"""
        validate_frame(frame, (FrameCol.INSTRUMENT_ID,))
        if self.input_column not in frame.columns:
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(self.output_column),
            )

        col = pl.col(self.input_column)

        if self.method == ScoringMethod.RAW:
            result = frame.with_columns(col.alias(self.output_column))
            self._emit_factor_contributions(result)
            return result

        if self.method == ScoringMethod.RANK:
            rank_expr = col.rank(method="average", descending=self.ascending)
            count_expr = col.count()
            result = frame.with_columns(
                (rank_expr / count_expr).alias(self.output_column),
            )
            self._emit_factor_contributions(result)
            return result

        # ScoringMethod.ZSCORE
        mean = col.mean()
        std = col.std()
        direction = -1.0 if self.ascending else 1.0
        result = frame.with_columns(
            pl.when(std == 0)
            .then(pl.lit(0.0))
            .otherwise(direction * (col - mean) / std)
            .alias(self.output_column),
        )
        self._emit_factor_contributions(result)
        return result

    def _emit_factor_contributions(self, result: pl.DataFrame) -> None:
        """Emit the exact compiled terms consumed by this scoring invocation."""
        if self.evidence_sink is None or not self.factor_bindings:
            return
        required_columns = {
            column
            for binding in self.factor_bindings
            for column in (
                binding.raw_column,
                binding.processed_column,
                binding.normalized_column,
            )
        } | {self.output_column}
        missing = tuple(sorted(required_columns - set(result.columns)))
        if missing:
            raise StrategySpecError(
                "compiled factor evidence columns are missing from scoring input",
                details={
                    "reason": "compiled_factor_evidence_column_missing",
                    "missing_columns": missing,
                },
            )
        weight_sum = sum(binding.weight for binding in self.factor_bindings)
        for binding in self.factor_bindings:
            effective_weight = 0.0 if weight_sum == 0 else binding.weight / weight_sum
            contribution = (
                pl.lit(0.0)
                if effective_weight == 0.0
                else pl.col(binding.normalized_column) * pl.lit(effective_weight)
            )
            rows = result.select(
                FrameCol.INSTRUMENT_ID,
                pl.col(binding.raw_column).alias("raw_value"),
                pl.col(binding.processed_column).alias("processed_value"),
                pl.col(binding.normalized_column).alias("normalized_value"),
                contribution.alias("contribution"),
                pl.col(self.output_column).alias("factor_signal_score"),
            ).iter_rows()
            for values in rows:
                self.evidence_sink.emit(
                    FactorContributionEvidence(
                        trade_date=self.evidence_sink.current_trade_date,
                        instrument_id=values[0],
                        factor_name=binding.factor_id,
                        raw_value=_optional_float(values[1]),
                        processed_value=_optional_float(values[2]),
                        normalized_value=_optional_float(values[3]),
                        weight=effective_weight,
                        contribution=_optional_float(values[4]),
                        factor_signal_score=_optional_float(values[5]),
                    ),
                )


def _optional_float(value: object) -> float | None:
    """Convert a materialized Polars scalar without inventing missing values."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("factor evidence value must be numeric or None")
    return float(value)
