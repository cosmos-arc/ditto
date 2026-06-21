"""Production safety checks for factor expressions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from ditto_features.errors import FactorValidationError

__all__ = [
    "UnsafeProductionFactorExpressionError",
    "validate_production_factor_expression",
]

_CROSS_SECTION_OPERATORS = frozenset({"cs_rank", "cs_zscore", "cs_demean"})
_CROSS_SECTION_CALL = re.compile(
    r"\b(?P<operator>cs_rank|cs_zscore|cs_demean)\s*\(",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TIME_SERIES_CALL = re.compile(r"^ts_[A-Za-z0-9_]*\(")


class UnsafeProductionFactorExpressionError(FactorValidationError):
    """Raised when a production factor expression is unsafe to run inline."""


def validate_production_factor_expression(
    expression: str,
    *,
    materialized_columns: Iterable[str] = (),
) -> None:
    """
    Reject production expressions that inline time-series ops inside cs ops.

    Cross-sectional operators over inline time-series expressions can silently
    produce nulls in the current codegen path. Production configs must
    materialize the time-series result first and reference that column by name.
    """
    materialized = frozenset(materialized_columns)
    for operator, first_arg in _iter_cross_section_first_args(expression):
        compact_arg = _strip_whitespace(first_arg)
        if _is_time_series_call(compact_arg):
            _raise_unsafe_expression(expression, operator, compact_arg)
        if _is_unmaterialized_time_series_identifier(compact_arg, materialized):
            _raise_unsafe_expression(expression, operator, compact_arg)


def _iter_cross_section_first_args(expression: str) -> Iterator[tuple[str, str]]:
    for match in _CROSS_SECTION_CALL.finditer(expression):
        operator = match.group("operator")
        if operator not in _CROSS_SECTION_OPERATORS:
            continue
        open_paren_index = expression.find("(", match.start())
        if open_paren_index == -1:
            continue
        yield operator, _first_argument(expression, open_paren_index + 1)


def _first_argument(expression: str, start_index: int) -> str:
    depth = 0
    for index in range(start_index, len(expression)):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return expression[start_index:index]
            depth -= 1
        elif char == "," and depth == 0:
            return expression[start_index:index]
    return expression[start_index:]


def _strip_whitespace(value: str) -> str:
    return "".join(value.split())


def _is_time_series_call(value: str) -> bool:
    return _TIME_SERIES_CALL.match(value) is not None


def _is_unmaterialized_time_series_identifier(
    value: str,
    materialized_columns: frozenset[str],
) -> bool:
    return (
        value.startswith("ts_")
        and _IDENTIFIER.match(value) is not None
        and value not in materialized_columns
    )


def _raise_unsafe_expression(
    expression: str,
    operator: str,
    first_arg: str,
) -> None:
    msg = (
        "production factor expression nests cross-sectional and time-series "
        "operators without materialized intermediates: "
        f"{operator}({first_arg}) in {expression!r}"
    )
    raise UnsafeProductionFactorExpressionError(msg)
