"""Catalog remediation approval command handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Protocol, cast
from uuid import uuid4

from ditto_data.catalog.remediation import (
    CatalogRemediationApproval as DataCatalogRemediationApproval,
)
from ditto_data.catalog.remediation import (
    CatalogRemediationApprovalEvent,
    CatalogRemediationApprovalReader,
    CatalogRemediationApprovalWriter,
)
from ditto_data.models.ingestion import IngestionResult

from ditto_application.commands.catalog import (
    DatasetPromotionReviewCommand,
    ReviewDatasetPromotionEvidenceHandler,
)
from ditto_application.contracts import IngestDateCommand
from ditto_application.exceptions import AppCommandError
from ditto_application.remediation_approval import (
    CatalogRemediationActionExecution,
    CatalogRemediationActionExecutionStatus,
    CatalogRemediationApproval,
    CatalogRemediationApprovalDecision,
    to_catalog_remediation_approval,
)

__all__ = [
    "CatalogFreshnessRemediationExecutor",
    "CatalogRemediationActionExecutor",
    "CatalogRemediationActionExecutorRegistry",
    "CatalogRemediationApprovalDecisionCommand",
    "CatalogRemediationApprovalExecutionCommand",
    "CatalogRemediationApprovalRequestCommand",
    "CatalogRemediationApprovalResult",
    "CatalogRemediationExecutionResult",
    "CatalogRemediationIngestDatePort",
    "CatalogSourceCoverageRemediationExecutor",
    "DatasetPromotionEvidenceRemediationExecutor",
    "DecideCatalogRemediationApprovalHandler",
    "ExecuteCatalogRemediationApprovalHandler",
    "LineageCatalogAssetRemediationExecutor",
    "RequestCatalogRemediationApprovalHandler",
]

_BLOCKED_SOURCE_SELECTION_STATUS = "blocked"
_SOURCE_COVERAGE_REPAIR_ACTION = "repair_catalog_source_coverage"


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalRequestCommand:
    """Operator request to persist approval state for one remediation intent."""

    item_id: str
    action: str
    requested_by: str
    intent_type: str
    method: str | None
    path: str | None
    request_payload: dict[str, object]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalDecisionCommand:
    """Operator decision for a pending remediation approval request."""

    approval_id: str
    expected_authority_hash: str
    decision: CatalogRemediationApprovalDecision
    decided_by: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalExecutionCommand:
    """Operator request to execute one approved remediation action."""

    approval_id: str
    expected_authority_hash: str
    executed_by: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogRemediationApprovalResult:
    """Current remediation approval state after a command."""

    approval: CatalogRemediationApproval


@dataclass(frozen=True, slots=True)
class CatalogRemediationExecutionResult:
    """Approved remediation execution result and resulting approval state."""

    approval: CatalogRemediationApproval
    execution: CatalogRemediationActionExecution


class CatalogRemediationActionExecutor(Protocol):
    """Execute one supported remediation action behind the application boundary."""

    action: str

    def execute(
        self,
        approval: CatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        """Execute an approved remediation action and return backend evidence."""
        ...


class CatalogRemediationIngestDatePort(Protocol):
    """Application-owned port for remediation-triggered date ingestion."""

    def handle(self, command: IngestDateCommand) -> IngestionResult:
        """Run one ingestion command and return its result."""
        ...


class CatalogRemediationActionExecutorRegistry:
    """Small action-code registry for approved remediation executors."""

    def __init__(
        self,
        executors: tuple[CatalogRemediationActionExecutor, ...],
    ) -> None:
        self._executors: dict[str, CatalogRemediationActionExecutor] = {}
        for executor in executors:
            if executor.action in self._executors:
                raise AppCommandError(
                    f"Duplicate remediation action executor: {executor.action}",
                    command="register_catalog_remediation_action_executor",
                    action=executor.action,
                )
            self._executors[executor.action] = executor

    def get(self, action: str) -> CatalogRemediationActionExecutor | None:
        """Return an executor for a remediation action code."""
        return self._executors.get(action)


class RequestCatalogRemediationApprovalHandler:
    """Persist a pending remediation approval request without executing it."""

    def __init__(
        self,
        approval_writer: CatalogRemediationApprovalWriter,
        *,
        now: Callable[[], datetime] | None = None,
        approval_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._approval_writer = approval_writer
        self._now = now or _utcnow
        self._approval_id_factory = approval_id_factory or _new_approval_id

    def handle(
        self,
        command: CatalogRemediationApprovalRequestCommand,
    ) -> CatalogRemediationApprovalResult:
        """Create current approval state and append a requested audit event."""
        _ensure_source_coverage_repair_not_blocked(
            command.action,
            command.request_payload,
            command="request_catalog_remediation_approval",
            verb="request",
        )
        requested_at = self._now()
        approval = DataCatalogRemediationApproval(
            approval_id=self._approval_id_factory(),
            item_id=command.item_id,
            action=command.action,
            status="requested",
            requested_by=command.requested_by,
            requested_at=requested_at,
            intent_type=command.intent_type,
            method=command.method,
            path=command.path,
            request_payload=command.request_payload,
            notes=command.notes,
        )
        event = CatalogRemediationApprovalEvent(
            approval_id=approval.approval_id,
            action="requested",
            actor=command.requested_by,
            action_at=requested_at,
            status="requested",
            notes=command.notes,
        )
        self._approval_writer.upsert_remediation_approval(approval)
        self._approval_writer.append_remediation_approval_event(event)
        return CatalogRemediationApprovalResult(
            approval=to_catalog_remediation_approval(approval)
        )


class ExecuteCatalogRemediationApprovalHandler:
    """Execute an approved remediation action through a registered executor."""

    def __init__(
        self,
        approval_reader: CatalogRemediationApprovalReader,
        approval_writer: CatalogRemediationApprovalWriter,
        executor_registry: CatalogRemediationActionExecutorRegistry,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._approval_reader = approval_reader
        self._approval_writer = approval_writer
        self._executor_registry = executor_registry
        self._now = now or _utcnow

    def handle(
        self,
        command: CatalogRemediationApprovalExecutionCommand,
    ) -> CatalogRemediationExecutionResult:
        """Run an approved action and persist completed state plus audit event."""
        current = self._approval_reader.get_remediation_approval(command.approval_id)
        if current is None:
            raise AppCommandError(
                f"Unknown remediation approval: {command.approval_id}",
                command="execute_catalog_remediation_approval",
                approval_id=command.approval_id,
            )
        if current.status == "completed":
            app_approval = _verify_approval_authority_hash(
                current,
                expected_authority_hash=command.expected_authority_hash,
                command="execute_catalog_remediation_approval",
            )
            return CatalogRemediationExecutionResult(
                approval=app_approval,
                execution=CatalogRemediationActionExecution(
                    approval_id=current.approval_id,
                    action=current.action,
                    executed_by=command.executed_by,
                    executed_at=self._now(),
                    result_payload={"idempotent_replay": True},
                    status="skipped",
                    notes="remediation execution already completed",
                ),
            )
        if current.status != "approved":
            raise AppCommandError(
                f"Remediation approval is not approved: {command.approval_id}",
                command="execute_catalog_remediation_approval",
                approval_id=command.approval_id,
                status=current.status,
            )
        app_approval = _verify_approval_authority(
            current,
            expected_authority_hash=command.expected_authority_hash,
            now=self._now(),
            command="execute_catalog_remediation_approval",
        )
        executor = self._executor_registry.get(current.action)
        if executor is None:
            raise AppCommandError(
                f"Unsupported remediation action: {current.action}",
                command="execute_catalog_remediation_approval",
                approval_id=command.approval_id,
                action=current.action,
            )

        executed_at = self._now()
        try:
            execution = executor.execute(
                app_approval,
                executed_by=command.executed_by,
                executed_at=executed_at,
            )
        except AppCommandError as exc:
            execution = CatalogRemediationActionExecution(
                approval_id=command.approval_id,
                action=current.action,
                executed_by=command.executed_by,
                executed_at=executed_at,
                result_payload=_command_error_payload(exc, approval=app_approval),
                status="failed",
                notes=str(exc),
            )
        if execution.status == "failed":
            event = CatalogRemediationApprovalEvent(
                approval_id=command.approval_id,
                action="execution_failed",
                actor=command.executed_by,
                action_at=executed_at,
                status=current.status,
                notes=_execution_failed_notes(
                    execution_notes=execution.notes,
                    operator_notes=command.notes,
                ),
            )
            self._approval_writer.append_remediation_approval_event(event)
            return CatalogRemediationExecutionResult(
                approval=app_approval,
                execution=execution,
            )

        completed = replace(current, status="completed")
        event = CatalogRemediationApprovalEvent(
            approval_id=command.approval_id,
            action="completed",
            actor=command.executed_by,
            action_at=executed_at,
            status="completed",
            notes=command.notes or execution.notes,
        )
        self._approval_writer.upsert_remediation_approval(completed)
        self._approval_writer.append_remediation_approval_event(event)
        return CatalogRemediationExecutionResult(
            approval=to_catalog_remediation_approval(completed),
            execution=execution,
        )


class DatasetPromotionEvidenceRemediationExecutor:
    """Execute the promotion-evidence remediation action through its handler."""

    action = "submit_or_fix_promotion_evidence"

    def __init__(self, review_handler: ReviewDatasetPromotionEvidenceHandler) -> None:
        self._review_handler = review_handler

    def execute(
        self,
        approval: CatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        """Persist reviewer evidence for an approved promotion remediation."""
        payload = approval.request_payload
        result = self._review_handler.handle(
            DatasetPromotionReviewCommand(
                dataset_id=_required_str(payload, "dataset_id"),
                criterion=_required_str(payload, "criterion"),
                evidence_uri=_required_str(payload, "evidence_uri"),
                reviewed_by=_required_str(payload, "reviewed_by"),
                passed=_optional_bool(payload, "passed", default=True),
                notes=_optional_str(payload, "notes"),
            )
        )
        return CatalogRemediationActionExecution(
            approval_id=approval.approval_id,
            action=approval.action,
            executed_by=executed_by,
            executed_at=executed_at,
            result_payload={
                "dataset_id": result.dataset_id,
                "reviewed_criterion": result.reviewed_criterion,
                "evidence_uri": result.evidence_uri,
                "reviewed_by": result.reviewed_by,
                "passed": result.passed,
                "reviewed_at": result.reviewed_at.isoformat(),
                "promotion_status": result.promotion_status,
                "missing_criteria": list(result.missing_criteria),
                "satisfied_criteria": list(result.satisfied_criteria),
                "rejected_criteria": list(result.rejected_criteria),
                "metadata_promoted": result.metadata_promoted,
                "dataset_maturity_before": result.dataset_maturity_before,
                "dataset_maturity_after": result.dataset_maturity_after,
            },
            status="success",
            notes="promotion evidence persisted",
        )


class CatalogSourceCoverageRemediationExecutor:
    """Execute source coverage repair through the existing ingest-date command."""

    action = _SOURCE_COVERAGE_REPAIR_ACTION

    def __init__(self, ingest_date_port: CatalogRemediationIngestDatePort) -> None:
        self._ingest_date_port = ingest_date_port

    def execute(
        self,
        approval: CatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        """Force a catalog/source-aware one-day ingest for the approved asset."""
        payload = approval.request_payload
        _ensure_source_coverage_repair_not_blocked(
            approval.action,
            payload,
            command="execute_catalog_remediation_approval",
            verb="execute",
        )
        dataset_id = _required_str(payload, "dataset_id")
        trade_date_text = _required_str(payload, "trade_date")
        force = _optional_bool(payload, "force", default=True)
        result = self._ingest_date_port.handle(
            IngestDateCommand(
                dataset=dataset_id,
                trade_date=_required_date(trade_date_text),
                force=force,
            )
        )
        return CatalogRemediationActionExecution(
            approval_id=approval.approval_id,
            action=approval.action,
            executed_by=executed_by,
            executed_at=executed_at,
            result_payload={
                "dataset_id": result.dataset,
                "trade_date": result.trade_date,
                "status": result.status,
                "row_count": result.row_count,
                "checksum": result.checksum,
                "message": result.message,
                "error": result.error,
                "force": force,
            },
            status=_ingestion_execution_status(result),
            notes=_ingestion_execution_notes("catalog source coverage", result),
        )


class CatalogFreshnessRemediationExecutor:
    """Execute catalog freshness repair through source-aware date ingestion."""

    action = "repair_catalog_freshness"

    def __init__(self, ingest_date_port: CatalogRemediationIngestDatePort) -> None:
        self._ingest_date_port = ingest_date_port

    def execute(
        self,
        approval: CatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        """Refresh one dataset/date catalog entry via the ingest-date path."""
        payload = approval.request_payload
        dataset_id = _required_str(payload, "dataset_id")
        trade_date_text = _required_str(payload, "trade_date")
        force = _optional_bool(payload, "force", default=True)
        result = self._ingest_date_port.handle(
            IngestDateCommand(
                dataset=dataset_id,
                trade_date=_required_date(trade_date_text),
                force=force,
            )
        )
        return CatalogRemediationActionExecution(
            approval_id=approval.approval_id,
            action=approval.action,
            executed_by=executed_by,
            executed_at=executed_at,
            result_payload={
                "dataset_id": result.dataset,
                "trade_date": result.trade_date,
                "status": result.status,
                "row_count": result.row_count,
                "checksum": result.checksum,
                "message": result.message,
                "error": result.error,
                "force": force,
            },
            status=_ingestion_execution_status(result),
            notes=_ingestion_execution_notes("catalog freshness", result),
        )


class LineageCatalogAssetRemediationExecutor:
    """Execute lineage catalog asset repair through source-aware date ingestion."""

    action = "repair_lineage_catalog_asset"

    def __init__(self, ingest_date_port: CatalogRemediationIngestDatePort) -> None:
        self._ingest_date_port = ingest_date_port

    def execute(
        self,
        approval: CatalogRemediationApproval,
        *,
        executed_by: str,
        executed_at: datetime,
    ) -> CatalogRemediationActionExecution:
        """Rebuild one lineage asset's catalog entry via the ingest-date path."""
        payload = approval.request_payload
        dataset_id = _required_str(payload, "dataset_id")
        trade_date_text = _required_str(payload, "trade_date")
        force = _optional_bool(payload, "force", default=True)
        partition_keys = _optional_str_sequence(payload, "partition_keys")
        result = self._ingest_date_port.handle(
            IngestDateCommand(
                dataset=dataset_id,
                trade_date=_required_date(trade_date_text),
                force=force,
            )
        )
        return CatalogRemediationActionExecution(
            approval_id=approval.approval_id,
            action=approval.action,
            executed_by=executed_by,
            executed_at=executed_at,
            result_payload={
                "dataset_id": result.dataset,
                "namespace": _optional_str(payload, "namespace"),
                "trade_date": result.trade_date,
                "run_id": _optional_str(payload, "run_id"),
                "side": _optional_str(payload, "side"),
                "partition_keys": list(partition_keys),
                "status": result.status,
                "row_count": result.row_count,
                "checksum": result.checksum,
                "message": result.message,
                "error": result.error,
                "force": force,
            },
            status=_ingestion_execution_status(result),
            notes=_ingestion_execution_notes("lineage catalog asset", result),
        )


class DecideCatalogRemediationApprovalHandler:
    """Approve or reject a pending remediation approval without execution."""

    def __init__(
        self,
        approval_reader: CatalogRemediationApprovalReader,
        approval_writer: CatalogRemediationApprovalWriter,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._approval_reader = approval_reader
        self._approval_writer = approval_writer
        self._now = now or _utcnow

    def handle(
        self,
        command: CatalogRemediationApprovalDecisionCommand,
    ) -> CatalogRemediationApprovalResult:
        """Transition a pending approval to approved or rejected."""
        current = self._approval_reader.get_remediation_approval(command.approval_id)
        if current is None:
            raise AppCommandError(
                f"Unknown remediation approval: {command.approval_id}",
                command="decide_catalog_remediation_approval",
                approval_id=command.approval_id,
            )
        if current.status == command.decision:
            return CatalogRemediationApprovalResult(
                approval=_verify_approval_authority_hash(
                    current,
                    expected_authority_hash=command.expected_authority_hash,
                    command="decide_catalog_remediation_approval",
                )
            )
        if current.status != "requested":
            raise AppCommandError(
                f"Remediation approval is not pending approval: {command.approval_id}",
                command="decide_catalog_remediation_approval",
                approval_id=command.approval_id,
                status=current.status,
            )

        decided_at = self._now()
        _verify_approval_authority(
            current,
            expected_authority_hash=command.expected_authority_hash,
            now=decided_at,
            command="decide_catalog_remediation_approval",
        )
        approval = replace(
            current,
            status=command.decision,
            decided_by=command.decided_by,
            decided_at=decided_at,
            decision_notes=command.notes,
        )
        event = CatalogRemediationApprovalEvent(
            approval_id=command.approval_id,
            action=command.decision,
            actor=command.decided_by,
            action_at=decided_at,
            status=command.decision,
            notes=command.notes,
        )
        self._approval_writer.upsert_remediation_approval(approval)
        self._approval_writer.append_remediation_approval_event(event)
        return CatalogRemediationApprovalResult(
            approval=to_catalog_remediation_approval(approval)
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_approval_id() -> str:
    return f"remediation-approval-{uuid4().hex}"


def _verify_approval_authority(
    approval: DataCatalogRemediationApproval,
    *,
    expected_authority_hash: str,
    now: datetime,
    command: str,
) -> CatalogRemediationApproval:
    app_approval = _verify_approval_authority_hash(
        approval,
        expected_authority_hash=expected_authority_hash,
        command=command,
    )
    if now >= app_approval.expires_at:
        raise AppCommandError(
            f"Remediation approval has expired: {approval.approval_id}",
            command=command,
            approval_id=approval.approval_id,
            expires_at=app_approval.expires_at.isoformat(),
        )
    return app_approval


def _verify_approval_authority_hash(
    approval: DataCatalogRemediationApproval,
    *,
    expected_authority_hash: str,
    command: str,
) -> CatalogRemediationApproval:
    app_approval = to_catalog_remediation_approval(approval)
    if expected_authority_hash != app_approval.authority_hash:
        raise AppCommandError(
            f"Remediation approval authority hash mismatch: {approval.approval_id}",
            command=command,
            approval_id=approval.approval_id,
            expected_authority_hash=expected_authority_hash,
            authority_hash=app_approval.authority_hash,
        )
    return app_approval


def _ensure_source_coverage_repair_not_blocked(
    action: str,
    payload: dict[str, object],
    *,
    command: str,
    verb: str,
) -> None:
    if action != _SOURCE_COVERAGE_REPAIR_ACTION:
        return
    if payload.get("source_selection_status") != _BLOCKED_SOURCE_SELECTION_STATUS:
        return
    raise AppCommandError(
        f"Blocked source selection cannot {verb} catalog source coverage repair",
        command=command,
        action=action,
        source_selection_status=_BLOCKED_SOURCE_SELECTION_STATUS,
        source_selection_blockers=list(
            _string_sequence_for_error(payload.get("source_selection_blockers"))
        ),
    )


def _string_sequence_for_error(value: object) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        return tuple(item for item in sequence if isinstance(item, str))
    return ()


def _required_str(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if isinstance(value, str) and value:
        return value
    raise AppCommandError(
        f"Missing remediation execution payload field: {field}",
        command="execute_catalog_remediation_approval",
        field=field,
    )


def _optional_str(payload: dict[str, object], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise AppCommandError(
        f"Invalid remediation execution payload field: {field}",
        command="execute_catalog_remediation_approval",
        field=field,
    )


def _optional_bool(
    payload: dict[str, object],
    field: str,
    *,
    default: bool,
) -> bool:
    value = payload.get(field, default)
    if isinstance(value, bool):
        return value
    raise AppCommandError(
        f"Invalid remediation execution payload field: {field}",
        command="execute_catalog_remediation_approval",
        field=field,
    )


def _optional_str_sequence(
    payload: dict[str, object],
    field: str,
) -> tuple[str, ...]:
    value = payload.get(field)
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        normalized: list[str] = []
        for item in sequence:
            if not isinstance(item, str):
                break
            normalized.append(item)
        else:
            return tuple(normalized)
    raise AppCommandError(
        f"Invalid remediation execution payload field: {field}",
        command="execute_catalog_remediation_approval",
        field=field,
    )


def _required_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AppCommandError(
            f"Invalid remediation execution payload date: {value}",
            command="execute_catalog_remediation_approval",
            field="trade_date",
        ) from exc


def _ingestion_execution_status(
    result: IngestionResult,
) -> CatalogRemediationActionExecutionStatus:
    if result.status in ("success", "skipped", "failed"):
        return result.status
    return "failed"


def _ingestion_execution_notes(label: str, result: IngestionResult) -> str:
    if result.status == "failed":
        if result.error:
            return f"{label} ingest failed: {result.error}"
        return f"{label} ingest failed"
    if result.status == "skipped":
        return f"{label} ingest skipped"
    return f"{label} ingest completed"


def _execution_failed_notes(
    *,
    execution_notes: str | None,
    operator_notes: str | None,
) -> str | None:
    if execution_notes is None:
        return operator_notes
    if operator_notes is None or operator_notes == execution_notes:
        return execution_notes
    return f"{execution_notes}; operator_notes={operator_notes}"


def _command_error_payload(
    error: AppCommandError,
    *,
    approval: CatalogRemediationApproval,
) -> dict[str, object]:
    details = dict(error.details)
    details.setdefault("approval_id", approval.approval_id)
    details.setdefault("item_id", approval.item_id)
    details.setdefault("action", approval.action)
    return {
        "error_type": type(error).__name__,
        "error": str(error),
        "details": details,
    }
