"""Immutable authority contracts for an executable governed Agent run."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)

NOW = datetime(2026, 8, 30, 8, tzinfo=UTC)


def _context(*, snapshot: str = "snapshot-certified-2026-08-29") -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=NOW,
            knowledge_cutoff=datetime(2026, 8, 30, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 30, 6, tzinfo=UTC),
            source_snapshot_id=snapshot,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "510500.SH"),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def test_execution_plan_binds_every_trusted_scope_field_to_authority() -> None:
    plan = AgentRunExecutionPlan(
        temporal_context=_context(),
        allowed_tools=("research_experiment_evidence",),
        max_output_tokens=512,
    )
    changed_snapshot = AgentRunExecutionPlan(
        temporal_context=_context(snapshot="snapshot-certified-2026-08-30"),
        allowed_tools=("research_experiment_evidence",),
        max_output_tokens=512,
    )

    assert len(plan.authority_hash) == 64
    assert plan.authority_hash != changed_snapshot.authority_hash
    assert plan.canonical_payload()["temporal_context"] == (
        plan.temporal_context.canonical_payload()
    )


def test_execution_plan_rejects_duplicate_or_empty_tool_authority() -> None:
    with pytest.raises(ValueError, match="allowed_tools"):
        AgentRunExecutionPlan(
            temporal_context=_context(),
            allowed_tools=(),
            max_output_tokens=512,
        )
    with pytest.raises(ValueError, match="allowed_tools"):
        AgentRunExecutionPlan(
            temporal_context=_context(),
            allowed_tools=(
                "research_experiment_evidence",
                "research_experiment_evidence",
            ),
            max_output_tokens=512,
        )
