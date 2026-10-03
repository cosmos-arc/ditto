"""Industry rotation and saved SelectionRun HTTP routes."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.selection.assemble_facts import (
    AssembleSelectionFacts,
    AssembleSelectionFactsRequest,
)
from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
    CreateResearchCaseRequest,
)
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    SelectionFactorWeightDraft,
    SelectionWorkspaceFacade,
    StockSelectionSpecDraft,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_runs import SelectionRunQueryService
from fastapi import APIRouter, Path, Query, status

from ditto_apps.api.errors import NotFoundError, UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.selection import (
    AssembledSelectionRunResponse,
    AssembleSelectionRunBody,
    CreateResearchCaseBody,
    CreateSelectionRunBody,
    IndustryRotationResponse,
    ResearchCaseResponse,
    SelectionRunDiffResponse,
    SelectionRunResponse,
    SelectionWorkspaceReceiptResponse,
)

router = APIRouter(prefix="/selections", tags=["selections"])


def _raise_query_error(exc: AppQueryError) -> Never:
    reason = exc.details.get("reason")
    if reason in {"selection_run_not_found", "industry_rotation_not_found"}:
        raise NotFoundError(str(exc)) from exc
    raise UnprocessableEntityError(
        str(exc),
        error_code=str(reason or "SELECTION_QUERY_INVALID"),
    ) from exc


def _assembly_request(body: AssembleSelectionRunBody) -> AssembleSelectionFactsRequest:
    """Lift the policy-only transport body into the assembly process."""
    return AssembleSelectionFactsRequest(
        universe_id=body.universe_id,
        asset_kind=body.asset_kind,
        as_of=body.as_of,
        spec_id=body.spec_id,
        spec_version=body.spec_version,
        top_k=body.top_k,
        min_average_turnover=body.min_average_turnover,
        min_listing_days=body.min_listing_days,
        factor_weights=tuple(
            SelectionFactorWeightDraft(item.name, item.weight)
            for item in body.factor_weights
        ),
        excluded_limit_states=body.excluded_limit_states,
        knowledge_cutoff=body.knowledge_cutoff,
        publication_cutoff=body.publication_cutoff,
        seed=body.seed,
        lookback_days=body.lookback_days,
    )


def _assembled_body(assembled: CreateSelectionRunRequest) -> CreateSelectionRunBody:
    """Render the assembled request as its preview transport body."""
    payload = asdict(assembled)
    payload["selection_spec"]["asset_kind"] = (
        "stock"
        if isinstance(assembled.selection_spec, StockSelectionSpecDraft)
        else "etf"
    )
    return CreateSelectionRunBody.model_validate(payload)


@router.post(
    "/runs",
    response_model=APIResponse[SelectionWorkspaceReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="selections_create_run",
)
@inject
async def create_selection_run(
    body: AssembleSelectionRunBody,
    process: Annotated[AssembleSelectionFacts, FromComponent()],
    facade: Annotated[SelectionWorkspaceFacade, FromComponent()],
) -> APIResponse[SelectionWorkspaceReceiptResponse]:
    """
    Assemble every PIT fact server-side, then create the exact run.

    The client submits strategy parameters and allowed request identity
    only; client-authored fact packages are no longer an authoritative
    write surface. Re-posting one policy under unchanged data replays to
    the same content-addressed run.
    """
    try:
        assembled = await asyncio.to_thread(process.assemble, _assembly_request(body))
        receipt = await asyncio.to_thread(facade.create, assembled)
    except AppProcessError as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("reason", "SELECTION_RUN_INVALID")),
        ) from exc
    return APIResponse(data=SelectionWorkspaceReceiptResponse.model_validate(receipt))


@router.post(
    "/runs:assembled",
    response_model=APIResponse[AssembledSelectionRunResponse],
    operation_id="selections_assemble_run",
)
@inject
async def assemble_selection_run(
    body: AssembleSelectionRunBody,
    process: Annotated[AssembleSelectionFacts, FromComponent()],
) -> APIResponse[AssembledSelectionRunResponse]:
    """Assemble every PIT fact server-side and preview the exact create body."""
    try:
        assembled = await asyncio.to_thread(process.assemble, _assembly_request(body))
    except AppProcessError as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("reason", "SELECTION_ASSEMBLY_INVALID")),
        ) from exc
    return APIResponse(
        data=AssembledSelectionRunResponse(request=_assembled_body(assembled))
    )


@router.post(
    "/runs/{run_id}/research-cases",
    response_model=APIResponse[ResearchCaseResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="selections_create_research_case",
)
@inject
async def create_research_case(
    run_id: Annotated[str, Path(min_length=1)],
    body: CreateResearchCaseBody,
    process: Annotated[CreateResearchCaseFromSelection, FromComponent()],
) -> APIResponse[ResearchCaseResponse]:
    """Derive a stable Research Case from one exact saved SelectionRun."""
    try:
        value = await asyncio.to_thread(
            process.create,
            CreateResearchCaseRequest(
                selection_run_id=run_id,
                objective=body.objective,
                candidate_instrument_ids=body.candidate_instrument_ids,
            ),
        )
    except AppProcessError as exc:
        reason = str(exc.details.get("reason", "RESEARCH_CASE_INVALID"))
        if reason == "selection_run_not_found":
            raise NotFoundError(str(exc)) from exc
        raise UnprocessableEntityError(str(exc), error_code=reason) from exc
    return APIResponse(data=ResearchCaseResponse.model_validate(value))


@router.get(
    "/industry-rotations/{snapshot_id}",
    response_model=APIResponse[IndustryRotationResponse],
    operation_id="selections_get_industry_rotation",
)
@inject
async def get_industry_rotation(
    query: Annotated[IndustryRotationQueryService, FromComponent()],
    snapshot_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[IndustryRotationResponse]:
    """Read one exact persisted IndustryRotation snapshot by content identity."""
    try:
        value = await asyncio.to_thread(query.get, snapshot_id)
    except AppQueryError as exc:
        _raise_query_error(exc)
    return APIResponse(data=IndustryRotationResponse.model_validate(value))


@router.get(
    "/runs",
    response_model=APIResponse[tuple[SelectionRunResponse, ...]],
    operation_id="selections_list_runs",
)
@inject
async def list_selection_runs(
    query: Annotated[SelectionRunQueryService, FromComponent()],
    spec_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> APIResponse[tuple[SelectionRunResponse, ...]]:
    """List saved runs for one spec family, newest first."""
    try:
        values = await asyncio.to_thread(query.list_by_spec, spec_id, limit=limit)
    except AppQueryError as exc:
        _raise_query_error(exc)
    return APIResponse(
        data=tuple(SelectionRunResponse.model_validate(item) for item in values)
    )


@router.get(
    "/runs/{run_id}",
    response_model=APIResponse[SelectionRunResponse],
    operation_id="selections_get_run",
)
@inject
async def get_selection_run(
    query: Annotated[SelectionRunQueryService, FromComponent()],
    run_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[SelectionRunResponse]:
    """Read one exact saved SelectionRun by content identity."""
    try:
        value = await asyncio.to_thread(query.get, run_id)
    except AppQueryError as exc:
        _raise_query_error(exc)
    return APIResponse(data=SelectionRunResponse.model_validate(value))


@router.get(
    "/runs/{before_run_id}/compare/{after_run_id}",
    response_model=APIResponse[SelectionRunDiffResponse],
    operation_id="selections_compare_runs",
)
@inject
async def compare_selection_runs(
    query: Annotated[SelectionRunQueryService, FromComponent()],
    before_run_id: Annotated[str, Path(min_length=1)],
    after_run_id: Annotated[str, Path(min_length=1)],
) -> APIResponse[SelectionRunDiffResponse]:
    """Compare two exact saved runs, including previous-run why-in/out changes."""
    try:
        value = await asyncio.to_thread(
            query.compare,
            before_run_id,
            after_run_id,
        )
    except AppQueryError as exc:
        _raise_query_error(exc)
    return APIResponse(data=SelectionRunDiffResponse.model_validate(value))
