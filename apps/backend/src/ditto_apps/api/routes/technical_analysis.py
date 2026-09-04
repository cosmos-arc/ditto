"""Exact deterministic technical-analysis API."""

from __future__ import annotations

import asyncio
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisRequest,
    TechnicalAnalysisSpecDraft,
)
from fastapi import APIRouter

from ditto_apps.api.errors import UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.technical_analysis import (
    TechnicalAnalysisQueryBody,
    TechnicalAnalysisSnapshotResponse,
)

router = APIRouter(prefix="/technical-analysis", tags=["technical-analysis"])


@router.post(
    "/snapshots/query",
    response_model=APIResponse[TechnicalAnalysisSnapshotResponse],
    operation_id="technical_analysis_query",
)
@inject
async def query_technical_analysis(
    body: TechnicalAnalysisQueryBody,
    facade: Annotated[TechnicalAnalysisFacade, FromComponent()],
) -> APIResponse[TechnicalAnalysisSnapshotResponse]:
    """Compute one exact snapshot from retained, explicitly identified data."""
    spec = body.spec
    try:
        snapshot = await asyncio.to_thread(
            facade.get_snapshot,
            TechnicalAnalysisRequest(
                instrument_id=body.instrument_id,
                instrument_name=body.instrument_name,
                instrument_code=body.instrument_code,
                as_of=body.as_of,
                knowledge_cutoff=body.knowledge_cutoff,
                publication_cutoff=body.publication_cutoff,
                source_snapshot_ids=body.source_snapshot_ids,
                spec=TechnicalAnalysisSpecDraft(
                    spec_id=spec.spec_id,
                    spec_version=spec.spec_version,
                    algorithm_version=spec.algorithm_version,
                    timeframes=spec.timeframes,
                    return_window=spec.return_window,
                    trend_window=spec.trend_window,
                    slope_window=spec.slope_window,
                    rsi_window=spec.rsi_window,
                    macd_fast=spec.macd_fast,
                    macd_slow=spec.macd_slow,
                    macd_signal=spec.macd_signal,
                    atr_window=spec.atr_window,
                    volatility_window=spec.volatility_window,
                    volume_window=spec.volume_window,
                    donchian_window=spec.donchian_window,
                    support_resistance_window=spec.support_resistance_window,
                ),
                selection_run_id=body.selection_run_id,
                research_case_id=body.research_case_id,
                portfolio_snapshot_id=body.portfolio_snapshot_id,
            ),
        )
    except (AppQueryError, ValueError) as error:
        raise UnprocessableEntityError(
            str(error),
            error_code="TECHNICAL_ANALYSIS_INVALID",
        ) from error
    return APIResponse(data=TechnicalAnalysisSnapshotResponse.model_validate(snapshot))
