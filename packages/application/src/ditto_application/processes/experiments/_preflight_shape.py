"""Exact structural schema for the persisted R3 preflight document."""

from __future__ import annotations

from typing import cast

from ditto_application.processes.experiments._baseline_runtime_evidence import (
    BASELINE_RUNTIME_EVIDENCE_KEYS,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)

__all__ = ["validate_preflight_shape"]


def _object(value: object, name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{name} must be an object")
    payload = cast("dict[str, object]", value)
    if set(payload) != keys:
        raise experiment_process_error(f"{name} has an invalid shape")
    return payload


def _array(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{name} must be an array")
    return cast("list[object]", value)


def _open_object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{name} must be an object")
    return cast("dict[str, object]", value)


def _objects(value: object, name: str, keys: set[str]) -> None:
    for item in _array(value, name):
        _object(item, f"{name}[]", keys)


def _window(value: object, name: str) -> None:
    _object(value, name, {"start", "end"})


def _validation_shape(value: object) -> None:
    validation = _object(value, "validation", {"protocol", "plan", "fold_protocol"})
    _open_object(validation["protocol"], "validation.protocol")
    plan = _object(
        validation["plan"],
        "validation.plan",
        {
            "eligibility",
            "reason_codes",
            "coverage_policy",
            "calendar_complete_month_count",
            "eligible_months",
            "isolation_width_sessions",
            "folds",
            "reserved_holdout",
        },
    )
    _object(
        plan["coverage_policy"],
        "validation.plan.coverage_policy",
        {
            "policy_id",
            "version",
            "min_eligible_instrument_count",
            "min_coverage_ratio_bps",
            "evaluator_hash",
        },
    )
    for raw_fold in _array(plan["folds"], "validation.plan.folds"):
        fold = _object(
            raw_fold,
            "validation.plan.fold",
            {
                "ordinal",
                "role",
                "train_window",
                "test_window",
                "purge_sessions",
                "embargo_sessions",
            },
        )
        if fold["train_window"] is not None:
            _window(fold["train_window"], "validation.plan.fold.train_window")
        _window(fold["test_window"], "validation.plan.fold.test_window")
    if plan["reserved_holdout"] is not None:
        holdout = _object(
            plan["reserved_holdout"],
            "validation.plan.reserved_holdout",
            {
                "train_window",
                "test_window",
                "purge_sessions",
                "embargo_sessions",
            },
        )
        _window(holdout["train_window"], "validation.plan.holdout.train_window")
        _window(holdout["test_window"], "validation.plan.holdout.test_window")
    _object(
        validation["fold_protocol"],
        "validation.fold_protocol",
        {"protocol_id", "protocol_version", "protocol_hash"},
    )


def _descriptor(value: object, name: str) -> None:
    _object(value, name, {"descriptor_type", "payload", "schema_version"})


def _work_shape(value: object) -> None:
    work = _object(
        value,
        "work",
        {
            "plan_hash",
            "track",
            "seed",
            "worker_count",
            "failure_policy",
            "workload",
            "cost_model",
            "budget",
            "estimate",
            "candidate_matrix",
            "matrix_spec",
        },
    )
    _object(
        work["workload"],
        "work.workload",
        {"fold_session_counts", "holdout_session_count"},
    )
    _object(
        work["cost_model"],
        "work.cost_model",
        {"bytes_per_run", "bytes_per_trading_session"},
    )
    _object(
        work["budget"],
        "work.budget",
        {
            "candidate_limit",
            "fold_run_limit",
            "trading_session_limit",
            "disk_byte_limit",
        },
    )
    _object(
        work["estimate"],
        "work.estimate",
        {
            "candidate_count",
            "validation_run_count",
            "holdout_run_count",
            "total_run_count",
            "estimated_trading_sessions",
            "estimated_disk_bytes",
        },
    )
    matrix = _object(
        work["candidate_matrix"],
        "work.candidate_matrix",
        {"candidate_limit", "matrix_hash", "candidates"},
    )
    for raw_candidate in _array(
        matrix["candidates"],
        "work.candidate_matrix.candidates",
    ):
        candidate = _object(
            raw_candidate,
            "work.candidate",
            {
                "ordinal",
                "role",
                "candidate_hash",
                "baseline_descriptor",
                "parameters",
            },
        )
        if candidate["baseline_descriptor"] is not None:
            _descriptor(candidate["baseline_descriptor"], "work.candidate.baseline")
        _objects(
            candidate["parameters"],
            "work.candidate.parameters",
            {"path", "type", "value"},
        )
    matrix_spec = _object(
        work["matrix_spec"],
        "work.matrix_spec",
        {"baseline", "axes", "candidate_limit"},
    )
    _descriptor(matrix_spec["baseline"], "work.matrix_spec.baseline")
    for raw_axis in _array(matrix_spec["axes"], "work.matrix_spec.axes"):
        axis = _object(raw_axis, "work.matrix_spec.axis", {"name", "values"})
        _objects(axis["values"], "work.matrix_spec.axis.values", {"type", "value"})


def _executor_shape(value: object) -> None:
    executor = _object(
        value,
        "executor",
        {
            "available",
            "code",
            "reason",
            "remediation",
            "strategy_spec_hash",
            "node_registry_manifest_hash",
            "factor_registry_manifest_hash",
            "factor_binding_hashes",
            "baseline_ref",
            "baseline_descriptor_hash",
            "baseline_registry_manifest_hash",
            "baseline_exact_strategy_hash",
            "baseline_runtime",
            "required_datasets",
            "candidates",
            "runtime_validation_evidence",
        },
    )
    _objects(
        executor["candidates"],
        "executor.candidates",
        {
            "candidate_hash",
            "resolved_spec_hash",
            "parameter_hash",
            "pipeline_execution_hash",
            "compiled_factor_set_hash",
        },
    )
    _array(executor["factor_binding_hashes"], "executor.factor_binding_hashes")
    if executor["baseline_runtime"] is not None:
        baseline_runtime = _object(
            executor["baseline_runtime"],
            "executor.baseline_runtime",
            set(BASELINE_RUNTIME_EVIDENCE_KEYS),
        )
        _array(
            baseline_runtime["factor_binding_hashes"],
            "executor.baseline_runtime.factor_binding_hashes",
        )
    runtime = _object(
        executor["runtime_validation_evidence"],
        "executor.runtime_validation_evidence",
        {
            "lane",
            "universe_id",
            "required_datasets",
            "max_lookback_sessions",
            "requires_pit_universe",
            "isolation",
        },
    )
    _object(
        runtime["isolation"],
        "executor.runtime_validation_evidence.isolation",
        {
            "forward_horizon_sessions",
            "holding_period_sessions",
            "execution_lag_sessions",
        },
    )


def _authority_shape(value: object) -> None:
    authority = _object(
        value,
        "authority",
        {
            "payload_hash",
            "runtime_evidence_hash",
            "universe_membership_hash",
            "membership_projection_hash",
            "requires_pit_universe",
            "snapshot_identity",
            "dataset_bindings",
            "protocol_hash",
            "summaries",
        },
    )
    _object(
        authority["snapshot_identity"],
        "authority.snapshot_identity",
        {"snapshot_id", "manifest_hash"},
    )
    _objects(
        authority["dataset_bindings"],
        "authority.dataset_bindings",
        {
            "dataset_id",
            "expected_snapshot_ids",
            "requires_pit_universe",
            "certified_from",
        },
    )
    _object(
        authority["summaries"],
        "authority.summaries",
        {"calendar", "membership", "eligibility", "policy", "semantics"},
    )


def _identities_shape(value: object) -> None:
    identities = _object(
        value,
        "identities",
        {
            "request_hash",
            "research_cycle_id",
            "research_cycle_hash",
            "strategy_id",
            "strategy_version",
            "snapshot_identity",
            "dataset_requirements",
            "certification",
        },
    )
    _object(
        identities["snapshot_identity"],
        "identities.snapshot_identity",
        {"snapshot_id", "manifest_hash"},
    )
    _objects(
        identities["dataset_requirements"],
        "identities.dataset_requirements",
        {
            "dataset_id",
            "expected_snapshot_ids",
            "requires_pit_universe",
            "certified_from",
        },
    )
    certification = _object(
        identities["certification"],
        "identities.certification",
        {
            "ready",
            "profile",
            "required_from",
            "required_to",
            "dataset_ids",
            "report_ids",
            "reason_codes",
            "snapshot_evidence",
        },
    )
    _object(
        certification["snapshot_evidence"],
        "identities.certification.snapshot_evidence",
        {
            "snapshot_id",
            "dataset_id",
            "manifest_hash",
            "source_snapshot_ids",
            "snapshot_start",
            "snapshot_end",
            "known_at_policy",
            "builder_version",
        },
    )


def validate_preflight_shape(value: object) -> dict[str, object]:
    """Reject every missing or extra structural field before semantic decoding."""
    preflight = _object(
        value,
        "preflight",
        {
            "schema_version",
            "policy_version",
            "status",
            "checks",
            "counts",
            "validation",
            "work",
            "executor",
            "authority",
            "identities",
        },
    )
    _objects(
        preflight["checks"],
        "preflight.checks",
        {"rule_id", "outcome", "code", "reason", "remediation", "observed", "policy"},
    )
    _object(
        preflight["counts"],
        "preflight.counts",
        {
            "candidate_count",
            "planned_fold_count",
            "budget_run_count",
            "estimated_trading_sessions",
            "estimated_disk_bytes",
            "eligible_month_count",
            "isolation_width_sessions",
        },
    )
    _validation_shape(preflight["validation"])
    _work_shape(preflight["work"])
    _executor_shape(preflight["executor"])
    _authority_shape(preflight["authority"])
    _identities_shape(preflight["identities"])
    return preflight
