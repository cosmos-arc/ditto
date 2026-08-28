"""Stable JSON payloads for governed Agent CLI projections."""

from __future__ import annotations

from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentEventView,
    AgentRunView,
    AgentSessionView,
)
from ditto_application.agent_campaign_runtime import CampaignView


def session_payload(session: AgentSessionView) -> dict[str, object]:
    """Serialize a stable session projection."""
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "retention_class": session.retention_class.value,
    }


def run_payload(run: AgentRunView) -> dict[str, object]:
    """Serialize every readable run projection field."""
    context = run.context
    guardrail = run.guardrail
    usage = run.usage
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "status": run.status.value,
        "objective_hash": run.objective_hash,
        "authority_hash": run.authority_hash,
        "max_model_tokens": run.max_model_tokens,
        "max_model_spend_usd": str(run.max_model_spend_usd),
        "model_profile": run.model_profile.value,
        "manifest_hash": run.manifest_hash,
        "created_at": run.created_at.isoformat(),
        "started_at": None if run.started_at is None else run.started_at.isoformat(),
        "finished_at": (
            None if run.finished_at is None else run.finished_at.isoformat()
        ),
        "revision": run.revision,
        "objective": run.objective,
        "context": (
            None
            if context is None
            else {
                "context_type": context.context_type,
                "context_id": context.context_id,
            }
        ),
        "output_summary": run.output_summary,
        "tool_records": [
            {
                "call_id": record.call_id,
                "tool_name": record.tool_name,
                "arguments_hash": record.arguments_hash,
                "result_hash": record.result_hash,
                "evidence_refs": list(record.evidence_refs),
                "artifact_refs": list(record.artifact_refs),
            }
            for record in run.tool_records
        ],
        "evidence_refs": list(run.evidence_refs),
        "artifact_refs": list(run.artifact_refs),
        "guardrail": (
            None
            if guardrail is None
            else {
                "status": guardrail.status,
                "reason_code": guardrail.reason_code,
            }
        ),
        "usage": (
            None
            if usage is None
            else {
                "model_attempts": usage.model_attempts,
                "model_turns": usage.model_turns,
                "tool_calls": usage.tool_calls,
                "retries": usage.retries,
                "total_tokens": usage.total_tokens,
                "model_spend_usd": str(usage.model_spend_usd),
                "exhausted_reason": usage.exhausted_reason,
            }
        ),
        "failure_code": run.failure_code,
        "event_cursor": run.event_cursor,
        "projection_state": run.projection_state.value,
        "projection_reason": run.projection_reason,
        "projection_version": run.projection_version,
        "projection_updated_at": (
            None
            if run.projection_updated_at is None
            else run.projection_updated_at.isoformat()
        ),
    }


def event_payload(event: AgentEventView) -> dict[str, object]:
    """Serialize a hash-chained Agent event."""
    return {
        "schema_version": event.schema_version,
        "event_id": event.event_id,
        "run_id": event.run_id,
        "run_sequence": event.run_sequence,
        "event_type": event.event_type,
        "payload_hash": event.payload_hash,
        "occurred_at": event.occurred_at.isoformat(),
        "prev_hash": event.prev_hash,
        "event_hash": event.event_hash,
    }


def approval_payload(decision: AgentApprovalDecision) -> dict[str, object]:
    """Serialize an immutable approval decision receipt."""
    return {
        "approval_id": decision.approval_id,
        "run_id": decision.run_id,
        "action_hash": decision.action_hash,
        "status": decision.status.value,
        "operator_id": decision.operator_id,
        "reason": decision.reason,
        "decided_at": decision.decided_at.isoformat(),
    }


def campaign_payload(campaign: CampaignView) -> dict[str, object]:
    """Serialize every readable Campaign projection field."""
    sandbox = campaign.budget.sandbox_resource_limits
    guardrail = campaign.guardrail
    usage = campaign.usage
    return {
        "campaign_id": campaign.campaign_id,
        "status": campaign.status.value,
        "manifest_hash": campaign.manifest_hash,
        "authorization_hash": campaign.authorization_hash,
        "authorized_by": campaign.authorized_by,
        "authorization_expires_at": (
            None
            if campaign.authorization_expires_at is None
            else campaign.authorization_expires_at.isoformat()
        ),
        "search_axis": campaign.search_axis,
        "source_snapshot_id": campaign.source_snapshot_id,
        "allowed_tools": list(campaign.allowed_tools),
        "budget": {
            "candidate_limit": campaign.budget.candidate_limit,
            "fold_run_limit": campaign.budget.fold_run_limit,
            "generation_limit": campaign.budget.generation_limit,
            "concurrent_sandbox_limit": campaign.budget.concurrent_sandbox_limit,
            "wall_time_limit_seconds": campaign.budget.wall_time_limit_seconds,
            "temporary_storage_limit_bytes": (
                campaign.budget.temporary_storage_limit_bytes
            ),
            "model_spend_limit_usd_micros": (
                campaign.budget.model_spend_limit_usd_micros
            ),
            "sandbox_resource_limits": {
                "cpu_count": sandbox.cpu_count,
                "memory_bytes": sandbox.memory_bytes,
                "process_limit": sandbox.process_limit,
                "temporary_storage_bytes": sandbox.temporary_storage_bytes,
                "wall_time_seconds": sandbox.wall_time_seconds,
                "output_bytes": sandbox.output_bytes,
            },
        },
        "best_primary_metric_value": campaign.best_primary_metric_value,
        "no_improvement_generations": campaign.no_improvement_generations,
        "statistical_trial_count": campaign.statistical_trial_count,
        "operational_attempt_count": campaign.operational_attempt_count,
        "revision": campaign.revision,
        "canonical_manifest": dict(campaign.canonical_manifest),
        "objective": campaign.objective,
        "output_summary": campaign.output_summary,
        "tool_records": [
            {
                "call_id": record.call_id,
                "tool_name": record.tool_name,
                "arguments_hash": record.arguments_hash,
                "result_hash": record.result_hash,
                "evidence_refs": list(record.evidence_refs),
                "artifact_refs": list(record.artifact_refs),
            }
            for record in campaign.tool_records
        ],
        "evidence_refs": list(campaign.evidence_refs),
        "artifact_refs": list(campaign.artifact_refs),
        "guardrail": (
            None
            if guardrail is None
            else {
                "status": guardrail.status,
                "reason_code": guardrail.reason_code,
            }
        ),
        "usage": (
            None
            if usage is None
            else {
                "statistical_trial_count": usage.statistical_trial_count,
                "operational_attempt_count": usage.operational_attempt_count,
                "no_improvement_generations": usage.no_improvement_generations,
                "model_spend_usd_micros": usage.model_spend_usd_micros,
                "exhausted_reason": usage.exhausted_reason,
            }
        ),
        "event_cursor": campaign.event_cursor,
        "projection_state": campaign.projection_state,
        "projection_reason": campaign.projection_reason,
        "projection_version": campaign.projection_version,
        "projection_updated_at": (
            None
            if campaign.projection_updated_at is None
            else campaign.projection_updated_at.isoformat()
        ),
    }


__all__ = [
    "approval_payload",
    "campaign_payload",
    "event_payload",
    "run_payload",
    "session_payload",
]
