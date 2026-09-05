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
        return _compile_cs_rank(arguments[0], time_keys)
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


def _compile_cs_rank(argument: pl.Expr, time_keys: list[str]) -> pl.Expr:
    """
    Rank values within each time grain without nesting window expressions.

    Polars evaluates an outer ``over(time_keys)`` wrapped around an argument that
    already contains ``over(entity_keys)`` as all-null.  Ranking the composite
    ``(time_keys, value, row_position)`` globally and subtracting the first
    non-null rank of the time group is algebraically equivalent to an ordinal
    rank within that group, while keeping a nested time-series argument outside
    another window.  The row position makes Polars' ordinal tie ordering explicit.
    """
    time_fields = [
        pl.col(key).alias(f"__ditto_cs_time_{index}")
        for index, key in enumerate(time_keys)
    ]
    present = argument.is_not_null()
    group_key = pl.when(present).then(pl.struct(time_fields)).otherwise(None)
    row_position = pl.int_range(pl.len(), dtype=pl.UInt32).alias(
        "__ditto_cs_row_position"
    )
    ranked_key = (
        pl.when(present)
        .then(
            pl.struct([*time_fields, argument.alias("__ditto_cs_value"), row_position])
        )
        .otherwise(None)
    )
    group_start = group_key.rank(method="min").cast(pl.Float64)
    global_rank = ranked_key.rank(method="ordinal").cast(pl.Float64)
    within_group_rank = global_rank - group_start + 1.0
    group_size = pl.len().over(time_keys).cast(pl.Float64)
    return within_group_rank / group_size


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
