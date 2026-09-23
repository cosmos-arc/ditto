"""Exact unified portfolio comparison and read-only scenario routes."""

from __future__ import annotations

import asyncio
from datetime import UTC
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppQueryError,
)
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationRequest,
)
from ditto_application.queries.history_comparison import (
    GetHistoryComparisonQuery,
    HistoryComparisonRequest,
)
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
from fastapi import APIRouter, Query, status

from ditto_apps.api.errors import ConflictError, UnprocessableEntityError
from ditto_apps.api.mutation_idempotency import IdempotencyKeyHeader
from ditto_apps.models.common import APIResponse
from ditto_apps.models.portfolio_comparison import (
    ETFAllocationBody,
    ETFAllocationVersionResponse,
    HistoryComparisonQueryParams,
    HistoryComparisonResponse,
    ModelHistoryQueryParams,
    ModelHistoryResponse,
    PortfolioComparisonQueryParams,
    PortfolioComparisonResponse,
    PortfolioScenarioBody,
    PortfolioScenarioPreviewResponse,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get(
    "/etf-allocations/{allocation_id}/versions",
    response_model=APIResponse[list[ETFAllocationVersionResponse]],
    operation_id="portfolio_list_etf_allocation_versions",
)
@inject
async def list_etf_allocation_versions(
    allocation_id: str,
    command: Annotated[ETFAllocationCommand, FromComponent()],
) -> APIResponse[list[ETFAllocationVersionResponse]]:
    """Restore all saved versions of one ETF research allocation."""
    try:
        versions = await asyncio.to_thread(command.list_versions, allocation_id)
    except AppCommandError as exc:
        raise UnprocessableEntityError(
            str(exc), error_code="ETF_ALLOCATION_INVALID"
        ) from exc
    return APIResponse(
        data=[ETFAllocationVersionResponse.model_validate(item) for item in versions]
    )


@router.post(
    "/etf-allocations/{allocation_id}/versions",
    response_model=APIResponse[ETFAllocationVersionResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="portfolio_save_etf_allocation_version",
)
@inject
async def save_etf_allocation_version(
    allocation_id: str,
    body: ETFAllocationBody,
    idempotency_key: IdempotencyKeyHeader,
    command: Annotated[ETFAllocationCommand, FromComponent()],
) -> APIResponse[ETFAllocationVersionResponse]:
    """Save or replay one evidence-bound ETF research target."""
    if body.knowledge_cutoff.tzinfo is None:
        raise UnprocessableEntityError(
            "knowledge_cutoff needs a timezone", error_code="ETF_ALLOCATION_INVALID"
        )
    try:
        version = await asyncio.to_thread(
            command.save,
            ETFAllocationRequest(
                allocation_id=allocation_id,
                idempotency_key=idempotency_key,
                parent_version_id=body.parent_version_id,
                asof=body.asof.isoformat(),
                knowledge_cutoff=body.knowledge_cutoff.astimezone(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                source_snapshot_id=body.source_snapshot_id,
                instrument_ids=body.instrument_ids,
                mode=body.mode,
                cash_weight=body.cash_weight,
                max_position_weight=body.max_position_weight,
                manual_weights=body.manual_weights,
                reason=body.reason,
            ),
        )
    except AppConflictError as exc:
        raise ConflictError(str(exc), error_code="ETF_ALLOCATION_CONFLICT") from exc
    except (AppCommandError, AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc), error_code="ETF_ALLOCATION_INVALID"
        ) from exc
    return APIResponse(data=ETFAllocationVersionResponse.model_validate(version))


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


@router.get(
    "/history-comparison",
    response_model=APIResponse[HistoryComparisonResponse],
    operation_id="portfolio_get_history_comparison",
)
@inject
async def get_history_comparison(
    params: Annotated[HistoryComparisonQueryParams, Query()],
    query: Annotated[GetHistoryComparisonQuery, FromComponent()],
) -> APIResponse[HistoryComparisonResponse]:
    """Compose the three leg replays into one common-window comparison."""
    try:
        result = await asyncio.to_thread(
            query.history,
            HistoryComparisonRequest(
                strategy_id=params.strategy_id,
                paper_account_id=params.paper_account_id,
                paper_session_id=params.paper_session_id,
                manual_account_id=params.manual_account_id,
                start_date=params.start_date.isoformat(),
                end_date=params.end_date.isoformat(),
                model_initial_capital=params.model_initial_capital,
                knowledge_cutoff=params.knowledge_cutoff,
                publication_cutoff=params.publication_cutoff,
                source_snapshot_ids=tuple(params.source_snapshot_ids),
                model_artifact_ids=tuple(params.model_artifact_ids),
                paper_ledger_event_count=params.paper_ledger_event_count,
                paper_ledger_hash=params.paper_ledger_hash,
                manual_ledger_event_count=params.manual_ledger_event_count,
                manual_ledger_hash=params.manual_ledger_hash,
                benchmark_symbol=params.benchmark_symbol,
                benchmark_type=params.benchmark_type,
            ),
        )
    except (AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code=str(exc.details.get("code", "HISTORY_COMPARISON_INVALID"))
            if isinstance(exc, AppQueryError)
            else "HISTORY_COMPARISON_INVALID",
        ) from exc
    return APIResponse(data=HistoryComparisonResponse.model_validate(result))


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
