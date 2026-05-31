"""
ExecutionReconciler — 期望与实际成交对账。

对账逻辑：比较期望订单（OrderTicket）与券商实际成交（FillEvent），
产出 ReconciliationReport 及类型化的差异条目。

ADR: Recovery Policy
--------------------
对账模块仅负责 **检测** 期望与实际之间的差异。
它 **不会** 自动修复或更新任何状态。
恢复（repair）是一个独立的关注点，留给未来的实现。

这意味着：
- reconcile() 是纯函数，无副作用
- 输出 ReconciliationReport 仅描述"发生了什么偏差"
- 调用方决定如何处理差异（告警、人工干预、或未来的自动修复流程）
"""

from __future__ import annotations

from ditto_portfolio.accounting.fills import FillEvent

from ditto_execution.orders.status import OrderStatus
from ditto_execution.orders.ticket import OrderTicket
from ditto_execution.reconciliation.types import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
)

__all__ = ["reconcile"]

_DEFAULT_PRICE_TOLERANCE: float = 0.001


def reconcile(
    report_id: str,
    account_id: str,
    trade_date: str,
    expected: list[OrderTicket],
    actual: list[FillEvent],
    price_tolerance: float = _DEFAULT_PRICE_TOLERANCE,
) -> ReconciliationReport:
    """
    比较期望订单与实际成交，返回对账报告。

    对账规则：
    1. 按 order_id 匹配期望与实际
    2. 未匹配的期望 → MISSING_FILL
    3. 未匹配的实际 → EXTRA_FILL
    4. 数量不一致 → QTY_MISMATCH
    5. 价格偏差超限 → PRICE_MISMATCH
    6. 状态非终态 → STATUS_MISMATCH（期望 FILLED 但实际非 FILLED）
    """
    diffs: list[ReconciliationDiff] = []

    fills_by_order: dict[str, list[FillEvent]] = {}
    for fill in actual:
        fills_by_order.setdefault(fill.order_id, []).append(fill)

    matched_order_ids: set[str] = set()

    for ticket in expected:
        order_id = ticket.order.order_id
        client_order_id = ticket.order.client_id.value
        matched_order_ids.add(order_id)
        matched_fills = fills_by_order.get(order_id, [])

        if not matched_fills:
            diffs.append(
                ReconciliationDiff(
                    mismatch_type=MismatchType.MISSING_FILL,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    expected_quantity=ticket.order.quantity,
                    expected_status=ticket.status,
                )
            )
            continue

        # 聚合该 order 下所有 fill 的成交量和加权均价
        total_qty = sum(f.filled_quantity for f in matched_fills)
        total_value = sum(f.filled_quantity * f.fill_price for f in matched_fills)
        avg_price = total_value / total_qty if total_qty > 0 else 0.0

        # 状态检查：实际非 FILLED 即为偏差（无论 qty 是否匹配）
        if ticket.status != OrderStatus.FILLED:
            diffs.append(
                ReconciliationDiff(
                    mismatch_type=MismatchType.STATUS_MISMATCH,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    expected_status=OrderStatus.FILLED,
                    actual_status=ticket.status,
                )
            )

        # 数量不一致
        if total_qty != ticket.order.quantity:
            diffs.append(
                ReconciliationDiff(
                    mismatch_type=MismatchType.QTY_MISMATCH,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    expected_quantity=ticket.order.quantity,
                    actual_quantity=total_qty,
                )
            )

        # 价格偏差超限
        expected_price = (
            ticket.average_fill_price if ticket.average_fill_price is not None else 0.0
        )
        if abs(avg_price - expected_price) > price_tolerance:
            diffs.append(
                ReconciliationDiff(
                    mismatch_type=MismatchType.PRICE_MISMATCH,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    expected_price=expected_price,
                    actual_price=avg_price,
                )
            )

    # 未匹配的实际成交 → EXTRA_FILL
    for order_id, fills in fills_by_order.items():
        if order_id not in matched_order_ids:
            for fill in fills:
                diffs.append(
                    ReconciliationDiff(
                        mismatch_type=MismatchType.EXTRA_FILL,
                        order_id=order_id,
                        fill_id=fill.fill_id,
                        actual_quantity=fill.filled_quantity,
                        actual_price=fill.fill_price,
                    )
                )

    diff_count = len(diffs)
    status = "matched" if diff_count == 0 else "mismatch"

    return ReconciliationReport(
        report_id=report_id,
        account_id=account_id,
        trade_date=trade_date,
        expected_count=len(expected),
        actual_count=len(actual),
        diff_count=diff_count,
        status=status,
        diffs=tuple(diffs),
    )
