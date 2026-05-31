"""Repair action execution orchestration for reconciliation workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from ditto_portfolio.accounting import FillEvent

from ditto_execution.errors import ReconciliationError
from ditto_execution.reconciliation.types import (
    RepairActionRecord,
    RepairActionStatus,
    RepairActionType,
    RepairExecutionResult,
)

__all__ = [
    "BrokerFillQueryPort",
    "BrokerRefreshRepairHandler",
    "RepairActionExecutor",
    "RepairActionHandler",
    "RepairExecutionAuditSink",
    "RepairWorkflowStore",
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
