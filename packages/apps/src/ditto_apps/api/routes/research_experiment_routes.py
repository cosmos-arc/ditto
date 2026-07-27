"""
Research experiment REST routes exposing durable experiment truth.

Maturity: experimental — R3 research control-plane surface, gated by the
analysis-owned experiment query facade; no storage or execution I/O here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated, Never, ParamSpec, TypeVar, cast

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.commands.experiments import (
    CancelExperimentCommand,
    CancelExperimentHandler,
    PauseExperimentCommand,
    PauseExperimentHandler,
    ResumeExperimentCommand,
    ResumeExperimentHandler,
    RetryExperimentFoldCommand,
    RetryExperimentFoldHandler,
)
from ditto_application.exceptions import AppError
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)
from ditto_application.queries.experiments import (
    ExperimentCandidateReadModel,
    ExperimentDetailReadModel,
    ExperimentFoldReadModel,
    ExperimentGateReadModel,
    ExperimentQueryFacade,
    ExperimentSummaryReadModel,
)
from fastapi import APIRouter

from ditto_apps.api.errors import BadRequestError, ConflictError, NotFoundError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    ExperimentCandidateResponse,
    ExperimentControlReceiptResponse,
    ExperimentControlRequest,
    ExperimentDetailResponse,
    ExperimentFoldResponse,
    ExperimentGateResponse,
    ExperimentRetryFoldRequest,
    ExperimentSummaryResponse,
)

router = APIRouter(prefix="/research/experiments", tags=["research"])

P = ParamSpec("P")
R = TypeVar("R")
type JsonScalar = str | bool | int | float | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def _to_json_value(value: object) -> JsonValue:
    """Thaw application read values into JSON-native containers."""
    if isinstance(value, Mapping):
        return _to_json_mapping(cast("Mapping[object, object]", value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return [_to_json_value(item) for item in sequence]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("research read value must be JSON-compatible")


def _to_json_mapping[K, V](value: Mapping[K, V]) -> dict[str, JsonValue]:
    """Preserve typed string keys and fail closed on read-contract drift."""
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("research read value mapping key must be str")
        result[key] = _to_json_value(item)
    return result


def to_candidate_response(
    candidate: ExperimentCandidateReadModel,
) -> ExperimentCandidateResponse:
    """将 ExperimentCandidateReadModel 转 API 响应."""
    return ExperimentCandidateResponse(
        candidate_id=candidate.candidate_id,
        ordinal=candidate.ordinal,
        is_baseline=candidate.is_baseline,
        parameters=_to_json_mapping(candidate.parameters),
    )


def to_fold_response(fold: ExperimentFoldReadModel) -> ExperimentFoldResponse:
    """将 ExperimentFoldReadModel 转 API 响应."""
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
    """将 ExperimentDetailReadModel 转 API 响应."""
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
    )


def to_gate_response(gate: ExperimentGateReadModel) -> ExperimentGateResponse:
    """将 ExperimentGateReadModel 转 API 响应."""
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
        observed=_to_json_value(gate.observed),
        policy=_to_json_value(gate.policy),
        artifact_id=gate.artifact_id,
        payload_hash=gate.payload_hash,
        evaluated_at=gate.evaluated_at,
    )


def _to_summary_response(
    summary: ExperimentSummaryReadModel,
) -> ExperimentSummaryResponse:
    """将 ExperimentSummaryReadModel 转 API 响应."""
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


@router.get("", response_model=APIResponse[list[ExperimentSummaryResponse]])
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
)
@inject
async def list_experiment_gates(
    experiment_id: str,
    facade: Annotated[ExperimentQueryFacade, FromComponent()],
) -> APIResponse[list[ExperimentGateResponse]]:
    """列出实验的门禁评估."""
    gates = await run_blocking(facade.list_gate_evaluations, experiment_id)
    return APIResponse(data=[to_gate_response(gate) for gate in gates])


_CONTROL_NOT_FOUND_REASONS = frozenset({"experiment_not_found"})
_CONTROL_NOT_FOUND_KEYWORD = "not_found"
_CONTROL_CONFLICT_REASONS = frozenset(
    {
        "stale_projection_revision",
        "stale_fold_revision",
        "operator_request_rejected",
    }
)
_CONTROL_CONFLICT_PREFIXES = (
    "illegal_experiment_state",
    "terminal_fold_retry",
    "experiment_desired_state_mismatch",
)
_CONTROL_NOTIFICATION_FAILED = (
    "experiment control was persisted but notification failed"
)


def _now_utc() -> datetime:
    """Current UTC timestamp for one control event occurrence."""
    return datetime.now(UTC)


def _to_control_receipt_response(
    receipt: ExperimentControlReceipt,
) -> ExperimentControlReceiptResponse:
    """将 ExperimentControlReceipt 转 API 响应."""
    return ExperimentControlReceiptResponse(
        experiment_id=receipt.experiment_id,
        status=receipt.status,
        desired_state=receipt.desired_state,
        revision=receipt.revision,
        occurred_at=receipt.occurred_at,
        live_run_ids=list(receipt.live_run_ids),
    )


def _map_control_error(exc: AppError) -> Never:
    """Map one experiment control AppError to a stable API error by reason."""
    reason = str(exc.details.get("reason", ""))
    message = str(exc)
    if reason in _CONTROL_NOT_FOUND_REASONS or _CONTROL_NOT_FOUND_KEYWORD in reason:
        raise NotFoundError(message) from exc
    if (
        reason in _CONTROL_CONFLICT_REASONS
        or any(reason.startswith(prefix) for prefix in _CONTROL_CONFLICT_PREFIXES)
        or message == _CONTROL_NOTIFICATION_FAILED
    ):
        raise ConflictError(message) from exc
    raise BadRequestError(message) from exc


async def _run_control[C](
    handle: Callable[[C], ExperimentControlReceipt],
    command: C,
) -> ExperimentControlReceipt:
    """Run one control handler and map typed AppError to a stable API error."""
    try:
        return await run_blocking(handle, command)
    except AppError as exc:
        _map_control_error(exc)


@router.post(
    "/{experiment_id}/pause",
    response_model=APIResponse[ExperimentControlReceiptResponse],
)
@inject
async def pause_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[PauseExperimentHandler, FromComponent()],
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求暂停实验 (revision-fenced cooperative pause).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await _run_control(
        handler.handle,
        PauseExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=_now_utc(),
        ),
    )
    return APIResponse(data=_to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/cancel",
    response_model=APIResponse[ExperimentControlReceiptResponse],
)
@inject
async def cancel_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[CancelExperimentHandler, FromComponent()],
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求取消实验 (revision-fenced terminal cancel).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await _run_control(
        handler.handle,
        CancelExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=_now_utc(),
        ),
    )
    return APIResponse(data=_to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/resume",
    response_model=APIResponse[ExperimentControlReceiptResponse],
)
@inject
async def resume_experiment(
    experiment_id: str,
    request: ExperimentControlRequest,
    handler: Annotated[ResumeExperimentHandler, FromComponent()],
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求恢复实验 (revision-fenced resume of one paused experiment).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await _run_control(
        handler.handle,
        ResumeExperimentCommand(
            experiment_id=experiment_id,
            expected_revision=request.expected_revision,
            occurred_at=_now_utc(),
        ),
    )
    return APIResponse(data=_to_control_receipt_response(receipt))


@router.post(
    "/{experiment_id}/retry-fold",
    response_model=APIResponse[ExperimentControlReceiptResponse],
)
@inject
async def retry_fold_experiment(
    experiment_id: str,
    request: ExperimentRetryFoldRequest,
    handler: Annotated[RetryExperimentFoldHandler, FromComponent()],
) -> APIResponse[ExperimentControlReceiptResponse]:
    """
    请求重试一个失败 fold (revision-fenced successor attempt).

    expected_revision is the fold projection revision (not experiment revision).

    Maturity: experimental — R3 research control-plane surface.
    """
    receipt = await _run_control(
        handler.handle,
        RetryExperimentFoldCommand(
            experiment_id=experiment_id,
            candidate_id=request.candidate_id,
            fold_id=request.fold_id,
            expected_revision=request.expected_revision,
            occurred_at=_now_utc(),
        ),
    )
    return APIResponse(data=_to_control_receipt_response(receipt))
