"""Exact unified portfolio comparison and read-only scenario routes."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.model_history import (
    GetModelHistoryQuery,
    ModelHistoryRequest,
)
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
)
from ditto_application.queries.portfolio_scenario import (
    PortfolioScenarioRequest,
    PreviewPortfolioScenarioQuery,
)
from fastapi import APIRouter, Query

from ditto_apps.api.errors import UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.portfolio_comparison import (
    ModelHistoryQueryParams,
    ModelHistoryResponse,
    PortfolioComparisonQueryParams,
    PortfolioComparisonResponse,
    PortfolioScenarioBody,
    PortfolioScenarioPreviewResponse,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _request(
    value: PortfolioComparisonQueryParams | PortfolioScenarioBody,
) -> PortfolioComparisonRequest:
    return PortfolioComparisonRequest(
        strategy_id=value.strategy_id,
        model_portfolio_id=value.model_portfolio_id,
        paper_account_id=value.paper_account_id,
        manual_account_id=value.manual_account_id,
        paper_session_id=value.paper_session_id,
        as_of=value.as_of.isoformat(),
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        source_snapshot_ids=tuple(value.source_snapshot_ids),
        valuation_snapshot_id=value.valuation_snapshot_id,
    )


@router.get(
    "/comparison",
    response_model=APIResponse[PortfolioComparisonResponse],
    operation_id="portfolio_get_comparison",
)
@inject
async def get_portfolio_comparison(
    params: Annotated[PortfolioComparisonQueryParams, Query()],
    query: Annotated[GetPortfolioComparisonQuery, FromComponent()],
) -> APIResponse[PortfolioComparisonResponse]:
    """Return a complete same-PIT three-column comparison or fail closed."""
    try:
        result = await asyncio.to_thread(
            query.get,
            _request(params),
        )
    except (AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("code", "PORTFOLIO_COMPARISON_INVALID"))
            if isinstance(exc, AppQueryError)
            else "PORTFOLIO_COMPARISON_INVALID",
        ) from exc
    return APIResponse(data=PortfolioComparisonResponse.model_validate(result))


@router.get(
    "/model-history",
    response_model=APIResponse[ModelHistoryResponse],
    operation_id="portfolio_get_model_history",
)
@inject
async def get_model_history(
    params: Annotated[ModelHistoryQueryParams, Query()],
    query: Annotated[GetModelHistoryQuery, FromComponent()],
) -> APIResponse[ModelHistoryResponse]:
    """Replay saved strategy targets into a cost-free historical series."""
    try:
        result = await asyncio.to_thread(
            query.history,
            ModelHistoryRequest(
                strategy_id=params.strategy_id,
                start_date=params.start_date.isoformat(),
                end_date=params.end_date.isoformat(),
                initial_capital=params.initial_capital,
                knowledge_cutoff=params.knowledge_cutoff,
                publication_cutoff=params.publication_cutoff,
                artifact_ids=tuple(params.artifact_ids),
            ),
        )
    except (AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("code", "MODEL_HISTORY_INVALID"))
            if isinstance(exc, AppQueryError)
            else "MODEL_HISTORY_INVALID",
        ) from exc
    return APIResponse(data=ModelHistoryResponse.model_validate(result))


@router.post(
    "/scenario-previews",
    response_model=APIResponse[PortfolioScenarioPreviewResponse],
    operation_id="portfolio_preview_scenario",
)
@inject
async def preview_portfolio_scenario(
    body: PortfolioScenarioBody,
    query: Annotated[PreviewPortfolioScenarioQuery, FromComponent()],
) -> APIResponse[PortfolioScenarioPreviewResponse]:
    """Preview deterministic target/risk changes without writing any portfolio."""
    try:
        result = await asyncio.to_thread(
            query.preview,
            PortfolioScenarioRequest(
                comparison=_request(body),
                baseline_kind=body.baseline_kind,
                excluded_instrument_ids=frozenset(body.excluded_instrument_ids),
                max_position_weight=body.max_position_weight,
                cash_reserve_weight=body.cash_reserve_weight,
                market_shock=body.market_shock,
                industry_shocks=body.industry_shocks,
            ),
        )
    except (AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("code", "PORTFOLIO_SCENARIO_INVALID"))
            if isinstance(exc, AppQueryError)
            else "PORTFOLIO_SCENARIO_INVALID",
        ) from exc
    return APIResponse(data=PortfolioScenarioPreviewResponse.model_validate(result))
