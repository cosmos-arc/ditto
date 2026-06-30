"""Shared validation helpers for code generation operator builders."""

from __future__ import annotations

import math

from ditto_features.expression.ast import ExpressionNode, NumberNode
from ditto_features.expression.diagnostics import Span, make_compile_error

__all__ = [
    "read_float_literal",
    "read_int_literal",
    "read_window_at",
    "require_positive",
]


def read_int_literal(
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


def read_float_literal(
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


def require_positive(value: int, span: Span, *, source: str) -> None:
    """Raise a compile error if *value* is not positive."""
    if value <= 0:
        raise make_compile_error(
            source=source,
            message=f"window size must be positive, got {value}",
            error_code="E033_INVALID_PARAMETER",
            span=span,
        )


def read_window_at(
    raw_arguments: tuple[ExpressionNode, ...],
    index: int,
    *,
    source: str,
) -> int:
    """Read and validate a positive window from raw arguments at *index*."""
    window = read_int_literal(raw_arguments, index, source=source)
    require_positive(window, raw_arguments[index].span, source=source)
    return window
