"""
Research experiment REST routes exposing durable experiment truth.

Maturity: experimental — R3 research control-plane surface, gated by the
analysis-owned experiment query facade; no storage or execution I/O here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated, ParamSpec, TypeVar

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.experiments import (
    ExperimentDetailReadModel,
    ExperimentGateReadModel,
    ExperimentQueryFacade,
    ExperimentSummaryReadModel,
)
from fastapi import APIRouter

from ditto_apps.api.errors import NotFoundError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    ExperimentDetailResponse,
    ExperimentGateResponse,
    ExperimentSummaryResponse,
)

router = APIRouter(prefix="/research/experiments", tags=["research"])

P = ParamSpec("P")
R = TypeVar("R")


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run blocking application work off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def to_experiment_response(
    detail: ExperimentDetailReadModel,
) -> ExperimentDetailResponse:
    """将 ExperimentDetailReadModel 转 API 响应."""
    return ExperimentDetailResponse(
        experiment_id=detail.experiment_id,
        status=detail.status,
        stage=detail.stage,
        strategy_version=detail.strategy_version,
        strategy_spec_hash=detail.strategy_spec_hash,
        snapshot_id=detail.snapshot_id,
        candidate_count=detail.candidate_count,
        fold_count=detail.fold_count,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


def to_gate_response(gate: ExperimentGateReadModel) -> ExperimentGateResponse:
    """将 ExperimentGateReadModel 转 API 响应."""
    return ExperimentGateResponse(
        evaluation_id=gate.evaluation_id,
        rule_id=gate.rule_id,
        policy_version=gate.policy_version,
        layer=gate.layer,
        outcome=gate.outcome,
        artifact_id=gate.artifact_id,
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
