"""Cross-section operator builders for code generation."""

from __future__ import annotations

import polars as pl

from ditto_features.expression.ast import ExpressionNode, StringNode
from ditto_features.expression.codegen._helpers import (
    read_float_literal,
    read_int_literal,
)

__all__ = ["compile_cross_section", "compile_grouped_cross_section"]

# cs_winsorize sigma 模式默认标准差倍数
_DEFAULT_WINSORIZE_SIGMA = 3

# ---------------------------------------------------------------------------
# Cross-section operators
# ---------------------------------------------------------------------------


def compile_cross_section(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    source: str,
    time_keys: list[str],
) -> pl.Expr | None:
    if name == "cs_rank":
        # NOTE(D7 cross-check): the *correct* cross-section semantics would rank
        # within each trade_date group: ``rank(method="ordinal").over(time_keys)
        # / pl.len().over(time_keys)``. That fix is blocked by a polars limit:
        # nested ``.over()`` with different group keys (cs over trade_date wrapping
        # a ts over entity) yields all-null without intermediate materialization,
        # and codegen emits one inlined expression. Every ``cs(ts(...))`` factor
        # (e.g. alpha.py ``cs_rank(ts_mean(...))``) would silently go null. The
        # real fix belongs in codegen (materialize ts results before cs ops), not
        # here. Until then cs_rank ranks across the whole frame; see the
        # xfail test in test_expression_cross_section_crosscheck_unit.py.
        return arguments[0].rank(method="ordinal").cast(pl.Float64) / pl.len().cast(
            pl.Float64
        )
    if name == "cs_scale":
        denominator = arguments[0].abs().sum().over(time_keys)
        return pl.when(denominator == 0).then(0.0).otherwise(arguments[0] / denominator)
    if name == "cs_zscore":
        mean = arguments[0].mean().over(time_keys)
        std = arguments[0].std().over(time_keys)
        return pl.when(std == 0).then(0.0).otherwise((arguments[0] - mean) / std)
    if name == "cs_demean":
        return arguments[0] - arguments[0].mean().over(time_keys)
    if name == "cs_winsorize":
        return _compile_cs_winsorize(arguments, raw_arguments, source, time_keys)
    return None


def _compile_cs_winsorize(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    source: str,
    time_keys: list[str],
) -> pl.Expr:
    """Compile cs_winsorize with sigma or quantile mode."""
    _first, *remaining = raw_arguments
    if remaining and isinstance(remaining[0], StringNode):
        method_node = remaining[0]
        if method_node.value == "quantile":
            lower = read_float_literal(raw_arguments, 2, source=source)
            upper = read_float_literal(raw_arguments, 3, source=source)
            q_lo = arguments[0].quantile(lower).over(time_keys)
            q_hi = arguments[0].quantile(upper).over(time_keys)
            return arguments[0].clip(q_lo, q_hi)
    # Sigma mode (default)
    mean = arguments[0].mean().over(time_keys)
    std = arguments[0].std().over(time_keys)
    n_sigma = _DEFAULT_WINSORIZE_SIGMA
    if remaining:
        n_sigma = read_int_literal(raw_arguments, 1, source=source)
    return arguments[0].clip(mean - n_sigma * std, mean + n_sigma * std)


# ---------------------------------------------------------------------------
# Grouped cross-section operators
# ---------------------------------------------------------------------------


def compile_grouped_cross_section(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
) -> pl.Expr | None:
    if name == "group_rank":
        group_size = pl.len().over(arguments[1]).cast(pl.Float64)
        return (
            arguments[0].rank(method="ordinal").over(arguments[1]).cast(pl.Float64)
            / group_size
        )
    if name == "group_zscore":
        mean = arguments[0].mean().over(arguments[1])
        std = arguments[0].std().over(arguments[1])
        return pl.when(std == 0).then(0.0).otherwise((arguments[0] - mean) / std)
    return None
