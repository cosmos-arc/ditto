"""Semantic analyzer for derived expressions."""

from __future__ import annotations

from collections import OrderedDict

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
from ditto_core.engine.materialization.contracts import Analysis

__all__ = ["analyze_expression"]

_WINDOW_FUNCTIONS = frozenset(
    {
        "ts_mean",
        "ts_sum",
        "ts_std",
        "ts_var",
        "ts_max",
        "ts_min",
        "ts_count",
        "ts_median",
        "ts_delay",
        "ts_delta",
        "ts_pct_change",
        "ts_diff",
        "ts_rank",
        "ts_argmax",
        "ts_argmin",
        "ts_corr",
        "ts_cov",
    }
)


def analyze_expression(expression: ExpressionNode) -> Analysis:
    """Collect compile-time metadata from an expression AST."""
    dependencies: OrderedDict[str, None] = OrderedDict()
    operators: OrderedDict[str, None] = OrderedDict()
    lookback = _visit_expression(expression, dependencies, operators)
    operator_names = tuple(operators.keys())
    has_ts = any(name.startswith("ts_") for name in operator_names)
    has_cs = any(name.startswith("cs_") for name in operator_names)

    return Analysis(
        dependencies=tuple(dependencies.keys()),
        operator_names=operator_names,
        lookback=lookback,
        requires_full_day=has_cs,
        scope=_resolve_scope(has_ts=has_ts, has_cs=has_cs),
        output_schema=("value",),
    )


def _visit_expression(
    node: ExpressionNode,
    dependencies: OrderedDict[str, None],
    operators: OrderedDict[str, None],
) -> int:
    lookback = 0
    match node:
        case IdentifierNode(name=name):
            dependencies.setdefault(name, None)
        case ColumnRefNode(dataset=dataset, column=column):
            dependencies.setdefault(f"{dataset}.{column}", None)
        case FeatureRefNode(name=name):
            dependencies.setdefault(name, None)
        case NumberNode() | StringNode():
            pass
        case UnaryOpNode(operand=operand):
            lookback = _visit_expression(operand, dependencies, operators)
        case BinaryOpNode(left=left, right=right):
            lookback = max(
                _visit_expression(left, dependencies, operators),
                _visit_expression(right, dependencies, operators),
            )
        case CallNode(name=name, arguments=arguments):
            operators.setdefault(name, None)
            child_lookback = max(
                (
                    _visit_expression(argument, dependencies, operators)
                    for argument in arguments
                ),
                default=0,
            )
            lookback = max(child_lookback, _extract_lookback(name, arguments))
    return lookback


def _resolve_scope(*, has_ts: bool, has_cs: bool) -> str:
    if has_ts and has_cs:
        return "mixed"
    if has_ts:
        return "ts"
    if has_cs:
        return "cs"
    return "scalar"


def _extract_lookback(name: str, arguments: tuple[ExpressionNode, ...]) -> int:
    """Extract lookback from windowed operators."""
    if name not in _WINDOW_FUNCTIONS:
        return 0
    number_index = 1
    if name in {"ts_corr", "ts_cov"}:
        number_index = 2
    if len(arguments) <= number_index:
        return 0
    argument = arguments[number_index]
    if isinstance(argument, NumberNode):
        return int(argument.value)
    return 0
