"""Durable approval adapter for research-memory promote and revoke commands."""

from __future__ import annotations

from ditto_application.exceptions import AppCommandError
from ditto_application.research_memory_approval_contracts import (
    ResearchMemoryApprovalCheck,
    ResearchMemoryApprovalVerifier,
    VerifiedResearchMemoryApproval,
)

from ditto_agent.approval_errors import ApprovalRuntimeError
from ditto_agent.approval_runtime import AgentApprovalRuntime


class ApprovalRuntimeResearchMemoryVerifier(ResearchMemoryApprovalVerifier):
    """Revalidate durable exact-action approval at the memory write boundary."""

    def __init__(self, *, runtime: AgentApprovalRuntime) -> None:
        self._runtime = runtime

    def verify(
        self,
        check: ResearchMemoryApprovalCheck,
    ) -> VerifiedResearchMemoryApproval:
        """Map one current durable operator receipt into Application proof."""
        try:
            approval = self._runtime.authorize_tool_execution(
                run_id=check.run_id,
                call_id=check.call_id,
                tool_name=check.tool_name,
                arguments=check.arguments,
            )
        except ApprovalRuntimeError as exc:
            raise AppCommandError(
                "Research memory approval failed closed",
                details={
                    "code": "RESEARCH_MEMORY_APPROVAL_INVALID",
                    "reason": exc.reason_code,
                },
            ) from exc
        return VerifiedResearchMemoryApproval.issue(
            check=check,
            approval_id=approval.approval_id,
            action_hash=approval.action_hash,
            operator_id=approval.operator_id,
            approved_at=approval.approved_at,
            expires_at=approval.expires_at,
            approved=True,
        )


__all__ = ["ApprovalRuntimeResearchMemoryVerifier"]
