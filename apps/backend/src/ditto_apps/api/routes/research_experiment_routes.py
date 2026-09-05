"""Experimental research experiment REST routes over application-owned truth."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, ParamSpec, TypeVar

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.experiments import (
    CancelExperimentCommand,
    CancelExperimentHandler,
    LaunchExperimentCommand,
    LaunchExperimentHandler,
    PauseExperimentCommand,
    PauseExperimentHandler,
    ResumeExperimentCommand,
    ResumeExperimentHandler,
    RetryExperimentFoldCommand,
    RetryExperimentFoldHandler,
)
from ditto_application.exceptions import AppError
from ditto_application.processes.experiments.comparison_reader import (
    ExperimentComparisonReader,
)
from ditto_application.processes.experiments.planning_process import (
    ExperimentPlanningProcess,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_application.processes.experiments.selection_evidence_reader import (
    ExperimentSelectionEvidenceReader,
)
from ditto_application.queries.experiments import (
    ExperimentQueryFacade,
)
from fastapi import APIRouter

from ditto_apps.api.errors import NotFoundError, UnprocessableEntityError
from ditto_apps.api.mutation_idempotency import (
    IdempotencyKeyHeader,
)
from ditto_apps.api.research_mutations import (
    control_mutation_idempotency,
    launch_mutation_idempotency,
    mutation_occurred_at,
    retry_fold_mutation_idempotency,
    run_research_control,
    to_control_receipt_response,
)
from ditto_apps.api.routes import research_experiment_transport as _transport
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    ExperimentArtifactResponse,
    ExperimentCandidateResponse,
    ExperimentComparisonResponse,
    ExperimentControlReceiptResponse,
    ExperimentControlRequest,
    ExperimentDetailResponse,
    ExperimentGateResponse,
    ExperimentLaunchRequest,
    ExperimentLaunchResponse,
    ExperimentPlanningRequest,
    ExperimentPreflightResponse,
    ExperimentRetryFoldRequest,
    ExperimentReviewPacketResponse,
    ExperimentSelectionEvidenceResponse,
    ExperimentSummaryResponse,
)

router = APIRouter(prefix="/research/experiments", tags=["research"])

P = ParamSpec("P")
R = TypeVar("R")

# Compatibility names retained for existing route-level consumers while transport
# projection ownership lives in the focused sibling module.
_raise_planning_error = _transport.raise_planning_error
_to_launch_response = _transport.to_launch_response
_to_preflight_response = _transport.to_preflight_response
_to_summary_response = _transport.to_summary_response
to_artifact_response = _transport.to_artifact_response
to_candidate_response = _transport.to_candidate_response
to_comparison_response = _transport.to_comparison_response
to_experiment_response = _transport.to_experiment_response
to_fold_response = _transport.to_fold_response
to_gate_response = _transport.to_gate_response
to_review_gate_outcome_response = _transport.to_review_gate_outcome_response
to_review_packet_response = _transport.to_review_packet_response
to_selection_evidence_response = _transport.to_selection_evidence_response
to_selection_trace_ref_response = _transport.to_selection_trace_ref_response


def _build_transport_planning_request(
    request: ExperimentPlanningRequest | ExperimentLaunchRequest,
) -> _transport.ApplicationExperimentPlanningRequest:
    """Decode via the route-level builder seam used by adapter tests."""
    return _transport.build_transport_planning_request(
        request,
        builder=build_experiment_planning_request,
    )


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


@router.post(
    "/{experiment_id}/preflight",
    response_model=APIResponse[ExperimentPreflightResponse],
    operation_id="research_preflight_experiment",
)
@inject
async def preflight_experiment(
    experiment_id: str,
    request: ExperimentPlanningRequest,
    process: Annotated[ExperimentPlanningProcess, FromComponent()],
) -> APIResponse[ExperimentPreflightResponse]:
    """Compute deterministic experiment eligibility without writing."""
    if experiment_id != request.experiment_id:
        raise UnprocessableEntityError(
            "path experiment_id must equal planning document experiment_id",
            error_code="SPEC_INVALID",
        )
    planning_request = _build_transport_planning_request(request)
    try:
        report = await run_blocking(process.preflight, planning_request)
    except AppError as exc:
        _raise_planning_error(exc)
    return APIResponse(data=_to_preflight_response(report))


@router.post(
    "",
    response_model=APIResponse[ExperimentLaunchResponse],
    operation_id="research_launch_experiment",
)
@inject
async def launch_experiment(
    request: ExperimentLaunchRequest,
    handler: Annotated[LaunchExperimentHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[ExperimentLaunchResponse]:
    """Rebuild and launch one exact operator-confirmed planning document."""
    planning_request = _build_transport_planning_request(request)
    try:
        receipt = await run_blocking(
            handler.handle,
            LaunchExperimentCommand(
                request=planning_request,
                confirmed_plan_hash=request.confirmed_plan_hash,
                idempotency=launch_mutation_idempotency(request, idempotency_key),
            ),
        )
    except AppError as exc:
        _raise_planning_error(exc)
    return APIResponse(data=_to_launch_response(receipt))


@router.get(
    "",
    response_model=APIResponse[list[ExperimentSummaryResponse]],
    operation_id="research_list_research_experiments",
)
@inject
async def list_research_experiments(
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[list[ExperimentSummaryResponse]]:
    """列出研究实验（newest first，不含候选/fold 展开）."""
    summaries = await run_blocking(facade.list_experiments)
    return APIResponse(data=[_to_summary_response(s) for s in summaries])


@router.get(
    "/{experiment_id}",
    response_model=APIResponse[ExperimentDetailResponse],
    operation_id="research_get_experiment",
)
@inject
async def get_experiment(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[ExperimentDetailResponse]:
    """获取实验详情."""
    detail = await run_blocking(facade.get, experiment_id)
    if detail is None:
        raise NotFoundError(f"Experiment not found: {experiment_id}")
    return APIResponse(data=to_experiment_response(detail))


@router.get(
    "/{experiment_id}/candidates",
    response_model=APIResponse[list[ExperimentCandidateResponse]],
    operation_id="research_list_experiment_candidates",
)
@inject
async def list_experiment_candidates(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[list[ExperimentCandidateResponse]]:
    """列出同一持久实验详情中的 immutable candidates."""
    detail = await run_blocking(facade.get, experiment_id)
    if detail is None:
        raise NotFoundError(f"Experiment not found: {experiment_id}")
    return APIResponse(
        data=[to_candidate_response(candidate) for candidate in detail.candidates]
    )


@router.get(
    "/{experiment_id}/gates",
    response_model=APIResponse[list[ExperimentGateResponse]],
    operation_id="research_list_experiment_gates",
)
@inject
async def list_experiment_gates(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[list[ExperimentGateResponse]]:
    """列出实验的门禁评估."""
    gates = await run_blocking(facade.list_gate_evaluations, experiment_id)
    return APIResponse(data=[to_gate_response(gate) for gate in gates])


@router.get(
    "/{experiment_id}/artifacts",
    response_model=APIResponse[list[ExperimentArtifactResponse]],
    operation_id="research_list_experiment_artifacts",
)
@inject
async def list_experiment_artifacts(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[list[ExperimentArtifactResponse]]:
    """列出实验的 immutable indexed artifacts（lineage order）."""
    detail = await run_blocking(facade.get, experiment_id)
    if detail is None:
        raise NotFoundError(f"Experiment not found: {experiment_id}")
    artifacts = await run_blocking(facade.list_artifacts, experiment_id)
    return APIResponse(data=[to_artifact_response(artifact) for artifact in artifacts])


@router.get(
    "/{experiment_id}/selection-evidence",
    response_model=APIResponse[ExperimentSelectionEvidenceResponse],
    operation_id="research_get_experiment_selection_evidence",
)
@inject
async def get_experiment_selection_evidence(
    experiment_id: str,
    reader: Annotated[ExperimentSelectionEvidenceReader, FromComponent()],
) -> APIResponse[ExperimentSelectionEvidenceResponse]:
    """读取实验已发布并验证的 selection-evidence ledger."""
    view = await run_blocking(reader.load_view, experiment_id)
    if view is None:
        raise NotFoundError(
            f"Selection evidence not found for experiment: {experiment_id}"
        )
    return APIResponse(data=to_selection_evidence_response(view))


@router.get(
    "/{experiment_id}/comparison",
    response_model=APIResponse[ExperimentComparisonResponse],
    operation_id="research_get_experiment_comparison",
)
@inject
async def get_experiment_comparison(
    experiment_id: str,
    reader: Annotated[ExperimentComparisonReader, FromComponent()],
) -> APIResponse[ExperimentComparisonResponse]:
    """
    读取实验的 candidate comparison（walk-forward 投影）.

    Maturity: experimental — R3 research control-plane surface.
    """
    view = await run_blocking(reader.load_comparison, experiment_id)
    if view is None:
        raise NotFoundError(f"Experiment not found: {experiment_id}")
    return APIResponse(data=to_comparison_response(view))


@router.get(
    "/{experiment_id}/review-packet",
    response_model=APIResponse[ExperimentReviewPacketResponse],
    operation_id="research_get_research_experiment_review_packet",
)
@inject
async def get_research_experiment_review_packet(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[ExperimentReviewPacketResponse]:
    """
    获取实验的 review packet（完整 hard gate + statistical evidence + lineage）.

    Maturity: experimental — R3 research control-plane surface.
    """
    packet = await run_blocking(facade.get_review_packet, experiment_id)
    if packet is None:
        raise NotFoundError(f"Review packet not found for experiment: {experiment_id}")
    return APIResponse(data=to_review_packet_response(packet))


@router.post(
    "/{experiment_id}/pause",
    response_model=APIResponse[ExperimentControlReceiptResponse],
    operation_id="research_pause_experiment",
)
@inject
async def pause_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[PauseExperimentHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求暂停实验 (revision-fenced cooperative pause).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await run_research_control(
        handler.handle,
        PauseExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=mutation_occurred_at(),
            idempotency=control_mutation_idempotency(
                "research_pause_experiment",
                experiment_id,
                request,
                idempotency_key,
            ),
        ),
        runner=run_blocking,
    )
    return APIResponse(data=to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/cancel",
    response_model=APIResponse[ExperimentControlReceiptResponse],
    operation_id="research_cancel_experiment",
)
@inject
async def cancel_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[CancelExperimentHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求取消实验 (revision-fenced terminal cancel).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await run_research_control(
        handler.handle,
        CancelExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=mutation_occurred_at(),
            idempotency=control_mutation_idempotency(
                "research_cancel_experiment",
                experiment_id,
                request,
                idempotency_key,
            ),
        ),
        runner=run_blocking,
    )
    return APIResponse(data=to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/resume",
    response_model=APIResponse[ExperimentControlReceiptResponse],
    operation_id="research_resume_experiment",
)
@inject
async def resume_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[ResumeExperimentHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求恢复实验 (revision-fenced resume of one paused experiment).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await run_research_control(
        handler.handle,
        ResumeExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=mutation_occurred_at(),
            idempotency=control_mutation_idempotency(
                "research_resume_experiment",
                experiment_id,
                request,
                idempotency_key,
            ),
        ),
        runner=run_blocking,
    )
    return APIResponse(data=to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/retry-fold",
    response_model=APIResponse[ExperimentControlReceiptResponse],
    operation_id="research_retry_fold_experiment",
)
@inject
async def retry_fold_experiment(
    experiment_id: str,
    request: ExperimentRetryFoldRequest,
    handler: Annotated[RetryExperimentFoldHandler, FromComponent()],
    idempotency_key: IdempotencyKeyHeader,
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求重试一个失败 fold (revision-fenced successor attempt).

    expected_revision is the fold projection revision (not experiment revision).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await run_research_control(
        handler.handle,
        RetryExperimentFoldCommand(
            experiment_id=experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
            expected_revision=request.expected_revision,
            occurred_at=mutation_occurred_at(),
            idempotency=retry_fold_mutation_idempotency(
                experiment_id,
                request,
                idempotency_key,
            ),
        ),
        runner=run_blocking,
    )
    return APIResponse(data=to_control_receipt_response(receipt))
