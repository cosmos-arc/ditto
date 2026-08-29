"""Pure public projections for the persisted Agent composition root."""

from ditto_agent.presentation import AgentRunPresentation
from ditto_agent.runtime.service import (
    AgentProjectionState,
    AgentRunView,
)
from ditto_agent.storage.sqlite.records import StoredAgentRun


def run_view(
    run: StoredAgentRun,
    *,
    presentation: AgentRunPresentation | None = None,
    projection_reason: str = "agent_presentation_unconfigured",
) -> AgentRunView:
    """Combine durable run identity with optional readable presentation data."""
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
        output_summary=(
            presentation.output_summary if presentation is not None else None
        ),
        tool_records=(presentation.tool_records if presentation is not None else ()),
        evidence_refs=(presentation.evidence_refs if presentation is not None else ()),
        artifact_refs=(presentation.artifact_refs if presentation is not None else ()),
        guardrail=(presentation.guardrail if presentation is not None else None),
        usage=(presentation.usage if presentation is not None else None),
        failure_code=(presentation.failure_code if presentation is not None else None),
        event_cursor=(presentation.event_cursor if presentation is not None else 0),
        projection_state=(
            AgentProjectionState.COMPLETE
            if presentation is not None
            else AgentProjectionState.PARTIAL
        ),
        projection_reason=None if presentation is not None else projection_reason,
        projection_version=(
            presentation.projection_version if presentation is not None else None
        ),
        projection_updated_at=(
            presentation.updated_at if presentation is not None else None
        ),
    )


__all__ = ["run_view"]
