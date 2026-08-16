"""Durable approval adapter for application-owned Agent authoring commands."""

from __future__ import annotations

from ditto_application.agent_authoring_contracts import (
    AgentAuthoringApprovalCheck,
    AgentAuthoringApprovalVerifier,
    VerifiedAgentAuthoringApproval,
)
from ditto_application.exceptions import AppCommandError

from ditto_agent.approval_errors import ApprovalRuntimeError
from ditto_agent.approval_runtime import AgentApprovalRuntime


class ApprovalRuntimeAuthoringVerifier(AgentAuthoringApprovalVerifier):
    """Adapt durable approval revalidation to application commands."""

    def __init__(self, *, runtime: AgentApprovalRuntime) -> None:
        self._runtime = runtime

    def verify(
        self,
        check: AgentAuthoringApprovalCheck,
    ) -> VerifiedAgentAuthoringApproval:
        """Revalidate one durable approval at the physical write boundary."""
        try:
            approval = self._runtime.authorize_tool_execution(
                run_id=check.run_id,
                call_id=check.call_id,
                tool_name=check.tool_name,
                arguments=check.arguments,
            )
        except ApprovalRuntimeError as exc:
            raise AppCommandError(
                "Agent authoring approval failed closed",
                details={
                    "code": "AGENT_AUTHORING_APPROVAL_INVALID",
                    "reason": exc.reason_code,
                },
            ) from exc
        return VerifiedAgentAuthoringApproval.issue(
            check=check,
            approval_id=approval.approval_id,
            action_hash=approval.action_hash,
            operator_id=approval.operator_id,
            approved_at=approval.approved_at,
            approved=True,
        )


__all__ = ["ApprovalRuntimeAuthoringVerifier"]
