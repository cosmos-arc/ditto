"""Semantic analyzer for derived expressions."""

from __future__ import annotations

from collections import OrderedDict
from enum import Enum

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
from ditto_core.engine.materialization.contracts import Analysis, AnalysisWarning

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
        "ts_ema",
        "ts_decay_linear",
    }
)

# Rolling-class functions use _rolling() which internally shifts by 1,
# so their effective lookback is window + 1.
_ROLLING_WINDOW_FUNCTIONS = frozenset(
    {
        "ts_mean",
        "ts_sum",
        "ts_std",
        "ts_var",
        "ts_max",
        "ts_min",
        "ts_count",
        "ts_median",
        "ts_rank",
        "ts_argmax",
        "ts_argmin",
        "ts_corr",
        "ts_cov",
        "ts_ema",
        "ts_decay_linear",
    }
)

# Shift-only functions shift by the user-specified period but do not
# apply a rolling window, so their lookback equals the period.
_SHIFT_ONLY_FUNCTIONS = frozenset(
    {
        "ts_delay",
        "ts_delta",
        "ts_pct_change",
        "ts_diff",
    }
)

# Operators whose first argument must be numeric (Float), not a bare
# string literal.  Window-size positions are excluded from checking.
_NUMERIC_FIRST_ARG_OPERATORS = frozenset(
    {
        "cs_rank",
        "cs_scale",
        "cs_zscore",
        "cs_demean",
        "cs_winsorize",
        "ts_mean",
        "ts_sum",
        "ts_std",
        "ts_var",
        "ts_max",
        "ts_min",
        "ts_count",
        "ts_median",
        "ts_rank",
        "ts_argmax",
        "ts_argmin",
        "ts_corr",
        "ts_cov",
        "ts_ema",
        "ts_decay_linear",
        "ts_delay",
        "ts_delta",
        "ts_pct_change",
        "ts_diff",
        "abs",
        "log",
        "log10",
        "log2",
        "floor",
        "ceil",
        "exp",
        "sqrt",
        "sign",
    }
)


class _ExprType(Enum):
    """Lightweight expression type for compile-time checking."""

    FLOAT = "float"
    STRING = "string"


def analyze_expression(expression: ExpressionNode) -> Analysis:
    """Collect compile-time metadata from an expression AST."""
    dependencies: OrderedDict[str, None] = OrderedDict()
    operators: OrderedDict[str, None] = OrderedDict()
    warnings: list[AnalysisWarning] = []
    lookback = _visit_expression(expression, dependencies, operators)
    _check_types(expression, warnings)
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
        warnings=tuple(warnings),
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


# ---------------------------------------------------------------------------
# Lightweight type checking
# ---------------------------------------------------------------------------


def _infer_type(node: ExpressionNode) -> _ExprType:
    """
    Infer the expression type of an AST node.

    This is a best-effort, compile-time approximation:
    - Column / feature / number references are treated as Float (the default
      for financial data columns).
    - String literals are String.
    - Function calls that return numeric values (most operators) are Float.
    - Binary arithmetic ops on Float operands produce Float.
    """
    if isinstance(node, StringNode):
        return _ExprType.STRING
    if isinstance(node, CallNode):
        return _infer_call_type(node.name, node.arguments)
    # NumberNode, IdentifierNode, ColumnRefNode, FeatureRefNode,
    # UnaryOpNode, BinaryOpNode all default to Float.
    return _ExprType.FLOAT


def _infer_call_type(name: str, arguments: tuple[ExpressionNode, ...]) -> _ExprType:
    """
    Infer the return type of a function call.

    if_else is special: it can return string or float depending on branches.
    Most other operators return Float.
    """
    _IF_ELSE_MIN_ARGS = 3
    if (
        name == "if_else"
        and len(arguments) >= _IF_ELSE_MIN_ARGS
        and (
            isinstance(arguments[1], StringNode) or isinstance(arguments[2], StringNode)
        )
    ):
        return _ExprType.STRING
    return _ExprType.FLOAT


def _check_types(
    node: ExpressionNode,
    warnings: list[AnalysisWarning],
) -> None:
    """Walk the AST and collect type mismatch warnings."""
    if isinstance(node, CallNode):
        _check_call_types(node, warnings)
        for argument in node.arguments:
            _check_types(argument, warnings)
    elif isinstance(node, UnaryOpNode):
        _check_types(node.operand, warnings)
    elif isinstance(node, BinaryOpNode):
        _check_types(node.left, warnings)
        _check_types(node.right, warnings)


def _check_call_types(
    node: CallNode,
    warnings: list[AnalysisWarning],
) -> None:
    """Check argument types for a function call node."""
    # Only check operators known to require a numeric first argument.
    if node.name not in _NUMERIC_FIRST_ARG_OPERATORS or not node.arguments:
        return

    first_arg = node.arguments[0]
    first_type = _infer_type(first_arg)
    if first_type is _ExprType.STRING:
        warnings.append(
            AnalysisWarning(
                message=(
                    f"operator '{node.name}' argument 0 expects numeric input, "
                    f"got string literal"
                ),
                error_code="W031_TYPE_MISMATCH",
            )
        )


def _resolve_scope(*, has_ts: bool, has_cs: bool) -> str:
    if has_ts and has_cs:
        return "mixed"
    if has_ts:
        return "ts"
    if has_cs:
        return "cs"
    return "scalar"


def _extract_lookback(name: str, arguments: tuple[ExpressionNode, ...]) -> int:
    """
    Extract lookback from windowed operators.

    Rolling-class functions shift internally by 1, so effective lookback = window + 1.
    Shift-only functions use the user-specified period directly.
    """
    if name not in _WINDOW_FUNCTIONS:
        return 0
    number_index = 1
    if name in {"ts_corr", "ts_cov"}:
        number_index = 2
    if len(arguments) <= number_index:
        return 0
    argument = arguments[number_index]
    if not isinstance(argument, NumberNode):
        return 0
    window = int(argument.value)
    if name in _ROLLING_WINDOW_FUNCTIONS:
        return window + 1
    # Shift-only: ts_delay, ts_delta, ts_pct_change, ts_diff
    return window
