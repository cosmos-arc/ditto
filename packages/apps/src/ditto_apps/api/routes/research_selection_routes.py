"""Durable candidate preselection and one-shot holdout mutation routes."""

from __future__ import annotations

from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.candidate_selection import (
    CandidateSelectionCommand,
    CandidateSelectionHandler,
)
from ditto_application.commands.candidate_selection import (
    CandidateSelectionRequest as ApplicationCandidateSelectionRequest,
)
from ditto_application.commands.experiments import (
    ClaimHoldoutCandidateCommand,
    ClaimHoldoutCandidateHandler,
)
from ditto_application.exceptions import AppError
from ditto_application.processes.experiments.holdout import (
    ClaimHoldoutCandidateRequest,
    HoldoutSelectionReason,
)
from fastapi import APIRouter

from ditto_apps.api.errors import APIError
from ditto_apps.api.mutation_idempotency import IdempotencyKeyHeader
from ditto_apps.api.research_mutations import (
    candidate_selection_mutation_idempotency,
    holdout_evaluation_mutation_idempotency,
    mutation_occurred_at,
    raise_selection_holdout_error,
)
from ditto_apps.api.routes.research_experiment_routes import run_blocking
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    CandidateSelectionReceiptResponse,
    CandidateSelectionRequest,
    HoldoutEvaluationReceiptResponse,
    HoldoutEvaluationRequest,
)

router = APIRouter(prefix="/research/experiments", tags=["research"])


@router.post(
    "/{experiment_id}/candidate-selection",
    response_model=APIResponse[CandidateSelectionReceiptResponse],
    operation_id="design_research_candidate_selection",
)
@inject
async def select_experiment_candidate(
    experiment_id: str,
    request: CandidateSelectionRequest,
    handler: Annotated[CandidateSelectionHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[CandidateSelectionReceiptResponse]:
    """Persist one server-side preselection distinct from local comparison pins."""
    try:
        receipt = await run_blocking(
            handler.handle,
            CandidateSelectionCommand(
                ApplicationCandidateSelectionRequest(
                    experiment_id=experiment_id,
                    candidate_id=request.candidate_id,
                    comparison_payload_hash=request.comparison_payload_hash,
                    expected_revision=request.expected_revision,
                    rationale=request.rationale,
                    occurred_at=mutation_occurred_at(),
                    idempotency=candidate_selection_mutation_idempotency(
                        experiment_id,
                        request,
                        idempotency_key,
                    ),
                )
            ),
        )
    except AppError as exc:
        raise_selection_holdout_error(exc)
    return APIResponse(
        data=CandidateSelectionReceiptResponse(
            selection_id=receipt.selection_id,
            experiment_id=receipt.experiment_id,
            candidate_id=receipt.candidate_id,
            comparison_payload_hash=receipt.comparison_payload_hash,
            candidate_evidence_artifact_id=receipt.candidate_evidence_artifact_id,
            candidate_evidence_content_hash=receipt.candidate_evidence_content_hash,
            selection_evidence_content_hash=receipt.selection_evidence_content_hash,
            revision=receipt.experiment_revision,
            event_id=receipt.event_id,
            occurred_at=receipt.occurred_at,
        )
    )


@router.post(
    "/{experiment_id}/holdout-evaluations",
    response_model=APIResponse[HoldoutEvaluationReceiptResponse],
    operation_id="design_research_holdout_evaluations",
)
@inject
async def claim_experiment_holdout(
    experiment_id: str,
    request: HoldoutEvaluationRequest,
    handler: Annotated[ClaimHoldoutCandidateHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[HoldoutEvaluationReceiptResponse]:
    """Claim the one candidate referenced by a durable preselection event."""
    try:
        receipt = await run_blocking(
            handler.handle,
            ClaimHoldoutCandidateCommand(
                ClaimHoldoutCandidateRequest(
                    experiment_id=experiment_id,
                    candidate_id=request.candidate_id,
                    expected_revision=request.expected_revision,
                    expected_selection_evidence_hash=(
                        request.expected_selection_evidence_hash
                    ),
                    operator_confirmation=request.operator_confirmation,
                    selection_reason=HoldoutSelectionReason(
                        request.selection_reason.code,
                        request.selection_reason.summary,
                    ),
                    occurred_at=mutation_occurred_at(),
                    selection_id=request.selection_id,
                    expected_candidate_evidence_content_hash=(
                        request.expected_candidate_evidence_content_hash
                    ),
                    idempotency=holdout_evaluation_mutation_idempotency(
                        experiment_id,
                        request,
                        idempotency_key,
                    ),
                )
            ),
        )
    except AppError as exc:
        raise_selection_holdout_error(exc)
    if receipt.selection_id is None or receipt.candidate_evidence_content_hash is None:
        raise APIError(
            "holdout receipt omitted preselection evidence",
            status_code=500,
            error_code="HOLDOUT_RECEIPT_INVALID",
        )
    return APIResponse(
        data=HoldoutEvaluationReceiptResponse(
            claim_id=receipt.claim_id,
            selection_id=receipt.selection_id,
            experiment_id=receipt.experiment_id,
            candidate_id=receipt.candidate_id,
            state="claimed",
            fold_id=receipt.fold_id,
            logical_run_id=receipt.logical_run_id,
            reproduction_fingerprint=receipt.reproduction_fingerprint,
            claim_payload_hash=receipt.claim_payload_hash,
            selection_evidence_content_hash=receipt.selection_evidence_hash,
            candidate_evidence_content_hash=receipt.candidate_evidence_content_hash,
            revision=receipt.experiment_revision,
            event_id=receipt.event_id,
            occurred_at=receipt.occurred_at,
        )
    )
