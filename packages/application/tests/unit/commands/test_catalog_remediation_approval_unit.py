"""Unit tests for catalog remediation approval command handlers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.commands.catalog_remediation import (
    CatalogFreshnessRemediationExecutor,
    CatalogRemediationActionExecutor,
    CatalogRemediationActionExecutorRegistry,
    CatalogRemediationApprovalDecisionCommand,
    CatalogRemediationApprovalExecutionCommand,
    CatalogRemediationApprovalRequestCommand,
    CatalogSourceCoverageRemediationExecutor,
    DatasetPromotionEvidenceRemediationExecutor,
    DecideCatalogRemediationApprovalHandler,
    ExecuteCatalogRemediationApprovalHandler,
    LineageCatalogAssetRemediationExecutor,
    RequestCatalogRemediationApprovalHandler,
)
from ditto_application.contracts import IngestDateCommand
from ditto_application.exceptions import AppCommandError
from ditto_application.queries.remediation_approval import (
    CatalogRemediationApprovalQueryFacade,
)
from ditto_application.remediation_approval import (
    CatalogRemediationActionExecution,
    to_catalog_remediation_approval,
)
from ditto_application.remediation_approval import (
    CatalogRemediationApproval as AppCatalogRemediationApproval,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApproval as DataCatalogRemediationApproval,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalEvent as DataCatalogRemediationApprovalEvent,
)
from ditto_data.models.ingestion import IngestionResult


class _ApprovalStore:
    def __init__(
        self,
        approvals: dict[str, DataCatalogRemediationApproval] | None = None,
    ) -> None:
        self.approvals = approvals or {}
        self.events: list[DataCatalogRemediationApprovalEvent] = []

    def upsert_remediation_approval(
        self,
        approval: DataCatalogRemediationApproval,
    ) -> None:
        self.approvals[approval.approval_id] = approval

    def append_remediation_approval_event(
        self,
        event: DataCatalogRemediationApprovalEvent,
    ) -> None:
        self.events.append(event)

    def get_remediation_approval(
        self,
        approval_id: str,
    ) -> DataCatalogRemediationApproval | None:
        return self.approvals.get(approval_id)

    def list_remediation_approvals(
        self,
        *,
        item_id: str | None = None,
        status: str | None = None,
    ) -> tuple[DataCatalogRemediationApproval, ...]:
        approvals = tuple(self.approvals.values())
        if item_id is not None:
            approvals = tuple(item for item in approvals if item.item_id == item_id)
        if status is not None:
            approvals = tuple(item for item in approvals if item.status == status)
        return tuple(sorted(approvals, key=lambda item: item.requested_at))

    def list_remediation_approval_events(
        self,
        approval_id: str,
    ) -> tuple[DataCatalogRemediationApprovalEvent, ...]:
        return tuple(event for event in self.events if event.approval_id == approval_id)


def _now() -> datetime:
    return datetime(2026, 6, 9, 10, 0, tzinfo=UTC)


def _data_approval(
    approval_id: str = "approval-001",
    *,
    status: str = "requested",
) -> DataCatalogRemediationApproval:
    return DataCatalogRemediationApproval(
        approval_id=approval_id,
        item_id="maturity_governance:stock_daily",
        action="submit_or_fix_promotion_evidence",
        status=status,
        requested_by="architecture-review",
        requested_at=_now(),
        intent_type="write",
        method="POST",
        path="/ingestion/catalog/promotion/evidence",
        request_payload={
            "dataset_id": "stock_daily",
            "criterion": "complete PIT/replay coverage for the dataset",
            "evidence_uri": "ditto://evidence/stock_daily/pit-replay",
            "reviewed_by": "architecture-review",
            "passed": True,
        },
        notes="request approval before persisting reviewer evidence",
    )


def _app_approval(
    approval_id: str = "approval-001",
    *,
    status: str = "requested",
) -> AppCatalogRemediationApproval:
    return AppCatalogRemediationApproval(
        approval_id=approval_id,
        item_id="maturity_governance:stock_daily",
        action="submit_or_fix_promotion_evidence",
        status=status,
        requested_by="architecture-review",
        requested_at=_now(),
        intent_type="write",
        method="POST",
        path="/ingestion/catalog/promotion/evidence",
        request_payload={
            "dataset_id": "stock_daily",
            "criterion": "complete PIT/replay coverage for the dataset",
            "evidence_uri": "ditto://evidence/stock_daily/pit-replay",
            "reviewed_by": "architecture-review",
            "passed": True,
        },
        notes="request approval before persisting reviewer evidence",
    )


class TestRequestCatalogRemediationApprovalHandler:
    """Request handler creates approval state without executing remediation."""

    def test_request_creates_requested_state_and_audit_event(self) -> None:
        store = _ApprovalStore()
        handler = RequestCatalogRemediationApprovalHandler(
            approval_writer=store,
            now=_now,
            approval_id_factory=lambda: "approval-001",
        )

        result = handler.handle(
            CatalogRemediationApprovalRequestCommand(
                item_id="maturity_governance:stock_daily",
                action="submit_or_fix_promotion_evidence",
                requested_by="architecture-review",
                intent_type="write",
                method="POST",
                path="/ingestion/catalog/promotion/evidence",
                request_payload={
                    "dataset_id": "stock_daily",
                    "criterion": "complete PIT/replay coverage for the dataset",
                    "evidence_uri": "ditto://evidence/stock_daily/pit-replay",
                    "reviewed_by": "architecture-review",
                    "passed": True,
                },
                notes="request approval before persisting reviewer evidence",
            )
        )

        assert result.approval == _app_approval()
        assert store.approvals == {"approval-001": _data_approval()}
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="requested",
                actor="architecture-review",
                action_at=_now(),
                status="requested",
                notes="request approval before persisting reviewer evidence",
            )
        ]

        assert len(result.approval.authority_hash) == 64
        assert result.approval.expires_at == datetime(
            2026,
            6,
            9,
            10,
            30,
            tzinfo=UTC,
        )

    def test_rejects_blocked_source_coverage_write_request(self) -> None:
        store = _ApprovalStore()
        handler = RequestCatalogRemediationApprovalHandler(
            approval_writer=store,
            now=_now,
            approval_id_factory=lambda: "approval-001",
        )

        with pytest.raises(
            AppCommandError,
            match="Blocked source selection cannot request catalog source coverage",
        ) as exc_info:
            handler.handle(
                CatalogRemediationApprovalRequestCommand(
                    item_id="source_health:stock_daily:2026-06-01",
                    action="repair_catalog_source_coverage",
                    requested_by="architecture-review",
                    intent_type="write",
                    method="POST",
                    path="/ingestion/stock_daily/2026-06-01",
                    request_payload={
                        "dataset_id": "stock_daily",
                        "trade_date": "2026-06-01",
                        "source_selection_status": "blocked",
                        "source_selection_blockers": ["selected_source_unsupported"],
                    },
                )
            )

        assert exc_info.value.details == {
            "command": "request_catalog_remediation_approval",
            "action": "repair_catalog_source_coverage",
            "source_selection_status": "blocked",
            "source_selection_blockers": ["selected_source_unsupported"],
        }
        assert store.approvals == {}
        assert store.events == []


class TestDecideCatalogRemediationApprovalHandler:
    """Decision handler transitions approval state only."""

    def test_approve_requested_state_without_executing_remediation(self) -> None:
        store = _ApprovalStore({"approval-001": _data_approval()})
        handler = DecideCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            now=lambda: datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogRemediationApprovalDecisionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                decision="approved",
                decided_by="lead-reviewer",
                notes="evidence write is approved",
            )
        )

        assert result.approval == replace(
            _app_approval(),
            status="approved",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
            decision_notes="evidence write is approved",
        )
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="approved",
                actor="lead-reviewer",
                action_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
                status="approved",
                notes="evidence write is approved",
            )
        ]

    def test_rejects_decision_for_missing_approval(self) -> None:
        store = _ApprovalStore()
        handler = DecideCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="Unknown remediation approval"):
            handler.handle(
                CatalogRemediationApprovalDecisionCommand(
                    approval_id="missing",
                    expected_authority_hash="0" * 64,
                    decision="approved",
                    decided_by="lead-reviewer",
                )
            )

    def test_rejects_decision_for_terminal_approval(self) -> None:
        store = _ApprovalStore({"approval-001": _data_approval(status="approved")})
        handler = DecideCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            now=_now,
        )

        with pytest.raises(AppCommandError, match="not pending approval"):
            handler.handle(
                CatalogRemediationApprovalDecisionCommand(
                    approval_id="approval-001",
                    expected_authority_hash=to_catalog_remediation_approval(
                        store.approvals["approval-001"]
                    ).authority_hash,
                    decision="rejected",
                    decided_by="lead-reviewer",
                )
            )

    def test_replays_the_same_decision_without_a_second_audit_event(self) -> None:
        current = replace(
            _data_approval(status="approved"),
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
        )
        store = _ApprovalStore({"approval-001": current})
        handler = DecideCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            now=lambda: datetime(2026, 6, 9, 10, 6, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogRemediationApprovalDecisionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    current
                ).authority_hash,
                decision="approved",
                decided_by="lead-reviewer",
            )
        )

        assert result.approval == to_catalog_remediation_approval(current)
        assert store.events == []

    def test_rejects_decision_for_mismatched_or_expired_authority(self) -> None:
        current = _data_approval()
        store = _ApprovalStore({"approval-001": current})
        handler = DecideCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            now=lambda: datetime(2026, 6, 9, 10, 31, tzinfo=UTC),
        )

        with pytest.raises(AppCommandError, match="authority hash mismatch"):
            handler.handle(
                CatalogRemediationApprovalDecisionCommand(
                    approval_id="approval-001",
                    expected_authority_hash="0" * 64,
                    decision="approved",
                    decided_by="lead-reviewer",
                )
            )

        with pytest.raises(AppCommandError, match="approval has expired"):
            handler.handle(
                CatalogRemediationApprovalDecisionCommand(
                    approval_id="approval-001",
                    expected_authority_hash=_app_approval().authority_hash,
                    decision="approved",
                    decided_by="lead-reviewer",
                )
            )


class _RecordingRemediationActionExecutor:
    action = "submit_or_fix_promotion_evidence"

    def __init__(self) -> None:
        self.executed: list[AppCatalogRemediationApproval] = []

    def execute(
        self,
        approval: AppCatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        self.executed.append(approval)
        return CatalogRemediationActionExecution(
            approval_id=approval.approval_id,
            action=approval.action,
            executed_by=executed_by,
            executed_at=executed_at,
            result_payload={"promotion_status": "ready"},
            notes="promotion evidence persisted",
        )


def _registered_executor_for_action(
    action: str,
    delegate: MagicMock,
) -> CatalogRemediationActionExecutor:
    if action == "submit_or_fix_promotion_evidence":
        return DatasetPromotionEvidenceRemediationExecutor(delegate)
    if action == "repair_catalog_source_coverage":
        return CatalogSourceCoverageRemediationExecutor(delegate)
    if action == "repair_catalog_freshness":
        return CatalogFreshnessRemediationExecutor(delegate)
    if action == "repair_lineage_catalog_asset":
        return LineageCatalogAssetRemediationExecutor(delegate)
    raise AssertionError(f"unknown remediation action fixture: {action}")


class TestExecuteCatalogRemediationApprovalHandler:
    """Execution handler runs only approved remediation actions."""

    def test_executor_registry_rejects_duplicate_action_codes(self) -> None:
        with pytest.raises(AppCommandError, match="Duplicate remediation action"):
            CatalogRemediationActionExecutorRegistry(
                (
                    _RecordingRemediationActionExecutor(),
                    _RecordingRemediationActionExecutor(),
                )
            )

    def test_executes_approved_action_and_marks_approval_completed(self) -> None:
        store = _ApprovalStore({"approval-001": _data_approval(status="approved")})
        executor = _RecordingRemediationActionExecutor()
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry((executor,)),
            now=lambda: datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
                notes="execute approved evidence write",
            )
        )

        assert result.approval == replace(
            _app_approval(status="approved"),
            status="completed",
        )
        assert result.execution == CatalogRemediationActionExecution(
            approval_id="approval-001",
            action="submit_or_fix_promotion_evidence",
            executed_by="ops-runner",
            executed_at=datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
            result_payload={"promotion_status": "ready"},
            notes="promotion evidence persisted",
        )
        assert executor.executed == [_app_approval(status="approved")]
        assert store.approvals["approval-001"].status == "completed"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="completed",
                actor="ops-runner",
                action_at=datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
                status="completed",
                notes="execute approved evidence write",
            )
        ]

    def test_rejects_execution_when_approval_is_not_approved(self) -> None:
        store = _ApprovalStore({"approval-001": _data_approval(status="requested")})
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (_RecordingRemediationActionExecutor(),)
            ),
            now=_now,
        )

        with pytest.raises(AppCommandError, match="not approved"):
            handler.handle(
                CatalogRemediationApprovalExecutionCommand(
                    approval_id="approval-001",
                    expected_authority_hash=to_catalog_remediation_approval(
                        store.approvals["approval-001"]
                    ).authority_hash,
                    executed_by="ops-runner",
                )
            )

        assert store.approvals["approval-001"].status == "requested"
        assert store.events == []

    def test_rejects_execution_after_authority_expiry(self) -> None:
        current = _data_approval(status="approved")
        store = _ApprovalStore({"approval-001": current})
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (_RecordingRemediationActionExecutor(),)
            ),
            now=lambda: datetime(2026, 6, 9, 10, 31, tzinfo=UTC),
        )

        with pytest.raises(AppCommandError, match="approval has expired"):
            handler.handle(
                CatalogRemediationApprovalExecutionCommand(
                    approval_id="approval-001",
                    expected_authority_hash=_app_approval().authority_hash,
                    executed_by="ops-runner",
                )
            )

    def test_replays_completed_execution_as_an_idempotent_skip(self) -> None:
        current = _data_approval(status="completed")
        store = _ApprovalStore({"approval-001": current})
        executor = _RecordingRemediationActionExecutor()
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry((executor,)),
            now=lambda: datetime(2026, 6, 9, 10, 11, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    current
                ).authority_hash,
                executed_by="ops-runner",
            )
        )

        assert result.approval.status == "completed"
        assert result.execution.status == "skipped"
        assert result.execution.result_payload == {"idempotent_replay": True}
        assert executor.executed == []
        assert store.events == []

    def test_rejects_execution_when_action_has_no_executor(self) -> None:
        store = _ApprovalStore(
            {
                "approval-001": replace(
                    _data_approval(status="approved"),
                    action="repair_catalog_source_coverage",
                )
            }
        )
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (_RecordingRemediationActionExecutor(),)
            ),
            now=_now,
        )

        with pytest.raises(AppCommandError, match="Unsupported remediation action"):
            handler.handle(
                CatalogRemediationApprovalExecutionCommand(
                    approval_id="approval-001",
                    expected_authority_hash=to_catalog_remediation_approval(
                        store.approvals["approval-001"]
                    ).authority_hash,
                    executed_by="ops-runner",
                )
            )

        assert store.approvals["approval-001"].status == "approved"
        assert store.events == []

    def test_failed_ingest_execution_keeps_approval_approved_and_audited(
        self,
    ) -> None:
        approved = replace(
            _data_approval(status="approved"),
            action="repair_catalog_freshness",
            request_payload={
                "dataset_id": "stock_daily",
                "trade_date": "2026-06-01",
            },
        )
        store = _ApprovalStore({"approval-001": approved})
        ingest_handler = MagicMock()
        ingest_handler.handle.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2026-06-01",
            status="failed",
            row_count=0,
            message="catalog freshness repair failed",
            error="source unavailable",
        )
        executed_at = datetime(2026, 6, 9, 10, 12, tzinfo=UTC)
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (CatalogFreshnessRemediationExecutor(ingest_handler),)
            ),
            now=lambda: executed_at,
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
                notes="attempt catalog freshness repair",
            )
        )

        assert result.approval.status == "approved"
        assert result.execution.status == "failed"
        assert result.execution.result_payload["error"] == "source unavailable"
        assert store.approvals["approval-001"].status == "approved"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="execution_failed",
                actor="ops-runner",
                action_at=executed_at,
                status="approved",
                notes=(
                    "catalog freshness ingest failed: source unavailable; "
                    "operator_notes=attempt catalog freshness repair"
                ),
            )
        ]

    @pytest.mark.parametrize(
        ("action", "request_payload"),
        [
            (
                "submit_or_fix_promotion_evidence",
                {
                    "dataset_id": "stock_daily",
                    "criterion": "complete PIT/replay coverage for the dataset",
                    "evidence_uri": "ditto://evidence/stock_daily/pit-replay",
                    "reviewed_by": "architecture-review",
                    "passed": True,
                },
            ),
            (
                "repair_catalog_source_coverage",
                {
                    "dataset_id": "stock_daily",
                    "trade_date": "2026-06-01",
                },
            ),
            (
                "repair_catalog_freshness",
                {
                    "dataset_id": "stock_daily",
                    "trade_date": "2026-06-01",
                },
            ),
            (
                "repair_lineage_catalog_asset",
                {
                    "dataset_id": "stock_daily",
                    "namespace": "market",
                    "trade_date": "2026-06-01",
                    "run_id": "run-001",
                    "side": "input",
                    "partition_keys": ["trade_date=2026-06-01"],
                },
            ),
        ],
    )
    def test_registered_action_command_errors_preserve_error_audit_notes(
        self,
        action: str,
        request_payload: dict[str, object],
    ) -> None:
        """All executable action typed failures stay retriable and auditable."""
        approved = replace(
            _data_approval(status="approved"),
            action=action,
            request_payload=request_payload,
        )
        store = _ApprovalStore({"approval-001": approved})
        delegate = MagicMock()
        error_message = f"{action} downstream command failed"
        error_details = {
            "command": f"{action}_command",
            "dataset_id": "stock_daily",
            "action": action,
        }
        delegate.handle.side_effect = AppCommandError(
            error_message,
            **error_details,
        )
        executed_at = datetime(2026, 6, 9, 10, 14, tzinfo=UTC)
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (_registered_executor_for_action(action, delegate),)
            ),
            now=lambda: executed_at,
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
                notes="operator requested retry",
            )
        )

        assert result.approval.status == "approved"
        assert result.execution.status == "failed"
        assert result.execution.result_payload == {
            "error_type": "AppCommandError",
            "error": error_message,
            "details": {
                **error_details,
                "approval_id": "approval-001",
                "item_id": "maturity_governance:stock_daily",
            },
        }
        assert result.execution.notes == error_message
        assert store.approvals["approval-001"].status == "approved"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="execution_failed",
                actor="ops-runner",
                action_at=executed_at,
                status="approved",
                notes=f"{error_message}; operator_notes=operator requested retry",
            )
        ]

    def test_invalid_approved_payload_keeps_context_and_does_not_dispatch(
        self,
    ) -> None:
        """Invalid approved payloads fail with execution context before dispatch."""
        approved = replace(
            _data_approval(status="approved"),
            item_id="maturity_governance:stock_daily",
            action="repair_catalog_freshness",
            request_payload={
                "dataset_id": "stock_daily",
            },
        )
        store = _ApprovalStore({"approval-001": approved})
        ingest_handler = MagicMock()
        executed_at = datetime(2026, 6, 9, 10, 15, tzinfo=UTC)
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (CatalogFreshnessRemediationExecutor(ingest_handler),)
            ),
            now=lambda: executed_at,
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
                notes="operator needs to fix payload",
            )
        )

        assert result.approval.status == "approved"
        assert result.execution.status == "failed"
        assert result.execution.result_payload == {
            "error_type": "AppCommandError",
            "error": "Missing remediation execution payload field: trade_date",
            "details": {
                "command": "execute_catalog_remediation_approval",
                "approval_id": "approval-001",
                "item_id": "maturity_governance:stock_daily",
                "action": "repair_catalog_freshness",
                "field": "trade_date",
            },
        }
        ingest_handler.handle.assert_not_called()
        assert store.approvals["approval-001"].status == "approved"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="execution_failed",
                actor="ops-runner",
                action_at=executed_at,
                status="approved",
                notes=(
                    "Missing remediation execution payload field: trade_date; "
                    "operator_notes=operator needs to fix payload"
                ),
            )
        ]

    def test_blocked_source_coverage_execution_fails_before_ingest_dispatch(
        self,
    ) -> None:
        approved = replace(
            _data_approval(status="approved"),
            item_id="source_health:stock_daily:2026-06-01",
            action="repair_catalog_source_coverage",
            request_payload={
                "dataset_id": "stock_daily",
                "trade_date": "2026-06-01",
                "source_selection_status": "blocked",
                "source_selection_blockers": ["selected_source_unsupported"],
            },
        )
        store = _ApprovalStore({"approval-001": approved})
        ingest_handler = MagicMock()
        executed_at = datetime(2026, 6, 9, 10, 16, tzinfo=UTC)
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (CatalogSourceCoverageRemediationExecutor(ingest_handler),)
            ),
            now=lambda: executed_at,
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
                notes="legacy approval should fail closed",
            )
        )

        assert result.approval.status == "approved"
        assert result.execution.status == "failed"
        assert result.execution.result_payload == {
            "error_type": "AppCommandError",
            "error": (
                "Blocked source selection cannot execute catalog source coverage repair"
            ),
            "details": {
                "command": "execute_catalog_remediation_approval",
                "action": "repair_catalog_source_coverage",
                "source_selection_status": "blocked",
                "source_selection_blockers": ["selected_source_unsupported"],
                "approval_id": "approval-001",
                "item_id": "source_health:stock_daily:2026-06-01",
            },
        }
        ingest_handler.handle.assert_not_called()
        assert store.approvals["approval-001"].status == "approved"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="execution_failed",
                actor="ops-runner",
                action_at=executed_at,
                status="approved",
                notes=(
                    "Blocked source selection cannot execute catalog source coverage "
                    "repair; operator_notes=legacy approval should fail closed"
                ),
            )
        ]

    def test_ingest_command_error_keeps_approval_approved_and_audited(
        self,
    ) -> None:
        """ingest-date 抛 typed AppCommandError 时也应返回 failed execution 证据."""
        approved = replace(
            _data_approval(status="approved"),
            action="repair_catalog_freshness",
            request_payload={
                "dataset_id": "stock_daily",
                "trade_date": "2026-06-01",
            },
        )
        store = _ApprovalStore({"approval-001": approved})
        ingest_handler = MagicMock()
        ingest_handler.handle.side_effect = AppCommandError(
            "Data source 'fred' does not support dataset stock_daily",
            command="ingest_date",
            dataset="stock_daily",
            trade_date="2026-06-01",
            force=True,
            field="source_name",
            value="fred",
            supported=["tushare"],
            operation="ingest_date",
            selection_date="2026-06-01",
        )
        executed_at = datetime(2026, 6, 9, 10, 13, tzinfo=UTC)
        handler = ExecuteCatalogRemediationApprovalHandler(
            approval_reader=store,
            approval_writer=store,
            executor_registry=CatalogRemediationActionExecutorRegistry(
                (CatalogFreshnessRemediationExecutor(ingest_handler),)
            ),
            now=lambda: executed_at,
        )

        result = handler.handle(
            CatalogRemediationApprovalExecutionCommand(
                approval_id="approval-001",
                expected_authority_hash=to_catalog_remediation_approval(
                    store.approvals["approval-001"]
                ).authority_hash,
                executed_by="ops-runner",
            )
        )

        assert result.approval.status == "approved"
        assert result.execution.status == "failed"
        assert result.execution.result_payload == {
            "error_type": "AppCommandError",
            "error": "Data source 'fred' does not support dataset stock_daily",
            "details": {
                "command": "ingest_date",
                "dataset": "stock_daily",
                "trade_date": "2026-06-01",
                "force": True,
                "field": "source_name",
                "value": "fred",
                "supported": ["tushare"],
                "operation": "ingest_date",
                "selection_date": "2026-06-01",
                "approval_id": "approval-001",
                "item_id": "maturity_governance:stock_daily",
                "action": "repair_catalog_freshness",
            },
        }
        assert result.execution.notes == (
            "Data source 'fred' does not support dataset stock_daily"
        )
        assert store.approvals["approval-001"].status == "approved"
        assert store.events == [
            DataCatalogRemediationApprovalEvent(
                approval_id="approval-001",
                action="execution_failed",
                actor="ops-runner",
                action_at=executed_at,
                status="approved",
                notes="Data source 'fred' does not support dataset stock_daily",
            )
        ]

    def test_promotion_evidence_executor_delegates_to_existing_review_handler(
        self,
    ) -> None:
        review_handler = MagicMock()
        reviewed_at = datetime(2026, 6, 9, 10, 10, tzinfo=UTC)
        review_handler.handle.return_value = SimpleNamespace(
            dataset_id="stock_daily",
            reviewed_criterion="complete PIT/replay coverage for the dataset",
            evidence_uri="ditto://evidence/stock_daily/pit-replay",
            reviewed_by="architecture-review",
            passed=True,
            reviewed_at=reviewed_at,
            promotion_status="ready",
            missing_criteria=(),
            satisfied_criteria=("complete PIT/replay coverage for the dataset",),
            rejected_criteria=(),
            metadata_promoted=False,
            dataset_maturity_before="experimental",
            dataset_maturity_after="experimental",
        )
        executor = DatasetPromotionEvidenceRemediationExecutor(review_handler)

        execution = executor.execute(
            _app_approval(status="approved"),
            executed_by="ops-runner",
            executed_at=reviewed_at,
        )

        assert execution.result_payload["dataset_id"] == "stock_daily"
        assert execution.result_payload["promotion_status"] == "ready"
        assert execution.notes == "promotion evidence persisted"
        review_handler.handle.assert_called_once()
        command = review_handler.handle.call_args.args[0]
        assert command.dataset_id == "stock_daily"
        assert command.criterion == "complete PIT/replay coverage for the dataset"
        assert command.evidence_uri == "ditto://evidence/stock_daily/pit-replay"

    def test_source_coverage_executor_delegates_to_ingest_date_handler(self) -> None:
        ingest_handler = MagicMock()
        ingested_at = datetime(2026, 6, 9, 10, 15, tzinfo=UTC)
        ingest_handler.handle.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2026-06-01",
            status="success",
            row_count=3580,
            checksum="sha256:catalog-repair",
            message="catalog source coverage repaired",
        )
        executor = CatalogSourceCoverageRemediationExecutor(ingest_handler)

        execution = executor.execute(
            replace(
                _app_approval(status="approved"),
                item_id="source_health:stock_daily:2026-06-01",
                action="repair_catalog_source_coverage",
                path="/ingestion/stock_daily/2026-06-01",
                request_payload={
                    "dataset_id": "stock_daily",
                    "trade_date": "2026-06-01",
                },
            ),
            executed_by="ops-runner",
            executed_at=ingested_at,
        )

        ingest_handler.handle.assert_called_once_with(
            IngestDateCommand(
                dataset="stock_daily",
                trade_date=date(2026, 6, 1),
                force=True,
            )
        )
        assert execution == CatalogRemediationActionExecution(
            approval_id="approval-001",
            action="repair_catalog_source_coverage",
            executed_by="ops-runner",
            executed_at=ingested_at,
            result_payload={
                "dataset_id": "stock_daily",
                "trade_date": "2026-06-01",
                "status": "success",
                "row_count": 3580,
                "checksum": "sha256:catalog-repair",
                "message": "catalog source coverage repaired",
                "error": None,
                "force": True,
            },
            notes="catalog source coverage ingest completed",
        )

    def test_catalog_freshness_executor_delegates_to_ingest_date_handler(
        self,
    ) -> None:
        ingest_handler = MagicMock()
        ingested_at = datetime(2026, 6, 9, 10, 18, tzinfo=UTC)
        ingest_handler.handle.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2026-06-01",
            status="success",
            row_count=3580,
            checksum="sha256:freshness-repair",
            message="catalog freshness repaired",
        )
        executor = CatalogFreshnessRemediationExecutor(ingest_handler)

        execution = executor.execute(
            replace(
                _app_approval(status="approved"),
                item_id="maturity_governance:stock_daily",
                action="repair_catalog_freshness",
                path="/ingestion/stock_daily/2026-06-01",
                request_payload={
                    "dataset_id": "stock_daily",
                    "trade_date": "2026-06-01",
                    "force": False,
                    "source": "auto",
                },
            ),
            executed_by="ops-runner",
            executed_at=ingested_at,
        )

        ingest_handler.handle.assert_called_once_with(
            IngestDateCommand(
                dataset="stock_daily",
                trade_date=date(2026, 6, 1),
                force=False,
            )
        )
        assert execution == CatalogRemediationActionExecution(
            approval_id="approval-001",
            action="repair_catalog_freshness",
            executed_by="ops-runner",
            executed_at=ingested_at,
            result_payload={
                "dataset_id": "stock_daily",
                "trade_date": "2026-06-01",
                "status": "success",
                "row_count": 3580,
                "checksum": "sha256:freshness-repair",
                "message": "catalog freshness repaired",
                "error": None,
                "force": False,
            },
            notes="catalog freshness ingest completed",
        )

    def test_lineage_catalog_asset_executor_delegates_to_ingest_date_handler(
        self,
    ) -> None:
        ingest_handler = MagicMock()
        ingested_at = datetime(2026, 6, 9, 10, 20, tzinfo=UTC)
        ingest_handler.handle.return_value = IngestionResult(
            dataset="stock_daily",
            trade_date="2026-06-01",
            status="success",
            row_count=3580,
            checksum="sha256:lineage-repair",
            message="lineage catalog asset repaired",
        )
        executor = LineageCatalogAssetRemediationExecutor(ingest_handler)

        execution = executor.execute(
            replace(
                _app_approval(status="approved"),
                item_id=(
                    "lineage_catalog:run-001:input:market:stock_daily:"
                    "trade_date=2026-06-01"
                ),
                action="repair_lineage_catalog_asset",
                path="/ingestion/stock_daily/2026-06-01",
                request_payload={
                    "dataset_id": "stock_daily",
                    "namespace": "market",
                    "trade_date": "2026-06-01",
                    "run_id": "run-001",
                    "side": "input",
                    "partition_keys": ["trade_date=2026-06-01"],
                    "force": False,
                },
            ),
            executed_by="ops-runner",
            executed_at=ingested_at,
        )

        ingest_handler.handle.assert_called_once_with(
            IngestDateCommand(
                dataset="stock_daily",
                trade_date=date(2026, 6, 1),
                force=False,
            )
        )
        assert execution == CatalogRemediationActionExecution(
            approval_id="approval-001",
            action="repair_lineage_catalog_asset",
            executed_by="ops-runner",
            executed_at=ingested_at,
            result_payload={
                "dataset_id": "stock_daily",
                "namespace": "market",
                "trade_date": "2026-06-01",
                "run_id": "run-001",
                "side": "input",
                "partition_keys": ["trade_date=2026-06-01"],
                "status": "success",
                "row_count": 3580,
                "checksum": "sha256:lineage-repair",
                "message": "lineage catalog asset repaired",
                "error": None,
                "force": False,
            },
            notes="lineage catalog asset ingest completed",
        )


class TestCatalogRemediationApprovalQueryFacade:
    """Query facade exposes current approval state and audit events."""

    def test_lists_approval_state_by_item_and_status(self) -> None:
        store = _ApprovalStore(
            {
                "approval-001": _data_approval(),
                "approval-002": replace(
                    _data_approval("approval-002"),
                    item_id="source_health:stock_daily:2026-06-01",
                    action="repair_catalog_source_coverage",
                    status="rejected",
                ),
            }
        )
        facade = CatalogRemediationApprovalQueryFacade(approval_reader=store)

        assert facade.list_remediation_approvals(
            item_id="maturity_governance:stock_daily",
            status="requested",
        ) == (_app_approval(),)
        assert (
            facade.list_remediation_approvals(
                item_id="source_health:stock_daily:2026-06-01",
                status=None,
            )[0].action
            == "repair_catalog_source_coverage"
        )

    def test_lists_approval_audit_events_as_application_dtos(self) -> None:
        store = _ApprovalStore({"approval-001": _data_approval(status="approved")})
        store.events.extend(
            (
                DataCatalogRemediationApprovalEvent(
                    approval_id="approval-001",
                    action="approved",
                    actor="lead-reviewer",
                    action_at=datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
                    status="approved",
                    notes="approved for execution",
                ),
                DataCatalogRemediationApprovalEvent(
                    approval_id="approval-001",
                    action="execution_failed",
                    actor="ops-runner",
                    action_at=datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
                    status="approved",
                    notes="missing required field: trade_date",
                ),
                DataCatalogRemediationApprovalEvent(
                    approval_id="approval-002",
                    action="requested",
                    actor="other-operator",
                    action_at=datetime(2026, 6, 9, 10, 1, tzinfo=UTC),
                    status="requested",
                ),
            )
        )
        facade = CatalogRemediationApprovalQueryFacade(approval_reader=store)

        events = facade.list_remediation_approval_events("approval-001")

        assert [event.action for event in events] == ["approved", "execution_failed"]
        assert events[0].actor == "lead-reviewer"
        assert events[1].status == "approved"
        assert events[1].notes == "missing required field: trade_date"
