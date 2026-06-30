"""Operator tables, rolling window builder, and main dispatch for code generation."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from ditto_features.expression.ast import ExpressionNode
from ditto_features.expression.codegen._cs_operators import (
    compile_cross_section,
    compile_grouped_cross_section,
)
from ditto_features.expression.codegen._helpers import (
    read_int_literal,
    require_positive,
)
from ditto_features.expression.codegen._scalar_operators import compile_scalar
from ditto_features.expression.codegen._ts_operators import compile_time_series_special
from ditto_features.expression.diagnostics import Span, make_compile_error
from ditto_features.expression.registry import suggest_operator_names

type BinaryOperation = Callable[[pl.Expr, pl.Expr], pl.Expr]
type RollingBuilder = Callable[[pl.Expr, int], pl.Expr]

# ---------------------------------------------------------------------------
# Rolling window operator tables
# ---------------------------------------------------------------------------

_WINDOW_KIND_BY_NAME = {
    "ts_count": "count",
    "ts_max": "max",
    "ts_mean": "mean",
    "ts_median": "median",
    "ts_min": "min",
    "ts_std": "std",
    "ts_sum": "sum",
    "ts_var": "var",
}

# PIT safety: Polars Expr-level .rolling_*() methods do NOT expose a
# ``closed`` parameter (unlike DataFrame.rolling()).  The caller (_rolling)
# therefore pre-shifts by 1 so the window only sees [T-window, T-1].
_ROLLING_BUILDERS: dict[str, RollingBuilder] = {
    "count": lambda expr, window: (
        expr.is_not_null()
        .cast(pl.Int64)
        .rolling_sum(window_size=window, min_samples=window)
    ),
    "max": lambda expr, window: expr.rolling_max(
        window_size=window,
        min_samples=window,
    ),
    "mean": lambda expr, window: expr.rolling_mean(
        window_size=window,
        min_samples=window,
    ),
    "median": lambda expr, window: expr.rolling_median(
        window_size=window,
        min_samples=window,
    ),
    "min": lambda expr, window: expr.rolling_min(
        window_size=window,
        min_samples=window,
    ),
    "std": lambda expr, window: expr.rolling_std(
        window_size=window,
        min_samples=window,
    ),
    "sum": lambda expr, window: expr.rolling_sum(
        window_size=window,
        min_samples=window,
    ),
    "var": lambda expr, window: expr.rolling_var(
        window_size=window,
        min_samples=window,
    ),
}


# ---------------------------------------------------------------------------
# Rolling window builder
# ---------------------------------------------------------------------------


def _rolling(
    argument: pl.Expr,
    raw_arguments: tuple[ExpressionNode, ...],
    index: int,
    kind: str,
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    """
    Construct a PIT-safe rolling expression.

    Uses ``shift(1)`` to prevent look-ahead bias: the rolling window
    operates on data up to *T-1* rather than including the current row *T*.

    **Window semantics**

    ``shift(1) + rolling(window)`` consumes data in ``[T-window, T-1]``
    (exactly *window* historical data points, excluding the current row).

    This is equivalent to ``rolling(window, closed="left")`` — both
    approaches yield the same number of data points and neither leaks
    future information.  The ``shift(1)`` strategy is required here
    because Polars Expr-level ``.rolling_*()`` methods do not expose a
    ``closed`` parameter (only ``DataFrame.rolling()`` does).  ``shift(1)``
    also composes cleanly with polars' ``.over()`` partitioning.
    """
    window = read_int_literal(raw_arguments, index, source=source)

    require_positive(window, raw_arguments[index].span, source=source)
    shifted = argument.shift(1)
    builder = _ROLLING_BUILDERS.get(kind)
    if builder is None:
        raise make_compile_error(
            source=source,
            message=f"unsupported rolling kind: {kind}",
            error_code="E021_UNKNOWN_OPERATOR",
            span=raw_arguments[index].span,
        )
    return builder(shifted, window).over(entity_keys)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------


def compile_call(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    time_keys: list[str],
    source: str,
    span: Span,
) -> pl.Expr:
    """
    表达式算子编译主调度入口。

    按优先级依次尝试：特殊时序算子 → 滚动窗口算子 → 截面算子 →
    分组截面算子 → 标量算子。若均不匹配则抛出
    ``E021_UNKNOWN_OPERATOR`` 编译错误。

    Args:
        name: 算子名称（如 ``"ts_mean"``、``"cs_rank"``）。
        arguments: 已编译的 Polars 表达式参数列表。
        raw_arguments: 原始 AST 节点参数列表（用于提取字面量）。
        entity_keys: 实体分组键（如 ``["instrument_id"]``）。
        time_keys: 时间分组键（如 ``["trade_date"]``）。
        source: 源表达式文本（用于错误信息）。
        span: 当前调用在源文本中的位置范围。

    Returns:
        编译后的 Polars 表达式。

    Raises:
        CompileError: 算子未知或参数不合法时。

    """
    ts_special = compile_time_series_special(
        name=name,
        arguments=arguments,
        raw_arguments=raw_arguments,
        entity_keys=entity_keys,
        source=source,
    )
    if ts_special is not None:
        return ts_special

    window_kind = _WINDOW_KIND_BY_NAME.get(name)
    if window_kind is not None:
        return _rolling(
            arguments[0],
            raw_arguments,
            1,
            window_kind,
            entity_keys,
            source=source,
        )

    cross_section = compile_cross_section(
        name=name,
        arguments=arguments,
        raw_arguments=raw_arguments,
        source=source,
        time_keys=time_keys,
    )
    if cross_section is not None:
        return cross_section

    grouped = compile_grouped_cross_section(name=name, arguments=arguments)
    if grouped is not None:
        return grouped

    scalar = compile_scalar(
        name=name,
        arguments=arguments,
        raw_arguments=raw_arguments,
        source=source,
    )
    if scalar is not None:
        return scalar

    raise make_compile_error(
        source=source,
        message=f"unknown operator '{name}'",
        error_code="E021_UNKNOWN_OPERATOR",
        span=span,
        suggestions=suggest_operator_names(name),
    )
