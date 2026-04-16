"""
共享 SQL 常量、白名单与 WHERE 子句构建器.

三个 Writer（TradeIntentWriter / FillWriter / PositionWriter）共用的
SQL 注入防护与查询构建工具。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ALLOWED_COLUMNS",
    "ALLOWED_ORDER_BY",
    "build_where_clause",
]

# ---------------------------------------------------------------------------
# Whitelist: 防止 SQL 注入
# ---------------------------------------------------------------------------

ALLOWED_ORDER_BY: frozenset[str] = frozenset(
    {
        "signal_date ASC",
        "signal_date DESC",
        "snapshot_date ASC",
        "snapshot_date DESC",
    }
)

ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "signal_date",
        "status",
        "snapshot_date",
    }
)


def build_where_clause(
    base_sql: str,
    strategy_id: str,
    filters: dict[str, Any],
    order_by: str,
) -> tuple[str, list[Any]]:
    """
    构建带 WHERE 子句和排序的完整 SQL.

    Args:
        base_sql: 基础 SELECT 语句（含 WHERE strategy_id = ?）.
        strategy_id: 策略 ID（第一个参数）.
        filters: 额外过滤条件 {列名: 值}, None 值自动跳过.
        order_by: ORDER BY 子句（含排序方向）.

    Returns:
        (完整 SQL, 参数列表) 元组.

    Raises:
        ValueError: order_by 不在白名单内或 filters 包含非法列名.

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
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)

    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return base_sql + where + f" ORDER BY {order_by}", params
