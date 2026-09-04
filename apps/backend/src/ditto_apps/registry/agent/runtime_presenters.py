"""Pure public projections for the persisted Agent composition root."""

from datetime import datetime
from typing import cast

import orjson
from ditto_agent.presentation import AgentContextPresentation, AgentRunPresentation
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalStatus,
    AgentApprovalView,
    AgentInvalidRequest,
    AgentProjectionState,
    AgentRuntimeUnavailable,
    AgentRunView,
    ApprovalDecisionStatus,
)
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    StoredAgentRun,
    StoredApproval,
)


def approval_decision(approval: StoredApproval) -> AgentApprovalDecision:
    """Project one durable approval decision receipt."""
    if approval.decided_at is None or approval.operator_id is None:
        raise AgentRuntimeUnavailable("agent_approval_receipt_invalid")
    status = {
        ApprovalStatus.APPROVED: ApprovalDecisionStatus.APPROVED,
        ApprovalStatus.REJECTED: ApprovalDecisionStatus.REJECTED,
    }.get(approval.status)
    if status is None:
        raise AgentRuntimeUnavailable("agent_approval_receipt_invalid")
    return AgentApprovalDecision(
        approval_id=approval.request_id,
        run_id=approval.run_id,
        action_hash=approval.action_hash,
        status=status,
        operator_id=approval.operator_id,
        reason=approval.reason,
        decided_at=approval.decided_at,
    )


def context_filter(
    context_type: str | None,
    context_id: str | None,
) -> AgentContextPresentation | None:
    """Validate and project an optional exact run-context filter."""
    if (context_type is None) != (context_id is None):
        raise AgentInvalidRequest(
            "Agent context filters must be supplied together",
            reason_code="agent_context_filter_incomplete",
        )
    if context_type is None or context_id is None:
        return None
    try:
        return AgentContextPresentation(
            context_type=context_type,
            context_id=context_id,
        )
    except ValueError as exc:
        raise AgentInvalidRequest(
            "Agent context filter is invalid",
            reason_code="agent_context_filter_invalid",
        ) from exc


def _approval_status(approval: StoredApproval, *, now: datetime) -> AgentApprovalStatus:
    if approval.status is ApprovalStatus.APPROVED:
        return AgentApprovalStatus.APPROVED
    if approval.status is ApprovalStatus.REJECTED:
        return AgentApprovalStatus.REJECTED
    if approval.expires_at <= now:
        return AgentApprovalStatus.EXPIRED
    return AgentApprovalStatus.PENDING


def approval_projection(
    approval: StoredApproval, *, now: datetime
) -> AgentApprovalView:
    """Project an approval request with its current expiry-aware status."""
    try:
        decoded = orjson.loads(approval.action_payload)
    except orjson.JSONDecodeError as exc:
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid") from exc
    if not isinstance(decoded, dict):
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid")
    payload = cast("dict[str, object]", decoded)
    action_type = payload.get("action_kind")
    target_identity = payload.get("subject_identity")
    if type(action_type) is not str or type(target_identity) is not str:
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid")
    return AgentApprovalView(
        approval_id=approval.request_id,
        run_id=approval.run_id,
        action_type=action_type,
        target_identity=target_identity,
        action_payload=payload,
        action_hash=approval.action_hash,
        status=_approval_status(approval, now=now),
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
        operator_id=approval.operator_id,
        reason=approval.reason,
        decided_at=approval.decided_at,
    )


def run_view(
    run: StoredAgentRun,
    *,
    presentation: AgentRunPresentation | None = None,
    projection_reason: str = "agent_presentation_unconfigured",
    projection_complete: bool = True,
    event_cursor: int | None = None,
) -> AgentRunView:
    """Combine durable run identity with optional readable presentation data."""
    if presentation is not None and projection_complete:
        output_summary = presentation.output_summary
        tool_records = presentation.tool_records
        evidence_refs = presentation.evidence_refs
        artifact_refs = presentation.artifact_refs
        guardrail = presentation.guardrail
        usage = presentation.usage
        failure_code = presentation.failure_code
    else:
        output_summary = None
        tool_records = ()
        evidence_refs = ()
        artifact_refs = ()
        guardrail = None
        usage = None
        failure_code = None
    return AgentRunView(
        run_id=run.run_id,
        session_id=run.session_id,
        status=run.status,
        objective_hash=run.objective_hash,
        authority_hash=run.authority_hash,
        max_model_tokens=run.max_model_tokens,
        max_model_spend_usd=run.max_model_spend_usd,
        model_profile=run.model_profile,
        manifest_hash=run.manifest_hash,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        revision=run.revision,
        objective=(presentation.objective if presentation is not None else None),
        context=(presentation.context if presentation is not None else None),
        output_summary=output_summary,
        tool_records=tool_records,
        evidence_refs=evidence_refs,
        artifact_refs=artifact_refs,
        guardrail=guardrail,
        usage=usage,
        failure_code=failure_code,
        event_cursor=(
            event_cursor
            if event_cursor is not None
            else presentation.event_cursor
            if presentation is not None
            else 0
        ),
        projection_state=(
            AgentProjectionState.COMPLETE
            if presentation is not None and projection_complete
            else AgentProjectionState.PARTIAL
        ),
        projection_reason=(
            None
            if presentation is not None and projection_complete
            else projection_reason
        ),
        projection_version=(
            presentation.projection_version if presentation is not None else None
        ),
        projection_updated_at=(
            presentation.updated_at if presentation is not None else None
        ),
        execution_plan=(
            presentation.execution_plan if presentation is not None else None
        ),
    )


__all__ = [
    "approval_decision",
    "approval_projection",
    "context_filter",
    "run_view",
]
