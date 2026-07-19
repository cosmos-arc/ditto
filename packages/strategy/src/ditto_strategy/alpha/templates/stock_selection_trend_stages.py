"""stock_selection_trend Stage 实现 -- MultiFactorSignalStage 与因子预处理."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol
from ditto_strategy.alpha.selection_evidence import (
    FactorContributionEvidence,
    SelectionEvidenceSink,
)
from ditto_strategy.errors import StrategySpecError

__all__ = ["MultiFactorSignalStage", "preprocess_factor_column"]


def preprocess_factor_column(
    col: pl.Expr,
    *,
    winsorize_sigma: float | None,
    zscore: bool,
    neutralize_by: str | None,
) -> pl.Expr:
    """
    对因子列应用横截面预处理链: winsorize → zscore → neutralize.

    语义对齐 ``ditto_features.expression.codegen._cs_operators``(横截面算子),
    但无 ``.over(time_keys)``:stage frame 是单日横截面,全 frame 即一个截面,
    故 mean/std/demean 直接在整个列上计算(std 用 polars 默认 ddof=1)。

    步骤顺序为经典量化预处理流程:
      1. winsorize(sigma): clip 到 ``[mean-sigma·std, mean+sigma·std]``,去极值;
      2. zscore: ``(x-mean)/std``,标准化(std==0 返回 0.0);
      3. neutralize(by): 按分组列 demean(``x - group_mean``),消除组间结构暴露。

    数学性质:winsorize/zscore 是单调线性变换,对纯 rank 加权不改变排序;
    neutralize 按组 demean 是非单调的,会改变横截面 rank。winsorize/zscore
    的价值在于为 neutralize 提供标准化前提并防御极值污染组均值。

    Args:
        col: 待预处理的因子列表达式。
        winsorize_sigma: sigma 倍数(正值);``None`` 跳过 winsorize。
        zscore: 是否标准化。
        neutralize_by: 中性化分组列名;``None`` 跳过(列存在性由调用方校验)。

    Returns:
        预处理后的因子列表达式。

    """
    expr = col
    if winsorize_sigma is not None:
        mean = expr.mean()
        std = expr.std()
        expr = expr.clip(mean - winsorize_sigma * std, mean + winsorize_sigma * std)
    if zscore:
        mean = expr.mean()
        std = expr.std()
        expr = pl.when(std == 0).then(pl.lit(0.0)).otherwise((expr - mean) / std)
    if neutralize_by is not None:
        expr = expr - expr.mean().over(neutralize_by)
    return expr


@dataclass(frozen=True)
class MultiFactorSignalStage:
    """
    多因子加权信号 Stage -- 从多个因子列计算加权综合信号.

    使用 rank-based 标准化: 对每个因子列独立做百分位排名 (0-1),
    然后加权求和: score = sum(w_i * rank_i) / sum(w_i)。

    可选预处理链(加权前对每个因子列应用):
      raw_factor → winsorize(3σ) → zscore → (中性化,可选) → rank → 加权。
    开关默认全部关闭,保持与历史行为完全一致(向后兼容)。

    Attributes:
        signal_factors: 因子列名列表。
        signal_weights: 因子权重列表。
        output_column: 输出列名。
        winsorize_sigma: 去极值 sigma 倍数;``None`` 关闭。
        zscore: 是否对因子列做 zscore 标准化。
        neutralize_by: 中性化分组列名(如 ``"industry"``);``None`` 关闭。
            指定的列缺失时 fail-closed 抛 ``StrategySpecError``,不泄漏 Polars 异常。

    """

    signal_factors: tuple[str, ...] = ("signal_value",)
    signal_weights: tuple[float, ...] = (1.0,)
    output_column: str = "signal_value"
    winsorize_sigma: float | None = None
    zscore: bool = False
    neutralize_by: str | None = None
    evidence_sink: SelectionEvidenceSink | None = None

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        计算多因子加权信号并写入 output_column.

        边界处理:
        - 空 frame 或无因子 → 填充 0.0
        - 缺失因子列 → rank 视为 0.0(权重仍计入分母)
        - neutralize_by 指定但列缺失 → 抛 ``StrategySpecError``
        """
        if frame.is_empty() or not self.signal_factors:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        weight_sum = sum(self.signal_weights)
        if weight_sum == 0.0:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        self._ensure_neutralize_column(frame)
        reserved_columns = set(frame.columns)
        enriched, temporary_cols, factor_to_raw, factor_to_prepped = (
            self._materialize_preprocessed(frame, reserved_columns)
        )
        ranked, factor_to_normalized = self._materialize_normalized(
            enriched,
            reserved_columns=reserved_columns,
            temporary_cols=temporary_cols,
            factor_to_prepped=factor_to_prepped,
        )
        result = ranked.with_columns(
            (self._weighted_sum(factor_to_normalized) / pl.lit(weight_sum)).alias(
                self.output_column
            ),
        )
        if self.evidence_sink is not None:
            result, factor_to_contribution = self._materialize_contributions(
                result,
                reserved_columns=reserved_columns,
                temporary_cols=temporary_cols,
                factor_to_normalized=factor_to_normalized,
                weight_sum=weight_sum,
            )
            self._emit_factor_contributions(
                result,
                weight_sum=weight_sum,
                factor_to_raw=factor_to_raw,
                factor_to_prepped=factor_to_prepped,
                factor_to_normalized=factor_to_normalized,
                factor_to_contribution=factor_to_contribution,
            )
        return result.drop(temporary_cols) if temporary_cols else result

    def _ensure_neutralize_column(self, frame: pl.DataFrame) -> None:
        """Fail closed with a strategy error when neutralization data is absent."""
        if self.neutralize_by is None or self.neutralize_by in frame.columns:
            return
        msg = (
            f"MultiFactorSignalStage neutralize_by 列 "
            f"'{self.neutralize_by}' 不存在于 frame"
        )
        raise StrategySpecError(
            msg,
            details={
                "neutralize_by": self.neutralize_by,
                "available_columns": tuple(frame.columns),
            },
        )

    def _materialize_preprocessed(
        self,
        frame: pl.DataFrame,
        reserved_columns: set[str],
    ) -> tuple[pl.DataFrame, list[str], dict[str, str], dict[str, str]]:
        """Materialize raw evidence and the actual factor preprocessing outputs."""
        temporary_cols: list[str] = []
        expressions: list[pl.Expr] = []
        factor_to_raw: dict[str, str] = {}
        factor_to_prepped: dict[str, str] = {}
        for factor_index, factor_name in enumerate(self.signal_factors):
            if factor_name not in frame.columns:
                continue
            prepped_col = _unused_temp_column(
                reserved_columns,
                f"_prepped_{factor_index}_{factor_name}",
            )
            temporary_cols.append(prepped_col)
            factor_to_prepped[factor_name] = prepped_col
            expressions.append(self._preprocessed_expr(factor_name, prepped_col))
            if self.evidence_sink is not None:
                raw_col = _unused_temp_column(
                    reserved_columns,
                    f"_raw_{factor_index}_{factor_name}",
                )
                temporary_cols.append(raw_col)
                factor_to_raw[factor_name] = raw_col
                expressions.append(pl.col(factor_name).alias(raw_col))
        enriched = frame.with_columns(expressions) if expressions else frame
        return enriched, temporary_cols, factor_to_raw, factor_to_prepped

    def _preprocessed_expr(self, factor_name: str, output_name: str) -> pl.Expr:
        """Build the one preprocessing expression used by scoring and evidence."""
        return preprocess_factor_column(
            pl.col(factor_name),
            winsorize_sigma=self.winsorize_sigma,
            zscore=self.zscore,
            neutralize_by=self.neutralize_by,
        ).alias(output_name)

    def _materialize_normalized(
        self,
        frame: pl.DataFrame,
        *,
        reserved_columns: set[str],
        temporary_cols: list[str],
        factor_to_prepped: dict[str, str],
    ) -> tuple[pl.DataFrame, dict[str, str]]:
        """Materialize the rank values consumed by the weighted score."""
        factor_to_normalized: dict[str, str] = {}
        expressions: list[pl.Expr] = []
        for factor_index, factor_name in enumerate(self.signal_factors):
            prepped_col = factor_to_prepped.get(factor_name)
            if prepped_col is None:
                continue
            normalized_col = _unused_temp_column(
                reserved_columns,
                f"_normalized_{factor_index}_{factor_name}",
            )
            temporary_cols.append(normalized_col)
            factor_to_normalized[factor_name] = normalized_col
            expressions.append(
                (
                    pl.col(prepped_col).rank(method="average", descending=False)
                    / frame.height
                ).alias(normalized_col),
            )
        ranked = frame.with_columns(expressions) if expressions else frame
        return ranked, factor_to_normalized

    def _weighted_sum(self, factor_to_normalized: dict[str, str]) -> pl.Expr:
        """Build the existing weighted-sum expression from materialized ranks."""
        weighted_sum = pl.lit(0.0)
        for factor_name, weight in zip(
            self.signal_factors,
            self.signal_weights,
            strict=True,
        ):
            normalized_col = factor_to_normalized.get(factor_name)
            if normalized_col is not None:
                weighted_sum = weighted_sum + pl.lit(weight) * pl.col(normalized_col)
        return weighted_sum

    def _materialize_contributions(
        self,
        result: pl.DataFrame,
        *,
        reserved_columns: set[str],
        temporary_cols: list[str],
        factor_to_normalized: dict[str, str],
        weight_sum: float,
    ) -> tuple[pl.DataFrame, dict[str, str]]:
        """Materialize per-factor terms from the same normalized score columns."""
        factor_to_contribution: dict[str, str] = {}
        contribution_exprs: list[pl.Expr] = []
        for factor_index, (factor_name, weight) in enumerate(
            zip(self.signal_factors, self.signal_weights, strict=True),
        ):
            normalized_col = factor_to_normalized.get(factor_name)
            if normalized_col is None:
                continue
            contribution_col = _unused_temp_column(
                reserved_columns,
                f"_contribution_{factor_index}_{factor_name}",
            )
            temporary_cols.append(contribution_col)
            factor_to_contribution[factor_name] = contribution_col
            contribution_exprs.append(
                (pl.lit(weight) * pl.col(normalized_col) / pl.lit(weight_sum)).alias(
                    contribution_col
                ),
            )
        enriched = (
            result.with_columns(contribution_exprs) if contribution_exprs else result
        )
        return enriched, factor_to_contribution

    def _emit_factor_contributions(
        self,
        result: pl.DataFrame,
        *,
        weight_sum: float,
        factor_to_raw: dict[str, str],
        factor_to_prepped: dict[str, str],
        factor_to_normalized: dict[str, str],
        factor_to_contribution: dict[str, str],
    ) -> None:
        """Emit values materialized by this exact calculation path."""
        if self.evidence_sink is None:
            return
        for factor_name, weight in zip(
            self.signal_factors,
            self.signal_weights,
            strict=True,
        ):
            raw_col = factor_to_raw.get(factor_name)
            prepped_col = factor_to_prepped.get(factor_name)
            normalized_col = factor_to_normalized.get(factor_name)
            contribution_col = factor_to_contribution.get(factor_name)
            if raw_col is None:
                self._emit_missing_factor_column(
                    result,
                    factor_name=factor_name,
                    effective_weight=weight / weight_sum,
                )
                continue
            evidence_frame = result.select(
                FrameCol.INSTRUMENT_ID,
                raw_col,
                prepped_col,
                normalized_col,
                contribution_col,
                self.output_column,
            )
            for values in evidence_frame.iter_rows():
                self.evidence_sink.emit(
                    FactorContributionEvidence(
                        instrument_id=values[0],
                        factor_name=factor_name,
                        raw_value=_optional_float(values[1]),
                        processed_value=_optional_float(values[2]),
                        normalized_value=_optional_float(values[3]),
                        weight=weight / weight_sum,
                        contribution=_optional_float(values[4]),
                        score=_optional_float(values[5]),
                    ),
                )

    def _emit_missing_factor_column(
        self,
        result: pl.DataFrame,
        *,
        factor_name: str,
        effective_weight: float,
    ) -> None:
        """Emit the algorithm's explicit zero contribution for an absent factor."""
        if self.evidence_sink is None:
            return
        for instrument_id, score in result.select(
            FrameCol.INSTRUMENT_ID,
            self.output_column,
        ).iter_rows():
            self.evidence_sink.emit(
                FactorContributionEvidence(
                    instrument_id=instrument_id,
                    factor_name=factor_name,
                    raw_value=None,
                    processed_value=None,
                    normalized_value=None,
                    weight=effective_weight,
                    contribution=0.0,
                    score=_optional_float(score),
                ),
            )


def _unused_temp_column(reserved: set[str], candidate: str) -> str:
    """Reserve a temporary column name without overwriting caller data."""
    while candidate in reserved:
        candidate = f"_{candidate}"
    reserved.add(candidate)
    return candidate


def _optional_float(value: object) -> float | None:
    """Convert a Polars numeric scalar while preserving explicit missing values."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("factor evidence value must be a finite number or None")
    return float(value)
