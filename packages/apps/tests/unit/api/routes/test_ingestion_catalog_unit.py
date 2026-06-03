"""Ingestion catalog API route tests."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from ditto_application.queries.catalog import (
    CatalogAsset,
    CatalogAssetRef,
    CatalogMaturityPromotionHistoryItem,
    CatalogQueryFacade,
    CatalogSchemaFingerprint,
    CatalogSourceHealth,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthAttentionReasonCount,
    CatalogSourceHealthReport,
    CatalogSourceHealthStatusCount,
    CatalogSourceHealthSummaryReport,
    CatalogSourceSelectionCount,
)
from ditto_apps.api.routes import ingestion
from ditto_apps.models.common import APIResponse, PaginationRequest
from ditto_apps.models.ingestion import (
    CatalogAssetResponse,
    CatalogSourceHealthReportResponse,
    CatalogSourceHealthSummaryReportResponse,
    MaturityPromotionHistoryItem,
)
from fastapi.params import Query

_CatalogListRoute = Callable[..., Awaitable[APIResponse[list[CatalogAssetResponse]]]]
_CatalogGetRoute = Callable[..., Awaitable[APIResponse[CatalogAssetResponse]]]
_PromotionHistoryRoute = Callable[
    ...,
    Awaitable[APIResponse[list[MaturityPromotionHistoryItem]]],
]
_SourceHealthRoute = Callable[
    ...,
    Awaitable[APIResponse[CatalogSourceHealthReportResponse]],
]
_SourceHealthSummaryRoute = Callable[
    ...,
    Awaitable[APIResponse[CatalogSourceHealthSummaryReportResponse]],
]
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _inline_ingestion_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        return func(*args, **kwargs)

    monkeypatch.setattr(ingestion, "run_blocking", run_inline)


def _asset() -> CatalogAsset:
    return CatalogAsset(
        asset=CatalogAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-06-01",),
        ),
        storage_uri="stock_daily/2026",
        schema=CatalogSchemaFingerprint(
            schema_hash="schema:stock_daily:v1",
            row_count=17,
            created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        ),
        source="tushare",
        freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
    )


async def _call_list(
    facade: CatalogQueryFacade,
    *,
    namespace: str | None = None,
    dataset_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> APIResponse[list[CatalogAssetResponse]]:
    route = cast(
        _CatalogListRoute,
        getattr(
            ingestion.list_catalog_assets,
            "__dishka_orig_func__",
            ingestion.list_catalog_assets,
        ),
    )
    return await route(
        facade=facade,
        namespace=namespace,
        dataset_id=dataset_id,
        pagination=PaginationRequest(limit=limit, offset=offset),
    )


async def _call_get(
    facade: CatalogQueryFacade,
    *,
    namespace: str,
    dataset_id: str,
    partition_keys: list[str] | None = None,
) -> APIResponse[CatalogAssetResponse]:
    route = cast(
        _CatalogGetRoute,
        getattr(
            ingestion.get_catalog_asset,
            "__dishka_orig_func__",
            ingestion.get_catalog_asset,
        ),
    )
    return await route(
        facade=facade,
        namespace=namespace,
        dataset_id=dataset_id,
        partition_keys=partition_keys,
    )


async def _call_promotion_history(
    facade: CatalogQueryFacade,
    *,
    dataset_id: str,
) -> APIResponse[list[MaturityPromotionHistoryItem]]:
    route = cast(
        _PromotionHistoryRoute,
        getattr(
            ingestion.list_dataset_maturity_promotion_history,
            "__dishka_orig_func__",
            ingestion.list_dataset_maturity_promotion_history,
        ),
    )
    return await route(facade=facade, dataset_id=dataset_id)


async def _call_source_health_report(
    facade: CatalogQueryFacade,
    *,
    dataset_id: str,
    trade_date: str,
    available_sources: list[str] | None = None,
) -> APIResponse[CatalogSourceHealthReportResponse]:
    route = cast(
        _SourceHealthRoute,
        getattr(
            ingestion.get_catalog_source_health_report,
            "__dishka_orig_func__",
            ingestion.get_catalog_source_health_report,
        ),
    )
    return await route(
        facade=facade,
        dataset_id=dataset_id,
        trade_date=trade_date,
        available_sources=available_sources,
    )


async def _call_source_health_summary_report(
    facade: CatalogQueryFacade,
    *,
    dataset_ids: list[str],
    trade_dates: list[str],
    available_sources: list[str] | None = None,
) -> APIResponse[CatalogSourceHealthSummaryReportResponse]:
    route = cast(
        _SourceHealthSummaryRoute,
        getattr(
            ingestion.get_catalog_source_health_summary_report,
            "__dishka_orig_func__",
            ingestion.get_catalog_source_health_summary_report,
        ),
    )
    return await route(
        facade=facade,
        dataset_ids=dataset_ids,
        trade_dates=trade_dates,
        available_sources=available_sources,
    )


class TestListCatalogAssets:
    async def test_returns_catalog_assets_with_freshness_and_schema(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        facade.list_assets.return_value = [_asset()]

        response = await _call_list(
            facade,
            namespace="market",
            dataset_id="stock_daily",
        )

        assert response.pagination is not None
        assert response.pagination.total == 1
        item = response.data[0]
        assert item.asset.dataset_id == "stock_daily"
        assert item.asset.namespace == "market"
        assert item.asset.partition_keys == ["trade_date=2026-06-01"]
        assert item.storage_uri == "stock_daily/2026"
        assert item.schema_fingerprint.schema_hash == "schema:stock_daily:v1"
        assert item.schema_fingerprint.row_count == 17
        assert item.schema_fingerprint.created_at == "2026-06-01T09:30:00+00:00"
        assert item.source == "tushare"
        assert item.freshness_at == "2026-06-01T09:31:00+00:00"
        facade.list_assets.assert_called_once_with(
            namespace="market",
            dataset_id="stock_daily",
        )


class TestGetCatalogAsset:
    async def test_returns_exact_catalog_asset(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        facade.get_asset.return_value = _asset()

        response = await _call_get(
            facade,
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=["trade_date=2026-06-01"],
        )

        assert response.data.storage_uri == "stock_daily/2026"
        facade.get_asset.assert_called_once_with(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-06-01",),
        )

    def test_requires_namespace_and_dataset_id_query_params(self) -> None:
        route = getattr(
            ingestion.get_catalog_asset,
            "__dishka_orig_func__",
            ingestion.get_catalog_asset,
        )
        params = inspect.signature(route).parameters

        assert isinstance(params["namespace"].default, Query)
        assert params["namespace"].default.is_required()
        assert isinstance(params["dataset_id"].default, Query)
        assert params["dataset_id"].default.is_required()

    async def test_raises_not_found_for_missing_asset(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        facade.get_asset.return_value = None

        with pytest.raises(ingestion.NotFoundError):
            await _call_get(
                facade,
                namespace="market",
                dataset_id="stock_daily",
                partition_keys=["trade_date=2026-06-01"],
            )


class TestListMaturityPromotionHistory:
    async def test_returns_dataset_promotion_history(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        facade.list_maturity_promotion_history.return_value = [
            CatalogMaturityPromotionHistoryItem(
                dataset_id="stock_daily",
                action="promoted",
                previous_maturity="experimental",
                next_maturity="initial-focus",
                actor="architecture-review",
                action_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
                evidence_uri="ditto://evidence/stock_daily/runtime-tests",
                notes="all criteria approved",
            )
        ]

        response = await _call_promotion_history(facade, dataset_id="stock_daily")

        item = response.data[0]
        assert item.dataset_id == "stock_daily"
        assert item.action == "promoted"
        assert item.next_maturity == "initial-focus"
        assert item.action_at == "2026-06-01T13:00:00+00:00"
        facade.list_maturity_promotion_history.assert_called_once_with("stock_daily")


class TestGetCatalogSourceHealthReport:
    async def test_returns_source_selection_health_report(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        facade.get_source_health_report.return_value = CatalogSourceHealthReport(
            dataset_id="macro_indicators",
            namespace="macro",
            trade_date="2024-12-27",
            default_source="tushare",
            selected_source="fred",
            selected_freshness_status="missing",
            attention_reasons=(
                "selected_source_missing",
                "default_source_failover",
            ),
            unsupported_sources=(),
            failover_from_default=True,
            fallback_sources=("fred",),
            latest_revocation_reason="policy_regression",
            latest_revoked_by="data-governance",
            latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
            sources=(
                CatalogSourceHealth(
                    source="tushare",
                    supported=True,
                    freshness_status="stale",
                    freshness_sla_hours=72,
                    freshness_at=datetime(2026, 5, 28, 8, tzinfo=UTC),
                    storage_uri="macro/macro_indicators/2024-12-27",
                    schema_hash="schema:macro:v1",
                    row_count=1,
                ),
                CatalogSourceHealth(
                    source="fred",
                    supported=True,
                    freshness_status="missing",
                    freshness_sla_hours=72,
                ),
            ),
        )

        response = await _call_source_health_report(
            facade,
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=["tushare", "fred"],
        )

        assert response.data.dataset_id == "macro_indicators"
        assert response.data.selected_source == "fred"
        assert response.data.selected_freshness_status == "missing"
        assert response.data.attention_reasons == [
            "selected_source_missing",
            "default_source_failover",
        ]
        assert response.data.sources[0].source == "tushare"
        assert response.data.sources[0].freshness_status == "stale"
        assert response.data.sources[0].freshness_at == "2026-05-28T08:00:00+00:00"
        assert response.data.sources[0].storage_uri == (
            "macro/macro_indicators/2024-12-27"
        )
        assert response.data.sources[1].source == "fred"
        assert response.data.sources[1].freshness_status == "missing"
        assert response.data.unsupported_sources == []
        assert response.data.latest_revocation_reason == "policy_regression"
        assert response.data.latest_revoked_by == "data-governance"
        assert response.data.latest_revoked_at == "2026-06-02T09:30:00+00:00"
        facade.get_source_health_report.assert_called_once_with(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )


class TestGetCatalogSourceHealthSummaryReport:
    async def test_returns_aggregated_source_health_report(self) -> None:
        facade = MagicMock(spec=CatalogQueryFacade)
        macro_report = CatalogSourceHealthReport(
            dataset_id="macro_indicators",
            namespace="macro",
            trade_date="2024-12-27",
            default_source="tushare",
            selected_source="fred",
            selected_freshness_status="missing",
            attention_reasons=(
                "selected_source_missing",
                "default_source_failover",
            ),
            unsupported_sources=(),
            failover_from_default=True,
            fallback_sources=("fred",),
            latest_revocation_reason="policy_regression",
            latest_revoked_by="data-governance",
            latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
            sources=(
                CatalogSourceHealth(
                    source="tushare",
                    supported=True,
                    freshness_status="stale",
                    freshness_sla_hours=72,
                ),
                CatalogSourceHealth(
                    source="fred",
                    supported=True,
                    freshness_status="missing",
                    freshness_sla_hours=72,
                ),
            ),
        )
        facade.get_source_health_summary.return_value = (
            CatalogSourceHealthSummaryReport(
                dataset_ids=("macro_indicators", "stock_daily"),
                trade_dates=("2024-12-27",),
                available_sources=("tushare", "fred"),
                total_reports=2,
                status_counts=(
                    CatalogSourceHealthStatusCount(status="fresh", count=1),
                    CatalogSourceHealthStatusCount(status="stale", count=1),
                    CatalogSourceHealthStatusCount(status="missing", count=1),
                    CatalogSourceHealthStatusCount(status="not_applicable", count=0),
                ),
                selected_source_counts=(
                    CatalogSourceSelectionCount(source="fred", count=1),
                    CatalogSourceSelectionCount(source="tushare", count=1),
                ),
                attention_required=(
                    CatalogSourceHealthAttentionItem(
                        dataset_id="macro_indicators",
                        trade_date="2024-12-27",
                        selected_source="fred",
                        selected_freshness_status="missing",
                        attention_reasons=(
                            "selected_source_missing",
                            "default_source_failover",
                        ),
                        failover_from_default=True,
                        fallback_sources=("fred",),
                        latest_revocation_reason="policy_regression",
                        latest_revoked_by="data-governance",
                        latest_revoked_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                    ),
                ),
                reports=(macro_report,),
                failover_count=1,
                no_fallback_source_count=1,
                revoked_promotion_count=1,
                fallback_source_counts=(
                    CatalogSourceSelectionCount(source="fred", count=1),
                ),
                attention_reason_counts=(
                    CatalogSourceHealthAttentionReasonCount(
                        reason="default_source_failover",
                        count=1,
                    ),
                    CatalogSourceHealthAttentionReasonCount(
                        reason="selected_source_missing",
                        count=1,
                    ),
                ),
            )
        )

        response = await _call_source_health_summary_report(
            facade,
            dataset_ids=["macro_indicators", "stock_daily"],
            trade_dates=["2024-12-27"],
            available_sources=["tushare", "fred"],
        )

        assert response.data.total_reports == 2
        assert response.data.failover_count == 1
        assert response.data.no_fallback_source_count == 1
        assert response.data.revoked_promotion_count == 1
        assert response.data.fallback_source_counts[0].source == "fred"
        assert [
            (item.reason, item.count) for item in response.data.attention_reason_counts
        ] == [
            ("default_source_failover", 1),
            ("selected_source_missing", 1),
        ]
        assert [item.status for item in response.data.status_counts] == [
            "fresh",
            "stale",
            "missing",
            "not_applicable",
        ]
        assert response.data.status_counts[2].count == 1
        assert response.data.selected_source_counts[0].source == "fred"
        assert response.data.attention_required[0].dataset_id == "macro_indicators"
        assert response.data.attention_required[0].selected_freshness_status == (
            "missing"
        )
        assert response.data.attention_required[0].attention_reasons == [
            "selected_source_missing",
            "default_source_failover",
        ]
        assert response.data.attention_required[0].failover_from_default is True
        assert response.data.attention_required[0].fallback_sources == ["fred"]
        assert response.data.attention_required[0].latest_revocation_reason == (
            "policy_regression"
        )
        assert response.data.attention_required[0].latest_revoked_by == (
            "data-governance"
        )
        assert response.data.attention_required[0].latest_revoked_at == (
            "2026-06-02T09:30:00+00:00"
        )
        assert response.data.reports[0].selected_source == "fred"
        assert response.data.reports[0].selected_freshness_status == "missing"
        assert response.data.reports[0].attention_reasons == [
            "selected_source_missing",
            "default_source_failover",
        ]
        assert response.data.reports[0].failover_from_default is True
        assert response.data.reports[0].fallback_sources == ["fred"]
        assert response.data.reports[0].latest_revocation_reason == (
            "policy_regression"
        )
        facade.get_source_health_summary.assert_called_once_with(
            dataset_ids=("macro_indicators", "stock_daily"),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )
