"""
因子桥接 — 字符串表达式 → 编译 → 信号计算.

FactorBridge 将声明式因子表达式字符串桥接到回测引擎的信号流中：
  1. 字符串表达式 → DerivedSpec → ExpressionCompiler → pl.Expr
  2. 多因子 rank 归一化 + 加权合成 → signal_value 列
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.contracts import CompiledDerivedExpression
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_kernel.strategy import (
    DerivedRole,
    DerivedSpec,
    ExecutionPolicy,
    MaterializationProfile,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "CompiledExpressions",
    "FactorBridge",
    "build_signal_spec",
]


def build_signal_spec(expr_str: str, index: int) -> DerivedSpec:
    """
    从表达式字符串构建信号 DerivedSpec.

    统一默认值: role=SIGNAL, materialization_profile=SERIES,
    entity_keys=("instrument_id",), grain="1d", calendar="cn_stock".

    Args:
        expr_str: 因子表达式字符串（如 ``"ts_mean(close, 20)"``）。
        index: 因子序号，用于生成 ``signal_{index}`` 形式的 id。

    Returns:
        配置好默认值的 ``DerivedSpec``。

    """
    return DerivedSpec(
        id=f"signal_{index}",
        version=1,
        role=DerivedRole.SIGNAL,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expr_str,
        entity_keys=("instrument_id",),
        grain="1d",
        calendar="cn_stock",
        execution_policy=ExecutionPolicy(),
    )


@dataclass(frozen=True)
class CompiledExpressions:
    """编译后的因子表达式集合."""

    expressions: tuple[CompiledDerivedExpression, ...]
    weights: tuple[float, ...]


class FactorBridge:
    """因子桥接 — 字符串表达式 → 编译 → 信号计算."""

    def __init__(self, compiler: ExpressionCompiler | None = None) -> None:
        self._compiler = compiler or ExpressionCompiler()

    def compile_and_validate(
        self,
        expressions: tuple[str, ...],
        weights: tuple[float, ...],
    ) -> CompiledExpressions:
        """
        编译并验证因子表达式.

        Args:
            expressions: 因子表达式字符串元组。
            weights: 对应权重元组。

        Returns:
            ``CompiledExpressions`` 包含编译后的 ``pl.Expr``。

        Raises:
            ValueError: 表达式为空、权重不匹配、权重非负、编译失败。

        """
        if not expressions:
            msg = "表达式不能为空"
            raise AppProcessError(msg)

        if len(expressions) != len(weights):
            msg = f"权重数量 ({len(weights)}) 与表达式数量 ({len(expressions)}) 不匹配"
            raise AppProcessError(msg)

        for i, w in enumerate(weights):
            if w < 0:
                msg = f"权重不能为负: weights[{i}] = {w}"
                raise AppProcessError(msg)

        compiled: list[CompiledDerivedExpression] = []
        for i, expr_str in enumerate(expressions):
            spec = build_signal_spec(expr_str, index=i)
            try:
                result = self._compiler.compile(spec)
            except ExpressionCompileError as exc:
                msg = f"编译失败 (signal_{i}): {exc}"
                raise AppProcessError(msg) from exc
            compiled.append(result)

        return CompiledExpressions(
            expressions=tuple(compiled),
            weights=weights,
        )

    def compute_signals(
        self,
        df: pl.DataFrame,
        compiled: CompiledExpressions,
    ) -> pl.DataFrame:
        """
        在 DataFrame 上计算因子值并合成 signal_value.

        步骤:
          1. ``df.with_columns([expr.alias(f"factor_{i}") for each compiled expr])``
          2. 各因子列 ``cs_rank()`` 归一化
          3. ``signal_value = sum(rank_f_i * w_i) / sum(w_i)``

        Args:
            df: 包含 ``instrument_id`` + 底层列的 DataFrame。
            compiled: 编译后的表达式集合。

        Returns:
            包含 ``instrument_id`` + ``signal_value`` 列的 DataFrame。

        """
        if df.height == 0:
            return pl.DataFrame(
                schema={
                    "instrument_id": df["instrument_id"].dtype,
                    "signal_value": pl.Float64,
                },
            )

        # Step 1: 计算各因子列
        factor_columns: list[str] = []
        factor_exprs: list[pl.Expr] = []
        for i, compiled_expr in enumerate(compiled.expressions):
            col_name = f"factor_{i}"
            factor_columns.append(col_name)
            factor_exprs.append(compiled_expr.expr.alias(col_name))

        enriched = df.with_columns(factor_exprs)

        # Step 2: rank 归一化各因子列
        # 当包含 trade_date 列（历史窗口）时，rank 只在最后一天截面上操作
        has_trade_date = "trade_date" in enriched.columns
        if has_trade_date:
            # 因子表达式可能产生 null（如历史不足），取每个标的最后一天的非 null 值
            last_day = enriched.group_by("instrument_id").last()
            enriched = last_day
            # 重新获取 factor_columns dtype
            enriched = enriched.with_columns(
                [
                    pl.col(c).cast(pl.Float64)
                    for c in factor_columns
                    if enriched[c].dtype != pl.Float64
                ],
            )

        rank_exprs: list[pl.Expr] = []
        for col_name in factor_columns:
            rank_exprs.append(
                (
                    pl.col(col_name).rank(method="ordinal").cast(pl.Float64)
                    / pl.len().cast(pl.Float64)
                ).alias(f"rank_{col_name}"),
            )

        enriched = enriched.with_columns(rank_exprs)

        # Step 3: 加权合成 signal_value
        weight_sum = sum(compiled.weights)
        if weight_sum == 0:
            # 所有权重为零时，signal_value 全部为零
            return enriched.select(
                "instrument_id",
                pl.lit(0.0).alias("signal_value"),
            )

        weighted_sum = pl.lit(0.0)
        for i, w in enumerate(compiled.weights):
            rank_col = f"rank_factor_{i}"
            weighted_sum = weighted_sum + pl.col(rank_col) * w

        return enriched.select(
            "instrument_id",
            (weighted_sum / weight_sum).alias("signal_value"),
        )
