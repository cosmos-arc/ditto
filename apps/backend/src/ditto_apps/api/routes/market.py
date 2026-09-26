"""行情数据 API 路由."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.experiments.regime_diagnostics_reader import (
    RegimeDiagnosticsReader,
    RegimeDiagnosticsScope,
    RegimeDiagnosticsView,
    RegimeObservation,
)
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.market_chart import (
    MarketChartQueryFacade,
    MarketChartRequest,
)
from ditto_application.queries.market_context import (
    MarketContextFacade,
    MarketContextRequest,
    MarketContextView,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from fastapi import APIRouter, Query

from ditto_apps.api.errors import NotFoundError, UnprocessableEntityError
from ditto_apps.models.common import APIResponse
from ditto_apps.models.market import (
    Bar,
    BarsQuery,
    EtfNavPoint,
    EtfNavQuery,
    EtfNavResponse,
    IndicatorSeriesColumn,
    IndicatorSeriesQuery,
    IndicatorSeriesResponse,
    MarketChartQuery,
    MarketChartResponse,
    MarketContextDriverResponse,
    MarketContextImpactResponse,
    MarketContextMetricResponse,
    MarketContextResponse,
    RegimeDiagnosticsResponse,
    RegimeIndicatorResponse,
    RegimeObservationResponse,
    RegimeTransitionResponse,
    to_bar_list,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.post(
    "/chart",
    response_model=APIResponse[MarketChartResponse],
    operation_id="market_post_chart",
)
@inject
async def post_chart(
    query: MarketChartQuery,
    chart: Annotated[MarketChartQueryFacade, FromComponent()],
    metadata: Annotated[MetadataQueryFacade, FromComponent()],
) -> APIResponse[MarketChartResponse]:
    """Read exact retained price and calendar evidence for the chart."""
    instrument = await asyncio.to_thread(metadata.get_instrument, query.instrument_id)
    if instrument is None:
        raise NotFoundError("Instrument not found")
    try:
        view = await asyncio.to_thread(
            chart.get_chart,
            MarketChartRequest(
                instrument_id=query.instrument_id,
                asset_class=str(instrument["asset_class"]),
                start_date=query.start_date,
                end_date=query.end_date,
                period=query.period,
                adjustment=query.adjustment.value,
                allow_experimental_data=query.allow_experimental_data,
                now=datetime.now(UTC),
                delisted_on=date.fromisoformat(str(instrument["delist_date"]))
                if instrument.get("delist_date")
                else None,
                listed_on=date.fromisoformat(str(instrument["list_date"]))
                if instrument.get("list_date")
                else None,
            ),
        )
    except (AppQueryError, ValueError) as error:
        raise UnprocessableEntityError(
            str(error), error_code="MARKET_CHART_UNAVAILABLE"
        ) from error
    return APIResponse(data=MarketChartResponse.model_validate(view))


def _market_context_response(view: MarketContextView) -> MarketContextResponse:
    return MarketContextResponse(
        as_of=view.as_of,
        knowledge_cutoff=view.knowledge_cutoff,
        publication_cutoff=view.publication_cutoff,
        source_snapshot_ids=list(view.source_snapshot_ids),
        source_snapshot_set_id=view.source_snapshot_set_id,
        status=view.status,
        feature_set_id=view.feature_set_id,
        feature_version=view.feature_version,
        regime_label=view.regime_label,
        regime_score=view.regime_score,
        drivers=[
            MarketContextDriverResponse(
                name=item.name,
                category=item.category,
                contribution=item.contribution,
                direction=item.direction,
            )
            for item in view.drivers
        ],
        metrics=[
            MarketContextMetricResponse(
                name=item.name,
                category=item.category,
                value=item.value,
                unit=item.unit,
                trend=item.trend,
                freshness=item.freshness,
                evidence_ref=item.evidence_ref,
            )
            for item in view.metrics
        ],
        impacts=[
            MarketContextImpactResponse(
                target_domain=item.target_domain,
                target=item.target,
                direction=item.direction,
                rationale_driver=item.rationale_driver,
            )
            for item in view.impacts
        ],
        missing_inputs=list(view.missing_inputs),
        data_conflicts=list(view.data_conflicts),
        uncertainties=list(view.uncertainties),
        evidence_refs=list(view.evidence_refs),
    )


def _regime_observation(value: RegimeObservation) -> RegimeObservationResponse:
    return RegimeObservationResponse(
        observed_at=value.observed_at,
        score=value.score,
        label=value.label.value,
        position_ratio=value.position_ratio,
        indicators=[
            RegimeIndicatorResponse(
                name=indicator.name,
                normalized_score=indicator.normalized_score,
            )
            for indicator in value.indicators
        ],
    )


def _regime_response(view: RegimeDiagnosticsView) -> RegimeDiagnosticsResponse:
    return RegimeDiagnosticsResponse(
        snapshot_id=view.snapshot_id,
        snapshot_manifest_hash=view.snapshot_manifest_hash,
        dataset_id=view.dataset_id,
        source_snapshot_ids=list(view.source_snapshot_ids),
        builder_version=view.builder_version,
        known_at_policy=view.known_at_policy,
        benchmark_instrument_id=view.benchmark_instrument_id,
        start_date=view.start_date,
        end_date=view.end_date,
        knowledge_cutoff=view.knowledge_cutoff,
        model_id=view.model_id,
        lookback_observations=view.lookback_observations,
        bear_threshold=view.bear_threshold,
        bull_threshold=view.bull_threshold,
        bars_input_id=view.bars_input_id,
        bars_content_hash=view.bars_content_hash,
        bars_schema_hash=view.bars_schema_hash,
        current=_regime_observation(view.current),
        observations=[_regime_observation(item) for item in view.observations],
        transitions=[
            RegimeTransitionResponse(
                observed_at=item.observed_at,
                from_label=item.from_label.value,
                to_label=item.to_label.value,
            )
            for item in view.transitions
        ],
    )


@router.get(
    "/context",
    response_model=APIResponse[MarketContextResponse],
    operation_id="market_get_context",
)
@inject
async def get_market_context(
    facade: Annotated[MarketContextFacade, FromComponent()],
    as_of: datetime,
    knowledge_cutoff: datetime,
    publication_cutoff: datetime,
    source_snapshot_id: Annotated[list[str], Query(min_length=1)],
) -> APIResponse[MarketContextResponse]:
    """Read one market context from explicit immutable provider snapshots."""
    try:
        view = await asyncio.to_thread(
            facade.get_context,
            MarketContextRequest(
                as_of=as_of,
                knowledge_cutoff=knowledge_cutoff,
                publication_cutoff=publication_cutoff,
                source_snapshot_ids=tuple(source_snapshot_id),
            ),
        )
    except (AppQueryError, ValueError) as exc:
        raise UnprocessableEntityError(
            str(exc),
            error_code="MARKET_CONTEXT_INVALID",
        ) from exc
    return APIResponse(data=_market_context_response(view))


@router.get(
    "/regime",
    response_model=APIResponse[RegimeDiagnosticsResponse],
    operation_id="market_get_regime",
)
@inject
async def get_regime_diagnostics(
    reader: Annotated[RegimeDiagnosticsReader, FromComponent()],
    snapshot_id: Annotated[str, Query(min_length=1)],
    snapshot_manifest_hash: Annotated[str, Query(min_length=64, max_length=64)],
    benchmark_instrument_id: Annotated[int, Query(gt=0)],
    start_date: date,
    end_date: date,
    knowledge_cutoff: date,
) -> APIResponse[RegimeDiagnosticsResponse]:
    """Read regime observations only from one immutable PIT research snapshot."""
    try:
        view = await asyncio.to_thread(
            reader.read,
            RegimeDiagnosticsScope(
                snapshot_id=snapshot_id,
                snapshot_manifest_hash=snapshot_manifest_hash,
                benchmark_instrument_id=benchmark_instrument_id,
                start_date=start_date,
                end_date=end_date,
                knowledge_cutoff=knowledge_cutoff,
            ),
        )
    except AppProcessError as exc:
        raw_code = exc.details.get("code")
        error_code = (
            raw_code if isinstance(raw_code, str) else "REGIME_DIAGNOSTICS_INVALID"
        )
        raise UnprocessableEntityError(str(exc), error_code=error_code) from exc
    return APIResponse(data=_regime_response(view))


@router.post(
    "/bars", response_model=APIResponse[list[Bar]], operation_id="market_post_bars"
)
@inject
async def post_bars(
    query: BarsQuery,
    facade: Annotated[MarketQueryFacade, FromComponent()],
) -> APIResponse[list[Bar]]:
    """
    查询 K 线数据.

    Args:
        query: 查询参数
            - instrument_ids: 标的 ID 列表 (可选)
            - start_date: 开始日期 (可选)
            - end_date: 结束日期 (可选)
            - adjustment: 复权类型 (none/qfq/hfq)
            - asset_class: 资产类别过滤 (可选)
            - allow_experimental_data: 显式允许 experimental 数据集进入研究态查询
            - limit: 返回数量限制 (1-10000)
        facade: MarketQueryFacade 依赖注入

    Returns:
        APIResponse 包含 K 线数据列表

    """
    # 调用 facade（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        facade.find_bars,
        instrument_ids=query.instrument_ids or [],
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
        adj=query.adjustment.value,
        asset_class=query.asset_class,
        allow_experimental_data=query.allow_experimental_data,
    )

    # 转换为模型列表
    bars = to_bar_list(df)

    # 应用 limit
    bars = bars[: query.limit]

    return APIResponse(data=bars)


@router.post(
    "/indicator-series",
    response_model=APIResponse[IndicatorSeriesResponse],
    operation_id="market_post_indicator_series",
)
@inject
async def post_indicator_series(
    query: IndicatorSeriesQuery,
    facade: Annotated[MarketQueryFacade, FromComponent()],
) -> APIResponse[IndicatorSeriesResponse]:
    """
    查询叠加指标全序列（technical-analysis registry 既有公式）.

    maturity 门控与 /market/bars 一致；warm-up 段输出 null。
    """
    df = await asyncio.to_thread(
        facade.indicator_series,
        instrument_id=query.instrument_id,
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
        adj=query.adjustment.value,
        allow_experimental_data=query.allow_experimental_data,
        ma_windows=query.ma_windows,
        include=frozenset(query.indicators),
    )
    trade_dates = (
        df.get_column("trade_date").cast(str).to_list() if not df.is_empty() else []
    )
    window_by_name = {f"ma_{window}": window for window in query.ma_windows}
    series = [
        IndicatorSeriesColumn(
            name=name,
            window=window_by_name.get(name),
            values=df.get_column(name).to_list(),
        )
        for name in df.columns
        if name != "trade_date"
    ]
    return APIResponse(
        data=IndicatorSeriesResponse(
            instrument_id=query.instrument_id,
            adjustment=query.adjustment,
            registry_version="technical-indicator-registry.v1",
            trade_dates=trade_dates,
            series=series,
        )
    )


@router.post(
    "/etf-nav",
    response_model=APIResponse[EtfNavResponse],
    operation_id="market_post_etf_nav",
)
@inject
async def post_etf_nav(
    query: EtfNavQuery,
    facade: Annotated[MarketQueryFacade, FromComponent()],
) -> APIResponse[EtfNavResponse]:
    """
    查询 ETF 净值序列.

    数据不可得（读取器未配置或无数据）时返回空 points，由前端诚实降级。
    """
    df = await asyncio.to_thread(
        facade.get_etf_nav,
        instrument_id=query.instrument_id,
        start=query.start_date.isoformat() if query.start_date else None,
        end=query.end_date.isoformat() if query.end_date else None,
    )
    date_column = "nav_date" if "nav_date" in df.columns else "trade_date"
    points = [
        EtfNavPoint(nav_date=str(row[date_column]), nav=float(row["nav"]))
        for row in df.to_dicts()
        if row.get("nav") is not None
    ]
    return APIResponse(
        data=EtfNavResponse(instrument_id=query.instrument_id, points=points)
    )
