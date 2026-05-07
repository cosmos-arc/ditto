"""
Shared SQL allowlists and WHERE clause builder for execution trade storage.

The helpers in this module are query/input validation utilities. The
``ValueError`` exceptions here intentionally remain plain validation errors,
not execution-domain order or fill failures.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ALLOWED_COLUMNS",
    "ALLOWED_ORDER_BY",
    "build_where_clause",
]

_RANGE_TUPLE_LEN = 2

ALLOWED_ORDER_BY: frozenset[str] = frozenset(
    {
        "signal_date ASC",
        "signal_date DESC",
        "snapshot_date ASC",
        "snapshot_date DESC",
        "trade_date ASC",
        "trade_date DESC",
    }
)

ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "signal_date",
        "status",
        "snapshot_date",
        "trade_date",
        "intent_id",
    }
)


def build_where_clause(
    base_sql: str,
    strategy_id: str,
    filters: dict[str, str | tuple[str, str] | None],
    order_by: str,
) -> tuple[str, list[Any]]:
    """
    Build a SELECT statement with whitelisted filters and ordering.

    Supported filter values:
    - ``str``: equality query, ``column = ?``
    - ``tuple[str, str]``: inclusive range query; empty bound means open-ended
    - ``None``: omitted filter
    """
    if order_by not in ALLOWED_ORDER_BY:
        raise ValueError(
            f"order_by 不在白名单内: {order_by!r}, 允许值: {sorted(ALLOWED_ORDER_BY)}"
        )

    for column in filters:
        if column not in ALLOWED_COLUMNS:
            raise ValueError(
                f"过滤列名不在白名单内: {column!r}, 允许值: {sorted(ALLOWED_COLUMNS)}"
            )

    clauses: list[str] = []
    params: list[Any] = [strategy_id]

    for column, value in filters.items():
        if value is None:
            continue
        if isinstance(value, tuple) and len(value) == _RANGE_TUPLE_LEN:
            low, high = str(value[0]), str(value[1])
            if low:
                clauses.append(f"{column} >= ?")
                params.append(low)
            if high:
                clauses.append(f"{column} <= ?")
                params.append(high)
        else:
            clauses.append(f"{column} = ?")
            params.append(value)

    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return base_sql + where + f" ORDER BY {order_by}", params
