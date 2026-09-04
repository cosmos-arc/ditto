"""Industry rotation and saved SelectionRun HTTP routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, Never

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
    CreateResearchCaseRequest,
)
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    EtfSelectionSpecDraft,
    IndustryRotationObservationDraft,
    SelectionFactorValueDraft,
    SelectionFactorWeightDraft,
    SelectionInstrumentDraft,
    SelectionWorkspaceFacade,
    StockSelectionSpecDraft,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.selection_runs import SelectionRunQueryService
from fastapi import APIRouter, Path, Query, status

from ditto_apps.api.errors import NotFoundError, UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.selection import (
    CreateResearchCaseBody,
    CreateSelectionRunBody,
    IndustryRotationResponse,
    ResearchCaseResponse,
    SelectionRunDiffResponse,
    SelectionRunResponse,
    SelectionWorkspaceReceiptResponse,
    StockSelectionSpecRequest,
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


def _application_request(body: CreateSelectionRunBody) -> CreateSelectionRunRequest:
    spec = body.selection_spec
    weights = tuple(
        SelectionFactorWeightDraft(item.name, item.weight)
        for item in spec.factor_weights
    )
    if isinstance(spec, StockSelectionSpecRequest):
        selection_spec = StockSelectionSpecDraft(
            spec_id=spec.spec_id,
            spec_version=spec.spec_version,
            top_k=spec.top_k,
            min_average_turnover=spec.min_average_turnover,
            min_listing_days=spec.min_listing_days,
            factor_weights=weights,
            excluded_limit_states=spec.excluded_limit_states,
        )
    else:
        selection_spec = EtfSelectionSpecDraft(
            spec_id=spec.spec_id,
            spec_version=spec.spec_version,
            top_k=spec.top_k,
            min_average_turnover=spec.min_average_turnover,
            min_listing_days=spec.min_listing_days,
            factor_weights=weights,
            max_tracking_error=spec.max_tracking_error,
            excluded_limit_states=spec.excluded_limit_states,
        )
    return CreateSelectionRunRequest(
        as_of=body.as_of,
        knowledge_cutoff=body.knowledge_cutoff,
        publication_cutoff=body.publication_cutoff,
        rotation_source_snapshot_ids=body.rotation_source_snapshot_ids,
        market_context_feature_set_id=body.market_context_feature_set_id,
        membership_version=body.membership_version,
        rotation_algorithm_version=body.rotation_algorithm_version,
        industries=tuple(
            IndustryRotationObservationDraft(
                industry_id=item.industry_id,
                industry_name=item.industry_name,
                relative_strength_5d=item.relative_strength_5d,
                relative_strength_20d=item.relative_strength_20d,
                relative_strength_60d=item.relative_strength_60d,
                advancing_count=item.advancing_count,
                declining_count=item.declining_count,
                member_count=item.member_count,
                trend_score=item.trend_score,
                fundamental_score=item.fundamental_score,
                regime_alignment_score=item.regime_alignment_score,
            )
            for item in body.industries
        ),
        rotation_missing_inputs=body.rotation_missing_inputs,
        universe_snapshot_id=body.universe_snapshot_id,
        selection_source_snapshot_ids=body.selection_source_snapshot_ids,
        selection_spec=selection_spec,
        seed=body.seed,
        instruments=tuple(
            SelectionInstrumentDraft(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                industry_id=item.industry_id,
                factor_values=tuple(
                    SelectionFactorValueDraft(factor.name, factor.value)
                    for factor in item.factor_values
                ),
                average_turnover=item.average_turnover,
                is_st=item.is_st,
                is_suspended=item.is_suspended,
                listing_days=item.listing_days,
                limit_state=item.limit_state,
                tracking_error=item.tracking_error,
                declared_missing_inputs=item.declared_missing_inputs,
            )
            for item in body.instruments
        ),
    )


@router.post(
    "/runs",
    response_model=APIResponse[SelectionWorkspaceReceiptResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="selections_create_run",
)
@inject
async def create_selection_run(
    body: CreateSelectionRunBody,
    facade: Annotated[SelectionWorkspaceFacade, FromComponent()],
) -> APIResponse[SelectionWorkspaceReceiptResponse]:
    """Create or exactly replay a content-addressed industry and selection run."""
    try:
        receipt = await asyncio.to_thread(facade.create, _application_request(body))
    except AppProcessError as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("reason", "SELECTION_RUN_INVALID")),
        ) from exc
    return APIResponse(data=SelectionWorkspaceReceiptResponse.model_validate(receipt))


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
