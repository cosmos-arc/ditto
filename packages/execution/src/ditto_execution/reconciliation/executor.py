"""Repair action execution orchestration for reconciliation workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ditto_portfolio.accounting import FillEvent

from ditto_execution.errors import ReconciliationError
from ditto_execution.models import FillRecord
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
    "RepairActionExecutor",
    "RepairActionHandler",
    "RepairExecutionAuditSink",
    "RepairWorkflowStore",
    "ReviewOrderStatusRepairHandler",
]


class RepairWorkflowStore(Protocol):
    """Workflow state store required by the repair executor."""

    def get_action(self, action_id: str) -> RepairActionRecord | None:
        """Return one persisted repair action."""
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
    """Narrow local fill store used by mutating repair handlers."""

    def get_fill(self, fill_id: str) -> FillRecord | None:
        """Return one local fill by ID."""
        ...

    def save_fill(self, record: FillRecord) -> None:
        """Persist one local fill record."""
        ...

    def replace_fill(self, record: FillRecord) -> bool:
        """Replace one existing local fill record."""
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
    ) -> None:
        self._broker_fill_source = broker_fill_source
        self._local_fill_store = local_fill_store

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

        existing = self._local_fill_store.get_fill(action.fill_id)
        if existing is not None:
            return RepairExecutionResult.executed(
                action,
                message=f"broker fill {action.fill_id} already imported",
                effect_count=0,
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

        self._local_fill_store.save_fill(record)
        return RepairExecutionResult.executed(
            action,
            message=f"imported broker fill {record.fill_id}",
            effect_count=1,
        )


class AmendLocalFillRepairHandler:
    """Mutating handler that replaces one approved local fill record."""

    def __init__(
        self,
        *,
        amendment_source: FillAmendmentSource,
        local_fill_store: LocalFillRepairPort,
    ) -> None:
        self._amendment_source = amendment_source
        self._local_fill_store = local_fill_store

    def execute(self, action: RepairActionRecord) -> RepairExecutionResult:
        """Replace a local fill after explicit workflow approval."""
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

        if amended == current:
            return RepairExecutionResult.executed(
                action,
                message=f"local fill {action.fill_id} already matched amendment",
                effect_count=0,
            )

        replaced = self._local_fill_store.replace_fill(amended)
        if not replaced:
            return RepairExecutionResult.failed(
                action,
                message=f"local fill {action.fill_id} could not be replaced",
            )
        return RepairExecutionResult.executed(
            action,
            message=f"amended local fill {amended.fill_id}",
            effect_count=1,
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

    def execute_action(
        self,
        action_id: str,
        *,
        executed_at: str = "",
    ) -> RepairExecutionResult:
        """Execute one ready or approved repair action."""
        action = self._workflow_store.get_action(action_id)
        if action is None:
            raise ReconciliationError(
                "repair action not found",
                action_id=action_id,
            )
        if action.status not in (
            RepairActionStatus.READY,
            RepairActionStatus.APPROVED,
        ):
            result = RepairExecutionResult.skipped(
                action,
                message=f"repair action is {action.status.value}",
            )
            self._record_audit(result)
            return result

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

        result = handler.execute(action)
        if result.status == "executed":
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
        self._record_audit(result)
        return result

    def _record_audit(self, result: RepairExecutionResult) -> None:
        if self._audit_sink is not None:
            self._audit_sink.record_repair_execution(result)
