"""Portfolio Agent tools may explain sealed host math but never author weights."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.portfolio import (
    PortfolioDiagnosticDraft,
    PortfolioNumericClaim,
    validate_portfolio_diagnostic,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.portfolio_comparison import (
    PortfolioComparisonEvidenceTool,
    PortfolioScenarioPreviewTool,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceIdentity,
    PortfolioComparisonEvidenceQueryPort,
    PortfolioComparisonEvidenceReadModel,
    PortfolioScenarioEvidenceQueryPort,
    PortfolioScenarioEvidenceReadModel,
    PortfolioScenarioEvidenceRequest,
)

_SNAPSHOT_SET = "snapshot-set:sha256:" + "a" * 64


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id=_SNAPSHOT_SET,
            execution_eligible_at="not_applicable",
            allowed_universe=("600519.SH", "510300.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _application_context() -> EvidenceTemporalContext:
    context = _context()
    return EvidenceTemporalContext(
        decision_time=context.decision_time,
        knowledge_cutoff=context.knowledge_cutoff,
        publication_cutoff=context.publication_cutoff,
        source_snapshot_id=context.source_snapshot_id,
    )


def _artifact() -> tuple[EvidenceArtifactReference, ...]:
    return (
        EvidenceArtifactReference(
            artifact_id="model-main",
            artifact_kind="signal_package",
            content_hash="b" * 64,
        ),
    )


class _Facade:
    def __init__(self) -> None:
        self.comparison_identities: list[PortfolioComparisonEvidenceIdentity] = []
        self.scenario_requests: list[PortfolioScenarioEvidenceRequest] = []

    def get_comparison_evidence(
        self,
        *,
        identity: PortfolioComparisonEvidenceIdentity,
        context: EvidenceTemporalContext,
    ) -> PortfolioComparisonEvidenceReadModel:
        self.comparison_identities.append(identity)
        return PortfolioComparisonEvidenceReadModel(
            identity=identity,
            as_of="2026-08-31",
            valuation_snapshot_id="portfolio-valuation:sha256:" + "c" * 64,
            source_snapshot_set_id=_SNAPSHOT_SET,
            source_snapshot_ids=("snapshot-stock",),
            temporal_context=context,
            payload=EvidencePayloadReadModel.seal(
                schema_version=1,
                value={
                    "as_of": "2026-08-31",
                    "valuation_snapshot_id": ("portfolio-valuation:sha256:" + "c" * 64),
                    "source_snapshot_ids": ("snapshot-stock",),
                    "model": {"total_value": "100000.00"},
                    "paper": {"total_value": "99500.00"},
                    "manual": {"total_value": "98000.00"},
                    "model_vs_paper": {
                        "attribution": {
                            "unfilled_bps": "250",
                            "slippage_amount": "12.50",
                            "fee_amount": "5.00",
                            "risk_blocked_bps": "100",
                        }
                    },
                    "model_vs_manual": {"attribution": {"user_choice_bps": "400"}},
                },
            ),
            artifact_refs=_artifact(),
            lineage=("signal-package:model-main", "snapshot:snapshot-stock"),
        )

    def preview_scenario(
        self,
        *,
        request: PortfolioScenarioEvidenceRequest,
        context: EvidenceTemporalContext,
    ) -> PortfolioScenarioEvidenceReadModel:
        self.scenario_requests.append(request)
        return PortfolioScenarioEvidenceReadModel(
            identity=request.identity,
            baseline_kind=request.baseline_kind,
            as_of="2026-08-31",
            valuation_snapshot_id="portfolio-valuation:sha256:" + "c" * 64,
            source_snapshot_set_id=_SNAPSHOT_SET,
            source_snapshot_ids=("snapshot-stock",),
            temporal_context=context,
            payload=EvidencePayloadReadModel.seal(
                schema_version=1,
                value={
                    "baseline_kind": request.baseline_kind,
                    "scenario_inputs": {
                        "cash_reserve_weight": "0.45",
                        "max_position_weight": "0.55",
                    },
                    "proposed_weights": {"1": "0.55"},
                    "risk": {
                        "as_of": "2026-08-31",
                        "valuation_snapshot_id": (
                            "portfolio-valuation:sha256:" + "c" * 64
                        ),
                        "source_snapshot_ids": ("snapshot-stock",),
                        "turnover": 0.125,
                        "constraint_findings": (),
                    },
                    "applied_constraints": (
                        "cash_reserve_weight=0.45",
                        "max_position_weight=0.55",
                    ),
                },
            ),
            artifact_refs=_artifact(),
            lineage=("signal-package:model-main", "snapshot:snapshot-stock"),
        )


def _identity_arguments() -> dict[str, object]:
    return {
        "strategy_id": "strategy-1",
        "model_portfolio_id": "model-main",
        "paper_account_id": "paper-main",
        "manual_account_id": "manual-main",
        "paper_session_id": "paper-session-1",
    }


def test_tools_seal_host_comparison_and_preview_without_temporal_arguments() -> None:
    facade = _Facade()
    comparison_tool = PortfolioComparisonEvidenceTool(
        facade=cast(PortfolioComparisonEvidenceQueryPort, facade)
    )
    scenario_tool = PortfolioScenarioPreviewTool(
        facade=cast(PortfolioScenarioEvidenceQueryPort, facade)
    )

    comparison = comparison_tool.invoke(
        arguments=_identity_arguments(),
        context=_context(),
    )
    scenario = scenario_tool.invoke(
        arguments={
            **_identity_arguments(),
            "baseline_kind": "model",
            "excluded_instrument_ids": [2],
            "max_position_weight": "0.55",
            "cash_reserve_weight": "0.45",
            "market_shock": -0.10,
            "industry_shocks": {"consumer": -0.05},
        },
        context=_context(),
    )

    assert comparison.result["kind"] == "portfolio_comparison"
    assert scenario.result["kind"] == "portfolio_scenario_preview"
    assert comparison.verify_integrity()
    assert scenario.verify_integrity()
    assert facade.scenario_requests[0].excluded_instrument_ids == frozenset({2})
    assert str(facade.scenario_requests[0].max_position_weight) == "0.55"
    forbidden = {
        "as_of",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
        "source_snapshot_ids",
        "valuation_snapshot_id",
        "target_weights",
    }
    assert forbidden.isdisjoint(comparison_tool.spec.input_schema["properties"])
    assert forbidden.isdisjoint(scenario_tool.spec.input_schema["properties"])


def test_tools_reject_model_attempt_to_override_host_snapshot() -> None:
    tool = PortfolioComparisonEvidenceTool(
        facade=cast(PortfolioComparisonEvidenceQueryPort, _Facade())
    )

    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={
                **_identity_arguments(),
                "source_snapshot_ids": ["future"],
            },
            context=_context(),
        )


def test_portfolio_diagnostic_accepts_only_numbers_present_in_sealed_evidence() -> None:
    facade = _Facade()
    comparison = PortfolioComparisonEvidenceTool(
        facade=cast(PortfolioComparisonEvidenceQueryPort, facade)
    ).invoke(arguments=_identity_arguments(), context=_context())
    scenario = PortfolioScenarioPreviewTool(
        facade=cast(PortfolioScenarioEvidenceQueryPort, facade)
    ).invoke(
        arguments={
            **_identity_arguments(),
            "baseline_kind": "model",
            "excluded_instrument_ids": [2],
            "max_position_weight": "0.55",
            "cash_reserve_weight": "0.45",
        },
        context=_context(),
    )
    draft = PortfolioDiagnosticDraft(
        summary="Paper 偏差主要来自未成交, 预演保留了更高现金。",
        facts=("Paper 未成交偏差为 250 bps。", "预演现金储备为 45%。"),
        interpretations=("当前成交链仍需观察。",),
        uncertainties=("下一交易日成交状况未知。",),
        numeric_claims=(
            PortfolioNumericClaim(
                evidence_ref=comparison.evidence_id,
                path="model_vs_paper.attribution.unfilled_bps",
                value="250",
            ),
            PortfolioNumericClaim(
                evidence_ref=scenario.evidence_id,
                path="proposed_weights.1",
                value="0.55",
            ),
            PortfolioNumericClaim(
                evidence_ref=scenario.evidence_id,
                path="scenario_inputs.cash_reserve_weight",
                value="0.45",
            ),
        ),
        evidence_refs=(comparison.evidence_id, scenario.evidence_id),
    )

    accepted = validate_portfolio_diagnostic(
        draft,
        evidence=(comparison, scenario),
    )

    assert accepted.guardrail_status == "passed"
    assert accepted.evidence_refs == draft.evidence_refs

    fabricated = replace(
        draft,
        numeric_claims=(
            PortfolioNumericClaim(
                evidence_ref=scenario.evidence_id,
                path="proposed_weights.1",
                value="0.65",
            ),
        ),
    )
    with pytest.raises(ValueError, match="does not match sealed evidence"):
        validate_portfolio_diagnostic(
            fabricated,
            evidence=(comparison, scenario),
        )
