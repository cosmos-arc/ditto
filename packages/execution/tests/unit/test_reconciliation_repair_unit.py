"""Tests for reconciliation repair planning semantics."""

from ditto_execution.reconciliation import (
    MismatchType,
    ReconciliationDiff,
    ReconciliationReport,
    RepairActionType,
    plan_repair,
)


def _report(*diffs: ReconciliationDiff) -> ReconciliationReport:
    return ReconciliationReport(
        report_id="rec-001",
        account_id="acct-001",
        trade_date="2026-05-31",
        expected_count=1,
        actual_count=1,
        diff_count=len(diffs),
        status="matched" if not diffs else "mismatch",
        diffs=diffs,
    )


class TestPlanRepairNoDiffs:
    def test_matched_report_produces_noop_plan(self) -> None:
        plan = plan_repair(_report())

        assert plan.report_id == "rec-001"
        assert plan.status == "not_needed"
        assert plan.action_count == 0
        assert plan.actions == ()
        assert plan.requires_manual_review is False


class TestPlanRepairActions:
    def test_missing_fill_plans_read_only_broker_refresh(self) -> None:
        diff = ReconciliationDiff(
            mismatch_type=MismatchType.MISSING_FILL,
            order_id="ord-001",
            client_order_id="client-001",
        )

        plan = plan_repair(_report(diff))

        action = plan.actions[0]
        assert action.action_type is RepairActionType.REFRESH_BROKER_ORDER
        assert action.mismatch_type is MismatchType.MISSING_FILL
        assert action.order_id == "ord-001"
        assert action.client_order_id == "client-001"
        assert action.requires_manual_review is False
        assert action.priority == "high"

    def test_extra_fill_plans_manual_import_with_fill_link(self) -> None:
        diff = ReconciliationDiff(
            mismatch_type=MismatchType.EXTRA_FILL,
            order_id="ord-extra",
            fill_id="fill-extra",
            broker_order_id="broker-extra",
        )

        plan = plan_repair(_report(diff))

        action = plan.actions[0]
        assert action.action_type is RepairActionType.IMPORT_BROKER_FILL
        assert action.fill_id == "fill-extra"
        assert action.broker_order_id == "broker-extra"
        assert action.requires_manual_review is True

    def test_qty_price_and_status_mismatches_plan_explicit_manual_actions(
        self,
    ) -> None:
        diffs = (
            ReconciliationDiff(
                mismatch_type=MismatchType.QTY_MISMATCH,
                order_id="ord-qty",
                client_order_id="client-qty",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.PRICE_MISMATCH,
                order_id="ord-price",
                client_order_id="client-price",
            ),
            ReconciliationDiff(
                mismatch_type=MismatchType.STATUS_MISMATCH,
                order_id="ord-status",
                client_order_id="client-status",
            ),
        )

        plan = plan_repair(_report(*diffs))

        assert plan.status == "planned"
        assert plan.action_count == 3
        assert plan.requires_manual_review is True
        assert [a.action_type for a in plan.actions] == [
            RepairActionType.AMEND_LOCAL_FILL,
            RepairActionType.AMEND_LOCAL_FILL,
            RepairActionType.REVIEW_ORDER_STATUS,
        ]
        assert [a.client_order_id for a in plan.actions] == [
            "client-qty",
            "client-price",
            "client-status",
        ]
