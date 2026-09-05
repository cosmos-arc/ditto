"""HTTP transport projections for research experiment application contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Never

from ditto_application.exceptions import AppError
from ditto_application.processes.experiments.comparison_reader import (
    CandidateComparisonView,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest as ApplicationExperimentPlanningRequest,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentLaunchReceipt,
    ExperimentPreflightReport,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_application.processes.experiments.selection_evidence_reader import (
    SelectionEvidenceView,
)
from ditto_application.queries.experiments import (
    ExperimentArtifactReadModel,
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
    ExperimentFoldReadModel,
    ExperimentGateReadModel,
    ExperimentReviewPacketReadModel,
    ExperimentSummaryReadModel,
    ReviewGateOutcome,
    ReviewSelectionTraceRef,
)

from ditto_apps.api.errors import APIError, ConflictError, UnprocessableEntityError
from ditto_apps.api.json_values import to_json_mapping, to_json_value
from ditto_apps.models.research import (
    ExperimentArtifactResponse,
    ExperimentCandidateResponse,
    ExperimentComparisonResponse,
    ExperimentDetailResponse,
    ExperimentFoldResponse,
    ExperimentGateResponse,
    ExperimentLaunchRequest,
    ExperimentLaunchResponse,
    ExperimentPlanningRequest,
    ExperimentPreflightCheckResponse,
    ExperimentPreflightResponse,
    ExperimentReviewPacketResponse,
    ExperimentSelectionEvidenceResponse,
    ExperimentSelectionStateResponse,
    ExperimentSummaryResponse,
    ReviewExposureWeightResponse,
    ReviewGateOutcomeResponse,
    ReviewSelectionExposureResponse,
    ReviewSelectionTraceRefResponse,
)

_PLANNING_CONFLICT_CODES = frozenset(
    {
        "PLAN_HASH_MISMATCH",
        "EXPERIMENT_ALREADY_EXISTS",
        "IDEMPOTENCY_KEY_REUSED",
    }
)
_PLANNING_UNPROCESSABLE_CODES = frozenset(
    {
        "BUDGET_EXCEEDED",
        "EXECUTOR_UNAVAILABLE",
        "HARD_GATE_FAILED",
        "INPUT_HASH_MISMATCH",
        "INSUFFICIENT_HISTORY",
        "MATRIX_TOO_LARGE",
        "PREFLIGHT_DETAIL_TOO_LARGE",
        "REPRODUCIBILITY_FAILED",
        "SNAPSHOT_NOT_CERTIFIED",
        "SPEC_INVALID",
        "VALIDATION_AUTHORITY_INVALID",
        "VALIDATION_AUTHORITY_MISMATCH",
        "WINDOW_LEAKAGE",
    }
)


def to_candidate_response(
    candidate: ExperimentCandidateReadModel,
) -> ExperimentCandidateResponse:
    """Project one application candidate read model to its HTTP DTO."""
    return ExperimentCandidateResponse(
        candidate_id=candidate.candidate_id,
        ordinal=candidate.ordinal,
        is_baseline=candidate.is_baseline,
        parameters=to_json_mapping(candidate.parameters),
    )


def to_fold_response(fold: ExperimentFoldReadModel) -> ExperimentFoldResponse:
    """Project one application fold read model to its HTTP DTO."""
    return ExperimentFoldResponse(
        candidate_id=fold.candidate_id,
        fold_id=fold.fold_id,
        ordinal=fold.ordinal,
        role=fold.role,
        status=fold.status,
        train_start=fold.train_start,
        train_end=fold.train_end,
        test_start=fold.test_start,
        test_end=fold.test_end,
        purge_sessions=fold.purge_sessions,
        embargo_sessions=fold.embargo_sessions,
        claim_owner_token=fold.claim_owner_token,
        revision=fold.revision,
        updated_at=fold.updated_at,
    )


def to_experiment_response(
    detail: ExperimentDetailReadModel,
) -> ExperimentDetailResponse:
    """Project one application experiment detail to its HTTP DTO."""
    selection = detail.selection_state
    return ExperimentDetailResponse(
        experiment_id=detail.experiment_id,
        research_cycle_id=detail.research_cycle_id,
        research_cycle_hash=detail.research_cycle_hash,
        strategy_version=detail.strategy_version,
        strategy_spec_hash=detail.strategy_spec_hash,
        snapshot_id=detail.snapshot_id,
        status=detail.status,
        desired_state=detail.desired_state,
        stage=detail.stage,
        failure_code=detail.failure_code,
        queue_ordinal=detail.queue_ordinal,
        revision=detail.revision,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        seed=detail.seed,
        worker_count=detail.worker_count,
        failure_policy=detail.failure_policy,
        candidate_limit=detail.candidate_limit,
        fold_run_limit=detail.fold_run_limit,
        fold_protocol_id=detail.fold_protocol_id,
        fold_protocol_version=detail.fold_protocol_version,
        fold_protocol_hash=detail.fold_protocol_hash,
        candidate_count=detail.candidate_count,
        fold_count=detail.fold_count,
        candidates=[
            to_candidate_response(candidate) for candidate in detail.candidates
        ],
        folds=[to_fold_response(fold) for fold in detail.folds],
        selection_state=(
            None
            if selection is None
            else ExperimentSelectionStateResponse(
                selection_id=selection.selection_id,
                experiment_id=selection.experiment_id,
                candidate_id=selection.candidate_id,
                comparison_payload_hash=selection.comparison_payload_hash,
                candidate_evidence_artifact_id=(
                    selection.candidate_evidence_artifact_id
                ),
                candidate_evidence_content_hash=(
                    selection.candidate_evidence_content_hash
                ),
                selection_evidence_content_hash=(
                    selection.selection_evidence_content_hash
                ),
                revision=selection.revision,
                event_id=selection.event_id,
                occurred_at=selection.occurred_at,
                holdout_claim_id=selection.holdout_claim_id,
            )
        ),
    )


def to_gate_response(gate: ExperimentGateReadModel) -> ExperimentGateResponse:
    """Project one gate evaluation without losing its lineage."""
    return ExperimentGateResponse(
        evaluation_id=gate.evaluation_id,
        experiment_id=gate.experiment_id,
        candidate_id=gate.candidate_id,
        fold_id=gate.fold_id,
        attempt_id=gate.attempt_id,
        rule_id=gate.rule_id,
        policy_version=gate.policy_version,
        layer=gate.layer,
        outcome=gate.outcome,
        observed=to_json_value(gate.observed),
        policy=to_json_value(gate.policy),
        artifact_id=gate.artifact_id,
        payload_hash=gate.payload_hash,
        evaluated_at=gate.evaluated_at,
    )


def to_artifact_response(
    artifact: ExperimentArtifactReadModel,
) -> ExperimentArtifactResponse:
    """Project one immutable indexed artifact to its HTTP DTO."""
    return ExperimentArtifactResponse(
        artifact_id=artifact.artifact_id,
        experiment_id=artifact.experiment_id,
        candidate_id=artifact.candidate_id,
        fold_id=artifact.fold_id,
        attempt_id=artifact.attempt_id,
        artifact_kind=artifact.artifact_kind,
        relative_path=artifact.relative_path,
        content_hash=artifact.content_hash,
        schema_hash=artifact.schema_hash,
        row_count=artifact.row_count,
        byte_size=artifact.byte_size,
        reproduction_fingerprint=artifact.reproduction_fingerprint,
        manifest=to_json_value(artifact.manifest),
        is_pinned=artifact.is_pinned,
        pinned_at=artifact.pinned_at,
        created_at=artifact.created_at,
        revision=artifact.revision,
    )


def to_selection_evidence_response(
    view: SelectionEvidenceView,
) -> ExperimentSelectionEvidenceResponse:
    """Project authenticated selection evidence to its HTTP DTO."""
    return ExperimentSelectionEvidenceResponse(
        artifact_id=view.artifact_id,
        experiment_id=view.experiment_id,
        content_hash=view.content_hash,
        byte_size=view.byte_size,
        is_pinned=view.is_pinned,
        created_at=view.created_at,
        payload=to_json_value(dict(view.payload)),
    )


def to_comparison_response(
    view: CandidateComparisonView,
) -> ExperimentComparisonResponse:
    """Project one candidate comparison to its HTTP DTO."""
    return ExperimentComparisonResponse(
        experiment_id=view.experiment_id,
        payload_hash=view.payload_hash,
        revision=view.revision,
        payload=to_json_value(dict(view.payload)),
    )


def to_summary_response(
    summary: ExperimentSummaryReadModel,
) -> ExperimentSummaryResponse:
    """Project one compact experiment summary to its HTTP DTO."""
    return ExperimentSummaryResponse(
        experiment_id=summary.experiment_id,
        status=summary.status,
        desired_state=summary.desired_state,
        stage=summary.stage,
        failure_code=summary.failure_code,
        queue_ordinal=summary.queue_ordinal,
        revision=summary.revision,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


def to_preflight_check_response(
    check: ExperimentPreflightCheck,
) -> ExperimentPreflightCheckResponse:
    """Project one deterministic application check without policy inference."""
    return ExperimentPreflightCheckResponse(
        rule_id=check.rule_id,
        outcome=check.outcome.value,
        code=check.code,
        reason=check.reason,
        remediation=check.remediation,
        observed=to_json_mapping(check.observed),
        policy=to_json_mapping(check.policy),
    )


def to_preflight_response(
    report: ExperimentPreflightReport,
) -> ExperimentPreflightResponse:
    """Project the complete preflight confirmation surface."""
    return ExperimentPreflightResponse(
        status=report.status.value,
        plan_hash=report.plan_hash,
        checks=[to_preflight_check_response(check) for check in report.checks],
        candidate_count=report.candidate_count,
        planned_fold_count=report.planned_fold_count,
        budget_run_count=report.budget_run_count,
        estimated_trading_sessions=report.estimated_trading_sessions,
        estimated_disk_bytes=report.estimated_disk_bytes,
        eligible_month_count=report.eligible_month_count,
        isolation_width_sessions=report.isolation_width_sessions,
    )


def to_launch_response(
    receipt: ExperimentLaunchReceipt,
) -> ExperimentLaunchResponse:
    """Project durable launch server truth, including exact replay receipts."""
    return ExperimentLaunchResponse(
        experiment_id=receipt.experiment_id,
        status=receipt.status,
        queue_ordinal=receipt.queue_ordinal,
        revision=receipt.revision,
        candidate_count=receipt.candidate_count,
        fold_count=receipt.fold_count,
        plan_hash=receipt.plan_hash,
    )


def raise_planning_error(exc: AppError) -> Never:
    """Map only application-owned planning error codes to HTTP semantics."""
    code = exc.details.get("code")
    if type(code) is not str:
        raise exc
    if code in _PLANNING_CONFLICT_CODES:
        raise ConflictError(str(exc), error_code=code) from exc
    if code in _PLANNING_UNPROCESSABLE_CODES:
        raise UnprocessableEntityError(str(exc), error_code=code) from exc
    raise APIError(str(exc), status_code=500, error_code=code) from exc


def build_transport_planning_request(
    request: ExperimentPlanningRequest | ExperimentLaunchRequest,
    *,
    builder: Callable[
        [Mapping[str, object]], ApplicationExperimentPlanningRequest
    ] = build_experiment_planning_request,
) -> ApplicationExperimentPlanningRequest:
    """Validate and decode one strict transport planning document."""
    exclude = (
        {"confirmed_plan_hash"} if type(request) is ExperimentLaunchRequest else None
    )
    document = request.model_dump(mode="python", exclude=exclude)
    try:
        return builder(document)
    except AppError as exc:
        raise_planning_error(exc)


def to_review_gate_outcome_response(
    outcome: ReviewGateOutcome,
) -> ReviewGateOutcomeResponse:
    """Project one review gate outcome to its HTTP DTO."""
    return ReviewGateOutcomeResponse(
        rule_id=outcome.rule_id,
        layer=outcome.layer,
        outcome=outcome.outcome,
    )


def to_selection_trace_ref_response(
    ref: ReviewSelectionTraceRef,
) -> ReviewSelectionTraceRefResponse:
    """Project one immutable selection trace reference to its HTTP DTO."""
    return ReviewSelectionTraceRefResponse(
        artifact_kind=ref.artifact_kind,
        artifact_id=ref.artifact_id,
        content_hash=ref.content_hash,
    )


def to_review_packet_response(
    packet: ExperimentReviewPacketReadModel,
) -> ExperimentReviewPacketResponse:
    """Project the complete application-owned review surface."""
    return ExperimentReviewPacketResponse(
        experiment_id=packet.experiment_id,
        candidate_id=packet.candidate_id,
        bundle_hash=packet.bundle_hash,
        hard_review_blocked=packet.hard_review_blocked,
        gate_outcomes=[
            to_review_gate_outcome_response(outcome) for outcome in packet.gate_outcomes
        ],
        schema_version=packet.schema_version,
        fold_ids=list(packet.fold_ids),
        attempt_ids=list(packet.attempt_ids),
        spec_hash=packet.spec_hash,
        resolved_spec_hash=packet.resolved_spec_hash,
        parameter_hash=packet.parameter_hash,
        snapshot_hash=packet.snapshot_hash,
        registry_hash=packet.registry_hash,
        objective_payload_hash=packet.objective_payload_hash,
        comparison_payload_hash=packet.comparison_payload_hash,
        r1_impact_payload_hash=packet.r1_impact_payload_hash,
        selection_evidence_artifact_id=packet.selection_evidence_artifact_id,
        holdout_claim_id=packet.holdout_claim_id,
        candidate_rationale=packet.candidate_rationale,
        selection_trace_artifact_refs=[
            to_selection_trace_ref_response(ref)
            for ref in packet.selection_trace_artifact_refs
        ],
        selection_exposure=(
            None
            if packet.selection_exposure is None
            else ReviewSelectionExposureResponse(
                applicability=packet.selection_exposure.applicability,
                lane=packet.selection_exposure.lane,
                industry_weights=[
                    ReviewExposureWeightResponse(key=item.key, weight=item.weight)
                    for item in packet.selection_exposure.industry_weights
                ],
                size_bucket_weights=[
                    ReviewExposureWeightResponse(key=item.key, weight=item.weight)
                    for item in packet.selection_exposure.size_bucket_weights
                ],
                artifact_refs=[
                    to_selection_trace_ref_response(ref)
                    for ref in packet.selection_exposure.artifact_refs
                ],
            )
        ),
    )
