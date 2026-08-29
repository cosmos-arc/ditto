"""Current-action revalidation at the physical approved-tool boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ditto_agent._canonical import canonical_sha256
from ditto_agent.approval_codec import (
    InterruptionBinding,
    ModelRequestIdentity,
    ResumeEnvelope,
)
from ditto_agent.approval_errors import (
    ApprovalRuntimeConflict,
    ApprovalRuntimeUnavailable,
    ApprovalRuntimeViolation,
)
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.models.port import ApprovalDecision, ModelRequest, ModelToolSpec
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_agent.storage.sqlite.records import StoredAgentRun, StoredApproval


@dataclass(frozen=True, slots=True)
class AuthorizedToolApproval:
    """Current durable approval admitted at the physical tool boundary."""

    approval_id: str
    run_id: str
    action_hash: str
    operator_id: str
    approved_at: datetime
    expires_at: datetime


class ApprovalAuthorizationReader(Protocol):
    """Minimal durable state required for physical-boundary authorization."""

    def get_run(self, run_id: str) -> StoredAgentRun | None: ...

    def get_approval(self, request_id: str) -> StoredApproval | None: ...


class DecisionValidator(Protocol):
    """Current-authority decision validator owned by the approval runtime."""

    def __call__(
        self,
        *,
        run_id: str,
        run: StoredAgentRun,
        binding: InterruptionBinding,
        tools: Mapping[str, ModelToolSpec],
        now: datetime,
    ) -> ApprovalDecision | None: ...


@dataclass(frozen=True, slots=True)
class ApprovalAuthorizationDependencies:
    """Runtime-owned collaborators used for one authorization check."""

    reader: ApprovalAuthorizationReader
    load_envelope: Callable[[str], tuple[ResumeEnvelope, str]]
    resolve_request: Callable[[str, ModelRequestIdentity], ModelRequest]
    validate_decision: DecisionValidator
    clock: Callable[[], datetime]


def authorize_tool_execution(
    *,
    dependencies: ApprovalAuthorizationDependencies,
    run_id: str,
    call_id: str,
    tool_name: str,
    arguments: Mapping[str, object],
) -> AuthorizedToolApproval:
    """Fail closed unless one exact action remains durably approved now."""
    try:
        envelope, _continuation_hash = dependencies.load_envelope(run_id)
        binding = next(
            (item for item in envelope.interruptions if item.call_id == call_id),
            None,
        )
        if binding is None:
            raise ApprovalRuntimeViolation(
                "tool call is not bound to the active approval continuation",
                reason_code="agent_approval_binding_mismatch",
            )
        if binding.tool_name != tool_name or (
            binding.arguments_hash != canonical_sha256(arguments)
        ):
            raise ApprovalRuntimeViolation(
                "tool execution does not match the approved action",
                reason_code="agent_approval_arguments_mismatch",
            )
        request = dependencies.resolve_request(run_id, envelope.request_identity)
        run = dependencies.reader.get_run(run_id)
        if run is None:
            raise ApprovalRuntimeConflict(
                "approval run does not exist",
                reason_code="agent_run_missing",
            )
        if run.status is not RunStatus.RUNNING:
            raise ApprovalRuntimeConflict(
                "approved tool execution requires a running resume",
                reason_code="agent_run_state_conflict",
            )
        decision = dependencies.validate_decision(
            run_id=run_id,
            run=run,
            binding=binding,
            tools={tool.name: tool for tool in request.tools},
            now=dependencies.clock(),
        )
        if decision is None or not decision.approved:
            raise ApprovalRuntimeViolation(
                "tool execution lacks a current operator approval",
                reason_code="agent_approval_required",
            )
        stored = dependencies.reader.get_approval(binding.request_id)
        if stored is None or stored.operator_id is None or stored.decided_at is None:
            raise ApprovalRuntimeViolation(
                "approved tool execution lacks a durable operator receipt",
                reason_code="agent_approval_receipt_invalid",
            )
        return AuthorizedToolApproval(
            approval_id=stored.request_id,
            run_id=stored.run_id,
            action_hash=stored.action_hash,
            operator_id=stored.operator_id,
            approved_at=stored.decided_at,
            expires_at=stored.expires_at,
        )
    except AgentPersistenceError as exc:
        raise ApprovalRuntimeUnavailable(
            "approval authorization storage is unavailable",
            reason_code=exc.reason_code,
        ) from exc


__all__ = [
    "ApprovalAuthorizationDependencies",
    "AuthorizedToolApproval",
    "authorize_tool_execution",
]
