"""Neutral request and preflight contracts for R3 experiment planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ditto_analysis.errors import AnalysisError
from ditto_analysis.experiments import (
    CandidateId,
    CandidateSpec,
    ExperimentFailurePolicy,
    ExperimentId,
)
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.promotion_objective import (
    decode_promotion_objective,
    promotion_objective_payload,
    validate_promotion_objective_graph,
)
from ditto_analysis.experiments.trial_family import (
    LogicalTrialIdentity,
    TrialFamilyDeclaration,
    TrialKind,
)
from ditto_analysis.experiments.trial_ledger import PromotionObjective
from ditto_backtest.context_inputs import ReplayContextInputRef
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.planning import (
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ResourceCostModel,
    expand_candidate_matrix,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolRequest,
    compile_validation_protocol,
)

__all__ = [
    "ExperimentPlanningRequest",
    "ExperimentPreflightCheck",
    "PreflightOutcome",
    "declare_trial_family",
    "decode_canonical_promotion_objective",
    "decode_experiment_failure_policy",
    "derive_canonical_research_cycle_hash",
    "seal_promotion_objective",
]


def _planning_contract_error(
    message: str,
    *,
    reason: str,
) -> AppProcessError:
    return AppProcessError(
        message,
        details={"code": "SPEC_INVALID", "reason": reason},
    )


def decode_canonical_promotion_objective(value: object) -> PromotionObjective:
    """Decode one exact versioned objective payload into a detached graph."""
    try:
        return decode_promotion_objective(value)
    except AnalysisError as exc:
        raise _planning_contract_error(
            "planning request has no canonical promotion objective",
            reason="invalid_promotion_objective_payload",
        ) from exc


def decode_experiment_failure_policy(value: object) -> ExperimentFailurePolicy:
    """Decode one exact failure-policy string without accepting coercion."""
    if type(value) is not str:
        raise _planning_contract_error(
            "planning request has no canonical failure policy",
            reason="invalid_experiment_failure_policy",
        )
    try:
        return ExperimentFailurePolicy(value)
    except ValueError as exc:
        raise _planning_contract_error(
            "planning request has no canonical failure policy",
            reason="invalid_experiment_failure_policy",
        ) from exc


def derive_canonical_research_cycle_hash(
    *,
    strategy_family_id: str,
    validation_request: ValidationProtocolRequest,
) -> str:
    """Derive the cycle hash from the validated reserved-holdout authority."""
    try:
        validation_plan = compile_validation_protocol(validation_request)
    except AppProcessError as exc:
        raise _planning_contract_error(
            "planning request has no canonical research-cycle authority",
            reason="invalid_research_cycle_authority",
        ) from exc
    holdout = validation_plan.reserved_holdout
    if holdout is None:
        raise _planning_contract_error(
            "planning request has no reserved holdout authority",
            reason="research_cycle_requires_reserved_holdout",
        )
    try:
        return str(
            canonical_research_cycle_hash(
                strategy_family_id=strategy_family_id,
                certified_data_cutoff=holdout.test_window.end,
                oos_window=holdout.test_window,
            )
        )
    except AnalysisError as exc:
        raise _planning_contract_error(
            "planning request has no canonical research-cycle authority",
            reason="invalid_research_cycle_authority",
        ) from exc


def declare_trial_family(
    *,
    experiment_id: str,
    matrix_spec: CandidateMatrixSpec,
    family_id: str,
    prior_members: Sequence[LogicalTrialIdentity] = (),
) -> TrialFamilyDeclaration:
    """Derive exact current logical trials from a canonical executable matrix."""
    plan = expand_candidate_matrix(matrix_spec)
    origin = ExperimentId(experiment_id)
    current_members: list[LogicalTrialIdentity] = []
    for candidate in plan.candidates:
        candidate_id = CandidateId(
            f"{experiment_id}:candidate:{candidate.ordinal}:{candidate.candidate_hash}"
        )
        spec = CandidateSpec(
            candidate_id=candidate_id,
            ordinal=candidate.ordinal,
            is_baseline=candidate.role.value == "baseline",
            parameters=candidate.persistence_parameters,
        )
        current_members.append(
            LogicalTrialIdentity(
                origin,
                candidate_id,
                candidate.ordinal,
                spec.parameter_hash,
                TrialKind.CURRENT,
            )
        )
    return TrialFamilyDeclaration(
        family_id,
        (*tuple(prior_members), *current_members),
    )


class PreflightOutcome(StrEnum):
    """Stable three-way outcome for one preflight rule."""

    PASS = "pass"  # noqa: S105 - policy outcome, not a credential
    FAIL = "fail"
    WARN = "warn"


@dataclass(frozen=True, slots=True)
class ExperimentPreflightCheck:
    """One deterministic pass/fail/warn result with remediation."""

    rule_id: str
    outcome: PreflightOutcome
    code: str | None
    reason: str | None
    remediation: str | None
    observed: Mapping[str, object]
    policy: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ExperimentPlanningRequest:
    """Frozen identities and pure inputs used by preflight and launch replay."""

    experiment_id: str
    research_cycle_id: str
    research_cycle_hash: str
    strategy_record: StrategySpecRecord
    snapshot_identity: ExperimentSnapshotIdentity
    validation_request: ValidationProtocolRequest
    matrix_spec: CandidateMatrixSpec
    promotion_objective: PromotionObjective
    dataset_requirements: tuple[ResearchDatasetRequirement, ...]
    cost_model: ResourceCostModel
    budget: ExperimentBudgetSpec
    seed: int
    worker_count: int
    failure_policy: ExperimentFailurePolicy
    created_at: datetime
    context_input_refs: tuple[ReplayContextInputRef, ...] = ()


def seal_promotion_objective(
    value: object,
) -> tuple[PromotionObjective, Mapping[str, object]]:
    """Detach and canonically project an untrusted objective request graph."""
    try:
        objective = validate_promotion_objective_graph(value)
        payload = promotion_objective_payload(objective)
    except AnalysisError as exc:
        raise AppProcessError(
            "planning request has no stable canonical objective",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_promotion_objective_graph",
            },
        ) from exc
    return objective, payload
