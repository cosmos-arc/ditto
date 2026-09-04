"""Six product business outputs share one strict canonical contract."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast

import pytest
from ditto_agent.contracts.business_outputs import (
    BUSINESS_OUTPUT_DISCLAIMER,
    BusinessAction,
    BusinessOutputDraft,
    BusinessOutputKind,
    CompletenessStatus,
    FreshnessStatus,
    GuardrailStatus,
    NumericEvidenceClaim,
    business_output_schema,
    validate_business_output,
)
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 6, 30, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 6, tzinfo=UTC),
            source_snapshot_id="snapshot-set-20260831",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _evidence() -> EvidenceEnvelope:
    return EvidenceEnvelope.seal(
        evidence_id="evidence-market-1",
        tool_name="market_context_evidence",
        result={
            "schema_version": 1,
            "kind": "market_context",
            "payload": {"breadth": {"advance_ratio": "0.56"}},
        },
        artifact_refs=("market-context:sha256:" + "a" * 64,),
        temporal_context=_context(),
        lineage=("market-context:context-1",),
    )


_DETAILS: dict[BusinessOutputKind, dict[str, object]] = {
    BusinessOutputKind.EVIDENCE_BRIEF: {
        "market_changes": ("Breadth improved to 56%.",),
        "drivers": ("Large-cap participation broadened.",),
        "risks": ("Publication coverage remains partial.",),
        "watch_items": ("Watch breadth persistence.",),
    },
    BusinessOutputKind.SELECTION_MEMO: {
        "inclusions": ("Candidate is inside the exact SelectionRun.",),
        "exclusions": ("Hard exclusions remain binding.",),
        "comparisons": ("No uncited ranking was introduced.",),
        "research_gaps": ("Fundamental confirmation is missing.",),
    },
    BusinessOutputKind.TECHNICAL_ANALYSIS_BRIEF: {
        "timeframe_alignment": ("Daily and weekly states agree.",),
        "levels": ("No level is asserted without snapshot evidence.",),
        "conditions": ("Trend must remain confirmed.",),
        "invalidations": ("Snapshot expiry invalidates this brief.",),
    },
    BusinessOutputKind.RESEARCH_MEMO: {
        "findings": ("The experiment result is reproducible.",),
        "methodology_notes": ("Holdout evidence stays hidden.",),
        "limitations": ("One regime is underrepresented.",),
        "research_gaps": ("Stress testing remains open.",),
    },
    BusinessOutputKind.PORTFOLIO_DIAGNOSTIC: {
        "drift": ("Execution drift is host-computed.",),
        "exposure": ("Exposure comes from sealed evidence.",),
        "pnl_attribution": ("Attribution is descriptive only.",),
        "scenario_references": ("Scenario preview writes no target.",),
    },
    BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL: {
        "spec_diff": ("One selector parameter changed.",),
        "validation": ("The detached draft validates.",),
        "tests": ("Compiler and validator previews passed.",),
        "open_assumptions": ("Budget approval remains open.",),
        "spec_json": {
            "schema_version": 2,
            "strategy_family_id": "selection-research-draft",
        },
    },
}


def _draft(
    *,
    kind: BusinessOutputKind = BusinessOutputKind.EVIDENCE_BRIEF,
) -> BusinessOutputDraft:
    return BusinessOutputDraft(
        output_kind=kind,
        schema_version=1,
        run_id="run-business-1",
        context_type="market_context",
        context_id="context-1",
        as_of=_context().decision_time,
        knowledge_cutoff=_context().knowledge_cutoff,
        publication_cutoff=_context().publication_cutoff,
        evidence_refs=("evidence-market-1",),
        artifact_refs=("market-context:sha256:" + "a" * 64,),
        source_snapshot_ids=("snapshot-set-20260831",),
        facts=("Market breadth reached 56%.",),
        interpretations=("Participation is broader.",),
        uncertainties=("Persistence is not yet known.",),
        conflicts=(),
        recommended_next_steps=("Review the next certified snapshot.",),
        numeric_claims=(
            NumericEvidenceClaim(
                evidence_ref="evidence-market-1",
                path="breadth.advance_ratio",
                value="0.56",
            ),
        ),
        action_intents=(BusinessAction.OPEN_CONTEXT,),
        model_version="model-snapshot-1",
        prompt_version="business-output-v1",
        tool_versions={"market_context_evidence": "1"},
        policy_version="grounding-policy-v1",
        guardrail_status=GuardrailStatus.PASSED,
        freshness=FreshnessStatus.CURRENT,
        completeness=CompletenessStatus.PARTIAL,
        disclaimer=BUSINESS_OUTPUT_DISCLAIMER,
        details=_DETAILS[kind],
    )


def test_all_six_output_schemas_are_closed_and_kind_specific() -> None:
    assert len(BusinessOutputKind) == 6

    for kind in BusinessOutputKind:
        schema = business_output_schema(kind)
        assert schema["additionalProperties"] is False
        assert schema["properties"]["output_kind"]["const"] == kind.value
        assert schema["properties"]["details"]["additionalProperties"] is False
        assert set(schema["properties"]["details"]["required"]) == set(_DETAILS[kind])


@pytest.mark.parametrize("kind", list(BusinessOutputKind))
def test_each_business_output_validates_to_a_canonical_immutable_record(
    kind: BusinessOutputKind,
) -> None:
    draft = _draft(kind=kind)

    output = validate_business_output(
        draft,
        evidence=(_evidence(),),
        expected_context=_context(),
        allowed_tool_names=("market_context_evidence",),
    )

    assert output.output_kind is kind
    assert output.verify_content_hash()
    assert output.guardrail_status is GuardrailStatus.PASSED
    assert isinstance(output.details, MappingProxyType)
    with pytest.raises(TypeError):
        cast(dict[str, object], output.details)["unexpected"] = True


def test_canonical_hash_is_independent_of_mapping_insertion_order() -> None:
    first = _draft()
    second = replace(
        first,
        tool_versions={"market_context_evidence": "1"},
        details=dict(reversed(tuple(_DETAILS[first.output_kind].items()))),
    )

    one = validate_business_output(
        first,
        evidence=(_evidence(),),
        expected_context=_context(),
        allowed_tool_names=("market_context_evidence",),
    )
    two = validate_business_output(
        second,
        evidence=(_evidence(),),
        expected_context=_context(),
        allowed_tool_names=("market_context_evidence",),
    )

    assert one.content_hash == two.content_hash


def test_uncited_number_or_unknown_evidence_fails_closed() -> None:
    with pytest.raises(ValueError, match="uncited number"):
        validate_business_output(
            replace(_draft(), facts=("Market breadth reached 57%.",)),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_business_output(
            replace(
                _draft(),
                numeric_claims=(
                    NumericEvidenceClaim(
                        evidence_ref="evidence-unknown",
                        path="breadth.advance_ratio",
                        value="0.56",
                    ),
                ),
            ),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )


def test_context_tool_and_artifact_conflicts_fail_closed() -> None:
    with pytest.raises(ValueError, match="temporal context"):
        validate_business_output(
            replace(
                _draft(),
                knowledge_cutoff=datetime(2026, 8, 31, 6, 31, tzinfo=UTC),
            ),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )
    with pytest.raises(ValueError, match="tool is outside"):
        validate_business_output(
            _draft(),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("selection_run_evidence",),
        )
    with pytest.raises(ValueError, match="artifact reference"):
        validate_business_output(
            replace(_draft(), artifact_refs=("fabricated-artifact",)),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )


def test_strategy_proposal_rejects_code_and_forbidden_action_intent() -> None:
    draft = _draft(kind=BusinessOutputKind.STRATEGY_DRAFT_PROPOSAL)
    details = dict(draft.details)
    details["spec_json"] = {
        "schema_version": 2,
        "strategy_family_id": "unsafe",
        "python_code": "place_real_order()",
    }

    with pytest.raises(ValueError, match="declarative"):
        validate_business_output(
            replace(draft, details=details),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )
    with pytest.raises(ValueError, match="action_intents"):
        validate_business_output(
            replace(
                draft, action_intents=cast(tuple[BusinessAction, ...], ("publish",))
            ),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )


def test_disclaimer_and_guardrail_status_are_not_model_overridable() -> None:
    with pytest.raises(ValueError, match="disclaimer"):
        validate_business_output(
            replace(_draft(), disclaimer="This is a real order."),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )
    with pytest.raises(ValueError, match="guardrail"):
        validate_business_output(
            replace(_draft(), guardrail_status=GuardrailStatus.BLOCKED),
            evidence=(_evidence(),),
            expected_context=_context(),
            allowed_tool_names=("market_context_evidence",),
        )
