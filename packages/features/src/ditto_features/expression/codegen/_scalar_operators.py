"""Scalar operator builders for code generation."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from ditto_features.expression.ast import ExpressionNode
from ditto_features.expression.codegen._helpers import read_int_literal

# ---------------------------------------------------------------------------
# Scalar operator tables
# ---------------------------------------------------------------------------

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

_SCALAR_BINARY_OPERATORS: dict[str, Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    "max2": pl.max_horizontal,
    "min2": pl.min_horizontal,
    "power": lambda left, right: left.pow(right),
}


# ---------------------------------------------------------------------------
# Scalar dispatch
# ---------------------------------------------------------------------------


def compile_scalar(
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
        decimals = read_int_literal(raw_arguments, 1, source=source)
        return arguments[0].round(decimals=decimals)

    binary_operation = _SCALAR_BINARY_OPERATORS.get(name)
    if binary_operation is not None:
        return binary_operation(arguments[0], arguments[1])

    if name == "clip":
        return arguments[0].clip(arguments[1], arguments[2])
    if name == "if_else":
        return pl.when(arguments[0]).then(arguments[1]).otherwise(arguments[2])
    return pl.coalesce(*arguments) if name == "coalesce" else None
