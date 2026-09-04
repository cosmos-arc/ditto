from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.fake import ScriptedAgentModel, ScriptedOutcome
from ditto_agent.models.port import (
    ModelRequest,
    ModelResult,
    ModelToolCall,
    ModelUsage,
)
from ditto_agent.tools.account_event import AccountEventEvidenceTool
from ditto_agent.tools.decision import DecisionEvidenceTool
from ditto_agent.tools.market_context import MarketContextEvidenceTool
from ditto_agent.tools.portfolio import PortfolioEvidenceTool
from ditto_agent.tools.portfolio_comparison import (
    PortfolioComparisonEvidenceTool,
    PortfolioScenarioPreviewTool,
)
from ditto_agent.tools.registry import EvidenceToolRegistry, ToolNotAllowedError
from ditto_agent.tools.research import (
    BacktestEvidenceTool,
    ExperimentEvidenceTool,
    FactorEvidenceTool,
    StrategyEvidenceTool,
)
from ditto_agent.tools.risk import RiskEvidenceTool
from ditto_agent.tools.selection import (
    IndustryRotationEvidenceTool,
    SelectionRunEvidenceTool,
)
from ditto_agent.tools.technical_analysis import InstrumentTechnicalEvidenceTool
from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceQueryPort,
)
from ditto_application.queries.evidence_contracts import (
    DecisionEvidenceQueryPort,
    IndustryRotationEvidenceQueryPort,
    InstrumentTechnicalEvidenceQueryPort,
    MarketContextEvidenceQueryPort,
    ResearchEvidenceQueryPort,
    SelectionRunEvidenceQueryPort,
)
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceQueryPort,
    PortfolioScenarioEvidenceQueryPort,
)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-20260812",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _registry() -> EvidenceToolRegistry:
    research = cast(ResearchEvidenceQueryPort, object())
    decision = cast(DecisionEvidenceQueryPort, object())
    market_context = cast(MarketContextEvidenceQueryPort, object())
    industry_rotation = cast(IndustryRotationEvidenceQueryPort, object())
    selection_run = cast(SelectionRunEvidenceQueryPort, object())
    technical = cast(InstrumentTechnicalEvidenceQueryPort, object())
    portfolio_comparison = cast(PortfolioComparisonEvidenceQueryPort, object())
    portfolio_scenario = cast(PortfolioScenarioEvidenceQueryPort, object())
    account_event = cast(AccountEventEvidenceQueryPort, object())
    return EvidenceToolRegistry(
        tools=(
            ExperimentEvidenceTool(facade=research),
            FactorEvidenceTool(facade=research),
            StrategyEvidenceTool(facade=research),
            BacktestEvidenceTool(facade=research),
            PortfolioEvidenceTool(facade=decision),
            PortfolioComparisonEvidenceTool(facade=portfolio_comparison),
            PortfolioScenarioPreviewTool(facade=portfolio_scenario),
            AccountEventEvidenceTool(facade=account_event),
            RiskEvidenceTool(facade=decision),
            DecisionEvidenceTool(facade=decision),
            MarketContextEvidenceTool(facade=market_context),
            IndustryRotationEvidenceTool(facade=industry_rotation),
            SelectionRunEvidenceTool(facade=selection_run),
            InstrumentTechnicalEvidenceTool(facade=technical),
        )
    )


def test_read_tool_allowlist_is_exact_and_contains_no_write_or_hosted_tools() -> None:
    registry = _registry()

    assert tuple(spec.name for spec in registry.specs) == (
        "research_experiment_evidence",
        "research_factor_evidence",
        "research_strategy_evidence",
        "research_backtest_evidence",
        "portfolio_evidence",
        "portfolio_comparison_evidence",
        "portfolio_scenario_preview",
        "account_event_evidence",
        "risk_evidence",
        "daily_decision_v3_evidence",
        "market_context_evidence",
        "industry_rotation_evidence",
        "selection_run_evidence",
        "instrument_technical_evidence",
    )
    assert all(spec.kind.value == "function" for spec in registry.specs)
    assert all(not spec.requires_approval for spec in registry.specs)
    assert all(
        spec.input_schema["additionalProperties"] is False for spec in registry.specs
    )
    forbidden_fragments = ("publish", "order", "broker", "write", "delete")
    assert not any(
        fragment in spec.name
        for spec in registry.specs
        for fragment in forbidden_fragments
    )


@pytest.mark.asyncio
async def test_fake_model_wrong_tool_choice_is_rejected_before_dispatch() -> None:
    wrong_call = ModelToolCall(
        call_id="call-001",
        tool_name="publish_strategy",
        arguments={"strategy_id": "strategy-001"},
    )
    model = ScriptedAgentModel(
        script=(
            ScriptedOutcome(
                result=ModelResult(
                    final_output=None,
                    tool_calls=(wrong_call,),
                    usage=ModelUsage(requests=1, input_tokens=12, output_tokens=6),
                    interruptions=(),
                    continuation=None,
                )
            ),
        )
    )
    result = await model.run(
        ModelRequest(
            run_id="run-001",
            agent_name="evidence-copilot",
            instructions="Use read-only evidence tools.",
            input_text="Publish strategy-001.",
            max_turns=2,
            max_output_tokens=128,
            tools=_registry().specs,
        )
    )

    with pytest.raises(ToolNotAllowedError, match="publish_strategy"):
        _registry().execute(call=result.tool_calls[0], context=_context())


def test_registry_rejects_duplicate_or_narrowed_out_tool_names() -> None:
    registry = _registry()
    experiment = registry.tools["research_experiment_evidence"]

    with pytest.raises(ValueError, match="duplicate tool"):
        EvidenceToolRegistry(tools=(experiment, experiment))

    narrowed = registry.restrict(("research_experiment_evidence",))
    with pytest.raises(ToolNotAllowedError, match="risk_evidence"):
        narrowed.execute(
            call=ModelToolCall(
                call_id="call-002",
                tool_name="risk_evidence",
                arguments={},
            ),
            context=_context(),
        )
