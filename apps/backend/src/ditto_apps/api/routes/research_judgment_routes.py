"""Saved research judgment record and reopen routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppCommandError, AppQueryError
from ditto_application.processes.research.record_research_judgment import (
    RecordResearchJudgment,
    RecordResearchJudgmentRequest,
)
from ditto_application.queries.research_judgments import (
    ResearchJudgmentQueryService,
)
from fastapi import APIRouter, Path, Query, status

from ditto_apps.api.errors import NotFoundError, UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.research_judgment import (
    CreateResearchJudgmentBody,
    ResearchJudgmentResponse,
    ResearchJudgmentSummaryResponse,
)

router = APIRouter(prefix="/research/judgments", tags=["research"])


@router.post(
    "",
    response_model=APIResponse[ResearchJudgmentResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="research_record_research_judgment",
)
@inject
async def record_research_judgment(
    body: CreateResearchJudgmentBody,
    process: Annotated[RecordResearchJudgment, FromComponent()],
) -> APIResponse[ResearchJudgmentResponse]:
    """Append one immutable judgment bound to explicit compared run identities."""
    try:
        view = await asyncio.to_thread(
            process.record,
            RecordResearchJudgmentRequest(
                run_ids=body.run_ids,
                judgment=body.judgment,
                strategy_id=body.strategy_id,
                strategy_version=body.strategy_version,
            ),
        )
    except AppCommandError as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("code", "RESEARCH_JUDGMENT_INVALID")),
        ) from exc
    return APIResponse(data=ResearchJudgmentResponse.model_validate(view))


@router.get(
    "",
    response_model=APIResponse[tuple[ResearchJudgmentSummaryResponse, ...]],
    operation_id="research_list_research_judgments",
)
@inject
async def list_research_judgments(
    query: Annotated[ResearchJudgmentQueryService, FromComponent()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[tuple[ResearchJudgmentSummaryResponse, ...]]:
    """Reopen saved comparison conclusions by their exact run identities."""
    try:
        summaries = await asyncio.to_thread(query.list_recent, limit=limit)
    except AppQueryError as exc:
        _raise_judgment_query_error(exc)
    return APIResponse(
        data=tuple(
            ResearchJudgmentSummaryResponse.model_validate(item) for item in summaries
        )
    )


@router.get(
    "/{judgment_id}",
    response_model=APIResponse[ResearchJudgmentResponse],
    operation_id="research_get_research_judgment",
)
@inject
async def get_research_judgment(
    judgment_id: Annotated[str, Path(min_length=1)],
    query: Annotated[ResearchJudgmentQueryService, FromComponent()],
) -> APIResponse[ResearchJudgmentResponse]:
    """Reopen one exact judgment; newer runs never rewrite the saved conclusion."""
    try:
        view = await asyncio.to_thread(query.get, judgment_id)
    except AppQueryError as exc:
        _raise_judgment_query_error(exc)
    return APIResponse(data=ResearchJudgmentResponse.model_validate(view))


def _raise_judgment_query_error(exc: AppQueryError) -> Never:
    reason = str(exc.details.get("reason", "RESEARCH_JUDGMENT_INVALID"))
    if reason == "research_judgment_not_found":
        raise NotFoundError(str(exc)) from exc
    raise UnprocessableEntityError(str(exc), error_code=reason) from exc
