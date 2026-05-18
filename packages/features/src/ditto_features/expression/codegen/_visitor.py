"""AST visitor: top-level dispatch and validation for expression code generation."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from ditto_features.derived_types import DerivedSpec
from ditto_features.expression.ast import (
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
from ditto_features.expression.codegen._builders import compile_call
from ditto_features.expression.diagnostics import Span, make_compile_error
from ditto_features.expression.registry import (
    P0_OPERATOR_SPECS,
    suggest_operator_names,
)

__all__ = ["compile_expression"]

type BinaryOperation = Callable[[pl.Expr, pl.Expr], pl.Expr]


@dataclass(frozen=True)
class _CodegenContext:
    source: str
    entity_keys: list[str]
    time_keys: list[str]


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
    return compile_call(
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
