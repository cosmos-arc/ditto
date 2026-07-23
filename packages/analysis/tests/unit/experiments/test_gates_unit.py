"""Unit tests for the two-layer R3 promotion gate engine."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_analysis.experiments import (
    CandidateId,
    ContentHash,
    ExperimentId,
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.gates import (
    GATE_POLICY_VERSION,
    HARD_GATE_RULE_IDS,
    EvidenceGateInput,
    GateEvaluation,
    GateFact,
    GateLayer,
    GateOutcome,
    HardGateEvidence,
    evaluate_evidence_gates,
    evaluate_hard_gates,
    review_blocked_by_hard_gates,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)


def _objective() -> PromotionObjective:
    """Minimal valid pre-registered objective used by evidence-gate tests."""

    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=CandidateId("candidate-1"),
        economic_rationale="Capture durable returns after costs.",
        trial_family=TrialFamilyDeclaration(
            "family-1",
            (
                LogicalTrialIdentity(
                    ExperimentId("experiment-1"),
                    CandidateId("candidate-1"),
                    1,
                    ContentHash("a" * 64),
                    TrialKind.CURRENT,
                ),
            ),
        ),
    )


def _all_satisfied_evidence() -> HardGateEvidence:
    """Hard-gate evidence where every fact is explicitly satisfied."""

    satisfied = GateFact(True, "verified")
    return HardGateEvidence(
        certified_snapshot=satisfied,
        ninety_six_month=satisfied,
        pit_known_at=satisfied,
        split_purge_embargo=satisfied,
        reproduction=satisfied,
        cost_assumptions=satisfied,
        baseline_declared=satisfied,
        trial_declaration=satisfied,
        holdout_claim=satisfied,
        artifact_completeness=satisfied,
        r2_live_gate=satisfied,
    )


def test_gate_policy_version_is_pinned() -> None:
    assert GATE_POLICY_VERSION == "r3.v1"


def test_gate_outcome_has_four_explicit_values() -> None:
    assert set(GateOutcome) == {
        GateOutcome.PASS,
        GateOutcome.FAIL,
        GateOutcome.WARN,
        GateOutcome.NOT_EVALUATED,
    }


def test_hard_gate_rule_ids_are_stable_and_complete() -> None:
    assert HARD_GATE_RULE_IDS == (
        "certified_snapshot",
        "ninety_six_month_protocol",
        "pit_known_at",
        "split_purge_embargo",
        "reproduction_fingerprint",
        "cost_assumptions",
        "baseline_declared",
        "trial_declaration",
        "holdout_claim",
        "artifact_completeness",
        "r2_live_gate",
    )
    assert len(set(HARD_GATE_RULE_IDS)) == len(HARD_GATE_RULE_IDS)


def test_evaluate_hard_gates_returns_one_per_rule_in_order() -> None:
    evaluations = evaluate_hard_gates(_all_satisfied_evidence())

    assert tuple(item.rule_id for item in evaluations) == HARD_GATE_RULE_IDS
    assert all(item.layer == GateLayer.HARD for item in evaluations)
    assert all(item.outcome == GateOutcome.PASS for item in evaluations)


@pytest.mark.parametrize("rule_id", HARD_GATE_RULE_IDS)
def test_hard_gate_single_failure_blocks_review(rule_id: str) -> None:
    evidence = replace(
        _all_satisfied_evidence(),
        **{_field_for_rule(rule_id): GateFact(False, "broken")},
    )

    evaluations = evaluate_hard_gates(evidence)
    failed = next(item for item in evaluations if item.rule_id == rule_id)

    assert failed.outcome == GateOutcome.FAIL
    assert review_blocked_by_hard_gates(evaluations) is True


@pytest.mark.parametrize("rule_id", HARD_GATE_RULE_IDS)
def test_hard_gate_missing_evidence_does_not_implicitly_pass(rule_id: str) -> None:
    evidence = replace(
        _all_satisfied_evidence(),
        **{_field_for_rule(rule_id): GateFact(None, "not evaluated")},
    )

    evaluations = evaluate_hard_gates(evidence)
    unevaluated = next(item for item in evaluations if item.rule_id == rule_id)

    assert unevaluated.outcome == GateOutcome.NOT_EVALUATED
    assert review_blocked_by_hard_gates(evaluations) is True


def test_review_not_blocked_when_every_hard_gate_passes() -> None:
    evaluations = evaluate_hard_gates(_all_satisfied_evidence())

    assert review_blocked_by_hard_gates(evaluations) is False


def test_review_blocked_ignores_evidence_layer_failures() -> None:
    """Statistical evidence failures never block review on their own."""

    evidence_fail = EvidenceGateInput(
        objective=_objective(),
        metric_values={
            ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                ResearchMetricId.MAX_DRAWDOWN, -35.0
            ),
            ResearchMetricId.NET_RETURN: ResearchMetricValue(
                ResearchMetricId.NET_RETURN, 0.05
            ),
        },
    )
    evidence_evaluations = evaluate_evidence_gates(evidence_fail)

    assert any(item.outcome == GateOutcome.FAIL for item in evidence_evaluations)
    assert review_blocked_by_hard_gates(evidence_evaluations) is False


def test_evidence_constraint_passes_when_threshold_met() -> None:
    evaluations = evaluate_evidence_gates(
        EvidenceGateInput(
            objective=_objective(),
            metric_values={
                ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                    ResearchMetricId.MAX_DRAWDOWN, -15.0
                ),
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN, 0.08
                ),
            },
        )
    )
    constraint = _evidence_rule(evaluations, "objective_constraint:max_drawdown")

    assert constraint.outcome == GateOutcome.PASS
    assert constraint.layer == GateLayer.EVIDENCE


def test_evidence_constraint_fails_when_threshold_breached() -> None:
    evaluations = evaluate_evidence_gates(
        EvidenceGateInput(
            objective=_objective(),
            metric_values={
                ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                    ResearchMetricId.MAX_DRAWDOWN, -25.0
                ),
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN, 0.08
                ),
            },
        )
    )
    constraint = _evidence_rule(evaluations, "objective_constraint:max_drawdown")

    assert constraint.outcome == GateOutcome.FAIL


def test_evidence_constraint_is_not_evaluated_when_metric_missing() -> None:
    evaluations = evaluate_evidence_gates(
        EvidenceGateInput(
            objective=_objective(),
            metric_values={
                ResearchMetricId.NET_RETURN: ResearchMetricValue(
                    ResearchMetricId.NET_RETURN, 0.08
                ),
            },
        )
    )
    constraint = _evidence_rule(evaluations, "objective_constraint:max_drawdown")

    assert constraint.outcome == GateOutcome.NOT_EVALUATED


def test_evidence_primary_metric_is_not_evaluated_when_missing() -> None:
    evaluations = evaluate_evidence_gates(
        EvidenceGateInput(
            objective=_objective(),
            metric_values={
                ResearchMetricId.MAX_DRAWDOWN: ResearchMetricValue(
                    ResearchMetricId.MAX_DRAWDOWN, -15.0
                ),
            },
        )
    )
    primary = _evidence_rule(evaluations, "primary_objective_metric")

    assert primary.outcome == GateOutcome.NOT_EVALUATED


def test_evidence_gate_covers_every_declared_constraint() -> None:
    evaluations = evaluate_evidence_gates(
        EvidenceGateInput(objective=_objective(), metric_values={})
    )
    rule_ids = {item.rule_id for item in evaluations}

    assert "objective_constraint:max_drawdown" in rule_ids
    assert "primary_objective_metric" in rule_ids
    assert all(item.outcome == GateOutcome.NOT_EVALUATED for item in evaluations)


def _field_for_rule(rule_id: str) -> str:
    """Map a hard rule id back to its HardGateEvidence field name."""

    return _RULE_TO_FIELD[rule_id]


def _evidence_rule(
    evaluations: tuple[GateEvaluation, ...], rule_id: str
) -> GateEvaluation:
    return next(item for item in evaluations if item.rule_id == rule_id)


_RULE_TO_FIELD = {
    "certified_snapshot": "certified_snapshot",
    "ninety_six_month_protocol": "ninety_six_month",
    "pit_known_at": "pit_known_at",
    "split_purge_embargo": "split_purge_embargo",
    "reproduction_fingerprint": "reproduction",
    "cost_assumptions": "cost_assumptions",
    "baseline_declared": "baseline_declared",
    "trial_declaration": "trial_declaration",
    "holdout_claim": "holdout_claim",
    "artifact_completeness": "artifact_completeness",
    "r2_live_gate": "r2_live_gate",
}
