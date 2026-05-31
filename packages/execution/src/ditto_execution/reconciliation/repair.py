"""Pure repair planning for reconciliation reports."""

from __future__ import annotations

from typing import Literal

from ditto_execution.reconciliation.types import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairAction,
    RepairActionType,
    RepairPlan,
)

__all__ = ["plan_repair"]


def plan_repair(report: ReconciliationReport) -> RepairPlan:
    """
    Convert reconciliation diffs into deterministic repair actions.

    The plan is intentionally side-effect free: safe read-only refreshes can be
    executed directly by an orchestrator, while state-changing actions are marked
    for manual review or an explicit approval workflow.
    """
    actions = tuple(_action_for_diff(diff) for diff in report.diffs)
    requires_manual_review = any(action.requires_manual_review for action in actions)
    return RepairPlan(
        report_id=report.report_id,
        account_id=report.account_id,
        trade_date=report.trade_date,
        action_count=len(actions),
        status="not_needed" if not actions else "planned",
        requires_manual_review=requires_manual_review,
        actions=actions,
    )


def _action_for_diff(diff: ReconciliationDiff) -> RepairAction:
    if diff.mismatch_type is MismatchType.MISSING_FILL:
        return _build_action(
            diff,
            action_type=RepairActionType.REFRESH_BROKER_ORDER,
            priority="high",
            requires_manual_review=False,
            reason="Expected fill is missing; refresh broker order/fill snapshot.",
        )
    if diff.mismatch_type is MismatchType.EXTRA_FILL:
        return _build_action(
            diff,
            action_type=RepairActionType.IMPORT_BROKER_FILL,
            priority="high",
            requires_manual_review=True,
            reason="Broker reported an unexpected fill; import only after review.",
        )
    if diff.mismatch_type in {
        MismatchType.QTY_MISMATCH,
        MismatchType.PRICE_MISMATCH,
    }:
        return _build_action(
            diff,
            action_type=RepairActionType.AMEND_LOCAL_FILL,
            priority="high",
            requires_manual_review=True,
            reason=(
                "Broker fill differs from local fill; amend local record after review."
            ),
        )
    return _build_action(
        diff,
        action_type=RepairActionType.REVIEW_ORDER_STATUS,
        priority="medium",
        requires_manual_review=True,
        reason="Order status differs from filled expectation; review OMS state.",
    )


def _build_action(
    diff: ReconciliationDiff,
    *,
    action_type: RepairActionType,
    priority: Literal["low", "medium", "high"],
    requires_manual_review: bool,
    reason: str,
) -> RepairAction:
    return RepairAction(
        action_type=action_type,
        mismatch_type=diff.mismatch_type,
        order_id=diff.order_id,
        fill_id=diff.fill_id,
        client_order_id=diff.client_order_id,
        broker_order_id=diff.broker_order_id,
        priority=priority,
        requires_manual_review=requires_manual_review,
        reason=reason,
    )
