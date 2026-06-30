"""Adapter from reconciliation repair results to persistent execution audit."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.audit.models import RepairExecutionPayload
from ditto_execution.reconciliation.types import RepairExecutionResult

__all__ = ["ExecutionRepairAuditSink"]


@dataclass(frozen=True)
class ExecutionRepairAuditSink:
    """Persist repair execution results into ``execution_audit``."""

    audit_service: ExecutionAuditService
    run_id: str

    def record_repair_execution(self, result: RepairExecutionResult) -> None:
        """Record one repair execution result in the execution audit table."""
        payload = RepairExecutionPayload(
            trade_date=result.trade_date,
            report_id=result.report_id,
            action_id=result.action_id,
            action_type=result.action_type.value,
            order_id=result.order_id,
            status=result.status,
            message=result.message,
            effect_count=result.effect_count,
            fill_id=result.fill_id,
            correlation_id=result.action_id,
            client_order_id=result.client_order_id,
            broker_order_id=result.broker_order_id,
        )
        self.audit_service.save_repair_execution_log(self.run_id, (payload,))
