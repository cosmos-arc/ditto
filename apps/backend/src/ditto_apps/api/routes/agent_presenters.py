"""Pure public DTO and SSE presenters for governed Agent routes."""

from __future__ import annotations

import orjson
from ditto_agent.runtime.episode import episode_event_hash
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalView,
    AgentCapabilityView,
    AgentEventView,
    AgentRunView,
    AgentSessionView,
)
from ditto_application.agent_campaign_runtime import (
    CampaignEventView,
    CampaignStatus,
    CampaignValidationView,
    CampaignView,
)
from ditto_application.queries.decision_opinion import DecisionOpinionReadModel

from ditto_apps.models.agent import (
    AGENT_RUN_TERMINAL_EVENT_TYPES,
    AgentApprovalDecisionResponse,
    AgentApprovalResponse,
    AgentCampaignBudget,
    AgentCampaignGuardrail,
    AgentCampaignResponse,
    AgentCampaignSandboxLimits,
    AgentCampaignSseEvent,
    AgentCampaignSseEventType,
    AgentCampaignToolRecord,
    AgentCampaignUsage,
    AgentCampaignValidationResponse,
    AgentCapabilityResponse,
    AgentDecisionOpinionIdentity,
    AgentDecisionOpinionResponse,
    AgentRunContext,
    AgentRunExecutionPlanResponse,
    AgentRunGuardrail,
    AgentRunResponse,
    AgentRunSseEvent,
    AgentRunSseEventType,
    AgentRunToolRecord,
    AgentRunUsage,
    AgentSessionResponse,
)


def session_response(session: AgentSessionView) -> AgentSessionResponse:
    """Map one session projection to its public DTO."""
    return AgentSessionResponse(
        session_id=session.session_id,
        created_at=session.created_at,
        retention_class=session.retention_class,
    )


def capability_response(capability: AgentCapabilityView) -> AgentCapabilityResponse:
    """Map redacted runtime capability state to its public DTO."""
    return AgentCapabilityResponse(
        enabled=capability.enabled,
        runtime_state=capability.runtime_state,
        provider=capability.provider,
        available_profiles=capability.available_profiles,
        default_profile=capability.default_profile,
        degradation_reason=capability.degradation_reason,
        checked_at=capability.checked_at,
    )


def decision_opinion_response(
    opinion: DecisionOpinionReadModel,
) -> AgentDecisionOpinionResponse:
    """Map one shadow-only decision opinion to its public DTO."""
    identity = opinion.identity
    context = identity.context
    return AgentDecisionOpinionResponse(
        decision_identity=AgentDecisionOpinionIdentity(
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            trade_date=identity.trade_date,
            account_id=identity.account_id,
            sleeve_id=identity.sleeve_id,
            v3_artifact_id=identity.v3_artifact_id,
            decision_time=context.decision_time,
            knowledge_cutoff=context.knowledge_cutoff,
            publication_cutoff=context.publication_cutoff,
            source_snapshot_id=context.source_snapshot_id,
        ),
        status=opinion.status,
        generated_at=opinion.generated_at,
        model_profile=opinion.model_profile,
        summary=opinion.summary,
        disagreements=opinion.disagreements,
        uncertainties=opinion.uncertainties,
        evidence_refs=opinion.evidence_refs,
        provenance_match=opinion.provenance_match,
        shadow_outcome_identity=opinion.shadow_outcome_identity,
        unavailable_reason=opinion.unavailable_reason,
    )


def run_response(run: AgentRunView) -> AgentRunResponse:
    """Map one readable run projection to its public DTO."""
    context = (
        AgentRunContext(
            context_type=run.context.context_type,
            context_id=run.context.context_id,
        )
        if run.context is not None
        else None
    )
    guardrail = (
        AgentRunGuardrail(
            status=run.guardrail.status,
            reason_code=run.guardrail.reason_code,
        )
        if run.guardrail is not None
        else None
    )
    usage = (
        AgentRunUsage(
            model_attempts=run.usage.model_attempts,
            model_turns=run.usage.model_turns,
            tool_calls=run.usage.tool_calls,
            retries=run.usage.retries,
            total_tokens=run.usage.total_tokens,
            model_spend_usd=run.usage.model_spend_usd,
            exhausted_reason=run.usage.exhausted_reason,
        )
        if run.usage is not None
        else None
    )
    execution_plan = (
        AgentRunExecutionPlanResponse(
            decision_time=run.execution_plan.temporal_context.decision_time,
            knowledge_cutoff=run.execution_plan.temporal_context.knowledge_cutoff,
            publication_cutoff=(run.execution_plan.temporal_context.publication_cutoff),
            source_snapshot_id=(run.execution_plan.temporal_context.source_snapshot_id),
            execution_eligible_at="not_applicable",
            allowed_universe=run.execution_plan.temporal_context.allowed_universe,
            license_class=run.execution_plan.temporal_context.license_class,
            egress_class="cloud_allowed",
            allowed_tools=run.execution_plan.allowed_tools,
            max_output_tokens=run.execution_plan.max_output_tokens,
            authority_hash=run.execution_plan.authority_hash,
        )
        if run.execution_plan is not None
        else None
    )
    return AgentRunResponse(
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
        objective=run.objective,
        context=context,
        output_summary=run.output_summary,
        tool_records=tuple(
            AgentRunToolRecord(
                call_id=record.call_id,
                tool_name=record.tool_name,
                arguments_hash=record.arguments_hash,
                result_hash=record.result_hash,
                evidence_refs=record.evidence_refs,
                artifact_refs=record.artifact_refs,
            )
            for record in run.tool_records
        ),
        evidence_refs=run.evidence_refs,
        artifact_refs=run.artifact_refs,
        guardrail=guardrail,
        usage=usage,
        failure_code=run.failure_code,
        event_cursor=run.event_cursor,
        projection_state=run.projection_state,
        projection_reason=run.projection_reason,
        projection_version=run.projection_version,
        projection_updated_at=run.projection_updated_at,
        execution_plan=execution_plan,
    )


def approval_response(
    decision: AgentApprovalDecision,
) -> AgentApprovalDecisionResponse:
    """Map one approval decision receipt to its public DTO."""
    return AgentApprovalDecisionResponse(
        approval_id=decision.approval_id,
        run_id=decision.run_id,
        action_hash=decision.action_hash,
        status=decision.status.value,
        operator_id=decision.operator_id,
        reason=decision.reason,
        decided_at=decision.decided_at,
    )


def approval_detail_response(approval: AgentApprovalView) -> AgentApprovalResponse:
    """Map one exact approval projection to its public DTO."""
    return AgentApprovalResponse(
        approval_id=approval.approval_id,
        run_id=approval.run_id,
        action_type=approval.action_type,
        target_identity=approval.target_identity,
        action_payload=dict(approval.action_payload),
        action_hash=approval.action_hash,
        status=approval.status,
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
        operator_id=approval.operator_id,
        reason=approval.reason,
        decided_at=approval.decided_at,
    )


def campaign_response(campaign: CampaignView) -> AgentCampaignResponse:
    """Map one governed campaign projection to its public DTO."""
    sandbox = campaign.budget.sandbox_resource_limits
    return AgentCampaignResponse(
        campaign_id=campaign.campaign_id,
        status=campaign.status,
        canonical_manifest=dict(campaign.canonical_manifest),
        manifest_hash=campaign.manifest_hash,
        authorization_hash=campaign.authorization_hash,
        authorized_by=campaign.authorized_by,
        authorization_expires_at=campaign.authorization_expires_at,
        search_axis=campaign.search_axis,
        source_snapshot_id=campaign.source_snapshot_id,
        allowed_tools=campaign.allowed_tools,
        budget=AgentCampaignBudget(
            candidate_limit=campaign.budget.candidate_limit,
            fold_run_limit=campaign.budget.fold_run_limit,
            generation_limit=campaign.budget.generation_limit,
            concurrent_sandbox_limit=campaign.budget.concurrent_sandbox_limit,
            wall_time_limit_seconds=campaign.budget.wall_time_limit_seconds,
            temporary_storage_limit_bytes=(
                campaign.budget.temporary_storage_limit_bytes
            ),
            model_spend_limit_usd_micros=(campaign.budget.model_spend_limit_usd_micros),
            sandbox_resource_limits=AgentCampaignSandboxLimits(
                cpu_count=sandbox.cpu_count,
                memory_bytes=sandbox.memory_bytes,
                process_limit=sandbox.process_limit,
                temporary_storage_bytes=sandbox.temporary_storage_bytes,
                wall_time_seconds=sandbox.wall_time_seconds,
                output_bytes=sandbox.output_bytes,
            ),
        ),
        best_primary_metric_value=campaign.best_primary_metric_value,
        no_improvement_generations=campaign.no_improvement_generations,
        statistical_trial_count=campaign.statistical_trial_count,
        operational_attempt_count=campaign.operational_attempt_count,
        revision=campaign.revision,
        objective=campaign.objective,
        output_summary=campaign.output_summary,
        tool_records=tuple(
            AgentCampaignToolRecord(
                call_id=record.call_id,
                tool_name=record.tool_name,
                arguments_hash=record.arguments_hash,
                result_hash=record.result_hash,
                evidence_refs=record.evidence_refs,
                artifact_refs=record.artifact_refs,
            )
            for record in campaign.tool_records
        ),
        evidence_refs=campaign.evidence_refs,
        artifact_refs=campaign.artifact_refs,
        guardrail=(
            None
            if campaign.guardrail is None
            else AgentCampaignGuardrail(
                status=campaign.guardrail.status,
                reason_code=campaign.guardrail.reason_code,
            )
        ),
        usage=(
            None
            if campaign.usage is None
            else AgentCampaignUsage(
                statistical_trial_count=campaign.usage.statistical_trial_count,
                operational_attempt_count=campaign.usage.operational_attempt_count,
                no_improvement_generations=(campaign.usage.no_improvement_generations),
                model_spend_usd_micros=campaign.usage.model_spend_usd_micros,
                exhausted_reason=campaign.usage.exhausted_reason,
            )
        ),
        event_cursor=campaign.event_cursor,
        projection_state=campaign.projection_state,
        projection_reason=campaign.projection_reason,
        projection_version=campaign.projection_version,
        projection_updated_at=campaign.projection_updated_at,
    )


def campaign_validation_response(
    validation: CampaignValidationView,
) -> AgentCampaignValidationResponse:
    """Map one stepwise campaign validation to its public DTO."""
    return AgentCampaignValidationResponse(
        step=validation.step,
        valid=validation.valid,
        canonical_manifest=(
            None
            if validation.canonical_manifest is None
            else dict(validation.canonical_manifest)
        ),
        manifest_hash=validation.manifest_hash,
    )


def _run_sse_event(event: AgentEventView) -> AgentRunSseEvent:
    """Validate one internal projection against the versioned public data DTO."""
    if event.schema_version != 1:
        raise ValueError("Agent SSE schema_version must be 1")
    return AgentRunSseEvent(
        schema_version=1,
        event_id=event.event_id,
        run_id=event.run_id,
        run_sequence=event.run_sequence,
        event_type=AgentRunSseEventType(event.event_type),
        payload_hash=event.payload_hash,
        occurred_at=event.occurred_at,
        prev_hash=event.prev_hash,
        event_hash=event.event_hash,
    )


def _campaign_sse_event(event: CampaignEventView) -> AgentCampaignSseEvent:
    """Validate one Campaign projection against the versioned public data DTO."""
    if event.schema_version != 1:
        raise ValueError("Campaign SSE schema_version must be 1")
    return AgentCampaignSseEvent(
        schema_version=1,
        event_id=event.event_id,
        durable_event_id=event.durable_event_id,
        campaign_id=event.campaign_id,
        event_type=AgentCampaignSseEventType(event.event_type),
        previous_status=(
            None
            if event.previous_status is None
            else CampaignStatus(event.previous_status)
        ),
        status=CampaignStatus(event.status),
        payload_hash=event.payload_hash,
        occurred_at=event.occurred_at,
    )


def _validate_replay_cursor(after_event_id: int | None) -> None:
    if after_event_id is not None and (
        type(after_event_id) is not int or after_event_id < 0
    ):
        raise ValueError("after_event_id must be a non-negative integer")


def _validate_run_adjacency(
    previous: AgentRunSseEvent,
    event: AgentRunSseEvent,
) -> None:
    if event.event_id <= previous.event_id:
        raise ValueError("Agent SSE events must have strictly increasing IDs")
    if event.run_id != previous.run_id:
        raise ValueError("Agent SSE replay cannot mix run identities")
    if event.run_sequence != previous.run_sequence + 1:
        raise ValueError("Agent SSE run_sequence must be contiguous")
    if event.prev_hash != previous.event_hash:
        raise ValueError("Agent SSE prev_hash must link the preceding event")


def _validate_run_event_hash(event: AgentRunSseEvent) -> None:
    expected_hash = episode_event_hash(
        event_id=event.event_id,
        run_id=event.run_id,
        run_sequence=event.run_sequence,
        event_type=event.event_type,
        payload_hash=event.payload_hash,
        occurred_at=event.occurred_at,
        prev_hash=event.prev_hash,
    )
    if event.event_hash != expected_hash:
        raise ValueError("Agent SSE event_hash does not authenticate its event")


def _validate_campaign_adjacency(
    previous: AgentCampaignSseEvent,
    event: AgentCampaignSseEvent,
) -> None:
    if event.event_id != previous.event_id + 1:
        raise ValueError("Campaign SSE event_id must be contiguous")
    if event.campaign_id != previous.campaign_id:
        raise ValueError("Campaign SSE replay cannot mix Campaign identities")
    if event.previous_status is not previous.status:
        raise ValueError("Campaign SSE previous_status must match the preceding status")


def encode_agent_sse(
    events: tuple[AgentEventView, ...],
    *,
    after_event_id: int | None = None,
) -> bytes:
    """Serialize an ordered persisted replay without creating business events."""
    _validate_replay_cursor(after_event_id)
    validated = tuple(_run_sse_event(event) for event in events)
    if validated and after_event_id is None and validated[0].run_sequence != 1:
        raise ValueError("Agent SSE fresh replay must start at run_sequence 1")
    chunks: list[bytes] = []
    previous: AgentRunSseEvent | None = None
    for index, event in enumerate(validated):
        if after_event_id is not None and event.event_id <= after_event_id:
            raise ValueError("Agent SSE event did not advance beyond after_event_id")
        if previous is not None:
            _validate_run_adjacency(previous, event)
        _validate_run_event_hash(event)
        if (
            event.event_type in AGENT_RUN_TERMINAL_EVENT_TYPES
            and index != len(validated) - 1
        ):
            raise ValueError("Agent SSE terminal event must be the final frame")
        data = orjson.dumps(
            event.model_dump(mode="python"),
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
        chunks.append(
            b"".join(
                (
                    f"id: {event.event_id}\n".encode(),
                    f"event: {event.event_type}\n".encode(),
                    b"data: ",
                    data,
                    b"\n\n",
                )
            )
        )
        previous = event
    return b"".join(chunks)


def encode_campaign_sse(
    events: tuple[CampaignEventView, ...],
    *,
    after_event_id: int | None = None,
) -> bytes:
    """Serialize ordered persisted Campaign events without executing work."""
    _validate_replay_cursor(after_event_id)
    validated = tuple(_campaign_sse_event(event) for event in events)
    chunks: list[bytes] = []
    previous: AgentCampaignSseEvent | None = None
    for event in validated:
        expected_first_id = 1 if after_event_id is None else after_event_id + 1
        if previous is None and event.event_id != expected_first_id:
            raise ValueError(
                "Campaign SSE event_id must be contiguous from the replay cursor"
            )
        if previous is not None:
            _validate_campaign_adjacency(previous, event)
        data = orjson.dumps(
            event.model_dump(mode="python"),
            option=orjson.OPT_SORT_KEYS | orjson.OPT_UTC_Z,
        )
        chunks.append(
            b"".join(
                (
                    f"id: {event.event_id}\n".encode(),
                    f"event: {event.event_type}\n".encode(),
                    b"data: ",
                    data,
                    b"\n\n",
                )
            )
        )
        previous = event
    return b"".join(chunks)


__all__ = [
    "approval_detail_response",
    "approval_response",
    "campaign_response",
    "campaign_validation_response",
    "capability_response",
    "decision_opinion_response",
    "encode_agent_sse",
    "encode_campaign_sse",
    "run_response",
    "session_response",
]
