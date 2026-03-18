"""Polars code generation for derived expressions."""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from ditto_core.engine.expression.ast import (
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
from ditto_core.engine.expression.diagnostics import Span, make_compile_error
from ditto_core.engine.expression.registry import (
    P0_OPERATOR_SPECS,
    suggest_operator_names,
)
from ditto_core.engine.specs import DerivedSpec

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
    "/": operator.truediv,
    "and": operator.and_,
    "or": operator.or_,
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
    "exp": lambda expr: expr.exp(),
    "log": lambda expr: expr.log(),
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
    literal_or_ref = _compile_literal_or_reference(node)
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


def _compile_literal_or_reference(node: ExpressionNode) -> pl.Expr | None:
    compiled: pl.Expr | None = None
    match node:
        case IdentifierNode(name=name):
            compiled = pl.col(name)
        case ColumnRefNode(column=column):
            compiled = pl.col(column)
        case FeatureRefNode(name=name):
            compiled = pl.col(name)
        case NumberNode(value=value):
            if float(value).is_integer():
                compiled = pl.lit(int(value))
            else:
                compiled = pl.lit(value)
        case StringNode(value=value):
            compiled = pl.lit(value)
        case _:
            pass
    return compiled


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
        time_keys=time_keys,
    )
    if cross_section is not None:
        return cross_section

    scalar = _compile_scalar(name=name, arguments=arguments)
    if scalar is not None:
        return scalar

    raise make_compile_error(
        source=source,
        message=f"unknown operator '{name}'",
        error_code="E021_UNKNOWN_OPERATOR",
        span=span,
        suggestions=suggest_operator_names(name),
    )


def _compile_time_series_special(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    raw_arguments: tuple[ExpressionNode, ...],
    entity_keys: list[str],
    source: str,
) -> pl.Expr | None:
    if name == "ts_delay":
        period = _read_int_literal(raw_arguments, 1, source=source)
        return arguments[0].shift(period).over(entity_keys)
    if name in {"ts_delta", "ts_diff"}:
        period = _read_int_literal(raw_arguments, 1, source=source)
        return arguments[0] - arguments[0].shift(period).over(entity_keys)
    if name == "ts_pct_change":
        period = _read_int_literal(raw_arguments, 1, source=source)
        return (arguments[0] / arguments[0].shift(period).over(entity_keys)) - 1
    if name == "ts_rank":
        window = _read_int_literal(raw_arguments, 1, source=source)
        shifted = arguments[0].shift(1)
        return (
            shifted.rolling_rank(window_size=window, min_samples=window)
            .cast(pl.Float64)
            .over(entity_keys)
            / window
        )
    if name in {"ts_argmax", "ts_argmin"}:
        window = _read_int_literal(raw_arguments, 1, source=source)
        shifted = arguments[0].shift(1)

        def _rolling_argmax(s: pl.Series) -> int:
            idx = s.arg_max()
            return idx if idx is not None else -1

        def _rolling_argmin(s: pl.Series) -> int:
            idx = s.arg_min()
            return idx if idx is not None else -1

        arg_func = _rolling_argmax if name == "ts_argmax" else _rolling_argmin
        return shifted.rolling_map(
            arg_func, window_size=window, min_samples=window
        ).over(entity_keys)
    return None


def _compile_cross_section(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
    time_keys: list[str],
) -> pl.Expr | None:
    if name == "cs_rank":
        return arguments[0].rank(method="ordinal").cast(pl.Float64) / pl.len().cast(
            pl.Float64
        )
    if name == "cs_scale":
        denominator = arguments[0].abs().sum().over(time_keys)
        return arguments[0] / denominator
    if name == "cs_zscore":
        mean = arguments[0].mean().over(time_keys)
        std = arguments[0].std().over(time_keys)
        return (arguments[0] - mean) / std
    if name == "cs_demean":
        return arguments[0] - arguments[0].mean().over(time_keys)
    if name == "cs_winsorize":
        mean = arguments[0].mean().over(time_keys)
        std = arguments[0].std().over(time_keys)
        return arguments[0].clip(mean - 3 * std, mean + 3 * std)
    return None


def _compile_scalar(
    *,
    name: str,
    arguments: tuple[pl.Expr, ...],
) -> pl.Expr | None:
    unary_operation = _SCALAR_UNARY_OPERATORS.get(name)
    if unary_operation is not None:
        return unary_operation(arguments[0])

    binary_operation = _SCALAR_BINARY_OPERATORS.get(name)
    if binary_operation is not None:
        return binary_operation(arguments[0], arguments[1])

    if name == "clip":
        return arguments[0].clip(arguments[1], arguments[2])
    if name == "if_else":
        return pl.when(arguments[0]).then(arguments[1]).otherwise(arguments[2])
    return None


def _rolling(
    argument: pl.Expr,
    raw_arguments: tuple[ExpressionNode, ...],
    index: int,
    kind: str,
    entity_keys: list[str],
    source: str,
) -> pl.Expr:
    window = _read_int_literal(raw_arguments, index, source=source)
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
