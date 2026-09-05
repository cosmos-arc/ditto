"""Unit tests for backtest data lineage query route."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.lineage import (
    DataLineageAsset,
    DataLineageCatalogAsset,
    DataLineageCatalogAttentionAsset,
    DataLineageCatalogAttentionReasonCount,
    DataLineageCatalogAttentionSeverityCount,
    DataLineageCatalogFreshnessStatusCount,
    DataLineageCatalogRunReport,
    DataLineageCatalogStatusCount,
    DataLineageEvent,
    DataLineageGraph,
    DataLineageGraphEdge,
    DataLineageRef,
    DataLineageRunSummary,
    LineageQueryFacade,
)
from ditto_apps.api.routes import backtest_query_routes
from ditto_apps.models.common import APIResponse, PaginationRequest
from ditto_apps.models.lineage import (
    DataLineageCatalogRunReportResponse,
    DataLineageEventResponse,
    DataLineageGraphResponse,
    DataLineageRunResponse,
)

pytestmark = pytest.mark.asyncio

_Route = Callable[..., Awaitable[APIResponse[list[DataLineageEventResponse]]]]
_RunSummaryRoute = Callable[..., Awaitable[APIResponse[DataLineageRunResponse]]]
_CatalogRoute = Callable[
    ...,
    Awaitable[APIResponse[DataLineageCatalogRunReportResponse]],
]
_GraphRoute = Callable[..., Awaitable[APIResponse[DataLineageGraphResponse]]]


async def test_data_lineage_events_route_returns_asset_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route should expose data lineage events for a queried asset."""

    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(backtest_query_routes, "run_blocking", run_inline)
    route_func = getattr(backtest_query_routes, "get_data_lineage_events", None)
    assert route_func is not None
    route = cast(
        _Route,
        getattr(route_func, "__dishka_orig_func__", route_func),
    )
    facade = MagicMock(spec=LineageQueryFacade)
    facade.list_data_events_for_asset.return_value = (
        DataLineageEvent(
            run_id="run-001",
            operation="backtest",
            timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
            inputs=(
                DataLineageRef(
                    asset=DataLineageAsset(
                        namespace="market",
                        dataset_id="stock_daily",
                        partition_keys=("trade_date=2026-01-05",),
                    ),
                    role="market_data",
                ),
            ),
            outputs=(
                DataLineageRef(
                    asset=DataLineageAsset(
                        namespace="backtest",
                        dataset_id="backtest_report",
                        partition_keys=("run_id=run-001",),
                    ),
                    role="backtest_report",
                ),
            ),
        ),
    )

    response = await route(
        namespace="backtest",
        dataset_id="backtest_report",
        partition_keys=["run_id=run-001"],
        pagination=PaginationRequest(limit=20, offset=0),
        lineage_facade=facade,
    )

    facade.list_data_events_for_asset.assert_called_once_with(
        namespace="backtest",
        dataset_id="backtest_report",
        partition_keys=("run_id=run-001",),
    )
    assert response.data[0].run_id == "run-001"
    assert response.data[0].inputs[0].role == "market_data"
    assert response.data[0].outputs[0].asset.dataset_id == "backtest_report"
    assert response.pagination is not None
    assert response.pagination.total == 1


async def test_run_data_lineage_route_returns_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route should expose a run-centric data lineage summary."""

    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(backtest_query_routes, "run_blocking", run_inline)
    route_func = getattr(backtest_query_routes, "get_run_data_lineage", None)
    assert route_func is not None
    route = cast(
        _RunSummaryRoute,
        getattr(route_func, "__dishka_orig_func__", route_func),
    )
    input_asset = DataLineageAsset(
        namespace="market",
        dataset_id="stock_daily",
        partition_keys=("trade_date=2026-01-05",),
    )
    output_asset = DataLineageAsset(
        namespace="backtest",
        dataset_id="backtest_report",
        partition_keys=("run_id=run-001",),
    )
    event = DataLineageEvent(
        run_id="run-001",
        operation="backtest",
        timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
        inputs=(DataLineageRef(asset=input_asset, role="market_data"),),
        outputs=(DataLineageRef(asset=output_asset, role="backtest_report"),),
    )
    facade = MagicMock(spec=LineageQueryFacade)
    facade.get_data_lineage_for_run.return_value = DataLineageRunSummary(
        run_id="run-001",
        events=(event,),
        input_assets=(input_asset,),
        output_assets=(output_asset,),
    )

    response = await route(run_id="run-001", lineage_facade=facade)

    facade.get_data_lineage_for_run.assert_called_once_with("run-001")
    assert response.data.run_id == "run-001"
    assert response.data.events[0].operation == "backtest"
    assert response.data.input_assets[0].dataset_id == "stock_daily"
    assert response.data.output_assets[0].dataset_id == "backtest_report"


async def test_run_data_lineage_catalog_report_route_returns_catalog_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route should expose run lineage assets enriched with catalog metadata."""

    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(backtest_query_routes, "run_blocking", run_inline)
    route_func = getattr(
        backtest_query_routes,
        "get_run_data_lineage_catalog_report",
        None,
    )
    assert route_func is not None
    route = cast(
        _CatalogRoute,
        getattr(route_func, "__dishka_orig_func__", route_func),
    )
    input_asset = DataLineageAsset(
        namespace="market",
        dataset_id="stock_daily",
        partition_keys=("trade_date=2026-01-05",),
    )
    output_asset = DataLineageAsset(
        namespace="backtest",
        dataset_id="backtest_report",
        partition_keys=("run_id=run-001",),
    )
    event = DataLineageEvent(
        run_id="run-001",
        operation="backtest",
        timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=UTC),
        inputs=(DataLineageRef(asset=input_asset, role="market_data"),),
        outputs=(DataLineageRef(asset=output_asset, role="backtest_report"),),
    )
    facade = MagicMock(spec=LineageQueryFacade)
    facade.get_data_lineage_catalog_report_for_run.return_value = (
        DataLineageCatalogRunReport(
            run_id="run-001",
            events=(event,),
            input_assets=(
                DataLineageCatalogAsset(
                    asset=input_asset,
                    catalog_status="found",
                    storage_uri="stock_daily/2026-01-05.parquet",
                    source="tushare",
                    schema_hash="schema:stock_daily:v1",
                    row_count=128,
                    schema_created_at=datetime(2026, 1, 5, 9, 31, tzinfo=UTC),
                    freshness_at=datetime(2026, 1, 5, 9, 32, tzinfo=UTC),
                    freshness_status="fresh",
                    freshness_sla_hours=36,
                ),
            ),
            output_assets=(
                DataLineageCatalogAsset(
                    asset=output_asset,
                    catalog_status="missing",
                    freshness_status="not_applicable",
                ),
            ),
            catalog_status_counts=(
                DataLineageCatalogStatusCount(status="found", count=1),
                DataLineageCatalogStatusCount(status="missing", count=1),
                DataLineageCatalogStatusCount(status="not_configured", count=0),
            ),
            freshness_status_counts=(
                DataLineageCatalogFreshnessStatusCount(status="fresh", count=1),
                DataLineageCatalogFreshnessStatusCount(status="stale", count=0),
                DataLineageCatalogFreshnessStatusCount(status="missing", count=0),
                DataLineageCatalogFreshnessStatusCount(
                    status="not_applicable",
                    count=1,
                ),
            ),
            attention_required=(
                DataLineageCatalogAttentionAsset(
                    side="output",
                    attention_reasons=("catalog_missing",),
                    attention_severity="critical",
                    asset=DataLineageCatalogAsset(
                        asset=output_asset,
                        catalog_status="missing",
                    ),
                ),
            ),
            attention_reason_counts=(
                DataLineageCatalogAttentionReasonCount(
                    reason="catalog_missing",
                    count=1,
                ),
            ),
            attention_severity_counts=(
                DataLineageCatalogAttentionSeverityCount(
                    severity="critical",
                    count=1,
                ),
                DataLineageCatalogAttentionSeverityCount(
                    severity="warning",
                    count=0,
                ),
                DataLineageCatalogAttentionSeverityCount(
                    severity="info",
                    count=0,
                ),
            ),
        )
    )

    response = await route(run_id="run-001", lineage_facade=facade)

    facade.get_data_lineage_catalog_report_for_run.assert_called_once_with("run-001")
    assert response.data.run_id == "run-001"
    assert response.data.events[0].operation == "backtest"
    assert response.data.input_assets[0].catalog_status == "found"
    assert response.data.input_assets[0].storage_uri == "stock_daily/2026-01-05.parquet"
    assert response.data.input_assets[0].schema_hash == "schema:stock_daily:v1"
    assert response.data.input_assets[0].row_count == 128
    assert response.data.input_assets[0].freshness_at == "2026-01-05T09:32:00+00:00"
    assert response.data.input_assets[0].freshness_status == "fresh"
    assert response.data.input_assets[0].freshness_sla_hours == 36
    assert response.data.output_assets[0].catalog_status == "missing"
    assert response.data.output_assets[0].freshness_status == "not_applicable"
    assert [
        (item.status, item.count) for item in response.data.catalog_status_counts
    ] == [
        ("found", 1),
        ("missing", 1),
        ("not_configured", 0),
    ]
    assert [
        (item.status, item.count) for item in response.data.freshness_status_counts
    ] == [
        ("fresh", 1),
        ("stale", 0),
        ("missing", 0),
        ("not_applicable", 1),
    ]
    assert response.data.attention_required[0].side == "output"
    assert response.data.attention_required[0].asset.catalog_status == "missing"
    assert response.data.attention_required[0].attention_reasons == ["catalog_missing"]
    assert response.data.attention_required[0].attention_severity == "critical"
    assert [
        (item.reason, item.count) for item in response.data.attention_reason_counts
    ] == [("catalog_missing", 1)]
    assert [
        (item.severity, item.count) for item in response.data.attention_severity_counts
    ] == [
        ("critical", 1),
        ("warning", 0),
        ("info", 0),
    ]


async def test_run_data_lineage_catalog_report_route_returns_policy_effect_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route should pass source context and expose backend policy-effect counts."""

    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(backtest_query_routes, "run_blocking", run_inline)
    route_func = getattr(
        backtest_query_routes,
        "get_run_data_lineage_catalog_report",
        None,
    )
    assert route_func is not None
    route = cast(
        _CatalogRoute,
        getattr(route_func, "__dishka_orig_func__", route_func),
    )
    input_asset = DataLineageAsset(
        namespace="market",
        dataset_id="stock_daily",
        partition_keys=("trade_date=2026-06-01",),
    )
    event = DataLineageEvent(
        run_id="run-001",
        operation="backtest",
        timestamp=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        inputs=(DataLineageRef(asset=input_asset, role="market_data"),),
        outputs=(),
    )
    facade = MagicMock(spec=LineageQueryFacade)
    facade.get_data_lineage_catalog_report_for_run.return_value = SimpleNamespace(
        run_id="run-001",
        events=(event,),
        input_assets=(
            DataLineageCatalogAsset(
                asset=input_asset,
                catalog_status="found",
                source="tushare",
                freshness_status="fresh",
            ),
        ),
        output_assets=(),
        catalog_status_counts=(
            DataLineageCatalogStatusCount(status="found", count=1),
            DataLineageCatalogStatusCount(status="missing", count=0),
            DataLineageCatalogStatusCount(status="not_configured", count=0),
        ),
        freshness_status_counts=(
            DataLineageCatalogFreshnessStatusCount(status="fresh", count=1),
            DataLineageCatalogFreshnessStatusCount(status="stale", count=0),
            DataLineageCatalogFreshnessStatusCount(status="missing", count=0),
            DataLineageCatalogFreshnessStatusCount(
                status="not_applicable",
                count=0,
            ),
        ),
        attention_required=(),
        attention_reason_counts=(),
        attention_severity_counts=(
            DataLineageCatalogAttentionSeverityCount(
                severity="critical",
                count=0,
            ),
            DataLineageCatalogAttentionSeverityCount(
                severity="warning",
                count=0,
            ),
            DataLineageCatalogAttentionSeverityCount(
                severity="info",
                count=0,
            ),
        ),
        source_fallback_policy_effect_counts=(
            SimpleNamespace(
                policy_id="fallback-policy-001",
                policy_status="active",
                catalog_selected_source="tushare",
                effective_selected_source="fred",
                count=2,
            ),
        ),
    )

    response = await route(
        run_id="run-001",
        trade_dates=["2026-06-01"],
        available_sources=["tushare", "fred"],
        lineage_facade=facade,
    )

    facade.get_data_lineage_catalog_report_for_run.assert_called_once_with(
        "run-001",
        trade_dates=("2026-06-01",),
        available_sources=("tushare", "fred"),
    )
    assert [
        (
            item.policy_id,
            item.policy_status,
            item.catalog_selected_source,
            item.effective_selected_source,
            item.count,
        )
        for item in response.data.source_fallback_policy_effect_counts
    ] == [
        ("fallback-policy-001", "active", "tushare", "fred", 2),
    ]


async def test_data_lineage_graph_route_returns_asset_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route should expose an asset-centric lineage graph."""

    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(backtest_query_routes, "run_blocking", run_inline)
    route_func = getattr(backtest_query_routes, "get_data_lineage_graph", None)
    assert route_func is not None
    route = cast(
        _GraphRoute,
        getattr(route_func, "__dishka_orig_func__", route_func),
    )
    raw_asset = DataLineageAsset(namespace="market", dataset_id="raw_bars")
    clean_asset = DataLineageAsset(namespace="market", dataset_id="clean_bars")
    event = DataLineageEvent(
        run_id="run-001",
        operation="ingest",
        timestamp=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        inputs=(DataLineageRef(asset=raw_asset, role="source"),),
        outputs=(DataLineageRef(asset=clean_asset, role="dataset"),),
    )
    facade = MagicMock(spec=LineageQueryFacade)
    facade.get_data_lineage_graph_for_asset.return_value = DataLineageGraph(
        root=raw_asset,
        direction="downstream",
        max_depth=2,
        assets=(raw_asset, clean_asset),
        events=(event,),
        edges=(
            DataLineageGraphEdge(
                source=raw_asset,
                target=clean_asset,
                event=event,
            ),
        ),
    )

    response = await route(
        namespace="market",
        dataset_id="raw_bars",
        partition_keys=None,
        direction="downstream",
        max_depth=2,
        lineage_facade=facade,
    )

    facade.get_data_lineage_graph_for_asset.assert_called_once_with(
        namespace="market",
        dataset_id="raw_bars",
        partition_keys=(),
        direction="downstream",
        max_depth=2,
    )
    assert response.data.root.dataset_id == "raw_bars"
    assert response.data.direction == "downstream"
    assert response.data.assets[1].dataset_id == "clean_bars"
    assert response.data.edges[0].source.dataset_id == "raw_bars"
    assert response.data.edges[0].target.dataset_id == "clean_bars"
