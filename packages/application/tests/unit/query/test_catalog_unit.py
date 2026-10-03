"""Tests for application-level DataCatalog query facade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog import (
    CatalogQueryFacade,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthSummaryReport,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)


def _entry(
    dataset_id: str,
    namespace: str,
    partition_keys: tuple[str, ...],
    *,
    storage_uri: str,
    freshness_at: datetime,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        ),
        storage_uri=storage_uri,
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}:v1",
            row_count=17,
            created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        ),
        source="tushare",
        freshness_at=freshness_at,
    )


class TestCatalogQueryFacadeListAssets:
    def test_lists_catalog_assets_with_schema_storage_and_freshness(self) -> None:
        catalog = InMemoryDataCatalog()
        target = _entry(
            "stock_daily",
            "market",
            ("trade_date=2026-06-01",),
            storage_uri="stock_daily/2026",
            freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        )
        catalog.upsert_asset(target)
        catalog.upsert_asset(
            _entry(
                "etf_daily",
                "market",
                ("trade_date=2026-06-01",),
                storage_uri="etf_daily/2026",
                freshness_at=datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
            )
        )
        facade = CatalogQueryFacade(catalog)

        result = facade.list_assets(namespace="market", dataset_id="stock_daily")

        assert len(result) == 1
        item = result[0]
        assert item.asset.dataset_id == "stock_daily"
        assert item.asset.namespace == "market"
        assert item.asset.partition_keys == ("trade_date=2026-06-01",)
        assert item.storage_uri == "stock_daily/2026"
        assert item.schema.schema_hash == "schema:stock_daily:v1"
        assert item.schema.row_count == 17
        assert item.source == "tushare"
        assert item.freshness_at == datetime(2026, 6, 1, 9, 31, tzinfo=UTC)

    def test_orders_assets_by_identity_for_stable_api_results(self) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _entry(
                "stock_daily",
                "market",
                ("trade_date=2026-06-02",),
                storage_uri="stock_daily/2026/02",
                freshness_at=datetime(2026, 6, 2, tzinfo=UTC),
            )
        )
        catalog.upsert_asset(
            _entry(
                "stock_daily",
                "market",
                ("trade_date=2026-06-01",),
                storage_uri="stock_daily/2026/01",
                freshness_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
        facade = CatalogQueryFacade(catalog)

        result = facade.list_assets(namespace="market")

        assert [item.asset.partition_keys for item in result] == [
            ("trade_date=2026-06-01",),
            ("trade_date=2026-06-02",),
        ]


class TestCatalogQueryFacadeGetAsset:
    def test_gets_exact_catalog_asset(self) -> None:
        catalog = InMemoryDataCatalog()
        entry = _entry(
            "stock_daily",
            "market",
            ("trade_date=2026-06-01",),
            storage_uri="stock_daily/2026",
            freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        )
        catalog.upsert_asset(entry)
        facade = CatalogQueryFacade(catalog)

        result = facade.get_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-06-01",),
        )

        assert result is not None
        assert result.storage_uri == "stock_daily/2026"
        assert result.schema.created_at == datetime(2026, 6, 1, 9, 30, tzinfo=UTC)

    def test_returns_none_for_missing_asset(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        result = facade.get_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-06-01",),
        )

        assert result is None


class TestCatalogQueryFacadeSourceHealth:
    def test_reports_source_freshness_and_selected_auto_source(self) -> None:
        with _evidence_support.evidence_stores() as stores:
            # tushare 请求过该日期但未完成 → stale;fred 无覆盖 → missing。
            stale_observed = datetime(2026, 6, 1, 12, tzinfo=UTC) - timedelta(hours=100)
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="a" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                observed_at=stale_observed,
                complete=False,
            )
            facade = CatalogQueryFacade(
                InMemoryDataCatalog(),
                snapshot_reader=stores.snapshots,
                lifecycle_reader=stores.lifecycle,
            )

            report = facade.get_source_health_report(
                dataset_id="macro_indicators",
                trade_date="2024-12-27",
                available_sources=("tushare", "fred"),
            )

        assert report.dataset_id == "macro_indicators"
        assert report.namespace == "macro"
        assert report.trade_date == "2024-12-27"
        assert report.default_source == "tushare"
        assert report.selected_source == "fred"
        assert report.selected_freshness_status == "missing"
        assert report.attention_reasons == (
            "selected_source_missing",
            "default_source_failover",
        )
        assert [source.source for source in report.sources] == ["tushare", "fred"]
        tushare, fred = report.sources
        assert tushare.supported is True
        assert tushare.freshness_status == "stale"
        # stale 源没有完成快照,证据字段保持空,只有状态可报。
        assert tushare.storage_uri is None
        assert tushare.row_count is None
        assert tushare.freshness_at is None
        assert fred.supported is True
        assert fred.freshness_status == "missing"
        assert fred.storage_uri is None
        assert fred.schema_hash is None
        assert report.unsupported_sources == ()
        assert report.selected_source_health.source == "fred"
        assert report.selected_source_health.supported is True
        assert report.selected_source_health.freshness_status == "missing"
        assert report.source_selection_status == "ready"
        assert report.source_selection_blockers == ()

    def test_reports_unsupported_source_attention_when_selected_source_is_fresh(
        self,
    ) -> None:
        with _evidence_support.evidence_stores() as stores:
            _evidence_support.commit_snapshot(
                stores,
                dataset="stock_daily",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="b" * 32,
                row_count=2300,
                schema_version="market.stock_daily.v1",
                observed_at=datetime(2026, 6, 1, 11, tzinfo=UTC),
            )
            facade = CatalogQueryFacade(
                InMemoryDataCatalog(),
                snapshot_reader=stores.snapshots,
                lifecycle_reader=stores.lifecycle,
            )

            report = facade.get_source_health_report(
                dataset_id="stock_daily",
                trade_date="2024-12-27",
                available_sources=("tushare", "fred"),
            )

        assert report.selected_source == "tushare"
        assert report.selected_freshness_status == "fresh"
        assert report.unsupported_sources == ("fred",)
        assert report.attention_reasons == ("unsupported_sources_present",)

    def test_reports_single_source_dataset_without_cross_source_fallback(self) -> None:
        with _evidence_support.evidence_stores() as stores:
            facade = CatalogQueryFacade(
                InMemoryDataCatalog(),
                snapshot_reader=stores.snapshots,
                lifecycle_reader=stores.lifecycle,
            )

            report = facade.get_source_health_report(
                dataset_id="stock_daily",
                trade_date="2024-12-27",
                available_sources=("tushare", "fred"),
            )

        assert report.default_source == "tushare"
        assert report.selected_source == "tushare"
        assert [source.source for source in report.sources] == ["tushare"]
        assert report.sources[0].freshness_status == "missing"
        assert report.unsupported_sources == ("fred",)

    def test_marks_selected_source_blocked_when_no_supported_source_is_available(
        self,
    ) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("fred",),
        )

        assert report.selected_source == "fred"
        assert report.sources == ()
        assert report.selected_source_health.source == "fred"
        assert report.selected_source_health.supported is False
        assert report.selected_source_health.freshness_status == "missing"
        assert report.source_selection_status == "blocked"
        assert report.source_selection_blockers == ("selected_source_unsupported",)

    def test_rejects_empty_available_sources(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="available_sources"):
            facade.get_source_health_report(
                dataset_id="stock_daily",
                trade_date="2024-12-27",
                available_sources=(),
            )


def _assert_source_health_summary_rollups(
    summary: CatalogSourceHealthSummaryReport,
) -> None:
    assert summary.dataset_ids == ("macro_indicators", "stock_daily")
    assert summary.trade_dates == ("2024-12-27",)
    assert summary.available_sources == ("tushare", "fred")
    assert summary.total_reports == 2
    assert summary.failover_count == 1
    assert summary.no_fallback_source_count == 1
    assert [(item.source, item.count) for item in summary.fallback_source_counts] == [
        ("fred", 1),
    ]
    assert [(item.status, item.count) for item in summary.status_counts] == [
        ("fresh", 1),
        ("stale", 1),
        ("missing", 1),
        ("not_applicable", 0),
    ]
    assert [(item.source, item.count) for item in summary.selected_source_counts] == [
        ("fred", 1),
        ("tushare", 1),
    ]
    assert [(item.reason, item.count) for item in summary.attention_reason_counts] == [
        ("default_source_failover", 1),
        ("selected_source_missing", 1),
        ("unsupported_sources_present", 1),
    ]
    assert [
        (item.severity, item.count) for item in summary.attention_severity_counts
    ] == [
        ("critical", 1),
        ("warning", 0),
        ("info", 1),
    ]


def _assert_macro_missing_attention(
    attention: CatalogSourceHealthAttentionItem,
) -> None:
    assert attention.dataset_id == "macro_indicators"
    assert attention.namespace == "macro"
    assert attention.trade_date == "2024-12-27"
    assert attention.default_source == "tushare"
    assert attention.selected_source == "fred"
    assert attention.selected_freshness_status == "missing"
    assert attention.selected_source_health.source == "fred"
    assert attention.selected_source_health.freshness_status == "missing"
    assert attention.selected_source_health.freshness_sla_hours == 72
    assert attention.selected_source_health.storage_uri is None
    assert attention.attention_reasons == (
        "selected_source_missing",
        "default_source_failover",
    )
    assert attention.attention_severity == "critical"
    assert attention.failover_from_default is True
    assert attention.fallback_sources == ("fred",)


def _assert_stock_unsupported_attention(
    attention: CatalogSourceHealthAttentionItem,
    storage_uri: str | None = None,
) -> None:
    assert attention.dataset_id == "stock_daily"
    assert attention.namespace == "market"
    assert attention.trade_date == "2024-12-27"
    assert attention.default_source == "tushare"
    assert attention.selected_source == "tushare"
    assert attention.selected_freshness_status == "fresh"
    assert attention.selected_source_health.source == "tushare"
    assert attention.selected_source_health.freshness_status == "fresh"
    assert attention.selected_source_health.storage_uri == storage_uri
    assert attention.selected_source_health.row_count == 2300
    assert attention.attention_reasons == ("unsupported_sources_present",)
    assert attention.attention_severity == "info"
    assert attention.unsupported_sources == ("fred",)


class TestCatalogQueryFacadeSourceHealthSummary:
    def test_summarizes_source_health_across_datasets_and_dates(self) -> None:
        with _evidence_support.evidence_stores() as stores:
            _evidence_support.commit_snapshot(
                stores,
                dataset="macro_indicators",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="c" * 32,
                row_count=1,
                schema_version="macro.macro_indicators.v1",
                namespace="macro",
                complete=False,
            )
            stock_snapshot = _evidence_support.commit_snapshot(
                stores,
                dataset="stock_daily",
                request_start="2024-12-27",
                request_end="2024-12-27",
                checksum="d" * 32,
                row_count=2300,
                schema_version="market.stock_daily.v1",
            )
            facade = CatalogQueryFacade(
                InMemoryDataCatalog(),
                snapshot_reader=stores.snapshots,
                lifecycle_reader=stores.lifecycle,
            )

            summary = facade.get_source_health_summary(
                dataset_ids=("macro_indicators", "stock_daily"),
                trade_dates=("2024-12-27",),
                available_sources=("tushare", "fred"),
            )

        _assert_source_health_summary_rollups(summary)
        assert len(summary.attention_required) == 2
        _assert_macro_missing_attention(summary.attention_required[0])
        _assert_stock_unsupported_attention(
            summary.attention_required[1], stock_snapshot.payload_uri
        )
        assert summary.reports[0].failover_from_default is True
        assert summary.reports[0].fallback_sources == ("fred",)
        assert summary.reports[1].failover_from_default is False
        assert summary.reports[1].fallback_sources == ()

    def test_summary_surfaces_blocked_source_selection_context(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        summary = facade.get_source_health_summary(
            dataset_ids=("stock_daily",),
            trade_dates=("2024-12-27",),
            available_sources=("fred",),
        )

        assert [
            (item.status, item.count) for item in summary.source_selection_status_counts
        ] == [
            ("ready", 0),
            ("blocked", 1),
        ]
        assert len(summary.attention_required) == 1
        attention = summary.attention_required[0]
        assert attention.source_selection_status == "blocked"
        assert attention.source_selection_blockers == ("selected_source_unsupported",)

    def test_rejects_empty_summary_inputs(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="dataset_ids"):
            facade.get_source_health_summary(
                dataset_ids=(),
                trade_dates=("2024-12-27",),
                available_sources=("tushare",),
            )

        with pytest.raises(AppQueryError, match="trade_dates"):
            facade.get_source_health_summary(
                dataset_ids=("stock_daily",),
                trade_dates=(),
                available_sources=("tushare",),
            )
