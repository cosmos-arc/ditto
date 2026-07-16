"""Repair action execution orchestration for reconciliation workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol, cast

from ditto_kernel.tracing import traced
from ditto_portfolio.accounting import FillEvent

from ditto_execution.errors import ReconciliationError
from ditto_execution.models import FillAdjustmentRecord, FillRecord
from ditto_execution.reconciliation.types import (
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
    RepairExecutionResult,
)

__all__ = [
    "AmendLocalFillRepairHandler",
    "BrokerFillImportSource",
    "BrokerFillQueryPort",
    "BrokerRefreshRepairHandler",
    "FillAmendmentSource",
    "ImportBrokerFillRepairHandler",
    "LocalFillRepairPort",
    "LocalOrderStatusRepairPort",
    "OrderStatusReviewSource",
    "ProjectedFillAppendPort",
    "ProjectedFillCorrectionPort",
    "RepairActionExecutor",
    "RepairActionHandler",
    "RepairExecutionAuditSink",
    "RepairWorkflowStore",
    "ReviewOrderStatusRepairHandler",
]

_BLOCKED_BY_IN_FLIGHT_CLAIM_MESSAGE = (
    "repair action is blocked by another in-flight claim"
)


class RepairWorkflowStore(Protocol):
    """Workflow state store required by the repair executor."""

    def get_action(self, action_id: str) -> RepairActionRecord | None:
        """Return one persisted repair action."""
        ...

    def list_actions(self, report_id: str) -> tuple[RepairActionRecord, ...]:
        """Return persisted repair actions for a report in execution order."""
        ...

    def claim_for_execution(
        self,
        action_id: str,
        *,
        executor: str,
        claimed_at: str = "",
        reclaim_before: str | None = None,
    ) -> RepairActionRecord | None:
        """Atomically claim one ready or approved action for execution."""
        ...

    def release_execution_claim(
        self,
        action_id: str,
        *,
        executor: str,
    ) -> bool:
        """Release an executor-owned in-flight claim."""
        ...

    def mark_executed(
        self,
        action_id: str,
        *,
        executor: str,
        result: str,
        executed_at: str = "",
    ) -> bool:
        """Record successful repair execution."""
        ...


class RepairActionHandler(Protocol):
    """Executes one approved or ready repair action."""

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Execute one repair action and return an execution result."""
        ...


class RepairExecutionAuditSink(Protocol):
    """Optional sink for repair execution audit events."""

    def record_repair_execution(self, result: RepairExecutionResult) -> None:
        """Record a repair execution result."""
        ...


class BrokerFillQueryPort(Protocol):
    """Small broker read port needed for refresh repair actions."""

    def query_fills(self, order_id: str) -> tuple[FillEvent, ...]:
        """Return broker-reported fills for an order."""
        ...


class BrokerFillImportSource(Protocol):
    """Source that resolves approved broker fills into local fill records."""

    def get_fill_record(self, action: RepairActionRecord) -> FillRecord | None:
        """Return the local fill record to import for one repair action."""
        ...


class FillAmendmentSource(Protocol):
    """Source that resolves approved local fill amendments."""

    def get_amended_fill_record(
        self,
        action: RepairActionRecord,
        current: FillRecord,
    ) -> FillRecord | None:
        """Return the approved replacement for an existing local fill."""
        ...


class OrderStatusReviewSource(Protocol):
    """Source that resolves approved local order status changes."""

    def get_reviewed_order_status(
        self,
        action: RepairActionRecord,
        current_status: str,
    ) -> str | None:
        """Return the approved status for one order status repair action."""
        ...


class LocalFillRepairPort(Protocol):
    """Narrow immutable local fill store used by repair handlers."""

    def get_fill(self, fill_id: str) -> FillRecord | None:
        """Return one local fill by ID."""
        ...


class ProjectedFillAppendPort(Protocol):
    """Append a fill and atomically rebuild intent/position projections."""

    def append_projected_fill(self, record: FillRecord) -> bool:
        """Return True for a new fill and False for an exact replay."""
        ...


class ProjectedFillCorrectionPort(Protocol):
    """Append a replacement and atomically rebuild intent/position projections."""

    def apply_projected_fill_replacement(
        self,
        *,
        adjustment: FillAdjustmentRecord,
        replacement_fill: FillRecord,
    ) -> bool:
        """Return True for a new event and False for an exact replay."""
        ...


class LocalOrderStatusRepairPort(Protocol):
    """Narrow local order status store used by mutating repair handlers."""

    def get_order_status(self, order_id: str) -> str | None:
        """Return one local order status."""
        ...

    def update_order_status(
        self,
        order_id: str,
        status: str,
        *,
        expected_current: tuple[str, ...],
    ) -> bool:
        """Update one local order status with an optimistic transition guard."""
        ...


class BrokerRefreshRepairHandler:
    """Read-only handler that refreshes broker fill visibility for one order."""

    def __init__(self, broker: BrokerFillQueryPort) -> None:
        self._broker = broker

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Query broker fills and summarize the observed state."""
        if action.action_type is not RepairActionType.REFRESH_BROKER_ORDER:
            raise ReconciliationError(
                "broker refresh handler received unsupported repair action",
                action_id=action.action_id,
                action_type=action.action_type.value,
            )
        fills = self._broker.query_fills(action.order_id)
        fill_count = len(fills)
        return RepairExecutionResult.executed(
            action,
            message=f"queried {fill_count} broker fills",
            effect_count=fill_count,
        )


class ImportBrokerFillRepairHandler:
    """Mutating handler that imports one approved broker fill into local storage."""

    def __init__(
        self,
        *,
        broker_fill_source: BrokerFillImportSource,
        local_fill_store: LocalFillRepairPort,
        projected_fill_port: ProjectedFillAppendPort | None = None,
    ) -> None:
        self._broker_fill_source = broker_fill_source
        resolved_port = projected_fill_port or local_fill_store
        append_fill = getattr(resolved_port, "append_projected_fill", None)
        if not callable(append_fill):
            msg = (
                "ImportBrokerFillRepairHandler requires a projection-capable "
                + "fill append adapter"
            )
            raise TypeError(msg)
        self._projected_fill_port = cast(ProjectedFillAppendPort, resolved_port)

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Import a broker fill after explicit workflow approval."""
        if action.action_type is not RepairActionType.IMPORT_BROKER_FILL:
            raise ReconciliationError(
                "broker fill import handler received unsupported repair action",
                action_id=action.action_id,
                action_type=action.action_type.value,
            )
        if action.fill_id is None:
            return RepairExecutionResult.failed(
                action,
                message="import broker fill action has no fill_id",
            )

        record = self._broker_fill_source.get_fill_record(action)
        if record is None:
            return RepairExecutionResult.failed(
                action,
                message=f"broker fill {action.fill_id} was not found",
            )
        if record.fill_id != action.fill_id:
            return RepairExecutionResult.failed(
                action,
                message=(
                    "broker fill source returned mismatched fill_id "
                    + f"{record.fill_id}"
                ),
            )

        created = self._projected_fill_port.append_projected_fill(record)
        if not created:
            return RepairExecutionResult.executed(
                action,
                message=f"broker fill {action.fill_id} already imported",
                effect_count=0,
            )
        return RepairExecutionResult.executed(
            action,
            message=f"imported broker fill {record.fill_id}",
            effect_count=1,
        )


class AmendLocalFillRepairHandler:
    """Append-only handler for one approved local fill correction."""

    def __init__(
        self,
        *,
        amendment_source: FillAmendmentSource,
        local_fill_store: LocalFillRepairPort,
        correction_port: ProjectedFillCorrectionPort | None = None,
    ) -> None:
        self._amendment_source = amendment_source
        self._local_fill_store = local_fill_store
        resolved_port = correction_port or local_fill_store
        apply_replacement = getattr(
            resolved_port,
            "apply_projected_fill_replacement",
            None,
        )
        if not callable(apply_replacement):
            msg = (
                "AmendLocalFillRepairHandler requires a projection-capable "
                + "fill correction adapter"
            )
            raise TypeError(msg)
        self._correction_port = cast(ProjectedFillCorrectionPort, resolved_port)

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Append a projected replacement after explicit workflow approval."""
        if action.action_type is not RepairActionType.AMEND_LOCAL_FILL:
            raise ReconciliationError(
                "local fill amendment handler received unsupported repair action",
                action_id=action.action_id,
                action_type=action.action_type.value,
            )
        loaded = self._load_amendment(action)
        if isinstance(loaded, RepairExecutionResult):
            return loaded
        current, amended = loaded

        evidence_time = (
            action.reviewed_at or action.created_at or f"{action.trade_date}T00:00:00Z"
        )
        replacement_fill_id = f"{current.fill_id}:repair:{action.action_id}"
        replacement_fill = replace(
            amended,
            fill_id=replacement_fill_id,
            created_at=evidence_time,
        )
        adjustment = FillAdjustmentRecord(
            adjustment_id=f"repair-adjustment:{action.action_id}",
            fill_id=current.fill_id,
            adjustment_type="replace",
            replacement_fill_id=replacement_fill_id,
            reason=(
                action.review_reason
                or action.reason
                or f"approved reconciliation amendment {action.action_id}"
            ),
            created_at=evidence_time,
        )
        created = self._correction_port.apply_projected_fill_replacement(
            adjustment=adjustment,
            replacement_fill=replacement_fill,
        )
        return RepairExecutionResult.executed(
            action,
            message=f"amended local fill {current.fill_id}",
            effect_count=int(created),
        )

    def _load_amendment(
        self,
        action: RepairActionRecord,
    ) -> tuple[FillRecord, FillRecord] | RepairExecutionResult:
        if action.fill_id is None:
            return RepairExecutionResult.failed(
                action,
                message="amend local fill action has no fill_id",
            )

        current = self._local_fill_store.get_fill(action.fill_id)
        if current is None:
            return RepairExecutionResult.failed(
                action,
                message=f"local fill {action.fill_id} was not found",
            )

        amended = self._amendment_source.get_amended_fill_record(action, current)
        if amended is None:
            return RepairExecutionResult.failed(
                action,
                message=f"amended fill {action.fill_id} was not found",
            )
        if amended.fill_id != action.fill_id:
            return RepairExecutionResult.failed(
                action,
                message=(
                    "fill amendment source returned mismatched fill_id "
                    + f"{amended.fill_id}"
                ),
            )
        return current, amended


class ReviewOrderStatusRepairHandler:
    """Mutating handler that applies one approved local order status repair."""

    def __init__(
        self,
        *,
        review_source: OrderStatusReviewSource,
        local_order_store: LocalOrderStatusRepairPort,
    ) -> None:
        self._review_source = review_source
        self._local_order_store = local_order_store

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Update a local order status after explicit workflow approval."""
        if action.action_type is not RepairActionType.REVIEW_ORDER_STATUS:
            raise ReconciliationError(
                "order status review handler received unsupported repair action",
                action_id=action.action_id,
                action_type=action.action_type.value,
            )

        current_status = self._local_order_store.get_order_status(action.order_id)
        if current_status is None:
            return RepairExecutionResult.failed(
                action,
                message=f"local order {action.order_id} status was not found",
            )

        reviewed_status = self._review_source.get_reviewed_order_status(
            action,
            current_status,
        )
        if reviewed_status is None:
            return RepairExecutionResult.failed(
                action,
                message=f"reviewed order status for {action.order_id} was not found",
            )
        if reviewed_status == current_status:
            return RepairExecutionResult.executed(
                action,
                message=(
                    f"local order {action.order_id} already matched reviewed status"
                ),
                effect_count=0,
            )

        updated = self._local_order_store.update_order_status(
            action.order_id,
            reviewed_status,
            expected_current=(current_status,),
        )
        if not updated:
            return RepairExecutionResult.failed(
                action,
                message=f"local order {action.order_id} status could not be updated",
            )
        return RepairExecutionResult.executed(
            action,
            message=(
                f"updated local order {action.order_id} status to {reviewed_status}"
            ),
            effect_count=1,
        )


class RepairActionExecutor:
    """Execute ready or approved repair actions through registered handlers."""

    def __init__(
        self,
        *,
        workflow_store: RepairWorkflowStore,
        handlers: Mapping[RepairActionType | str, RepairActionHandler],
        audit_sink: RepairExecutionAuditSink | None = None,
        executor_id: str = "repair-executor",
    ) -> None:
        self._workflow_store = workflow_store
        self._handlers = {
            RepairActionType(str(action_type)): handler
            for action_type, handler in handlers.items()
        }
        self._audit_sink = audit_sink
        self._executor_id = executor_id

    @traced("execution.repair.execute_action")
    def execute_action(
        self,
        action_id: str,
        *,
        executed_at: str = "",
        reclaim_before: str | None = None,
    ) -> RepairExecutionResult:
        """Execute one ready or approved repair action."""
        action = self._workflow_store.get_action(action_id)
        if action is None:
            raise ReconciliationError(
                "repair action not found",
                action_id=action_id,
            )
        can_claim = action.status in (
            RepairActionStatus.READY,
            RepairActionStatus.APPROVED,
        )
        can_reclaim = (
            action.status is RepairActionStatus.EXECUTING and reclaim_before is not None
        )
        if not can_claim and not can_reclaim:
            result = RepairExecutionResult.skipped(
                action,
                message=f"repair action is {action.status.value}",
            )
            self._record_audit(result)
            return result

        if can_claim:
            dependency_result = self._prior_local_mutation_dependency_result(action)
            if dependency_result is not None:
                self._record_audit(dependency_result)
                return dependency_result

        handler = self._handlers.get(action.action_type)
        if handler is None:
            result = RepairExecutionResult.skipped(
                action,
                message=(
                    "no repair handler registered for " + f"{action.action_type.value}"
                ),
            )
            self._record_audit(result)
            return result

        claimed_action = self._workflow_store.claim_for_execution(
            action.action_id,
            executor=self._executor_id,
            claimed_at=executed_at,
            reclaim_before=reclaim_before,
        )
        if claimed_action is None:
            result = self._skipped_claim_result(action_id)
            self._record_audit(result)
            return result

        try:
            result = handler.execute(claimed_action)
        except Exception:
            self._release_execution_claim(claimed_action)
            raise
        if result.status == "executed":
            self._mark_executed(claimed_action, result, executed_at=executed_at)
        else:
            self._release_execution_claim(claimed_action)
        self._record_audit(result)
        return result

    @traced("execution.repair.execute_report_actions")
    def execute_report_actions(
        self,
        report_id: str,
        *,
        executed_at: str = "",
        reclaim_before: str | None = None,
    ) -> tuple[RepairExecutionResult, ...]:
        """Execute all persisted actions for one report in workflow order."""
        results: list[RepairExecutionResult] = []
        amended_fill_ids: set[str] = set()
        failed_local_mutation_fill_ids: set[str] = set()
        failed_local_mutation_kinds: dict[str, str] = {}
        in_flight_local_mutation_fill_ids: set[str] = set()
        in_flight_local_mutation_kinds: dict[str, str] = {}
        for action in self._workflow_store.list_actions(report_id):
            amendment_fill_id = _local_fill_amendment_target(action)
            mutation_fill_id = _local_fill_mutation_target(action)
            if (
                action.status is RepairActionStatus.EXECUTED
                and amendment_fill_id is not None
            ):
                amended_fill_ids.add(amendment_fill_id)
            if (
                action.status is RepairActionStatus.EXECUTING
                and mutation_fill_id is not None
            ):
                in_flight_local_mutation_fill_ids.add(mutation_fill_id)
                in_flight_local_mutation_kinds[mutation_fill_id] = (
                    _local_fill_mutation_kind(action)
                )
            if (
                action.status in (RepairActionStatus.READY, RepairActionStatus.APPROVED)
                and amendment_fill_id is not None
                and amendment_fill_id in amended_fill_ids
            ):
                result = self._close_already_amended_action(
                    action,
                    fill_id=amendment_fill_id,
                    executed_at=executed_at,
                    reclaim_before=reclaim_before,
                )
                self._record_audit(result)
            elif (
                action.status in (RepairActionStatus.READY, RepairActionStatus.APPROVED)
                and mutation_fill_id is not None
                and mutation_fill_id in failed_local_mutation_fill_ids
            ):
                mutation_kind = failed_local_mutation_kinds.get(
                    mutation_fill_id,
                    "local mutation",
                )
                result = RepairExecutionResult.skipped(
                    action,
                    message=(
                        f"local fill {mutation_fill_id} blocked by earlier failed "
                        f"{mutation_kind} in report"
                    ),
                )
                self._record_audit(result)
            elif (
                action.status in (RepairActionStatus.READY, RepairActionStatus.APPROVED)
                and mutation_fill_id is not None
                and mutation_fill_id in in_flight_local_mutation_fill_ids
            ):
                mutation_kind = in_flight_local_mutation_kinds.get(
                    mutation_fill_id,
                    "local mutation",
                )
                result = RepairExecutionResult.skipped(
                    action,
                    message=(
                        f"local fill {mutation_fill_id} blocked by earlier in-flight "
                        f"{mutation_kind} in report"
                    ),
                )
                self._record_audit(result)
            else:
                result = self.execute_action(
                    action.action_id,
                    executed_at=executed_at,
                    reclaim_before=reclaim_before,
                )
            if result.status == "executed" and amendment_fill_id is not None:
                amended_fill_ids.add(amendment_fill_id)
            if result.status == "failed" and mutation_fill_id is not None:
                failed_local_mutation_fill_ids.add(mutation_fill_id)
                failed_local_mutation_kinds[mutation_fill_id] = (
                    _local_fill_mutation_kind(action)
                )
            if (
                result.status == "skipped"
                and mutation_fill_id is not None
                and result.message
                in (
                    "repair action is executing",
                    _BLOCKED_BY_IN_FLIGHT_CLAIM_MESSAGE,
                )
            ):
                in_flight_local_mutation_fill_ids.add(mutation_fill_id)
                in_flight_local_mutation_kinds[mutation_fill_id] = (
                    _local_fill_mutation_kind(action)
                )
            results.append(result)
        return tuple(results)

    def _close_already_amended_action(
        self,
        action: RepairActionRecord,
        *,
        fill_id: str,
        executed_at: str,
        reclaim_before: str | None,
    ) -> RepairExecutionResult:
        claimed_action = self._workflow_store.claim_for_execution(
            action.action_id,
            executor=self._executor_id,
            claimed_at=executed_at,
            reclaim_before=reclaim_before,
        )
        if claimed_action is None:
            return self._skipped_claim_result(action.action_id)
        result = RepairExecutionResult.executed(
            claimed_action,
            message=f"local fill {fill_id} already amended earlier in report",
            effect_count=0,
        )
        self._mark_executed(
            claimed_action,
            result,
            executed_at=executed_at,
        )
        return result

    def _skipped_claim_result(self, action_id: str) -> RepairExecutionResult:
        latest = self._workflow_store.get_action(action_id)
        if latest is None:
            raise ReconciliationError(
                "repair action not found",
                action_id=action_id,
            )
        message = (
            _BLOCKED_BY_IN_FLIGHT_CLAIM_MESSAGE
            if latest.status in (RepairActionStatus.READY, RepairActionStatus.APPROVED)
            else f"repair action is {latest.status.value}"
        )
        return RepairExecutionResult.skipped(
            latest,
            message=message,
        )

    def _prior_local_mutation_dependency_result(
        self,
        action: RepairActionRecord,
    ) -> RepairExecutionResult | None:
        fill_id = _local_fill_mutation_target(action)
        if fill_id is None:
            return None
        for prior in self._workflow_store.list_actions(action.report_id):
            if prior.action_index >= action.action_index:
                break
            if _local_fill_mutation_target(prior) != fill_id:
                continue
            mutation_kind = _local_fill_mutation_kind(prior)
            if prior.status is RepairActionStatus.EXECUTING:
                return RepairExecutionResult.skipped(
                    action,
                    message=(
                        f"local fill {fill_id} blocked by earlier in-flight "
                        f"{mutation_kind} in report"
                    ),
                )
            if prior.status in (
                RepairActionStatus.READY,
                RepairActionStatus.PENDING_REVIEW,
                RepairActionStatus.APPROVED,
            ):
                return RepairExecutionResult.skipped(
                    action,
                    message=(
                        f"local fill {fill_id} blocked by earlier unfinished "
                        f"{mutation_kind} in report"
                    ),
                )
        return None

    def _mark_executed(
        self,
        action: RepairActionRecord,
        result: RepairExecutionResult,
        *,
        executed_at: str,
    ) -> None:
        marked = self._workflow_store.mark_executed(
            action.action_id,
            executor=self._executor_id,
            result=result.message,
            executed_at=executed_at,
        )
        if not marked:
            raise ReconciliationError(
                "repair action execution state could not be recorded",
                action_id=action.action_id,
                action_status=action.status.value,
            )

    def _release_execution_claim(self, action: RepairActionRecord) -> None:
        released = self._workflow_store.release_execution_claim(
            action.action_id,
            executor=self._executor_id,
        )
        if not released:
            raise ReconciliationError(
                "repair action execution claim could not be released",
                action_id=action.action_id,
                action_status=action.status.value,
            )

    def _record_audit(self, result: RepairExecutionResult) -> None:
        if self._audit_sink is not None:
            self._audit_sink.record_repair_execution(result)


def _local_fill_amendment_target(action: RepairActionRecord) -> str | None:
    if action.action_type is not RepairActionType.AMEND_LOCAL_FILL:
        return None
    return action.fill_id


def _local_fill_mutation_target(action: RepairActionRecord) -> str | None:
    if action.action_type not in {
        RepairActionType.AMEND_LOCAL_FILL,
        RepairActionType.IMPORT_BROKER_FILL,
    }:
        return None
    return action.fill_id


def _local_fill_mutation_kind(action: RepairActionRecord) -> str:
    if action.action_type is RepairActionType.AMEND_LOCAL_FILL:
        return "amendment"
    return "local mutation"
