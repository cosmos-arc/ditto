"""Strict type and canonicalization edges for campaign contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import campaign
from ditto_analysis.experiments.campaign import (
    CampaignBudget,
    EvaluationResult,
    ExperimentPlan,
    HypothesisSpec,
    ResearchCampaignManifest,
    ResearchCandidateSpec,
    SearchAxis,
)
from ditto_analysis.experiments.generated_code import SandboxResourceLimits
from ditto_analysis.experiments.metric_schema import ResearchMetricId
from ditto_analysis.experiments.models import (
    CandidateId,
    ContentHash,
    ExperimentId,
    SnapshotId,
)
from ditto_analysis.experiments.specs import (
    CandidateSpec,
    ExperimentBudget,
    FoldProtocolSpec,
)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _candidate(*, is_baseline: bool = True) -> CandidateSpec:
    return CandidateSpec(
        CandidateId("candidate-1"),
        1,
        is_baseline,
        {"lookback": 20},
    )


def _research_candidate(*, is_baseline: bool = True) -> ResearchCandidateSpec:
    return ResearchCandidateSpec(
        candidate=_candidate(is_baseline=is_baseline),
        search_axis=SearchAxis.FACTOR_CODE,
        parent_candidate_id=None,
        factor_code_hash=_hash("a"),
        model_code_hash=None,
        data_requirement_hashes=(_hash("b"),),
    )


def _budget() -> CampaignBudget:
    return CampaignBudget(ExperimentBudget(4, 8))


def _hypothesis() -> HypothesisSpec:
    return HypothesisSpec(
        statement="Reversal survives costs.",
        mechanism="Liquidity provision.",
        universe_hash=_hash("c"),
        expected_signal="Positive forward return.",
        failure_condition="Non-positive Sharpe.",
    )


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        fold_protocol=FoldProtocolSpec("walk-forward", 1, _hash("d")),
        snapshot_id=SnapshotId("snapshot-1"),
        validation_objective_hash=_hash("e"),
        cost_model_hash=_hash("f"),
        seed=1,
        purge_sessions=1,
        embargo_sessions=1,
    )


def _evaluation() -> EvaluationResult:
    return EvaluationResult(
        candidate_id=CandidateId("candidate-1"),
        candidate_hash=_hash("1"),
        validation_protocol_hash=_hash("2"),
        evaluation_input_hash=_hash("3"),
        metrics_artifact_hash=_hash("4"),
        constraints_passed=True,
        significance_evidence_hash=_hash("5"),
        failure_classification=None,
        evidence_refs=(_hash("6"),),
    )


def _manifest() -> ResearchCampaignManifest:
    return ResearchCampaignManifest(
        campaign_id=ExperimentId("campaign-1"),
        objective="Find a robust signal.",
        primary_metric_id=ResearchMetricId.SHARPE_RATIO,
        hypothesis=_hypothesis(),
        baseline_candidate=_research_candidate(),
        experiment_plan=_plan(),
        budget=_budget(),
        search_axis=SearchAxis.FACTOR_CODE,
        search_space_hash=_hash("7"),
        lineage_root=_hash("8"),
        stopping_rule="Stop after the budget is exhausted.",
        allowed_tools=("research.evaluate",),
        prohibited_actions=("broker.submit",),
    )


def _reason(exc_info: pytest.ExceptionInfo[ExperimentSpecError]) -> object:
    return exc_info.value.details["reason_code"]


def test_campaign_scalar_helpers_reject_padded_and_negative_values() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        campaign._non_empty(" padded", "field")
    assert _reason(exc_info) == "invalid_campaign_text"

    with pytest.raises(ExperimentSpecError) as exc_info:
        campaign._non_negative_int(-1, "seed")
    assert _reason(exc_info) == "invalid_experiment_plan"


def test_campaign_hash_sequences_require_typed_unique_ordered_values() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        campaign._freeze_hashes("not-a-sequence", "hashes")
    assert _reason(exc_info) == "invalid_campaign_hash_sequence"

    for value in ((), (_hash("a"), "untyped"), (_hash("a"), _hash("a"))):
        with pytest.raises(ExperimentSpecError) as exc_info:
            campaign._freeze_hashes(value, "hashes")
        assert _reason(exc_info) in {
            "invalid_campaign_hash_sequence",
            "duplicate_campaign_hash",
        }


def test_campaign_name_sequences_require_canonical_nonempty_values() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        campaign._freeze_names("tool", "tools")
    assert _reason(exc_info) == "invalid_campaign_name_sequence"

    with pytest.raises(ExperimentSpecError) as exc_info:
        campaign._freeze_names((), "tools")
    assert _reason(exc_info) == "invalid_campaign_name_sequence"


def test_campaign_budget_requires_exact_nested_contract_types() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            _budget(),
            experiment_budget=cast("ExperimentBudget", object()),
        )
    assert _reason(exc_info) == "invalid_campaign_budget"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            _budget(),
            sandbox_resource_limits=cast("SandboxResourceLimits", object()),
        )
    assert _reason(exc_info) == "invalid_campaign_budget"


def test_hypothesis_requires_a_typed_universe_hash() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_hypothesis(), universe_hash=cast("ContentHash", "a" * 64))
    assert _reason(exc_info) == "invalid_hypothesis_spec"


def test_research_candidate_rejects_untyped_nested_and_lineage_nodes() -> None:
    candidate = _research_candidate()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(candidate, candidate=cast("CandidateSpec", object()))
    assert _reason(exc_info) == "invalid_research_candidate"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(candidate, parent_candidate_id=cast("CandidateId", "parent"))
    assert _reason(exc_info) == "invalid_candidate_lineage"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(candidate, factor_code_hash=cast("ContentHash", "a" * 64))
    assert _reason(exc_info) == "invalid_research_candidate"


def test_experiment_plan_requires_exact_typed_identity_nodes() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_plan(), snapshot_id=cast("SnapshotId", "snapshot-1"))
    assert _reason(exc_info) == "invalid_experiment_plan"


def test_evaluation_result_rejects_partial_or_untyped_evidence() -> None:
    result = _evaluation()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(result, candidate_id=cast("CandidateId", "candidate-1"))
    assert _reason(exc_info) == "invalid_evaluation_result"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(result, constraints_passed=cast("bool", 1))
    assert _reason(exc_info) == "invalid_evaluation_result"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(result, constraints_passed=False, failure_classification=" ")
    assert _reason(exc_info) == "invalid_campaign_text"


def test_manifest_requires_exact_nodes_and_an_explicit_baseline() -> None:
    manifest = _manifest()
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(manifest, campaign_id=cast("ExperimentId", "campaign-1"))
    assert _reason(exc_info) == "invalid_campaign_manifest"

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(manifest, baseline_candidate=_research_candidate(is_baseline=False))
    assert _reason(exc_info) == "campaign_baseline_missing"
