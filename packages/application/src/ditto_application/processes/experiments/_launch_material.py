"""Compile an exact, content-addressed experiment launch aggregate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

import orjson
from ditto_analysis.experiments import (
    CandidateExecutionBinding,
    CandidateId,
    CandidateSpec,
    CanonicalPayload,
    ContentHash,
    DateWindow,
    ExperimentBudget,
    ExperimentDesiredState,
    ExperimentId,
    ExperimentLaunchSpec,
    ExperimentRecord,
    ExperimentStage,
    ExperimentStatus,
    FoldId,
    FoldKey,
    FoldPersistenceSpec,
    FoldProtocolSpec,
    FoldRole,
    GateEvaluationRecord,
    ResearchCycleIdentity,
    SnapshotId,
    StrategyVersion,
    canonical_payload,
    encode_launch_spec,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._baseline_runtime_evidence import (
    baseline_runtime_payload,
)
from ditto_application.processes.experiments._creation_identity import (
    compile_creation_identity,
)
from ditto_application.processes.experiments._launch_saga import (
    PreparedExperimentLaunch,
)
from ditto_application.processes.experiments._planning_request_identity import (
    planning_request_hash,
)
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    BinderCandidatePlan,
    CandidateMatrixSpec,
    ExperimentWorkPlan,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    ExperimentPreflightCheck,
)
from ditto_application.processes.experiments.planning_probes import (
    ResearchCertificationResult,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolPlan,
    ValidationProtocolRequest,
    canonical_validation_protocol_hash,
    canonical_validation_protocol_payload,
)

__all__ = ["LaunchMaterialInput", "compile_launch_material"]

_MAX_ENQUEUE_DETAIL_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class LaunchMaterialInput:
    """Complete validated inputs and policy identities for launch compilation."""

    request: ExperimentPlanningRequest
    validation: ValidationProtocolPlan
    work: ExperimentWorkPlan
    executor: ResearchExecutorProbeResult
    certification: ResearchCertificationResult
    authority: ResearchValidationAuthorityEvidence
    checks: tuple[ExperimentPreflightCheck, ...]
    preflight_policy_version: str
    fold_protocol_id: str
    fold_protocol_version: int
    fold_id_prefix: str


def _certification_bounds(material: LaunchMaterialInput) -> tuple[str, str]:
    protocol = material.authority.protocol
    holdout = material.validation.reserved_holdout
    if holdout is None:
        raise AssertionError("launch material requires a reserved holdout")
    return (
        protocol.required_input_start.isoformat(),
        holdout.test_window.end.isoformat(),
    )


def _snapshot_payload(value: ResearchSnapshotEvidence) -> Mapping[str, object]:
    return {
        "snapshot_id": value.snapshot_id,
        "dataset_id": value.dataset_id,
        "manifest_hash": value.manifest_hash,
        "source_snapshot_ids": list(value.source_snapshot_ids),
        "snapshot_start": value.snapshot_start.isoformat(),
        "snapshot_end": value.snapshot_end.isoformat(),
        "known_at_policy": value.known_at_policy,
        "builder_version": value.builder_version,
    }


def _protocol_payload(protocol: ValidationProtocolRequest) -> Mapping[str, object]:
    return canonical_validation_protocol_payload(protocol)


def _window_payload(window: DateWindow) -> Mapping[str, object]:
    return {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
    }


def _validation_plan_payload(plan: ValidationProtocolPlan) -> Mapping[str, object]:
    holdout = plan.reserved_holdout
    return {
        "eligibility": plan.eligibility.value,
        "reason_codes": [reason.value for reason in plan.reason_codes],
        "coverage_policy": {
            "policy_id": plan.coverage_policy.policy_id,
            "version": plan.coverage_policy.version,
            "min_eligible_instrument_count": (
                plan.coverage_policy.min_eligible_instrument_count
            ),
            "min_coverage_ratio_bps": plan.coverage_policy.min_coverage_ratio_bps,
            "evaluator_hash": plan.coverage_policy.evaluator_hash,
        },
        "calendar_complete_month_count": plan.calendar_complete_month_count,
        "eligible_months": [str(month) for month in plan.eligible_months],
        "isolation_width_sessions": plan.isolation_width_sessions,
        "folds": [
            {
                "ordinal": fold.ordinal,
                "role": fold.role.value,
                "train_window": (
                    None
                    if fold.train_window is None
                    else _window_payload(fold.train_window)
                ),
                "test_window": _window_payload(fold.test_window),
                "purge_sessions": fold.purge_sessions,
                "embargo_sessions": fold.embargo_sessions,
            }
            for fold in plan.folds
        ],
        "reserved_holdout": (
            None
            if holdout is None
            else {
                "train_window": _window_payload(holdout.train_window),
                "test_window": _window_payload(holdout.test_window),
                "purge_sessions": holdout.purge_sessions,
                "embargo_sessions": holdout.embargo_sessions,
            }
        ),
    }


def _parameter_type(value: object) -> str:
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    if type(value) is float:
        return "float"
    return "string"


def _candidate_payload(
    candidate: BaselineCandidatePlan | BinderCandidatePlan,
) -> Mapping[str, object]:
    if isinstance(candidate, BaselineCandidatePlan):
        return {
            "ordinal": candidate.ordinal,
            "role": candidate.role.value,
            "candidate_hash": candidate.candidate_hash,
            "baseline_descriptor": {
                "descriptor_type": candidate.descriptor.descriptor_type,
                "payload": candidate.descriptor.payload,
                "schema_version": candidate.descriptor.schema_version,
            },
            "parameters": [],
        }
    return {
        "ordinal": candidate.ordinal,
        "role": candidate.role.value,
        "candidate_hash": candidate.candidate_hash,
        "baseline_descriptor": None,
        "parameters": [
            {
                "path": parameter.path,
                "type": _parameter_type(parameter.value),
                "value": parameter.value,
            }
            for parameter in candidate.binder_parameters
        ],
    }


def _matrix_spec_payload(matrix: CandidateMatrixSpec) -> Mapping[str, object]:
    return {
        "baseline": {
            "descriptor_type": matrix.baseline.descriptor_type,
            "payload": matrix.baseline.payload,
            "schema_version": matrix.baseline.schema_version,
        },
        "axes": [
            {
                "name": axis.name,
                "values": [
                    {"type": _parameter_type(value), "value": value}
                    for value in axis.values
                ],
            }
            for axis in matrix.axes
        ],
        "candidate_limit": matrix.candidate_limit,
    }


def _work_payload(
    work: ExperimentWorkPlan,
    matrix_spec: CandidateMatrixSpec,
) -> Mapping[str, object]:
    estimate = work.estimate
    return {
        "plan_hash": work.plan_hash,
        "track": work.track.value,
        "seed": work.seed,
        "worker_count": work.worker_count,
        "failure_policy": work.failure_policy.value,
        "workload": {
            "fold_session_counts": list(work.workload.fold_session_counts),
            "holdout_session_count": work.workload.holdout_session_count,
        },
        "cost_model": {
            "bytes_per_run": work.cost_model.bytes_per_run,
            "bytes_per_trading_session": work.cost_model.bytes_per_trading_session,
        },
        "budget": {
            "candidate_limit": work.budget.candidate_limit,
            "fold_run_limit": work.budget.fold_run_limit,
            "trading_session_limit": work.budget.trading_session_limit,
            "disk_byte_limit": work.budget.disk_byte_limit,
        },
        "estimate": {
            "candidate_count": estimate.candidate_count,
            "validation_run_count": estimate.validation_run_count,
            "holdout_run_count": estimate.holdout_run_count,
            "total_run_count": estimate.total_run_count,
            "estimated_trading_sessions": estimate.estimated_trading_sessions,
            "estimated_disk_bytes": estimate.estimated_disk_bytes,
        },
        "candidate_matrix": {
            "candidate_limit": work.candidate_matrix.candidate_limit,
            "matrix_hash": work.candidate_matrix.matrix_hash,
            "candidates": [
                _candidate_payload(candidate)
                for candidate in work.candidate_matrix.candidates
            ],
        },
        "matrix_spec": _matrix_spec_payload(matrix_spec),
    }


def _executor_payload(result: ResearchExecutorProbeResult) -> Mapping[str, object]:
    runtime = result.runtime_validation_evidence
    return {
        "available": result.available,
        "code": result.code,
        "reason": result.reason,
        "remediation": result.remediation,
        "strategy_spec_hash": result.strategy_spec_hash,
        "node_registry_manifest_hash": result.node_registry_manifest_hash,
        "factor_registry_manifest_hash": result.factor_registry_manifest_hash,
        "factor_binding_hashes": list(result.factor_binding_hashes),
        "baseline_ref": result.baseline_ref,
        "baseline_descriptor_hash": result.baseline_descriptor_hash,
        "baseline_registry_manifest_hash": result.baseline_registry_manifest_hash,
        "baseline_exact_strategy_hash": result.baseline_exact_strategy_hash,
        "baseline_runtime": baseline_runtime_payload(result.baseline_runtime),
        "required_datasets": list(result.required_datasets),
        "candidates": [
            {
                "candidate_hash": candidate.candidate_hash,
                "resolved_spec_hash": candidate.resolved_spec_hash,
                "parameter_hash": candidate.parameter_hash,
                "pipeline_execution_hash": candidate.pipeline_execution_hash,
                "compiled_factor_set_hash": candidate.compiled_factor_set_hash,
            }
            for candidate in result.candidates
        ],
        "runtime_validation_evidence": (
            None if runtime is None else runtime.as_payload()
        ),
    }


def _authority_payload(
    authority: ResearchValidationAuthorityEvidence,
    protocol_hash: str,
) -> Mapping[str, object]:
    return {
        "payload_hash": authority.payload_hash,
        "runtime_evidence_hash": authority.runtime_evidence_hash,
        "universe_membership_hash": authority.universe_membership_hash,
        "membership_projection_hash": authority.membership_projection_hash,
        "requires_pit_universe": authority.requires_pit_universe,
        "snapshot_identity": {
            "snapshot_id": authority.snapshot_identity.snapshot_id,
            "manifest_hash": authority.snapshot_identity.manifest_hash,
        },
        "dataset_bindings": [
            binding.as_payload() for binding in authority.dataset_bindings
        ],
        "protocol_hash": protocol_hash,
        "summaries": authority.summaries,
    }


def _check_payload(check: ExperimentPreflightCheck) -> Mapping[str, object]:
    return {
        "rule_id": check.rule_id,
        "outcome": check.outcome.value,
        "code": check.code,
        "reason": check.reason,
        "remediation": check.remediation,
        "observed": check.observed,
        "policy": check.policy,
    }


def _freeze_decoded_json(value: object) -> object:
    if type(value) is dict:
        mapping = cast("dict[str, object]", value)
        return MappingProxyType(
            {key: _freeze_decoded_json(item) for key, item in mapping.items()}
        )
    if type(value) is list:
        return tuple(_freeze_decoded_json(item) for item in cast("list[object]", value))
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise AssertionError("canonical JSON unexpectedly decoded an unsupported value")


def _canonical_frozen_mapping(
    value: Mapping[str, object],
) -> tuple[Mapping[str, object], CanonicalPayload]:
    encoded = canonical_payload(value)
    decoded = cast("object", orjson.loads(encoded.json_bytes))
    frozen = _freeze_decoded_json(decoded)
    if not isinstance(frozen, Mapping):
        raise AssertionError("canonical mapping unexpectedly decoded as a scalar")
    return cast("Mapping[str, object]", frozen), encoded


def _preflight_payload(
    *,
    material: LaunchMaterialInput,
    spec: ExperimentLaunchSpec,
) -> Mapping[str, object]:
    validation = material.validation
    work = material.work
    authority = material.authority
    executor = material.executor
    certification = material.certification
    snapshot = certification.snapshot_evidence
    if snapshot is None:
        raise AssertionError("launch material requires certified snapshot evidence")
    request = material.request
    request_hash = planning_request_hash(request)
    protocol_payload = _protocol_payload(authority.protocol)
    protocol_hash = canonical_validation_protocol_hash(authority.protocol)
    certification_required_from, certification_required_to = _certification_bounds(
        material
    )
    return {
        "schema_version": 1,
        "policy_version": material.preflight_policy_version,
        "status": "ready" if validation.promotion_eligible else "research_only",
        "checks": [_check_payload(check) for check in material.checks],
        "counts": {
            "candidate_count": work.candidate_matrix.candidate_count,
            "planned_fold_count": (
                work.candidate_matrix.candidate_count
                * (len(validation.folds) + (validation.reserved_holdout is not None))
            ),
            "budget_run_count": work.estimate.total_run_count,
            "estimated_trading_sessions": work.estimate.estimated_trading_sessions,
            "estimated_disk_bytes": work.estimate.estimated_disk_bytes,
            "eligible_month_count": len(validation.eligible_months),
            "isolation_width_sessions": validation.isolation_width_sessions,
        },
        "validation": {
            "protocol": protocol_payload,
            "plan": _validation_plan_payload(validation),
            "fold_protocol": {
                "protocol_id": spec.fold_protocol.protocol_id,
                "protocol_version": spec.fold_protocol.protocol_version,
                "protocol_hash": str(spec.fold_protocol.protocol_hash),
            },
        },
        "work": _work_payload(work, request.matrix_spec),
        "executor": _executor_payload(executor),
        "authority": _authority_payload(authority, protocol_hash),
        "identities": {
            "request_hash": request_hash,
            "research_cycle_id": request.research_cycle_id,
            "research_cycle_hash": request.research_cycle_hash,
            "strategy_id": request.strategy_record.strategy_id,
            "strategy_version": request.strategy_record.version,
            "snapshot_identity": {
                "snapshot_id": request.snapshot_identity.snapshot_id,
                "manifest_hash": request.snapshot_identity.manifest_hash,
            },
            "dataset_requirements": [
                item.as_payload() for item in request.dataset_requirements
            ],
            "certification": {
                "ready": certification.ready,
                "profile": certification.profile,
                "required_from": certification_required_from,
                "required_to": certification_required_to,
                "dataset_ids": list(certification.dataset_ids),
                "report_ids": list(certification.report_ids),
                "reason_codes": list(certification.reason_codes),
                "snapshot_evidence": _snapshot_payload(snapshot),
            },
        },
    }


def _frozen_gate(
    *,
    request: ExperimentPlanningRequest,
    check: ExperimentPreflightCheck,
    index: int,
    policy_version: str,
) -> GateEvaluationRecord:
    observed, _ = _canonical_frozen_mapping(check.observed)
    policy, _ = _canonical_frozen_mapping(check.policy)
    return GateEvaluationRecord(
        evaluation_id=f"{request.experiment_id}:preflight:{index}:{check.rule_id}",
        experiment_id=ExperimentId(request.experiment_id),
        candidate_id=None,
        fold_id=None,
        attempt_id=None,
        rule_id=check.rule_id,
        policy_version=policy_version,
        layer="hard",
        outcome=check.outcome.value,
        observed=observed,
        policy=policy,
        artifact_id=None,
        evaluated_at=request.created_at,
    )


def _plan_preimage(
    *,
    material: LaunchMaterialInput,
    spec_payload: CanonicalPayload,
    gates: tuple[GateEvaluationRecord, ...],
    folds: tuple[FoldPersistenceSpec, ...],
    snapshot: ResearchSnapshotEvidence,
    validation_payload: Mapping[str, object],
    preflight_hash: ContentHash,
) -> Mapping[str, object]:
    request = material.request
    authority = material.authority
    executor = material.executor
    certification = material.certification
    certification_required_from, certification_required_to = _certification_bounds(
        material
    )
    request_hash = planning_request_hash(request)
    return {
        "schema_version": 1,
        "launch_spec_hash": str(spec_payload.content_hash),
        "gate_payload_hashes": [str(gate.payload_hash) for gate in gates],
        "fold_payload_hashes": [str(fold.payload_hash) for fold in folds],
        "research_cycle_id": request.research_cycle_id,
        "research_cycle_hash": request.research_cycle_hash,
        "request_hash": request_hash,
        "snapshot_evidence": _snapshot_payload(snapshot),
        "dataset_requirements": [
            item.as_payload() for item in request.dataset_requirements
        ],
        "validation": validation_payload,
        "validation_authority": {
            "payload_hash": authority.payload_hash,
            "runtime_evidence_hash": authority.runtime_evidence_hash,
            "universe_membership_hash": authority.universe_membership_hash,
            "membership_projection_hash": authority.membership_projection_hash,
            "requires_pit_universe": authority.requires_pit_universe,
            "dataset_bindings": [
                binding.as_payload() for binding in authority.dataset_bindings
            ],
        },
        "work_plan_hash": material.work.plan_hash,
        "node_registry_manifest_hash": executor.node_registry_manifest_hash,
        "factor_registry_manifest_hash": executor.factor_registry_manifest_hash,
        "factor_binding_hashes": list(executor.factor_binding_hashes),
        "baseline_ref": executor.baseline_ref,
        "baseline_descriptor_hash": executor.baseline_descriptor_hash,
        "baseline_registry_manifest_hash": executor.baseline_registry_manifest_hash,
        "baseline_exact_strategy_hash": executor.baseline_exact_strategy_hash,
        "baseline_runtime": baseline_runtime_payload(executor.baseline_runtime),
        "executor_candidates": [
            {
                "candidate_hash": item.candidate_hash,
                "resolved_spec_hash": item.resolved_spec_hash,
                "parameter_hash": item.parameter_hash,
                "pipeline_execution_hash": item.pipeline_execution_hash,
                "compiled_factor_set_hash": item.compiled_factor_set_hash,
            }
            for item in executor.candidates
        ],
        "certification": {
            "profile": certification.profile,
            "required_from": certification_required_from,
            "required_to": certification_required_to,
            "report_ids": list(certification.report_ids),
            "reason_codes": list(certification.reason_codes),
        },
        "preflight_hash": str(preflight_hash),
    }


def compile_launch_material(
    material: LaunchMaterialInput,
) -> tuple[PreparedExperimentLaunch | None, str | None]:
    """Create every immutable row before hashing and before the first write."""
    request = material.request
    validation = material.validation
    work = material.work
    executor = material.executor
    certification = material.certification
    checks = material.checks
    if (
        executor.strategy_spec_hash is None
        or executor.node_registry_manifest_hash is None
        or certification.snapshot_evidence is None
    ):
        return None, None
    snapshot = certification.snapshot_evidence
    experiment_id = ExperimentId(request.experiment_id)
    candidate_specs = tuple(
        CandidateSpec(
            candidate_id=CandidateId(
                ":".join(
                    (
                        request.experiment_id,
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
        for candidate in work.candidate_matrix.candidates
    )
    if len(executor.candidates) != len(candidate_specs) - 1:
        return None, None
    baseline_resolved_spec_hash = (
        executor.baseline_runtime.resolved_spec_hash
        if executor.baseline_runtime is not None
        else executor.baseline_descriptor_hash
    )
    if baseline_resolved_spec_hash is None:
        return None, None
    execution_bindings = (
        CandidateExecutionBinding(
            candidate_specs[0].candidate_id,
            candidate_specs[0].ordinal,
            candidate_specs[0].parameter_hash,
            ContentHash(baseline_resolved_spec_hash),
        ),
        *tuple(
            CandidateExecutionBinding(
                candidate.candidate_id,
                candidate.ordinal,
                candidate.parameter_hash,
                ContentHash(runtime.resolved_spec_hash),
            )
            for candidate, runtime in zip(
                candidate_specs[1:],
                executor.candidates,
                strict=True,
            )
        ),
    )
    validation_payload = _validation_plan_payload(validation)
    spec = ExperimentLaunchSpec(
        experiment_id=experiment_id,
        strategy_version=StrategyVersion(
            f"{request.strategy_record.strategy_id}@{request.strategy_record.version}"
        ),
        strategy_spec_hash=ContentHash(executor.strategy_spec_hash),
        snapshot_id=SnapshotId(snapshot.snapshot_id),
        candidates=candidate_specs,
        execution_bindings=execution_bindings,
        promotion_objective=request.promotion_objective,
        fold_protocol=FoldProtocolSpec(
            material.fold_protocol_id,
            material.fold_protocol_version,
            canonical_payload(validation_payload).content_hash,
        ),
        seed=work.seed,
        worker_count=work.worker_count,
        failure_policy=work.failure_policy,
        budget=ExperimentBudget(
            candidate_limit=work.budget.candidate_limit,
            fold_run_limit=work.budget.fold_run_limit,
        ),
        desired_state=ExperimentDesiredState.RUN,
        created_at=request.created_at,
    )
    spec_payload = encode_launch_spec(spec)
    gates = tuple(
        _frozen_gate(
            request=request,
            check=check,
            index=index,
            policy_version=material.preflight_policy_version,
        )
        for index, check in enumerate(checks, start=1)
    )
    folds = tuple(
        FoldPersistenceSpec.create(
            key=FoldKey(
                experiment_id,
                candidate.candidate_id,
                FoldId(f"{material.fold_id_prefix}-{fold.ordinal}-{fold.role.value}"),
            ),
            ordinal=fold.ordinal,
            fold_role=fold.role,
            train_window=fold.train_window,
            test_window=fold.test_window,
            purge_sessions=fold.purge_sessions,
            embargo_sessions=fold.embargo_sessions,
        )
        for candidate in candidate_specs
        for fold in validation.folds
    ) + tuple(
        FoldPersistenceSpec.create(
            key=FoldKey(
                experiment_id,
                candidate.candidate_id,
                FoldId(
                    f"{material.fold_id_prefix}-{len(validation.folds) + 1}-holdout"
                ),
            ),
            ordinal=len(validation.folds) + 1,
            fold_role=FoldRole.HOLDOUT,
            train_window=validation.reserved_holdout.train_window,
            test_window=validation.reserved_holdout.test_window,
            purge_sessions=validation.reserved_holdout.purge_sessions,
            embargo_sessions=validation.reserved_holdout.embargo_sessions,
        )
        for candidate in candidate_specs
        if validation.reserved_holdout is not None
    )
    preflight, preflight_payload = _canonical_frozen_mapping(
        _preflight_payload(material=material, spec=spec)
    )
    plan_preimage, plan_preimage_payload = _canonical_frozen_mapping(
        _plan_preimage(
            material=material,
            spec_payload=spec_payload,
            gates=gates,
            folds=folds,
            snapshot=snapshot,
            validation_payload=validation_payload,
            preflight_hash=preflight_payload.content_hash,
        )
    )
    plan_hash = str(plan_preimage_payload.content_hash)
    creation_detail, creation_detail_payload = compile_creation_identity(
        request_hash=planning_request_hash(material.request),
        plan_hash=plan_hash,
    )
    enqueue_detail, enqueue_detail_payload = _canonical_frozen_mapping(
        {
            "plan_hash": plan_hash,
            "plan_preimage": plan_preimage,
            "preflight": preflight,
            "preflight_hash": str(preflight_payload.content_hash),
        }
    )
    detail_bytes = len(enqueue_detail_payload.json_bytes)
    if detail_bytes > _MAX_ENQUEUE_DETAIL_BYTES:
        raise AppProcessError(
            "canonical experiment preflight detail exceeds its persistence limit",
            details={
                "code": "PREFLIGHT_DETAIL_TOO_LARGE",
                "reason": "canonical_preflight_detail_exceeds_limit",
                "canonical_detail_bytes": detail_bytes,
                "maximum_canonical_detail_bytes": _MAX_ENQUEUE_DETAIL_BYTES,
            },
        )
    cycle = ResearchCycleIdentity(
        request.research_cycle_id,
        ContentHash(request.research_cycle_hash),
    )
    initial = ExperimentRecord(
        experiment_id,
        ExperimentStatus.DRAFT,
        ExperimentDesiredState.RUN,
        ExperimentStage.PREFLIGHT,
        request.created_at,
    )
    return (
        PreparedExperimentLaunch(
            cycle=cycle,
            spec=spec,
            initial_record=initial,
            gates=gates,
            folds=folds,
            launch_spec_json=spec_payload.json_bytes,
            launch_spec_hash=spec_payload.content_hash,
            gate_payload_hashes=tuple(gate.payload_hash for gate in gates),
            fold_payload_hashes=tuple(fold.payload_hash for fold in folds),
            preflight_json=preflight_payload.json_bytes,
            preflight_hash=preflight_payload.content_hash,
            plan_preimage_json=plan_preimage_payload.json_bytes,
            plan_hash=plan_hash,
            creation_detail=creation_detail,
            creation_detail_json=creation_detail_payload.json_bytes,
            creation_detail_hash=creation_detail_payload.content_hash,
            enqueue_detail=enqueue_detail,
            enqueue_detail_json=enqueue_detail_payload.json_bytes,
            enqueue_detail_hash=enqueue_detail_payload.content_hash,
        ),
        plan_hash,
    )
