"""Launch-only semantic reconstruction for persisted R3 preflight evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import cast

import orjson

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments._validation_workload import (
    compile_validation_workload,
)
from ditto_application.processes.experiments.planning import (
    ExperimentTrack,
    ExperimentWorkPlan,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    is_canonical_content_hash,
    is_canonical_identity,
)
from ditto_application.research_validation_contracts import (
    ResearchValidationAuthorityEvidence,
    RuntimeValidationEvidence,
)
from ditto_application.research_validation_protocol import (
    ValidationEligibility,
    ValidationProtocolPlan,
)

__all__ = ["validate_launch_preflight_semantics"]

_RULE_IDS = (
    "matrix",
    "executor",
    "authority",
    "history",
    "certification",
    "budget",
)


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{field_name} must be a list")
    return cast("list[object]", value)


def _string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise experiment_process_error(f"{field_name} must be an integer")
    return value


def _same(left: object, right: object) -> bool:
    return orjson.dumps({"value": left}, option=orjson.OPT_SORT_KEYS) == orjson.dumps(
        {"value": right},
        option=orjson.OPT_SORT_KEYS,
    )


def _require_check(
    check: ExperimentPreflightCheck,
    *,
    outcome: PreflightOutcome,
    code: str | None,
    reason: str | None,
    remediation: str | None,
    observed: Mapping[str, object],
    policy: Mapping[str, object],
) -> None:
    if (
        check.outcome is not outcome
        or check.code != code
        or check.reason != reason
        or check.remediation != remediation
        or not _same(check.observed, observed)
        or not _same(check.policy, policy)
    ):
        raise experiment_process_error(
            f"persisted {check.rule_id} check is not canonical"
        )


def _validate_fold_protocol(preflight: Mapping[str, object]) -> None:
    validation = _mapping(preflight.get("validation"), "validation")
    plan = _mapping(validation.get("plan"), "validation.plan")
    fold_protocol = _mapping(
        validation.get("fold_protocol"),
        "validation.fold_protocol",
    )
    if (
        fold_protocol.get("protocol_id") != "r3-complete-month-walk-forward"
        or fold_protocol.get("protocol_version") != 1
        or fold_protocol.get("protocol_hash")
        != hashlib.sha256(orjson.dumps(plan, option=orjson.OPT_SORT_KEYS)).hexdigest()
    ):
        raise experiment_process_error(
            "persisted fold protocol is not the registered R3 protocol"
        )


def _validate_identities(
    *,
    preflight: Mapping[str, object],
    runtime: RuntimeValidationEvidence,
    authority_evidence: ResearchValidationAuthorityEvidence,
) -> tuple[dict[str, object], dict[str, object], list[str]]:
    identities = _mapping(preflight.get("identities"), "identities")
    authority = _mapping(preflight.get("authority"), "authority")
    executor = _mapping(preflight.get("executor"), "executor")
    requirements = _list(
        identities.get("dataset_requirements"),
        "identities.dataset_requirements",
    )
    requirement_ids = [
        _string(
            _mapping(item, "identities.dataset_requirement").get("dataset_id"),
            "identities.dataset_requirement.dataset_id",
        )
        for item in requirements
    ]
    certification = _mapping(
        identities.get("certification"),
        "identities.certification",
    )
    identity_snapshot = _mapping(
        identities.get("snapshot_identity"),
        "identities.snapshot_identity",
    )
    authority_snapshot = _mapping(
        authority.get("snapshot_identity"),
        "authority.snapshot_identity",
    )
    snapshot = _mapping(
        certification.get("snapshot_evidence"),
        "identities.certification.snapshot_evidence",
    )
    if (
        not is_canonical_content_hash(identities.get("request_hash"))
        or not is_canonical_identity(identities.get("research_cycle_id"))
        or not is_canonical_content_hash(identities.get("research_cycle_hash"))
        or not is_canonical_identity(identities.get("strategy_id"))
        or _integer(identities.get("strategy_version"), "identities.strategy_version")
        <= 0
        or not _same(identity_snapshot, authority_snapshot)
        or snapshot.get("snapshot_id") != identity_snapshot.get("snapshot_id")
        or snapshot.get("manifest_hash") != identity_snapshot.get("manifest_hash")
        or not _same(requirements, authority.get("dataset_bindings"))
        or requirement_ids != sorted(requirement_ids)
        or len(set(requirement_ids)) != len(requirement_ids)
        or tuple(requirement_ids) != runtime.required_datasets
        or executor.get("required_datasets") != requirement_ids
    ):
        raise experiment_process_error("persisted launch identities are inconsistent")
    return identities, certification, requirement_ids


def _validate_certification(
    *,
    certification: Mapping[str, object],
    requirements: list[object],
    requirement_ids: list[str],
) -> tuple[dict[str, object], list[str], list[str]]:
    dataset_ids = [
        _string(item, "identities.certification.dataset_id")
        for item in _list(
            certification.get("dataset_ids"),
            "identities.certification.dataset_ids",
        )
    ]
    report_ids = [
        _string(item, "identities.certification.report_id")
        for item in _list(
            certification.get("report_ids"),
            "identities.certification.report_ids",
        )
    ]
    reason_codes = _list(
        certification.get("reason_codes"),
        "identities.certification.reason_codes",
    )
    snapshot = _mapping(
        certification.get("snapshot_evidence"),
        "identities.certification.snapshot_evidence",
    )
    source_ids = [
        _string(item, "identities.certification.source_snapshot_id")
        for item in _list(
            snapshot.get("source_snapshot_ids"),
            "identities.certification.source_snapshot_ids",
        )
    ]
    expected_sources = {
        _string(snapshot_id, "requirement.expected_snapshot_id")
        for raw_requirement in requirements
        for snapshot_id in _list(
            _mapping(raw_requirement, "requirement").get("expected_snapshot_ids"),
            "requirement.expected_snapshot_ids",
        )
    }
    if (
        certification.get("ready") is not True
        or certification.get("profile") != R3_RESEARCH_CERTIFICATION_PROFILE
        or dataset_ids != requirement_ids
        or len(report_ids) != len(requirement_ids)
        or not report_ids
        or not all(is_canonical_identity(item) for item in report_ids)
        or reason_codes
        or not source_ids
        or len(set(source_ids)) != len(source_ids)
        or not all(is_canonical_identity(item) for item in source_ids)
        or not expected_sources.issubset(source_ids)
        or not is_canonical_identity(snapshot.get("snapshot_id"))
        or not is_canonical_identity(snapshot.get("dataset_id"))
        or not is_canonical_content_hash(snapshot.get("manifest_hash"))
        or snapshot.get("known_at_policy") not in {"sample_time", "explicit_cutoff"}
        or not is_canonical_identity(snapshot.get("builder_version"))
    ):
        raise experiment_process_error(
            "persisted certification evidence is not launch-ready"
        )
    return snapshot, dataset_ids, report_ids


def _validate_executor(
    *,
    preflight: Mapping[str, object],
    work: ExperimentWorkPlan,
    runtime: RuntimeValidationEvidence,
) -> tuple[dict[str, object], list[str], list[str]]:
    executor = _mapping(preflight.get("executor"), "executor")
    candidates = _list(executor.get("candidates"), "executor.candidates")
    candidate_hashes = [
        _string(
            _mapping(item, "executor.candidate").get("candidate_hash"),
            "executor.candidate.candidate_hash",
        )
        for item in candidates
    ]
    expected_hashes = [
        item.candidate_hash for item in work.candidate_matrix.binder_candidates
    ]
    required_datasets = [
        _string(item, "executor.required_dataset")
        for item in _list(
            executor.get("required_datasets"),
            "executor.required_datasets",
        )
    ]
    if (
        executor.get("available") is not True
        or executor.get("code") is not None
        or executor.get("reason") is not None
        or executor.get("remediation") is not None
        or not is_canonical_content_hash(executor.get("strategy_spec_hash"))
        or not is_canonical_content_hash(executor.get("node_registry_manifest_hash"))
        or candidate_hashes != expected_hashes
        or tuple(required_datasets) != runtime.required_datasets
    ):
        raise experiment_process_error(
            "persisted executor evidence is not launch-ready"
        )
    return executor, candidate_hashes, required_datasets


def validate_launch_preflight_semantics(
    *,
    preflight: dict[str, object],
    validation: ValidationProtocolPlan,
    work: ExperimentWorkPlan,
    checks: tuple[ExperimentPreflightCheck, ...],
    runtime: RuntimeValidationEvidence,
    authority_evidence: ResearchValidationAuthorityEvidence,
) -> None:
    """Rebuild every launch gate and reject self-consistent illegal documents."""
    if tuple(check.rule_id for check in checks) != _RULE_IDS:
        raise experiment_process_error(
            "persisted launch checks are incomplete or out of order"
        )
    expected_track = (
        ExperimentTrack.PROMOTION
        if validation.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE
        else ExperimentTrack.RESEARCH_ONLY
    )
    expected_workload = compile_validation_workload(
        authority_evidence.protocol,
        validation,
    )
    if (
        work.track is not expected_track
        or tuple(work.workload.fold_session_counts)
        != tuple(expected_workload.fold_session_counts)
        or work.workload.holdout_session_count
        != expected_workload.holdout_session_count
    ):
        raise experiment_process_error(
            "persisted work does not match compiled validation semantics"
        )
    _validate_fold_protocol(preflight)
    identities, certification, requirement_ids = _validate_identities(
        preflight=preflight,
        runtime=runtime,
        authority_evidence=authority_evidence,
    )
    requirements = _list(
        identities.get("dataset_requirements"),
        "identities.dataset_requirements",
    )
    snapshot, dataset_ids, report_ids = _validate_certification(
        certification=certification,
        requirements=requirements,
        requirement_ids=requirement_ids,
    )
    executor, candidate_hashes, required_datasets = _validate_executor(
        preflight=preflight,
        work=work,
        runtime=runtime,
    )
    authority = _mapping(preflight.get("authority"), "authority")
    authority_summaries = _mapping(authority.get("summaries"), "authority.summaries")
    expected_authority_summaries = {
        **authority_summaries,
        "eligibility": {
            **_mapping(
                authority_summaries.get("eligibility"),
                "authority.summaries.eligibility",
            ),
            "eligible_month_count": len(validation.eligible_months),
        },
    }
    matrix = work.candidate_matrix
    _require_check(
        checks[0],
        outcome=PreflightOutcome.PASS,
        code=None,
        reason=None,
        remediation=None,
        observed={
            "candidate_count": matrix.candidate_count,
            "matrix_hash": matrix.matrix_hash,
        },
        policy={"candidate_limit": matrix.candidate_limit},
    )
    _require_check(
        checks[1],
        outcome=PreflightOutcome.PASS,
        code=None,
        reason=None,
        remediation=None,
        observed={
            "available": True,
            "evidence_hashes_valid": True,
            "node_registry_manifest_hash": executor.get("node_registry_manifest_hash"),
            "required_datasets": required_datasets,
            "candidate_hashes": candidate_hashes,
        },
        policy={
            "declared_datasets": requirement_ids,
            "expected_candidate_hashes": candidate_hashes,
        },
    )
    _require_check(
        checks[2],
        outcome=PreflightOutcome.PASS,
        code=None,
        reason=None,
        remediation=None,
        observed={
            "ready": True,
            "authority_payload_hash": authority.get("payload_hash"),
            "runtime_evidence_hash": authority.get("runtime_evidence_hash"),
            "authority_protocol_hash": authority.get("protocol_hash"),
            "declared_protocol_hash": authority.get("protocol_hash"),
            "summaries": expected_authority_summaries,
        },
        policy={
            "authority_protocol_required": True,
            "runtime_evidence_binding_required": True,
            "caller_assertion_must_match_exactly": True,
        },
    )
    history_passes = validation.eligibility is ValidationEligibility.PROMOTION_ELIGIBLE
    _require_check(
        checks[3],
        outcome=(PreflightOutcome.PASS if history_passes else PreflightOutcome.WARN),
        code=None if history_passes else "INSUFFICIENT_PROMOTION_HISTORY",
        reason=(None if history_passes else "continuous_complete_months_below_policy"),
        remediation=(
            None
            if history_passes
            else "collect 96 continuous eligible complete months before review"
        ),
        observed={"eligible_month_count": len(validation.eligible_months)},
        policy={"research_minimum": 37, "promotion_minimum": 96},
    )
    _require_check(
        checks[4],
        outcome=PreflightOutcome.PASS,
        code=None,
        reason=None,
        remediation=None,
        observed={
            "ready": True,
            "profile": R3_RESEARCH_CERTIFICATION_PROFILE,
            "dataset_ids": dataset_ids,
            "report_ids": report_ids,
            "reason_codes": [],
            "snapshot_evidence": snapshot,
            "snapshot_evidence_valid": True,
        },
        policy={
            "profile": R3_RESEARCH_CERTIFICATION_PROFILE,
            "required_from": certification.get("required_from"),
            "required_to": certification.get("required_to"),
            "requirements": requirements,
            "snapshot_identity": identities.get("snapshot_identity"),
        },
    )
    _require_check(
        checks[5],
        outcome=PreflightOutcome.PASS,
        code=None,
        reason=None,
        remediation=None,
        observed={
            "total_run_count": work.estimate.total_run_count,
            "estimated_trading_sessions": work.estimate.estimated_trading_sessions,
            "estimated_disk_bytes": work.estimate.estimated_disk_bytes,
        },
        policy={
            "fold_run_limit": work.budget.fold_run_limit,
            "trading_session_limit": work.budget.trading_session_limit,
            "disk_byte_limit": work.budget.disk_byte_limit,
            "worker_count": work.worker_count,
        },
    )
