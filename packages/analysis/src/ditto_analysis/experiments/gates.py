"""
Two-layer governed gate policy engine for R3 promotion evidence.

The hard-correctness layer (design section 9.1) must explicitly pass before a
candidate can enter review; any failure or unevaluated fact blocks promotion.
The statistical-evidence layer (section 9.2) is display-only: it never auto-
decides promotion, and missing metrics surface as explicit ``not_evaluated``
rather than implicit passes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from ditto_analysis.experiments.metric_schema import (
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.promotion_models import (
    ConstraintOperator,
    MetricConstraint,
    PromotionObjective,
)

__all__ = [
    "GATE_POLICY_VERSION",
    "HARD_GATE_RULE_IDS",
    "EvidenceGateInput",
    "GateEvaluation",
    "GateFact",
    "GateLayer",
    "GateOutcome",
    "HardGateEvidence",
    "evaluate_evidence_gates",
    "evaluate_hard_gates",
    "review_blocked_by_hard_gates",
]

GATE_POLICY_VERSION = "r3.v1"


class GateOutcome(StrEnum):
    """Explicit evaluation outcomes; statistical evidence is never implicit."""

    PASS = "pass"  # noqa: S105 - gate outcome literal, not a credential
    FAIL = "fail"
    WARN = "warn"
    NOT_EVALUATED = "not_evaluated"


class GateLayer(StrEnum):
    """The two governed gate layers with distinct decision semantics."""

    HARD = "hard"
    EVIDENCE = "evidence"


# Stable, ordered hard-gate rule ids (design section 9.1).
_CERTIFIED_SNAPSHOT = "certified_snapshot"
_NINETY_SIX_MONTH = "ninety_six_month_protocol"
_PIT_KNOWN_AT = "pit_known_at"
_SPLIT_PURGE_EMBARGO = "split_purge_embargo"
_REPRODUCTION = "reproduction_fingerprint"
_COST_ASSUMPTIONS = "cost_assumptions"
_BASELINE_DECLARED = "baseline_declared"
_TRIAL_DECLARATION = "trial_declaration"
_HOLDOUT_CLAIM = "holdout_claim"
_ARTIFACT_COMPLETENESS = "artifact_completeness"
_R2_LIVE_GATE = "r2_live_gate"

HARD_GATE_RULE_IDS = (
    _CERTIFIED_SNAPSHOT,
    _NINETY_SIX_MONTH,
    _PIT_KNOWN_AT,
    _SPLIT_PURGE_EMBARGO,
    _REPRODUCTION,
    _COST_ASSUMPTIONS,
    _BASELINE_DECLARED,
    _TRIAL_DECLARATION,
    _HOLDOUT_CLAIM,
    _ARTIFACT_COMPLETENESS,
    _R2_LIVE_GATE,
)


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    """Domain result of one gate rule, free of persistence identity/time."""

    rule_id: str
    layer: GateLayer
    outcome: GateOutcome
    observed: object
    policy: object
    artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class GateFact:
    """One observed hard-gate fact: explicit satisfaction plus detail."""

    satisfied: bool | None
    detail: object = None


@dataclass(frozen=True, slots=True)
class HardGateEvidence:
    """Typed observed evidence for every hard-correctness gate."""

    certified_snapshot: GateFact
    ninety_six_month: GateFact
    pit_known_at: GateFact
    split_purge_embargo: GateFact
    reproduction: GateFact
    cost_assumptions: GateFact
    baseline_declared: GateFact
    trial_declaration: GateFact
    holdout_claim: GateFact
    artifact_completeness: GateFact
    r2_live_gate: GateFact


_HARD_POLICY: Mapping[str, object] = {"required": True}


def _hard_outcome(satisfied: bool | None) -> GateOutcome:
    if satisfied is True:
        return GateOutcome.PASS
    if satisfied is False:
        return GateOutcome.FAIL
    return GateOutcome.NOT_EVALUATED


def evaluate_hard_gates(evidence: HardGateEvidence) -> tuple[GateEvaluation, ...]:
    """Evaluate every hard-correctness gate against typed observed facts."""
    facts: tuple[tuple[str, GateFact], ...] = (
        (_CERTIFIED_SNAPSHOT, evidence.certified_snapshot),
        (_NINETY_SIX_MONTH, evidence.ninety_six_month),
        (_PIT_KNOWN_AT, evidence.pit_known_at),
        (_SPLIT_PURGE_EMBARGO, evidence.split_purge_embargo),
        (_REPRODUCTION, evidence.reproduction),
        (_COST_ASSUMPTIONS, evidence.cost_assumptions),
        (_BASELINE_DECLARED, evidence.baseline_declared),
        (_TRIAL_DECLARATION, evidence.trial_declaration),
        (_HOLDOUT_CLAIM, evidence.holdout_claim),
        (_ARTIFACT_COMPLETENESS, evidence.artifact_completeness),
        (_R2_LIVE_GATE, evidence.r2_live_gate),
    )
    return tuple(
        GateEvaluation(
            rule_id=rule_id,
            layer=GateLayer.HARD,
            outcome=_hard_outcome(fact.satisfied),
            observed=fact.detail,
            policy=_HARD_POLICY,
        )
        for rule_id, fact in facts
    )


def review_blocked_by_hard_gates(
    evaluations: Sequence[GateEvaluation],
) -> bool:
    """
    True iff any hard gate is not an explicit pass.

    Hard gates cannot be satisfied implicitly: a ``fail`` or ``not_evaluated``
    outcome blocks review. Evidence-layer outcomes are ignored here.
    """
    return any(
        item.layer == GateLayer.HARD and item.outcome != GateOutcome.PASS
        for item in evaluations
    )


@dataclass(frozen=True, slots=True)
class EvidenceGateInput:
    """Pre-registered objective plus observed metric values."""

    objective: PromotionObjective
    metric_values: Mapping[ResearchMetricId, ResearchMetricValue]


def _constraint_satisfied(
    constraint: MetricConstraint,
    value: ResearchMetricValue,
) -> bool:
    observed = value.value
    threshold = constraint.threshold.value
    if constraint.operator is ConstraintOperator.GREATER_THAN_OR_EQUAL:
        return observed >= threshold
    return observed <= threshold


def evaluate_evidence_gates(
    gate_input: EvidenceGateInput,
) -> tuple[GateEvaluation, ...]:
    """
    Evaluate objective constraints and primary metric for display.

    Statistical evidence is never auto-decisive (section 9.2); missing metrics
    surface as explicit ``not_evaluated`` rather than implicit passes.
    """
    objective = gate_input.objective
    values = gate_input.metric_values
    evaluations: list[GateEvaluation] = []
    for constraint in objective.hard_constraints:
        metric_id = constraint.metric_id
        policy: dict[str, object] = {
            "metric_id": metric_id.value,
            "threshold": constraint.threshold.value,
            "operator": constraint.operator.value,
        }
        observed_value = values.get(metric_id)
        if observed_value is None:
            outcome = GateOutcome.NOT_EVALUATED
            observed: object = None
        elif _constraint_satisfied(constraint, observed_value):
            outcome = GateOutcome.PASS
            observed = observed_value.value
        else:
            outcome = GateOutcome.FAIL
            observed = observed_value.value
        evaluations.append(
            GateEvaluation(
                rule_id=f"objective_constraint:{metric_id.value}",
                layer=GateLayer.EVIDENCE,
                outcome=outcome,
                observed=observed,
                policy=policy,
            )
        )
    primary_id = objective.primary.metric_id
    primary_value = values.get(primary_id)
    evaluations.append(
        GateEvaluation(
            rule_id="primary_objective_metric",
            layer=GateLayer.EVIDENCE,
            outcome=(
                GateOutcome.PASS
                if primary_value is not None
                else GateOutcome.NOT_EVALUATED
            ),
            observed=None if primary_value is None else primary_value.value,
            policy={
                "metric_id": primary_id.value,
                "direction": objective.primary.direction.value,
            },
        )
    )
    return tuple(evaluations)
