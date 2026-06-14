"""Report-sequence execution tests for reconciliation repair execution."""

from __future__ import annotations

from dataclasses import replace

from _reconciliation_executor_helpers import (
    _duplicate_fill_amendment_plan,
    _FakeAuditSink,
    _FakeBrokerFillImportSource,
    _FakeBrokerFillQuery,
    _FakeFillAmendmentSource,
    _FakeLocalFillStore,
    _FakeLocalOrderStatusStore,
    _FakeOrderStatusReviewSource,
    _fill,
    _fill_record,
    _mixed_repair_sequence_plan,
    _ReportReentrantFillAmendmentSource,
)
from ditto_execution.reconciliation import RepairActionStatus
from ditto_execution.reconciliation.executor import (
    AmendLocalFillRepairHandler,
    BrokerRefreshRepairHandler,
    ImportBrokerFillRepairHandler,
    RepairActionExecutor,
    ReviewOrderStatusRepairHandler,
)
from ditto_execution.storage.sqlite.reconciliation import SQLiteRepairWorkflowStore
from ditto_platform.foundation import SQLiteClient


class TestRepairActionExecutorReportSequence:
    def test_report_sequence_executes_mixed_actions_in_plan_order(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _mixed_repair_sequence_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-sequence:0001",
            "rec-sequence:0002",
            "rec-sequence:0003",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        broker = _FakeBrokerFillQuery((_fill("ord-alpha-refresh"),))
        local_fills = _FakeLocalFillStore()
        current_fill = _fill_record(
            fill_id="fill-alpha-amend",
            intent_id="ord-alpha-amend",
        )
        amended_fill = replace(current_fill, quantity=120)
        local_fills.save_fill(current_fill)
        local_fills.saved_fill_ids.clear()
        import_source = _FakeBrokerFillImportSource(
            {
                "fill-beta-import": _fill_record(
                    fill_id="fill-beta-import",
                    intent_id="ord-beta-import",
                )
            }
        )
        amend_source = _FakeFillAmendmentSource({"fill-alpha-amend": amended_fill})
        local_orders = _FakeLocalOrderStatusStore({"ord-beta-status": "submitted"})
        status_source = _FakeOrderStatusReviewSource({"rec-sequence:0003": "filled"})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "refresh_broker_order": BrokerRefreshRepairHandler(broker),
                "import_broker_fill": ImportBrokerFillRepairHandler(
                    broker_fill_source=import_source,
                    local_fill_store=local_fills,
                ),
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=amend_source,
                    local_fill_store=local_fills,
                ),
                "review_order_status": ReviewOrderStatusRepairHandler(
                    review_source=status_source,
                    local_order_store=local_orders,
                ),
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-sequence",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-sequence")
        assert [result.action_id for result in results] == [
            "rec-sequence:0000",
            "rec-sequence:0001",
            "rec-sequence:0002",
            "rec-sequence:0003",
        ]
        assert [result.status for result in results] == [
            "executed",
            "executed",
            "executed",
            "executed",
        ]
        assert broker.queried_order_ids == ["ord-alpha-refresh"]
        assert import_source.requested_action_ids == ["rec-sequence:0001"]
        assert amend_source.requested_action_ids == ["rec-sequence:0002"]
        assert status_source.requested_action_ids == ["rec-sequence:0003"]
        assert local_fills.saved_fill_ids == ["fill-beta-import"]
        assert local_fills.replaced_fill_ids == ["fill-alpha-amend"]
        assert local_orders.updated == [("ord-beta-status", "filled", ("submitted",))]
        assert audit.results == list(results)
        assert [result.client_order_id for result in results] == [
            "client-alpha-refresh",
            "client-beta-import",
            "client-alpha-amend",
            "client-beta-status",
        ]
        assert [result.broker_order_id for result in results] == [
            "broker-alpha-refresh",
            "broker-beta-import",
            "broker-alpha-amend",
            "broker-beta-status",
        ]
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]
        assert [record.broker_order_id for record in records] == [
            "broker-alpha-refresh",
            "broker-beta-import",
            "broker-alpha-amend",
            "broker-beta-status",
        ]

    def test_report_sequence_closes_duplicate_fill_amendments_without_second_write(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        current = _fill_record(
            fill_id="fill-combined-amend",
            intent_id="ord-combined-amend",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(
            current,
            quantity=100,
            fill_price=4.5,
            notes="combined quantity and price amendment",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        source = _FakeFillAmendmentSource({"fill-combined-amend": amended})
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-duplicate-amend")
        assert [result.action_id for result in results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in results] == ["executed", "executed"]
        assert [result.effect_count for result in results] == [1, 0]
        assert results[1].message == (
            "local fill fill-combined-amend already amended earlier in report"
        )
        assert source.requested_action_ids == ["rec-duplicate-amend:0000"]
        assert source.observed_current_records == [current]
        assert local_fills.replaced_fill_ids == ["fill-combined-amend"]
        assert local_fills.get_fill("fill-combined-amend") == amended
        assert audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]

    def test_report_sequence_blocks_duplicate_fill_amendments_after_first_failure(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        source = _FakeFillAmendmentSource(
            {
                "fill-combined-amend": _fill_record(
                    fill_id="fill-combined-amend",
                    intent_id="ord-combined-amend",
                    quantity=100,
                    fill_price=4.5,
                )
            }
        )
        local_fills = _FakeLocalFillStore()
        audit = _FakeAuditSink()
        executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=audit,
            executor_id="repair-worker",
        )

        results = executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        records = store.list_actions("rec-duplicate-amend")
        assert [result.action_id for result in results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in results] == ["failed", "skipped"]
        assert results[0].message == "local fill fill-combined-amend was not found"
        assert results[1].message == (
            "local fill fill-combined-amend blocked by earlier failed amendment "
            "in report"
        )
        assert source.requested_action_ids == []
        assert source.observed_current_records == []
        assert local_fills.replaced_fill_ids == []
        assert audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.APPROVED,
            RepairActionStatus.APPROVED,
        ]

    def test_report_sequence_blocks_later_same_fill_amendments_while_prior_is_in_flight(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        store = SQLiteRepairWorkflowStore(sqlite_client)
        store.init_schema()
        store.save_plan(
            _duplicate_fill_amendment_plan(),
            created_at="2026-05-31T09:30:00Z",
        )
        for action_id in (
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ):
            store.approve_action(
                action_id,
                reviewer="ops",
                reason="broker statement checked",
                reviewed_at="2026-05-31T09:40:00Z",
            )
        current = _fill_record(
            fill_id="fill-combined-amend",
            intent_id="ord-combined-amend",
            quantity=80,
            fill_price=4.2,
        )
        amended = replace(
            current,
            quantity=100,
            fill_price=4.5,
            notes="combined quantity and price amendment",
        )
        local_fills = _FakeLocalFillStore()
        local_fills.save_fill(current)
        local_fills.saved_fill_ids.clear()
        primary_source = _ReportReentrantFillAmendmentSource(
            {"fill-combined-amend": amended}
        )
        competing_source = _FakeFillAmendmentSource({"fill-combined-amend": amended})
        primary_audit = _FakeAuditSink()
        competing_audit = _FakeAuditSink()
        competing_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=competing_source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=competing_audit,
            executor_id="repair-worker-b",
        )
        primary_source.competing_executor = competing_executor
        primary_executor = RepairActionExecutor(
            workflow_store=store,
            handlers={
                "amend_local_fill": AmendLocalFillRepairHandler(
                    amendment_source=primary_source,
                    local_fill_store=local_fills,
                )
            },
            audit_sink=primary_audit,
            executor_id="repair-worker-a",
        )

        results = primary_executor.execute_report_actions(
            "rec-duplicate-amend",
            executed_at="2026-05-31T09:45:00Z",
        )

        competing_results = primary_source.competing_results
        records = store.list_actions("rec-duplicate-amend")
        assert competing_results is not None
        assert [result.action_id for result in competing_results] == [
            "rec-duplicate-amend:0000",
            "rec-duplicate-amend:0001",
        ]
        assert [result.status for result in competing_results] == [
            "skipped",
            "skipped",
        ]
        assert competing_results[0].message == "repair action is executing"
        assert competing_results[1].message == (
            "local fill fill-combined-amend blocked by earlier in-flight amendment "
            "in report"
        )
        assert [result.status for result in results] == ["executed", "executed"]
        assert [result.effect_count for result in results] == [1, 0]
        assert results[1].message == (
            "local fill fill-combined-amend already amended earlier in report"
        )
        assert primary_source.requested_action_ids == ["rec-duplicate-amend:0000"]
        assert primary_source.observed_current_records == [current]
        assert competing_source.requested_action_ids == []
        assert competing_source.observed_current_records == []
        assert local_fills.replaced_fill_ids == ["fill-combined-amend"]
        assert local_fills.get_fill("fill-combined-amend") == amended
        assert competing_audit.results == list(competing_results)
        assert primary_audit.results == list(results)
        assert [record.status for record in records] == [
            RepairActionStatus.EXECUTED,
            RepairActionStatus.EXECUTED,
        ]
