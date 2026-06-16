"""stock_selection_trend Stage 实现 -- MultiFactorSignalStage 与因子预处理."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.context import StrategyContext
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

        # fail-closed: neutralize_by 指定但列缺失 → StrategySpecError
        # (不泄漏 Polars 异常)
        if self.neutralize_by is not None and self.neutralize_by not in frame.columns:
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

        # 对每个存在的因子列应用预处理,写入临时列,再 rank 加权(最后 drop 临时列)
        prepped_cols: list[str] = []
        prepped_exprs: list[pl.Expr] = []
        factor_to_prepped: dict[str, str] = {}
        for factor_name in self.signal_factors:
            if factor_name not in frame.columns:
                continue  # 缺失因子: rank 视为 0(不计入加权分子)
            temp_col = f"_prepped_{factor_name}"
            prepped_cols.append(temp_col)
            factor_to_prepped[factor_name] = temp_col
            prepped_exprs.append(
                preprocess_factor_column(
                    pl.col(factor_name),
                    winsorize_sigma=self.winsorize_sigma,
                    zscore=self.zscore,
                    neutralize_by=self.neutralize_by,
                ).alias(temp_col),
            )

        enriched = frame.with_columns(prepped_exprs) if prepped_exprs else frame

        n = frame.height
        weighted_sum = pl.lit(0.0)
        for factor_name, weight in zip(
            self.signal_factors,
            self.signal_weights,
            strict=True,
        ):
            temp_col = factor_to_prepped.get(factor_name)
            if temp_col is None:
                continue
            rank_expr = pl.col(temp_col).rank(method="average", descending=False) / n
            weighted_sum = weighted_sum + pl.lit(weight) * rank_expr

        result = enriched.with_columns(
            (weighted_sum / pl.lit(weight_sum)).alias(self.output_column),
        )
        if prepped_cols:
            result = result.drop(prepped_cols)
        return result
