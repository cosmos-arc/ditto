"""CMP factual and permission gate for grounded portfolio assistance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolCall
from ditto_agent.tools.portfolio_comparison import (
    PortfolioComparisonEvidenceTool,
    PortfolioScenarioPreviewTool,
)
from ditto_agent.tools.registry import EvidenceToolRegistry, ToolNotAllowedError
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceQueryPort,
    PortfolioScenarioEvidenceQueryPort,
)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id="snapshot-set:sha256:" + "a" * 64,
            execution_eligible_at="not_applicable",
            allowed_universe=("600519.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _registry() -> EvidenceToolRegistry:
    return EvidenceToolRegistry(
        tools=(
            PortfolioComparisonEvidenceTool(
                facade=cast(PortfolioComparisonEvidenceQueryPort, object())
            ),
            PortfolioScenarioPreviewTool(
                facade=cast(PortfolioScenarioEvidenceQueryPort, object())
            ),
        )
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "portfolio_apply_target",
        "paper_start_session",
        "manual_write_event",
        "broker_place_order",
    ],
)
def test_portfolio_permission_gate_rejects_every_mutating_action(
    tool_name: str,
) -> None:
    with pytest.raises(ToolNotAllowedError, match=tool_name):
        _registry().execute(
            call=ModelToolCall(
                call_id="call-forbidden", tool_name=tool_name, arguments={}
            ),
            context=_context(),
        )


def test_portfolio_scenario_schema_cannot_accept_model_authored_target_weights() -> (
    None
):
    properties = (
        _registry().tools["portfolio_scenario_preview"].spec.input_schema["properties"]
    )

    assert "target_weights" not in properties
    assert "source_snapshot_ids" not in properties
    assert "valuation_snapshot_id" not in properties
