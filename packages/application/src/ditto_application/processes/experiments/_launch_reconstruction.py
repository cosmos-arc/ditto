"""Strict reconstruction of every prepared launch row before the first write."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from ditto_analysis.experiments import (
    CandidateId,
    CandidateSpec,
    ContentHash,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldRole,
    GateEvaluationRecord,
    ResearchCycleIdentity,
)

from ditto_application.processes.experiments._preflight_codec import (
    DecodedPreflightReport,
    decode_preflight_report,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)

__all__ = ["validate_prepared_launch_rows"]

_PREFLIGHT_POLICY_VERSION = "r3-experiment-preflight-v1"


class _PreparedExperimentLaunch(Protocol):
    """Read-only neutral view consumed by strict row reconstruction."""

    @property
    def cycle(self) -> ResearchCycleIdentity: ...

    @property
    def spec(self) -> ExperimentLaunchSpec: ...

    @property
    def initial_record(self) -> ExperimentRecord: ...

    @property
    def gates(self) -> tuple[GateEvaluationRecord, ...]: ...

    @property
    def folds(self) -> tuple[FoldPersistenceSpec, ...]: ...

    @property
    def gate_payload_hashes(self) -> tuple[ContentHash, ...]: ...

    @property
    def fold_payload_hashes(self) -> tuple[ContentHash, ...]: ...


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise experiment_process_error(f"{field_name} must be an object")
    return dict(cast("Mapping[str, object]", value))


def _expected_candidates(
    prepared: _PreparedExperimentLaunch,
    decoded: DecodedPreflightReport,
) -> tuple[CandidateSpec, ...]:
    experiment_id = prepared.spec.experiment_id
    return tuple(
        CandidateSpec(
            candidate_id=CandidateId(
                ":".join(
                    (
                        str(experiment_id),
                        "candidate",
                        str(candidate.ordinal),
                        candidate.candidate_hash,
                    )
                )
            ),
            ordinal=candidate.ordinal,
            is_baseline=candidate.role.value == "baseline",
            parameters=candidate.persistence_parameters,
        )
        for candidate in decoded.work_plan.candidate_matrix.candidates
    )


def _expected_folds(
    prepared: _PreparedExperimentLaunch,
    decoded: DecodedPreflightReport,
    candidates: tuple[CandidateSpec, ...],
) -> tuple[FoldPersistenceSpec, ...]:
    experiment_id = prepared.spec.experiment_id
    validation = decoded.validation_plan
    regular = tuple(
        FoldPersistenceSpec.create(
            key=FoldKey(
                experiment_id,
                candidate.candidate_id,
                FoldId(f"r3-fold-{fold.ordinal}-{fold.role.value}"),
            ),
            ordinal=fold.ordinal,
            fold_role=fold.role,
            train_window=fold.train_window,
            test_window=fold.test_window,
            purge_sessions=fold.purge_sessions,
            embargo_sessions=fold.embargo_sessions,
        )
        for candidate in candidates
        for fold in validation.folds
    )
    holdout = validation.reserved_holdout
    if holdout is None:
        return regular
    holdout_ordinal = len(validation.folds) + 1
    return regular + tuple(
        FoldPersistenceSpec.create(
            key=FoldKey(
                experiment_id,
                candidate.candidate_id,
                FoldId(f"r3-fold-{holdout_ordinal}-holdout"),
            ),
            ordinal=holdout_ordinal,
            fold_role=FoldRole.HOLDOUT,
            train_window=holdout.train_window,
            test_window=holdout.test_window,
            purge_sessions=holdout.purge_sessions,
            embargo_sessions=holdout.embargo_sessions,
        )
        for candidate in candidates
    )


def _validate_spec(
    prepared: _PreparedExperimentLaunch,
    decoded: DecodedPreflightReport,
    preflight: Mapping[str, object],
    candidates: tuple[CandidateSpec, ...],
) -> None:
    identities = _mapping(preflight.get("identities"), "identities")
    executor = _mapping(preflight.get("executor"), "executor")
    validation = _mapping(preflight.get("validation"), "validation")
    protocol = _mapping(validation.get("protocol"), "validation.protocol")
    fold_protocol = _mapping(
        validation.get("fold_protocol"),
        "validation.fold_protocol",
    )
    certification = _mapping(
        identities.get("certification"),
        "identities.certification",
    )
    snapshot = _mapping(
        certification.get("snapshot_evidence"),
        "identities.certification.snapshot_evidence",
    )
    work = decoded.work_plan
    spec = prepared.spec
    if (
        spec.experiment_id != ExperimentId(str(prepared.initial_record.experiment_id))
        or spec.candidates != candidates
        or str(spec.strategy_version)
        != f"{identities.get('strategy_id')}@{identities.get('strategy_version')}"
        or str(spec.strategy_spec_hash) != executor.get("strategy_spec_hash")
        or str(spec.snapshot_id) != snapshot.get("snapshot_id")
        or spec.fold_protocol.protocol_id != fold_protocol.get("protocol_id")
        or spec.fold_protocol.protocol_version != fold_protocol.get("protocol_version")
        or str(spec.fold_protocol.protocol_hash) != fold_protocol.get("protocol_hash")
        or protocol.get("planning_decision_date") != spec.created_at.date().isoformat()
        or spec.seed != work.seed
        or spec.worker_count != work.worker_count
        or spec.failure_policy is not work.failure_policy
        or spec.budget.candidate_limit != work.budget.candidate_limit
        or spec.budget.fold_run_limit != work.budget.fold_run_limit
        or spec.desired_state is not ExperimentDesiredState.RUN
        or prepared.cycle.cycle_id != identities.get("research_cycle_id")
        or str(prepared.cycle.cycle_hash) != identities.get("research_cycle_hash")
    ):
        raise experiment_process_error(
            "launch spec does not match reconstructed preflight"
        )


def _validate_gates(
    prepared: _PreparedExperimentLaunch,
    decoded: DecodedPreflightReport,
) -> None:
    expected = tuple(
        GateEvaluationRecord(
            evaluation_id=(
                f"{prepared.spec.experiment_id}:preflight:{index}:{check.rule_id}"
            ),
            experiment_id=prepared.spec.experiment_id,
            candidate_id=None,
            fold_id=None,
            attempt_id=None,
            rule_id=check.rule_id,
            policy_version=_PREFLIGHT_POLICY_VERSION,
            layer="hard",
            outcome=check.outcome.value,
            observed=check.observed,
            policy=check.policy,
            artifact_id=None,
            evaluated_at=prepared.spec.created_at,
        )
        for index, check in enumerate(decoded.checks, start=1)
    )
    rows_match = len(prepared.gates) == len(expected) and all(
        actual.evaluation_id == rebuilt.evaluation_id
        and actual.experiment_id == rebuilt.experiment_id
        and actual.candidate_id is None
        and actual.fold_id is None
        and actual.attempt_id is None
        and actual.rule_id == rebuilt.rule_id
        and actual.policy_version == rebuilt.policy_version
        and actual.layer == rebuilt.layer
        and actual.outcome == rebuilt.outcome
        and actual.artifact_id is None
        and actual.evaluated_at == rebuilt.evaluated_at
        and actual.payload_hash == rebuilt.payload_hash
        for actual, rebuilt in zip(prepared.gates, expected, strict=True)
    )
    if (
        not rows_match
        or tuple(item.payload_hash for item in expected) != prepared.gate_payload_hashes
    ):
        raise experiment_process_error(
            "prepared gates do not match reconstructed preflight checks"
        )


def validate_prepared_launch_rows(
    prepared: _PreparedExperimentLaunch,
    enqueue_detail: Mapping[str, object],
) -> None:
    """Decode strict evidence and require exact spec, gate, and fold row parity."""
    decoded = decode_preflight_report(
        enqueue_detail,
        expected_policy_version=_PREFLIGHT_POLICY_VERSION,
    )
    preflight = _mapping(enqueue_detail.get("preflight"), "detail.preflight")
    candidates = _expected_candidates(prepared, decoded)
    _validate_spec(prepared, decoded, preflight, candidates)
    _validate_gates(prepared, decoded)
    expected_folds = _expected_folds(prepared, decoded, candidates)
    if (
        len(expected_folds) != decoded.planned_fold_count
        or prepared.folds != expected_folds
        or tuple(item.payload_hash for item in expected_folds)
        != prepared.fold_payload_hashes
    ):
        raise experiment_process_error(
            "prepared folds do not match reconstructed validation rows"
        )
