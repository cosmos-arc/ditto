"""Polars code generation for derived expressions."""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from ditto_kernel.strategy import DerivedSpec

from ditto_analytics.expression.ast import (
    BinaryOpNode,
    CallNode,
    ColumnRefNode,
    ExpressionNode,
    FeatureRefNode,
    IdentifierNode,
    NumberNode,
    StringNode,
    UnaryOpNode,
)
from ditto_analytics.expression.diagnostics import Span, make_compile_error
from ditto_analytics.expression.registry import (
    P0_OPERATOR_SPECS,
    suggest_operator_names,
)

__all__ = ["compile_expression"]

type BinaryOperation = Callable[[pl.Expr, pl.Expr], pl.Expr]
type RollingBuilder = Callable[[pl.Expr, int], pl.Expr]


@dataclass(frozen=True)
class _CodegenContext:
    source: str
    entity_keys: list[str]
    time_keys: list[str]


def _max_horizontal(left: pl.Expr, right: pl.Expr) -> pl.Expr:
    return pl.max_horizontal(left, right)


def _min_horizontal(left: pl.Expr, right: pl.Expr) -> pl.Expr:
    return pl.min_horizontal(left, right)


def _power(left: pl.Expr, right: pl.Expr) -> pl.Expr:
    return left.pow(right)


_BINARY_OPERATORS: dict[str, BinaryOperation] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": lambda left, right: left / right,
    "and": lambda left, right: left & right,
    "or": lambda left, right: left | right,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

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

_SCALAR_UNARY_OPERATORS: dict[str, Callable[[pl.Expr], pl.Expr]] = {
    "abs": lambda expr: expr.abs(),
    "ceil": lambda expr: expr.ceil(),
    "exp": lambda expr: expr.exp(),
    "floor": lambda expr: expr.floor(),
    "log": lambda expr: expr.log(),
    "log10": lambda expr: expr.log10(),
    "log2": lambda expr: expr.log(base=2),
    "sign": lambda expr: expr.sign(),
    "sqrt": lambda expr: expr.sqrt(),
}

_SCALAR_BINARY_OPERATORS: dict[str, BinaryOperation] = {
    "max2": _max_horizontal,
    "min2": _min_horizontal,
    "power": _power,
}

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


def compile_expression(
    expression: ExpressionNode,
    spec: DerivedSpec,
    *,
    source: str,
) -> pl.Expr:
    """Compile an AST into a Polars expression."""
    context = _CodegenContext(
        source=source,
        entity_keys=list(spec.entity_keys),
        time_keys=list(spec.effective_time_keys),
    )
    return _build_expression(expression, context)


def _build_expression(node: ExpressionNode, context: _CodegenContext) -> pl.Expr:
    literal_or_ref = _compile_literal_or_reference(node, context)
    if literal_or_ref is not None:
        return literal_or_ref
    if isinstance(node, UnaryOpNode):
        return _compile_unary_node(node, context)
    if isinstance(node, BinaryOpNode):
        return _compile_binary_node(node, context)
    if isinstance(node, CallNode):
        return _compile_call_node(node, context)
    raise make_compile_error(
        source=context.source,
        message=f"unsupported node: {node!r}",
        error_code="E021_UNKNOWN_OPERATOR",
        span=node.span,
    )


def _compile_literal_or_reference(
    node: ExpressionNode, context: _CodegenContext
) -> pl.Expr | None:
    """
    Compile literal/reference nodes to polars expressions.

    Compound nodes (UnaryOp, BinaryOp, Call) return None,
    signaling the caller to use the general _build_expression path.
    """
    if isinstance(node, UnaryOpNode | BinaryOpNode | CallNode):
        return None

    col_name: str | None = None
    match node:
        case IdentifierNode(name=name):
            col_name = name
        case ColumnRefNode(column=column):
            col_name = column
        case FeatureRefNode(name=name):
            col_name = name
        case NumberNode(value=value):
            if float(value).is_integer():
                return pl.lit(int(value))
            return pl.lit(value)
        case StringNode(value=value):
            return pl.lit(value)

    return pl.col(col_name) if col_name else None


def _compile_unary_node(node: UnaryOpNode, context: _CodegenContext) -> pl.Expr:
    operand = _build_expression(node.operand, context)
    if node.operator == "-":
        return -operand
    if node.operator == "not":
        return operand.not_()
    raise make_compile_error(
        source=context.source,
        message=f"unsupported unary operator: {node.operator}",
        error_code="E021_UNKNOWN_OPERATOR",
        span=node.span,
    )


def _compile_binary_node(node: BinaryOpNode, context: _CodegenContext) -> pl.Expr:
    left_expr = _build_expression(node.left, context)
    right_expr = _build_expression(node.right, context)
    return _compile_binary(
        node.operator,
        left_expr,
        right_expr,
        source=context.source,
        span=node.span,
    )


def _compile_call_node(node: CallNode, context: _CodegenContext) -> pl.Expr:
    _validate_operator_call(
        name=node.name,
        arguments=node.arguments,
        source=context.source,
        span=node.span,
    )
    compiled_args = tuple(
        _build_expression(argument, context) for argument in node.arguments
    )
    return _compile_call(
        name=node.name,
        arguments=compiled_args,
        raw_arguments=node.arguments,
        entity_keys=context.entity_keys,
        time_keys=context.time_keys,
        source=context.source,
        span=node.span,
    )


def _compile_binary(
    operator: str,
    left: pl.Expr,
    right: pl.Expr,
    *,
    source: str,
    span: Span,
) -> pl.Expr:
    operation = _BINARY_OPERATORS.get(operator)
    if operation is None:
        raise make_compile_error(
            source=source,
            message=f"unsupported binary operator: {operator}",
            error_code="E021_UNKNOWN_OPERATOR",
            span=span,
        )
    return operation(left, right)


def _compile_call(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    time_keys: list[str],
    source: str,
    span: Span,
) -> pl.Expr:
    ts_special = _compile_time_series_special(
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

    cross_section = _compile_cross_section(
        name=name,
        arguments=arguments,
        raw_arguments=raw_arguments,
        source=source,
        time_keys=time_keys,
    )
    if cross_section is not None:
        return cross_section

    grouped = _compile_grouped_cross_section(name=name, arguments=arguments)
    if grouped is not None:
        return grouped

    scalar = _compile_scalar(
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


def _read_window_at(
    raw_arguments: tuple[ExpressionNode, ...],
    index: int,
    *,
    source: str,
) -> int:
    """Read and validate a positive window from raw arguments at *index*."""
    window = _read_int_literal(raw_arguments, index, source=source)
    _require_positive(window, raw_arguments[index].span, source=source)
    return window


def _ts_delay(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = _read_window_at(raw_arguments, 1, source=source)
    return arguments[0].shift(period).over(entity_keys)


def _ts_delta(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = _read_window_at(raw_arguments, 1, source=source)
    return arguments[0] - arguments[0].shift(period).over(entity_keys)


def _ts_pct_change(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    period = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(period).over(entity_keys)
    return pl.when(shifted == 0).then(0.0).otherwise((arguments[0] / shifted) - 1)


def _ts_rank(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)
    return (
        shifted.rolling_rank(window_size=window, min_samples=window)
        .cast(pl.Float64)
        .over(entity_keys)
        / window
    )


def _ts_argmax(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)

    def _rolling_argmax(s: pl.Series) -> int:
        idx = s.arg_max()
        return idx if idx is not None else -1

    return shifted.rolling_map(
        _rolling_argmax,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_argmin(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)

    def _rolling_argmin(s: pl.Series) -> int:
        idx = s.arg_min()
        return idx if idx is not None else -1

    return shifted.rolling_map(
        _rolling_argmin,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_corr(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 2, source=source)
    shifted_x = arguments[0].shift(1)
    shifted_y = arguments[1].shift(1)
    return pl.rolling_corr(
        shifted_x,
        shifted_y,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_cov(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 2, source=source)
    shifted_x = arguments[0].shift(1)
    shifted_y = arguments[1].shift(1)
    return pl.rolling_cov(
        shifted_x,
        shifted_y,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


def _ts_ema(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)
    return shifted.ewm_mean(span=window, min_samples=1).over(
        entity_keys,
    )


def _ts_decay_linear(
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_window_at(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)

    def _wma(s: pl.Series) -> float:
        valid = s.drop_nulls()
        if valid.is_empty():
            return float("nan")
        n = len(valid)
        weights = list(range(1, n + 1))
        total_weight = n * (n + 1) // 2
        return (
            sum(w * v for w, v in zip(weights, valid.to_list(), strict=True))
            / total_weight
        )

    return shifted.rolling_map(
        _wma,
        window_size=window,
        min_samples=window,
    ).over(entity_keys)


type _TsSpecialFn = Callable[
    [tuple[pl.Expr, ...], tuple[ExpressionNode, ...], list[str], str],
    pl.Expr,
]

_TS_SPECIAL_DISPATCH: dict[str, _TsSpecialFn] = {
    "ts_delay": _ts_delay,
    "ts_delta": _ts_delta,
    "ts_pct_change": _ts_pct_change,
    "ts_rank": _ts_rank,
    "ts_argmax": _ts_argmax,
    "ts_argmin": _ts_argmin,
    "ts_corr": _ts_corr,
    "ts_cov": _ts_cov,
    "ts_ema": _ts_ema,
    "ts_decay_linear": _ts_decay_linear,
}


def _compile_time_series_special(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr | None:
    handler = _TS_SPECIAL_DISPATCH.get(name)
    if handler is None:
        return None
    return handler(arguments, raw_arguments, entity_keys, source)


def _compile_cross_section(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    source: str,
    time_keys: list[str],
) -> pl.Expr | None:
    if name == "cs_rank":
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
            lower = _read_float_literal(raw_arguments, 2, source=source)
            upper = _read_float_literal(raw_arguments, 3, source=source)
            q_lo = arguments[0].quantile(lower).over(time_keys)
            q_hi = arguments[0].quantile(upper).over(time_keys)
            return arguments[0].clip(q_lo, q_hi)
    # Sigma mode (default)
    mean = arguments[0].mean().over(time_keys)
    std = arguments[0].std().over(time_keys)
    n_sigma = 3  # default
    if remaining:
        n_sigma = _read_int_literal(raw_arguments, 1, source=source)
    return arguments[0].clip(mean - n_sigma * std, mean + n_sigma * std)


def _compile_scalar(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    source: str,
) -> pl.Expr | None:
    unary_operation = _SCALAR_UNARY_OPERATORS.get(name)
    if unary_operation is not None:
        return unary_operation(arguments[0])

    if name == "round":
        decimals = _read_int_literal(raw_arguments, 1, source=source)
        return arguments[0].round(decimals=decimals)

    binary_operation = _SCALAR_BINARY_OPERATORS.get(name)
    if binary_operation is not None:
        return binary_operation(arguments[0], arguments[1])

    if name == "clip":
        return arguments[0].clip(arguments[1], arguments[2])
    if name == "if_else":
        return pl.when(arguments[0]).then(arguments[1]).otherwise(arguments[2])
    return pl.coalesce(*arguments) if name == "coalesce" else None


def _compile_grouped_cross_section(
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
    future information.  The ``shift(1)`` strategy is preferred here
    because it composes cleanly with polars' ``.over()`` partitioning.
    """
    window = _read_int_literal(raw_arguments, index, source=source)
    _require_positive(window, raw_arguments[index].span, source=source)
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


def _read_int_literal(
    arguments: tuple[ExpressionNode, ...],
    index: int,
    *,
    source: str,
) -> int:
    argument = arguments[index]
    if not isinstance(argument, NumberNode):
        raise make_compile_error(
            source=source,
            message="window size must be an integer",
            error_code="E031_TYPE_MISMATCH",
            span=argument.span,
        )
    return math.floor(argument.value)


def _read_float_literal(
    arguments: tuple[ExpressionNode, ...],
    index: int,
    *,
    source: str,
) -> float:
    """Read and validate a float literal from raw arguments at *index*."""
    argument = arguments[index]
    if not isinstance(argument, NumberNode):
        raise make_compile_error(
            source=source,
            message="quantile value must be a number",
            error_code="E031_TYPE_MISMATCH",
            span=argument.span,
        )
    return float(argument.value)


def _require_positive(value: int, span: Span, *, source: str) -> None:
    """Raise a compile error if *value* is not positive."""
    if value <= 0:
        raise make_compile_error(
            source=source,
            message=f"window size must be positive, got {value}",
            error_code="E033_INVALID_PARAMETER",
            span=span,
        )


def _validate_operator_call(
    *,
    name: str,
    arguments: tuple[ExpressionNode, ...],
    source: str,
    span: Span,
) -> None:
    operator = P0_OPERATOR_SPECS.get(name)
    if operator is None:
        raise make_compile_error(
            source=source,
            message=f"unknown operator '{name}'",
            error_code="E021_UNKNOWN_OPERATOR",
            span=span,
            suggestions=suggest_operator_names(name),
        )
    if not operator.accepts_arity(len(arguments)):
        raise make_compile_error(
            source=source,
            message=(
                f"operator '{name}' expects "
                f"{operator.min_args}..{operator.max_args} arguments, "
                f"got {len(arguments)}"
            ),
            error_code="E032_ARGUMENT_ARITY",
            span=span,
        )
    if name.startswith("ts_"):
        for i, arg in enumerate(arguments):
            if isinstance(arg, StringNode):
                raise make_compile_error(
                    source=source,
                    message=f"operator '{name}' argument {i} must be numeric",
                    error_code="E031_TYPE_MISMATCH",
                    span=arg.span,
                )
