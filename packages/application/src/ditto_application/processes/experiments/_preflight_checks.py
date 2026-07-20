"""Pure evidence-to-check projections for experiment preflight."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_application.processes.experiments._planning_evidence import (
    candidate_evidence_tuple,
    canonical_text,
    canonical_text_tuple,
    snapshot_payload,
    text_tuple_payload,
)
from ditto_application.processes.experiments.planning import CandidateMatrixPlan
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    ExperimentPreflightCheck,
    PreflightOutcome,
)
from ditto_application.processes.experiments.planning_probes import (
    R3_RESEARCH_CERTIFICATION_PROFILE,
    ResearchCertificationRequest,
    ResearchCertificationResult,
    ResearchExecutorProbeResult,
    ResearchSnapshotEvidence,
    is_canonical_content_hash,
)

__all__ = ["certification_check", "executor_check"]


def executor_check(
    result: ResearchExecutorProbeResult,
    matrix: CandidateMatrixPlan,
    request: ExperimentPlanningRequest,
) -> ExperimentPreflightCheck:
    """Project normalized executor evidence into one exact hard gate."""
    required_valid = canonical_text_tuple(result.required_datasets)
    required = tuple(sorted(result.required_datasets)) if required_valid else ()
    declared = tuple(sorted(item.dataset_id for item in request.dataset_requirements))
    candidates = candidate_evidence_tuple(cast("object", result.candidates))
    candidates_valid = candidates is not None
    candidate_hashes = (
        tuple(item.candidate_hash for item in candidates) if candidates else ()
    )
    expected_hashes = tuple(item.candidate_hash for item in matrix.binder_candidates)
    evidence_hashes = (
        () if result.strategy_spec_hash is None else (result.strategy_spec_hash,)
    ) + (
        tuple(item.resolved_spec_hash for item in candidates)
        + tuple(item.parameter_hash for item in candidates)
        if candidates
        else ()
    )
    evidence_hashes_valid = bool(evidence_hashes) and all(
        is_canonical_content_hash(value) for value in evidence_hashes
    )
    registry_valid = is_canonical_content_hash(result.node_registry_manifest_hash)
    available = (
        type(result.available) is bool
        and result.available
        and result.code is None
        and result.reason is None
        and result.remediation is None
        and result.strategy_spec_hash is not None
        and evidence_hashes_valid
        and registry_valid
        and required_valid
        and candidates_valid
        and required == declared
        and candidate_hashes == expected_hashes
    )
    return ExperimentPreflightCheck(
        rule_id="executor",
        outcome=PreflightOutcome.PASS if available else PreflightOutcome.FAIL,
        code=(
            None
            if available
            else (result.code if canonical_text(result.code) else None)
            or (
                "REPRODUCIBILITY_FAILED"
                if not evidence_hashes_valid or not registry_valid
                else "SPEC_INVALID"
            )
        ),
        reason=(
            None
            if available
            else (
                result.reason
                if canonical_text(result.reason)
                else "executor_or_dataset_evidence_mismatch"
            )
        ),
        remediation=(
            None
            if available or not canonical_text(result.remediation)
            else result.remediation
        ),
        observed={
            "available": result.available,
            "evidence_hashes_valid": evidence_hashes_valid,
            "node_registry_manifest_hash": result.node_registry_manifest_hash,
            "required_datasets": list(required),
            "candidate_hashes": list(candidate_hashes),
        },
        policy={
            "declared_datasets": list(declared),
            "expected_candidate_hashes": list(expected_hashes),
        },
    )


def certification_check(
    result: ResearchCertificationResult,
    request: ResearchCertificationRequest,
) -> ExperimentPreflightCheck:
    """Project normalized certification evidence into one exact hard gate."""
    declared = tuple(item.dataset_id for item in request.requirements)
    expected_sources = {
        snapshot_id
        for item in request.requirements
        for snapshot_id in item.expected_snapshot_ids
    }
    snapshot = result.snapshot_evidence
    snapshot_valid = (
        type(snapshot) is ResearchSnapshotEvidence
        and canonical_text(snapshot.snapshot_id)
        and canonical_text(snapshot.dataset_id)
        and is_canonical_content_hash(snapshot.manifest_hash)
        and canonical_text_tuple(snapshot.source_snapshot_ids, nonempty=True)
        and type(cast("object", snapshot.snapshot_start)) is date
        and type(cast("object", snapshot.snapshot_end)) is date
        and snapshot.snapshot_start <= request.required_from
        and snapshot.snapshot_end >= request.required_to
        and snapshot.snapshot_end >= snapshot.snapshot_start
        and canonical_text(snapshot.known_at_policy)
        and snapshot.known_at_policy in {"sample_time", "explicit_cutoff"}
        and canonical_text(snapshot.builder_version)
        and snapshot.snapshot_id == request.snapshot_identity.snapshot_id
        and snapshot.manifest_hash == request.snapshot_identity.manifest_hash
        and expected_sources.issubset(snapshot.source_snapshot_ids)
    )
    scalar_evidence_valid = (
        type(result.ready) is bool
        and canonical_text(result.profile)
        and canonical_text_tuple(result.dataset_ids, nonempty=True)
        and canonical_text_tuple(result.report_ids, nonempty=True)
        and canonical_text_tuple(result.reason_codes)
    )
    ready = (
        scalar_evidence_valid
        and result.ready
        and result.profile == R3_RESEARCH_CERTIFICATION_PROFILE
        and result.dataset_ids == declared
        and len(result.report_ids) == len(declared)
        and not result.reason_codes
        and snapshot_valid
    )
    return ExperimentPreflightCheck(
        rule_id="certification",
        outcome=PreflightOutcome.PASS if ready else PreflightOutcome.FAIL,
        code=None if ready else "SNAPSHOT_NOT_CERTIFIED",
        reason=None if ready else "certification_profile_or_interval_blocked",
        remediation=(None if ready else "certify every required dataset and snapshot"),
        observed={
            "ready": result.ready,
            "profile": result.profile,
            "dataset_ids": text_tuple_payload(result.dataset_ids),
            "report_ids": text_tuple_payload(result.report_ids),
            "reason_codes": text_tuple_payload(result.reason_codes),
            "snapshot_evidence": snapshot_payload(snapshot),
            "snapshot_evidence_valid": snapshot_valid,
        },
        policy={
            "profile": R3_RESEARCH_CERTIFICATION_PROFILE,
            "required_from": request.required_from.isoformat(),
            "required_to": request.required_to.isoformat(),
            "requirements": [item.as_payload() for item in request.requirements],
            "snapshot_identity": {
                "snapshot_id": request.snapshot_identity.snapshot_id,
                "manifest_hash": request.snapshot_identity.manifest_hash,
            },
        },
    )
