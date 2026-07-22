"""Canonical codec for reconstructing one persisted experiment preflight report."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import orjson
from ditto_analysis.experiments import (
    DateWindow,
    ExperimentFailurePolicy,
    FoldRole,
    canonical_payload,
)
from ditto_analysis.experiments.preflight_authority import (
    decode_preflight_authority,
)
from ditto_strategy.alpha.parameters import ParameterValue

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._baseline_runtime_evidence import (
    decode_baseline_runtime_evidence,
)
from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
)
from ditto_application.processes.experiments._preflight_certification_codec import (
    validate_certification_preimage,
)
from ditto_application.processes.experiments._preflight_check_codec import (
    decode_preflight_checks,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_boolean as _boolean,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_date as _date,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_integer as _integer,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_list as _list,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_mapping as _mapping,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_month as _month,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_string as _string,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_window_dates,
)
from ditto_application.processes.experiments._preflight_semantics import (
    validate_launch_preflight_semantics,
)
from ditto_application.processes.experiments._preflight_shape import (
    validate_preflight_shape,
)
from ditto_application.processes.experiments._preflight_validation_codec import (
    decode_validation_protocol,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    BaselineDescriptor,
    BinderCandidatePlan,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ExperimentPlanningSpec,
    ExperimentTrack,
    ExperimentWorkPlan,
    ParameterAxis,
    ResourceCostModel,
    ValidationWorkload,
    plan_experiment_work,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
)
from ditto_application.processes.experiments.planning_probes import (
    CandidateExecutorEvidence,
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
    is_canonical_content_hash,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    RuntimeValidationEvidence,
    validation_authority_facts_match,
)
from ditto_application.research_validation_protocol import (
    ReservedHoldoutPlan,
    UniverseCoveragePolicy,
    ValidationEligibility,
    ValidationFoldPlan,
    ValidationProtocolPlan,
    ValidationProtocolRequest,
    ValidationReasonCode,
    canonical_validation_protocol_hash,
    compile_validation_protocol,
)

__all__ = ["DecodedPreflightReport", "decode_preflight_report"]


@dataclass(frozen=True, slots=True)
class DecodedPreflightReport:
    """Verified report fields independent of the process module's public DTO."""

    status: str
    plan_hash: str
    checks: tuple[ExperimentPreflightCheck, ...]
    candidate_count: int
    planned_fold_count: int
    budget_run_count: int
    estimated_trading_sessions: int
    estimated_disk_bytes: int
    eligible_month_count: int
    isolation_width_sessions: int
    validation_plan: ValidationProtocolPlan
    work_plan: ExperimentWorkPlan


def _window(value: object, field_name: str) -> DateWindow:
    return DateWindow(*decode_window_dates(value, field_name))


def _coverage_policy(value: object, field_name: str) -> UniverseCoveragePolicy:
    payload = _mapping(value, field_name)
    return UniverseCoveragePolicy(
        _string(payload.get("policy_id"), f"{field_name}.policy_id"),
        _integer(payload.get("version"), f"{field_name}.version"),
        _integer(
            payload.get("min_eligible_instrument_count"),
            f"{field_name}.min_eligible_instrument_count",
        ),
        _integer(
            payload.get("min_coverage_ratio_bps"),
            f"{field_name}.min_coverage_ratio_bps",
        ),
        _string(payload.get("evaluator_hash"), f"{field_name}.evaluator_hash"),
    )


def _validation_plan(value: object) -> ValidationProtocolPlan:
    payload = _mapping(value, "validation.plan")
    folds = tuple(
        ValidationFoldPlan(
            ordinal=_integer(item.get("ordinal"), "validation.fold.ordinal"),
            role=FoldRole(_string(item.get("role"), "validation.fold.role")),
            train_window=(
                None
                if item.get("train_window") is None
                else _window(item.get("train_window"), "validation.fold.train_window")
            ),
            test_window=_window(item.get("test_window"), "validation.fold.test_window"),
            purge_sessions=_integer(
                item.get("purge_sessions"), "validation.fold.purge_sessions"
            ),
            embargo_sessions=_integer(
                item.get("embargo_sessions"), "validation.fold.embargo_sessions"
            ),
        )
        for raw_item in _list(payload.get("folds"), "validation.plan.folds")
        for item in (_mapping(raw_item, "validation.fold"),)
    )
    raw_holdout = payload.get("reserved_holdout")
    holdout = None
    if raw_holdout is not None:
        item = _mapping(raw_holdout, "validation.plan.reserved_holdout")
        holdout = ReservedHoldoutPlan(
            train_window=_window(
                item.get("train_window"), "validation.holdout.train_window"
            ),
            test_window=_window(
                item.get("test_window"), "validation.holdout.test_window"
            ),
            purge_sessions=_integer(
                item.get("purge_sessions"), "validation.holdout.purge_sessions"
            ),
            embargo_sessions=_integer(
                item.get("embargo_sessions"), "validation.holdout.embargo_sessions"
            ),
        )
    return ValidationProtocolPlan(
        eligibility=ValidationEligibility(
            _string(payload.get("eligibility"), "validation.plan.eligibility")
        ),
        reason_codes=tuple(
            ValidationReasonCode(_string(item, "validation.plan.reason_code"))
            for item in _list(
                payload.get("reason_codes"), "validation.plan.reason_codes"
            )
        ),
        coverage_policy=_coverage_policy(
            payload.get("coverage_policy"), "validation.plan.coverage_policy"
        ),
        calendar_complete_month_count=_integer(
            payload.get("calendar_complete_month_count"),
            "validation.plan.calendar_complete_month_count",
        ),
        eligible_months=tuple(
            _month(item, "validation.plan.eligible_month")
            for item in _list(
                payload.get("eligible_months"), "validation.plan.eligible_months"
            )
        ),
        isolation_width_sessions=_integer(
            payload.get("isolation_width_sessions"),
            "validation.plan.isolation_width_sessions",
        ),
        folds=folds,
        reserved_holdout=holdout,
    )


def _parameter_type(value: object) -> str:
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    if type(value) is float:
        return "float"
    if type(value) is str:
        return "string"
    raise experiment_process_error("candidate parameter has an unsupported JSON type")


def _typed_parameter(value: object, declared_type: object) -> ParameterValue:
    if _parameter_type(value) != _string(declared_type, "candidate_parameter.type"):
        raise experiment_process_error(
            "candidate parameter type tag does not match its value"
        )
    return cast("ParameterValue", value)


def _matrix_spec(value: object) -> CandidateMatrixSpec:
    payload = _mapping(value, "work.matrix_spec")
    baseline = _mapping(payload.get("baseline"), "work.matrix_spec.baseline")
    axes = tuple(
        ParameterAxis(
            name=_string(axis.get("name"), "work.matrix_spec.axis.name"),
            values=tuple(
                _typed_parameter(item.get("value"), item.get("type"))
                for raw_item in _list(
                    axis.get("values"), "work.matrix_spec.axis.values"
                )
                for item in (_mapping(raw_item, "work.matrix_spec.axis.value"),)
            ),
        )
        for raw_axis in _list(payload.get("axes"), "work.matrix_spec.axes")
        for axis in (_mapping(raw_axis, "work.matrix_spec.axis"),)
    )
    return CandidateMatrixSpec(
        baseline=BaselineDescriptor(
            descriptor_type=_string(
                baseline.get("descriptor_type"),
                "work.matrix_spec.baseline.descriptor_type",
            ),
            payload=cast(
                "Mapping[str, BaselineInputValue]",
                _mapping(baseline.get("payload"), "work.matrix_spec.baseline.payload"),
            ),
            schema_version=_integer(
                baseline.get("schema_version"),
                "work.matrix_spec.baseline.schema_version",
            ),
        ),
        axes=axes,
        candidate_limit=_integer(
            payload.get("candidate_limit"), "work.matrix_spec.candidate_limit"
        ),
    )


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
    matrix: CandidateMatrixSpec,
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
        "matrix_spec": _matrix_spec_payload(matrix),
    }


def _work(value: object) -> ExperimentWorkPlan:
    payload = _mapping(value, "work")
    matrix = _matrix_spec(payload.get("matrix_spec"))
    workload = _mapping(payload.get("workload"), "work.workload")
    cost = _mapping(payload.get("cost_model"), "work.cost_model")
    budget = _mapping(payload.get("budget"), "work.budget")
    work = plan_experiment_work(
        ExperimentPlanningSpec(
            matrix=matrix,
            track=ExperimentTrack(_string(payload.get("track"), "work.track")),
            workload=ValidationWorkload(
                fold_session_counts=tuple(
                    _integer(item, "work.workload.fold_session_count")
                    for item in _list(
                        workload.get("fold_session_counts"),
                        "work.workload.fold_session_counts",
                    )
                ),
                holdout_session_count=_integer(
                    workload.get("holdout_session_count"),
                    "work.workload.holdout_session_count",
                ),
            ),
            cost_model=ResourceCostModel(
                bytes_per_run=_integer(
                    cost.get("bytes_per_run"), "work.cost_model.bytes_per_run"
                ),
                bytes_per_trading_session=_integer(
                    cost.get("bytes_per_trading_session"),
                    "work.cost_model.bytes_per_trading_session",
                ),
            ),
            budget=ExperimentBudgetSpec(
                candidate_limit=_integer(
                    budget.get("candidate_limit"), "work.budget.candidate_limit"
                ),
                fold_run_limit=_integer(
                    budget.get("fold_run_limit"), "work.budget.fold_run_limit"
                ),
                trading_session_limit=_integer(
                    budget.get("trading_session_limit"),
                    "work.budget.trading_session_limit",
                ),
                disk_byte_limit=_integer(
                    budget.get("disk_byte_limit"), "work.budget.disk_byte_limit"
                ),
            ),
            seed=_integer(payload.get("seed"), "work.seed"),
            worker_count=_integer(payload.get("worker_count"), "work.worker_count"),
            failure_policy=ExperimentFailurePolicy(
                _string(payload.get("failure_policy"), "work.failure_policy")
            ),
        )
    )
    if (
        canonical_payload(payload).json_bytes
        != canonical_payload(_work_payload(work, matrix)).json_bytes
    ):
        raise experiment_process_error(
            "persisted work plan does not match its canonical preimage"
        )
    return work


def _runtime_evidence(value: object) -> RuntimeValidationEvidence:
    payload = _mapping(value, "executor.runtime_validation_evidence")
    isolation = _mapping(
        payload.get("isolation"), "executor.runtime_validation_evidence.isolation"
    )
    return RuntimeValidationEvidence(
        lane=_string(payload.get("lane"), "runtime_validation.lane"),
        universe_id=_string(
            payload.get("universe_id"), "runtime_validation.universe_id"
        ),
        required_datasets=tuple(
            _string(item, "runtime_validation.required_dataset")
            for item in _list(
                payload.get("required_datasets"),
                "runtime_validation.required_datasets",
            )
        ),
        max_lookback_sessions=_integer(
            payload.get("max_lookback_sessions"),
            "runtime_validation.max_lookback_sessions",
        ),
        requires_pit_universe=_boolean(
            payload.get("requires_pit_universe"),
            "runtime_validation.requires_pit_universe",
        ),
        forward_horizon_sessions=_integer(
            isolation.get("forward_horizon_sessions"),
            "runtime_validation.isolation.forward_horizon_sessions",
        ),
        holding_period_sessions=_integer(
            isolation.get("holding_period_sessions"),
            "runtime_validation.isolation.holding_period_sessions",
        ),
        execution_lag_sessions=_integer(
            isolation.get("execution_lag_sessions"),
            "runtime_validation.isolation.execution_lag_sessions",
        ),
    )


def _dataset_bindings(value: object) -> tuple[ResearchDatasetRequirement, ...]:
    return tuple(
        ResearchDatasetRequirement(
            dataset_id=_string(item.get("dataset_id"), "binding.dataset_id"),
            expected_snapshot_ids=tuple(
                _string(snapshot_id, "binding.expected_snapshot_id")
                for snapshot_id in _list(
                    item.get("expected_snapshot_ids"),
                    "binding.expected_snapshot_ids",
                )
            ),
            requires_pit_universe=_boolean(
                item.get("requires_pit_universe"), "binding.requires_pit_universe"
            ),
            certified_from=_date(
                item.get("certified_from"),
                "binding.certified_from",
            ),
        )
        for raw_item in _list(value, "authority.dataset_bindings")
        for item in (_mapping(raw_item, "authority.dataset_binding"),)
    )


def _validate_executor_and_authority(
    *,
    preflight: Mapping[str, object],
    protocol: ValidationProtocolRequest,
    work: ExperimentWorkPlan,
) -> tuple[RuntimeValidationEvidence, ResearchValidationAuthorityEvidence]:
    executor = _mapping(preflight.get("executor"), "executor")
    if not _boolean(executor.get("available"), "executor.available"):
        raise experiment_process_error("persisted launch executor is unavailable")
    identity_hashes = (
        _string(executor.get(field), f"executor.{field}")
        for field in (
            "strategy_spec_hash",
            "node_registry_manifest_hash",
            "factor_registry_manifest_hash",
        )
    )
    factor_binding_hashes = tuple(
        _string(item, "executor.factor_binding_hash")
        for item in _list(
            executor.get("factor_binding_hashes"),
            "executor.factor_binding_hashes",
        )
    )
    if any(
        not is_canonical_content_hash(item)
        for item in (*identity_hashes, *factor_binding_hashes)
    ) or len(set(factor_binding_hashes)) != len(factor_binding_hashes):
        raise experiment_process_error("executor identity hash is invalid")
    baseline_runtime = decode_baseline_runtime_evidence(
        executor.get("baseline_runtime")
    )
    baseline_exact_strategy_hash = executor.get("baseline_exact_strategy_hash")
    if (baseline_exact_strategy_hash is None and baseline_runtime is not None) or (
        baseline_exact_strategy_hash is not None
        and (
            not is_canonical_content_hash(baseline_exact_strategy_hash)
            or baseline_runtime is None
        )
    ):
        raise experiment_process_error("baseline runtime identity is incomplete")
    runtime = _runtime_evidence(executor.get("runtime_validation_evidence"))
    candidates = tuple(
        CandidateExecutorEvidence(
            candidate_hash=_string(
                item.get("candidate_hash"), "executor.candidate.candidate_hash"
            ),
            resolved_spec_hash=_string(
                item.get("resolved_spec_hash"),
                "executor.candidate.resolved_spec_hash",
            ),
            parameter_hash=_string(
                item.get("parameter_hash"), "executor.candidate.parameter_hash"
            ),
            pipeline_execution_hash=_string(
                item.get("pipeline_execution_hash"),
                "executor.candidate.pipeline_execution_hash",
            ),
            compiled_factor_set_hash=_string(
                item.get("compiled_factor_set_hash"),
                "executor.candidate.compiled_factor_set_hash",
            ),
        )
        for raw_item in _list(executor.get("candidates"), "executor.candidates")
        for item in (_mapping(raw_item, "executor.candidate"),)
    )
    expected_hashes = tuple(
        candidate.candidate_hash
        for candidate in work.candidate_matrix.binder_candidates
    )
    if tuple(item.candidate_hash for item in candidates) != expected_hashes or not all(
        is_canonical_content_hash(item.candidate_hash)
        and is_canonical_content_hash(item.resolved_spec_hash)
        and is_canonical_content_hash(item.parameter_hash)
        and is_canonical_content_hash(item.pipeline_execution_hash)
        and is_canonical_content_hash(item.compiled_factor_set_hash)
        for item in candidates
    ):
        raise experiment_process_error(
            "executor candidate identity does not match the work plan"
        )
    authority = _mapping(preflight.get("authority"), "authority")
    authority_protocol_hash = _string(
        authority.get("protocol_hash"),
        "authority.protocol_hash",
    )
    if authority_protocol_hash != canonical_validation_protocol_hash(protocol):
        msg = "authority protocol does not match validation protocol"
        raise experiment_process_error(msg)
    snapshot = _mapping(
        authority.get("snapshot_identity"), "authority.snapshot_identity"
    )
    snapshot_identity = ExperimentSnapshotIdentity(
        _string(snapshot.get("snapshot_id"), "authority.snapshot_id"),
        _string(snapshot.get("manifest_hash"), "authority.manifest_hash"),
    )
    rebuilt = ResearchValidationAuthorityEvidence.create(
        protocol=protocol,
        snapshot_identity=snapshot_identity,
        runtime_evidence_hash=runtime.payload_hash,
        universe_membership_hash=_string(
            authority.get("universe_membership_hash"),
            "authority.universe_membership_hash",
        ),
        requires_pit_universe=_boolean(
            authority.get("requires_pit_universe"),
            "authority.requires_pit_universe",
        ),
        dataset_bindings=_dataset_bindings(authority.get("dataset_bindings")),
    )
    identities = _mapping(preflight.get("identities"), "identities")
    identity_snapshot = _mapping(
        identities.get("snapshot_identity"),
        "identities.snapshot_identity",
    )
    declared_snapshot = ExperimentSnapshotIdentity(
        _string(
            identity_snapshot.get("snapshot_id"),
            "identities.snapshot_identity.snapshot_id",
        ),
        _string(
            identity_snapshot.get("manifest_hash"),
            "identities.snapshot_identity.manifest_hash",
        ),
    )
    declared_requirements = _dataset_bindings(identities.get("dataset_requirements"))
    if (
        rebuilt.payload_hash
        != _string(authority.get("payload_hash"), "authority.payload_hash")
        or rebuilt.membership_projection_hash
        != _string(
            authority.get("membership_projection_hash"),
            "authority.membership_projection_hash",
        )
        or rebuilt.runtime_evidence_hash
        != _string(
            authority.get("runtime_evidence_hash"),
            "authority.runtime_evidence_hash",
        )
        or tuple(runtime.required_datasets)
        != tuple(
            _string(item, "executor.required_dataset")
            for item in _list(
                executor.get("required_datasets"), "executor.required_datasets"
            )
        )
        or canonical_payload(rebuilt.summaries).json_bytes
        != canonical_payload(
            _mapping(authority.get("summaries"), "authority.summaries")
        ).json_bytes
        or not validation_authority_facts_match(
            rebuilt,
            runtime,
            snapshot_identity=declared_snapshot,
            dataset_requirements=declared_requirements,
        )
    ):
        raise experiment_process_error(
            "authority identity does not match executor evidence"
        )
    return runtime, rebuilt


def _decode(
    detail: Mapping[str, object],
    *,
    expected_policy_version: str,
) -> DecodedPreflightReport:
    encoded = canonical_payload(detail)
    decoded = _mapping(cast("object", orjson.loads(encoded.json_bytes)), "detail")
    authority_identity = decode_preflight_authority(decoded)
    plan_hash = str(authority_identity.plan_hash)
    preflight = validate_preflight_shape(decoded.get("preflight"))
    if (
        _integer(preflight.get("schema_version"), "preflight.schema_version") != 1
        or _string(preflight.get("policy_version"), "preflight.policy_version")
        != expected_policy_version
    ):
        raise experiment_process_error("preflight content identity is invalid")
    validation = _mapping(preflight.get("validation"), "validation")
    protocol = decode_validation_protocol(validation.get("protocol"))
    stored_plan = _validation_plan(validation.get("plan"))
    compiled_plan = compile_validation_protocol(protocol)
    if stored_plan != compiled_plan:
        msg = "validation plan does not match its protocol preimage"
        raise experiment_process_error(msg)
    work = _work(preflight.get("work"))
    runtime, authority = _validate_executor_and_authority(
        preflight=preflight,
        protocol=protocol,
        work=work,
    )
    checks = decode_preflight_checks(preflight.get("checks"))
    validate_certification_preimage(
        preflight=preflight,
        protocol=protocol,
        validation=compiled_plan,
        checks=checks,
    )
    validate_launch_preflight_semantics(
        preflight=preflight,
        validation=compiled_plan,
        work=work,
        checks=checks,
        runtime=runtime,
        authority_evidence=authority,
    )
    counts = _mapping(preflight.get("counts"), "preflight.counts")
    expected_counts = {
        "candidate_count": work.candidate_matrix.candidate_count,
        "planned_fold_count": work.candidate_matrix.candidate_count
        * (len(compiled_plan.folds) + (compiled_plan.reserved_holdout is not None)),
        "budget_run_count": work.estimate.total_run_count,
        "estimated_trading_sessions": work.estimate.estimated_trading_sessions,
        "estimated_disk_bytes": work.estimate.estimated_disk_bytes,
        "eligible_month_count": len(compiled_plan.eligible_months),
        "isolation_width_sessions": compiled_plan.isolation_width_sessions,
    }
    actual_counts = {
        key: _integer(counts.get(key), f"preflight.counts.{key}")
        for key in expected_counts
    }
    if actual_counts != expected_counts:
        raise experiment_process_error(
            "preflight counts do not match the reconstructed plans"
        )
    status = _string(preflight.get("status"), "preflight.status")
    expected_status = "ready" if compiled_plan.promotion_eligible else "research_only"
    if status != expected_status:
        raise experiment_process_error(
            "preflight status does not match validation eligibility"
        )
    return DecodedPreflightReport(
        status=status,
        plan_hash=plan_hash,
        checks=checks,
        candidate_count=actual_counts["candidate_count"],
        planned_fold_count=actual_counts["planned_fold_count"],
        budget_run_count=actual_counts["budget_run_count"],
        estimated_trading_sessions=actual_counts["estimated_trading_sessions"],
        estimated_disk_bytes=actual_counts["estimated_disk_bytes"],
        eligible_month_count=actual_counts["eligible_month_count"],
        isolation_width_sessions=actual_counts["isolation_width_sessions"],
        validation_plan=compiled_plan,
        work_plan=work,
    )


def decode_preflight_report(
    detail: Mapping[str, object],
    *,
    expected_policy_version: str,
) -> DecodedPreflightReport:
    """Decode canonical detail and fail closed on any preimage or hash drift."""
    try:
        return _decode(detail, expected_policy_version=expected_policy_version)
    except Exception as exc:
        raise AppProcessError(
            "persisted experiment preflight detail is invalid",
            details={
                "code": "PREFLIGHT_DETAIL_INVALID",
                "reason": "persisted_preflight_reconstruction_failed",
                "error_type": type(exc).__name__,
            },
        ) from exc
