"""R5 governed research campaign domain contract tests."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
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


def _candidate(*, axis: SearchAxis = SearchAxis.FACTOR_CODE) -> ResearchCandidateSpec:
    return ResearchCandidateSpec(
        candidate=CandidateSpec(
            candidate_id=CandidateId("candidate-1"),
            ordinal=1,
            is_baseline=True,
            parameters={"lookback": 20},
        ),
        search_axis=axis,
        parent_candidate_id=None,
        factor_code_hash=_hash("a") if axis is SearchAxis.FACTOR_CODE else None,
        model_code_hash=_hash("b") if axis is SearchAxis.MODEL_CODE else None,
        data_requirement_hashes=(_hash("c"),),
    )


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        fold_protocol=FoldProtocolSpec(
            protocol_id="walk-forward-v1",
            protocol_version=1,
            protocol_hash=_hash("d"),
        ),
        snapshot_id=SnapshotId("snapshot-2026-08-12"),
        validation_objective_hash=_hash("e"),
        cost_model_hash=_hash("f"),
        seed=42,
        purge_sessions=5,
        embargo_sessions=2,
    )


def _manifest(*, axis: SearchAxis = SearchAxis.FACTOR_CODE) -> ResearchCampaignManifest:
    return ResearchCampaignManifest(
        campaign_id=ExperimentId("campaign-1"),
        objective="Find a robust ETF timing signal.",
        primary_metric_id=ResearchMetricId.SHARPE_RATIO,
        hypothesis=HypothesisSpec(
            statement="Short-term reversal persists after costs.",
            mechanism="Liquidity provision earns a reversal premium.",
            universe_hash=_hash("1"),
            expected_signal=(
                "Negative weekly return predicts positive next-week return."
            ),
            failure_condition="Net validation Sharpe is non-positive.",
        ),
        baseline_candidate=_candidate(axis=axis),
        experiment_plan=_plan(),
        budget=CampaignBudget(
            experiment_budget=ExperimentBudget(
                candidate_limit=128,
                fold_run_limit=384,
            )
        ),
        search_axis=axis,
        search_space_hash=_hash("2"),
        lineage_root=_hash("3"),
        stopping_rule="Stop after two generations without improvement.",
        allowed_tools=("research.evaluate", "research.generate_candidate"),
        prohibited_actions=("broker.submit_order", "strategy.publish"),
    )


def test_campaign_manifest_is_immutable_content_addressed_and_agent_independent() -> (
    None
):
    manifest = _manifest()
    replay = _manifest()

    assert manifest == replay
    assert manifest.manifest_hash == replay.manifest_hash
    assert manifest.canonical_payload.content_hash == manifest.manifest_hash
    assert manifest.baseline_candidate.candidate_hash != (
        manifest.baseline_candidate.candidate.parameter_hash
    )
    assert manifest.allowed_tools == (
        "research.evaluate",
        "research.generate_candidate",
    )


def test_campaign_hash_binds_per_sandbox_resource_limits() -> None:
    manifest = _manifest()
    reduced = replace(
        manifest,
        budget=replace(
            manifest.budget,
            sandbox_resource_limits=replace(
                manifest.budget.sandbox_resource_limits,
                cpu_count=1,
            ),
        ),
    )

    assert manifest.manifest_hash != reduced.manifest_hash


@pytest.mark.parametrize(
    ("changes", "reason_code"),
    [
        ({"generation_limit": 0}, "invalid_campaign_budget"),
        ({"concurrent_sandbox_limit": 3}, "campaign_budget_limit_exceeded"),
        ({"wall_time_limit_seconds": 14_401}, "campaign_budget_limit_exceeded"),
        (
            {"temporary_storage_limit_bytes": 20 * 1024**3 + 1},
            "campaign_budget_limit_exceeded",
        ),
        ({"model_spend_limit_usd_micros": 8_000_001}, "campaign_budget_limit_exceeded"),
    ],
)
def test_campaign_budget_fails_closed(
    changes: dict[str, int], reason_code: str
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        CampaignBudget(
            experiment_budget=ExperimentBudget(
                candidate_limit=128,
                fold_run_limit=384,
            ),
            **changes,
        )

    assert exc_info.value.details["reason_code"] == reason_code


def test_campaign_budget_reuses_existing_candidate_and_fold_budget() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        CampaignBudget(
            experiment_budget=ExperimentBudget(
                candidate_limit=128,
                fold_run_limit=385,
            )
        )

    assert exc_info.value.details["reason_code"] == "campaign_budget_limit_exceeded"


@pytest.mark.parametrize(
    "limits",
    [
        SandboxResourceLimits(cpu_count=3),
        SandboxResourceLimits(memory_bytes=4 * 1024**3 + 1),
    ],
)
def test_campaign_budget_rejects_expanded_per_sandbox_authority(
    limits: SandboxResourceLimits,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        CampaignBudget(
            experiment_budget=ExperimentBudget(
                candidate_limit=128,
                fold_run_limit=384,
            ),
            sandbox_resource_limits=limits,
        )

    assert exc_info.value.details["reason_code"] == "campaign_budget_limit_exceeded"


@pytest.mark.parametrize("axis", tuple(SearchAxis))
def test_candidate_allows_exactly_one_registered_search_axis(axis: SearchAxis) -> None:
    candidate = _candidate(axis=axis)

    assert candidate.search_axis is axis
    assert candidate.candidate_hash == _candidate(axis=axis).candidate_hash


def test_candidate_rejects_code_hash_from_a_second_search_axis() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_candidate(), model_code_hash=_hash("b"))

    assert exc_info.value.details["reason_code"] == "multiple_campaign_search_axes"


def test_candidate_rejects_untyped_search_axis_with_domain_error() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(
            _candidate(),
            search_axis=cast("SearchAxis", "factor_code"),
        )

    assert exc_info.value.details["reason_code"] == "invalid_campaign_search_axis"


def test_manifest_rejects_candidate_from_a_different_search_axis() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_manifest(), search_axis=SearchAxis.PARAMETERS)

    assert exc_info.value.details["reason_code"] == "campaign_search_axis_mismatch"


def test_candidate_lineage_rejects_self_parent() -> None:
    candidate = _candidate()

    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(candidate, parent_candidate_id=candidate.candidate.candidate_id)

    assert exc_info.value.details["reason_code"] == "invalid_candidate_lineage"


def test_experiment_plan_hash_changes_with_pit_sensitive_protocol_input() -> None:
    plan = _plan()

    assert (
        plan.validation_protocol_hash
        != replace(
            plan,
            snapshot_id=SnapshotId("snapshot-revised"),
        ).validation_protocol_hash
    )
    assert (
        plan.validation_protocol_hash
        != replace(
            plan,
            embargo_sessions=3,
        ).validation_protocol_hash
    )


def test_evaluation_result_freezes_trusted_evidence_without_agent_fields() -> None:
    candidate = _candidate()
    result = EvaluationResult(
        candidate_id=candidate.candidate.candidate_id,
        candidate_hash=candidate.candidate_hash,
        validation_protocol_hash=_plan().validation_protocol_hash,
        evaluation_input_hash=_hash("3"),
        metrics_artifact_hash=_hash("4"),
        constraints_passed=True,
        significance_evidence_hash=_hash("5"),
        failure_classification=None,
        evidence_refs=(_hash("6"), _hash("7")),
    )

    assert result.evidence_refs == (_hash("6"), _hash("7"))
    assert not hasattr(result, "model_verdict")


def test_failed_evaluation_requires_a_failure_classification() -> None:
    candidate = _candidate()

    with pytest.raises(ExperimentSpecError) as exc_info:
        EvaluationResult(
            candidate_id=candidate.candidate.candidate_id,
            candidate_hash=candidate.candidate_hash,
            validation_protocol_hash=_plan().validation_protocol_hash,
            evaluation_input_hash=_hash("3"),
            metrics_artifact_hash=_hash("4"),
            constraints_passed=False,
            significance_evidence_hash=_hash("5"),
            failure_classification=None,
            evidence_refs=(_hash("6"),),
        )

    assert exc_info.value.details["reason_code"] == "invalid_evaluation_result"
