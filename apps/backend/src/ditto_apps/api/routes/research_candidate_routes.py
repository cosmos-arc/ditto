"""Typed candidate trace drill-down routes over immutable evidence bundles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Annotated, Never, ParamSpec, TypeVar

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_evidence_reader import (
    CandidateEvidencePage,
    CandidateEvidenceReader,
    CandidateEvidenceResourceKind,
)
from fastapi import APIRouter, Query

from ditto_apps.api.errors import APIError, ConflictError, UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research import (
    CandidateExclusionEventResponse,
    CandidateExclusionPageResponse,
    CandidateFactorContributionPageResponse,
    CandidateFactorContributionResponse,
    CandidateSelectionEventResponse,
    CandidateSelectionPageResponse,
)

router = APIRouter(prefix="/research/candidates", tags=["research"])

P = ParamSpec("P")
R = TypeVar("R")


async def run_blocking[**P, R](
    func: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
) -> R:
    """Run verified artifact reads away from the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def _raise_read_error(exc: AppProcessError) -> Never:
    code = exc.details.get("code")
    error_code = code if isinstance(code, str) else "INTERNAL_ERROR"
    if error_code == "CANDIDATE_EVIDENCE_NOT_FOUND":
        raise APIError(str(exc), status_code=404, error_code=error_code) from exc
    if error_code == "EVIDENCE_STALE":
        raise ConflictError(str(exc), error_code=error_code) from exc
    if error_code in {
        "CANDIDATE_EXPERIMENT_MISMATCH",
        "INVALID_CANDIDATE_EVIDENCE_CURSOR",
        "INVALID_CANDIDATE_EVIDENCE_SCOPE",
    }:
        raise UnprocessableEntityError(str(exc), error_code=error_code) from exc
    raise APIError(str(exc), status_code=500, error_code=error_code) from exc


async def _page(
    reader: CandidateEvidenceReader,
    *,
    experiment_id: str,
    candidate_id: str,
    resource_kind: CandidateEvidenceResourceKind,
    cursor: str | None,
    limit: int,
) -> CandidateEvidencePage:
    try:
        return await run_blocking(
            reader.read_page,
            experiment_id=experiment_id,
            candidate_id=candidate_id,
            resource_kind=resource_kind,
            cursor=cursor,
            limit=limit,
        )
    except AppProcessError as exc:
        _raise_read_error(exc)


def _selection_item(item: Mapping[str, object]) -> CandidateSelectionEventResponse:
    return CandidateSelectionEventResponse.model_validate(dict(item))


def _exclusion_item(item: Mapping[str, object]) -> CandidateExclusionEventResponse:
    return CandidateExclusionEventResponse.model_validate(dict(item))


def _contribution_item(
    item: Mapping[str, object],
) -> CandidateFactorContributionResponse:
    return CandidateFactorContributionResponse.model_validate(dict(item))


@router.get(
    "/{candidate_id}/selections",
    response_model=APIResponse[CandidateSelectionPageResponse],
    operation_id="design_research_candidate_selections",
)
@inject
async def get_candidate_selections(
    candidate_id: str,
    reader: Annotated[CandidateEvidenceReader, FromComponent()],
    experiment_id: Annotated[str, Query(min_length=1)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[CandidateSelectionPageResponse]:
    """Read selected-instrument decisions from the current candidate bundle."""
    page = await _page(
        reader,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        resource_kind=CandidateEvidenceResourceKind.SELECTIONS,
        cursor=cursor,
        limit=limit,
    )
    return APIResponse(
        data=CandidateSelectionPageResponse(
            candidate_id=page.candidate_id,
            experiment_id=page.experiment_id,
            artifact_id=page.artifact_id,
            content_hash=page.content_hash,
            items=[_selection_item(item) for item in page.items],
            next_cursor=page.next_cursor,
        )
    )


@router.get(
    "/{candidate_id}/exclusions",
    response_model=APIResponse[CandidateExclusionPageResponse],
    operation_id="design_research_candidate_exclusions",
)
@inject
async def get_candidate_exclusions(
    candidate_id: str,
    reader: Annotated[CandidateEvidenceReader, FromComponent()],
    experiment_id: Annotated[str, Query(min_length=1)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[CandidateExclusionPageResponse]:
    """Read exclusion events from the current candidate bundle."""
    page = await _page(
        reader,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        resource_kind=CandidateEvidenceResourceKind.EXCLUSIONS,
        cursor=cursor,
        limit=limit,
    )
    return APIResponse(
        data=CandidateExclusionPageResponse(
            candidate_id=page.candidate_id,
            experiment_id=page.experiment_id,
            artifact_id=page.artifact_id,
            content_hash=page.content_hash,
            items=[_exclusion_item(item) for item in page.items],
            next_cursor=page.next_cursor,
        )
    )


@router.get(
    "/{candidate_id}/factor-contributions",
    response_model=APIResponse[CandidateFactorContributionPageResponse],
    operation_id="design_research_candidate_factor_contributions",
)
@inject
async def get_candidate_factor_contributions(
    candidate_id: str,
    reader: Annotated[CandidateEvidenceReader, FromComponent()],
    experiment_id: Annotated[str, Query(min_length=1)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[CandidateFactorContributionPageResponse]:
    """Read factor contributions from the current candidate bundle."""
    page = await _page(
        reader,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        resource_kind=CandidateEvidenceResourceKind.FACTOR_CONTRIBUTIONS,
        cursor=cursor,
        limit=limit,
    )
    return APIResponse(
        data=CandidateFactorContributionPageResponse(
            candidate_id=page.candidate_id,
            experiment_id=page.experiment_id,
            artifact_id=page.artifact_id,
            content_hash=page.content_hash,
            items=[_contribution_item(item) for item in page.items],
            next_cursor=page.next_cursor,
        )
    )
