"""Tests for application-level DataCatalog query facade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog import CatalogQueryFacade
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.promotion import DatasetMaturityPromotionEvent


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


class _MaturityPromotionHistoryReader:
    def __init__(
        self,
        events_by_dataset: dict[str, tuple[DatasetMaturityPromotionEvent, ...]],
    ) -> None:
        self._events_by_dataset = events_by_dataset

    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        return self._events_by_dataset.get(dataset_id, ())


class TestCatalogQueryFacadePromotionHistory:
    def test_lists_dataset_maturity_promotion_history(self) -> None:
        promoted = DatasetMaturityPromotionEvent(
            dataset_id="stock_daily",
            action="promoted",
            previous_maturity="experimental",
            next_maturity="initial-focus",
            actor="architecture-review",
            action_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            notes="all criteria approved",
        )
        revoked = DatasetMaturityPromotionEvent(
            dataset_id="stock_daily",
            action="revoked",
            previous_maturity="initial-focus",
            next_maturity="experimental",
            actor="architecture-review",
            action_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            revocation_reason="failed_revalidation",
            notes="PIT regression reopened promotion",
        )
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {"stock_daily": (promoted, revoked)}
            ),
        )

        result = facade.list_maturity_promotion_history("stock_daily")

        assert len(result) == 2
        assert result[0].dataset_id == "stock_daily"
        assert result[0].action == "promoted"
        assert result[0].previous_maturity == "experimental"
        assert result[0].next_maturity == "initial-focus"
        assert result[0].actor == "architecture-review"
        assert result[0].evidence_uri == "ditto://evidence/stock_daily/runtime-tests"
        assert result[1].action == "revoked"
        assert result[1].revocation_reason == "failed_revalidation"


class TestCatalogQueryFacadeSourceHealth:
    def test_reports_source_freshness_and_selected_auto_source(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(schema_hash="stale", row_count=1),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

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
        assert tushare.storage_uri == "macro/macro_indicators/2024-12-27"
        assert tushare.schema_hash == "stale"
        assert tushare.row_count == 1
        assert tushare.freshness_at == now - timedelta(hours=100)
        assert fred.supported is True
        assert fred.freshness_status == "missing"
        assert fred.storage_uri is None
        assert fred.schema_hash is None
        assert report.unsupported_sources == ()

    def test_reports_latest_revocation_context_with_source_health(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "macro_indicators": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="macro_indicators",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/macro/pit",
                            revocation_reason="policy_regression",
                            notes="source health must surface maturity reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        report = facade.get_source_health_report(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.latest_revocation_reason == "policy_regression"
        assert report.latest_revoked_by == "data-governance"
        assert report.latest_revoked_at == datetime(2026, 6, 2, 9, 30, tzinfo=UTC)

    def test_reports_unsupported_source_attention_when_selected_source_is_fresh(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.selected_source == "tushare"
        assert report.selected_freshness_status == "fresh"
        assert report.unsupported_sources == ("fred",)
        assert report.attention_reasons == ("unsupported_sources_present",)

    def test_reports_revocation_attention_when_selected_source_is_fresh(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(
            catalog,
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "stock_daily": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/stock_daily/pit",
                            revocation_reason="failed_revalidation",
                            notes="fresh source data still carries promotion reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("tushare",),
        )

        assert report.selected_source == "tushare"
        assert report.selected_freshness_status == "fresh"
        assert report.latest_revocation_reason == "failed_revalidation"
        assert report.attention_reasons == ("latest_maturity_promotion_revoked",)

    def test_reports_single_source_dataset_without_cross_source_fallback(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(InMemoryDataCatalog(), now=lambda: now)

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

    def test_rejects_empty_available_sources(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="available_sources"):
            facade.get_source_health_report(
                dataset_id="stock_daily",
                trade_date="2024-12-27",
                available_sources=(),
            )


class TestCatalogQueryFacadeSourceHealthSummary:
    def test_summarizes_source_health_across_datasets_and_dates(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:macro:v1", row_count=1
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        summary = facade.get_source_health_summary(
            dataset_ids=("macro_indicators", "stock_daily"),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )

        assert summary.dataset_ids == ("macro_indicators", "stock_daily")
        assert summary.trade_dates == ("2024-12-27",)
        assert summary.available_sources == ("tushare", "fred")
        assert summary.total_reports == 2
        assert summary.failover_count == 1
        assert summary.no_fallback_source_count == 1
        assert [
            (item.source, item.count) for item in summary.fallback_source_counts
        ] == [
            ("fred", 1),
        ]
        assert [(item.status, item.count) for item in summary.status_counts] == [
            ("fresh", 1),
            ("stale", 1),
            ("missing", 1),
            ("not_applicable", 0),
        ]
        assert [
            (item.source, item.count) for item in summary.selected_source_counts
        ] == [
            ("fred", 1),
            ("tushare", 1),
        ]
        assert [
            (item.reason, item.count) for item in summary.attention_reason_counts
        ] == [
            ("default_source_failover", 1),
            ("selected_source_missing", 1),
            ("unsupported_sources_present", 1),
        ]
        assert len(summary.attention_required) == 2
        attention = summary.attention_required[0]
        assert attention.dataset_id == "macro_indicators"
        assert attention.trade_date == "2024-12-27"
        assert attention.selected_source == "fred"
        assert attention.selected_freshness_status == "missing"
        assert attention.attention_reasons == (
            "selected_source_missing",
            "default_source_failover",
        )
        assert attention.failover_from_default is True
        assert attention.fallback_sources == ("fred",)
        assert attention.latest_revocation_reason is None
        unsupported_attention = summary.attention_required[1]
        assert unsupported_attention.dataset_id == "stock_daily"
        assert unsupported_attention.trade_date == "2024-12-27"
        assert unsupported_attention.selected_source == "tushare"
        assert unsupported_attention.selected_freshness_status == "fresh"
        assert unsupported_attention.attention_reasons == (
            "unsupported_sources_present",
        )
        assert unsupported_attention.unsupported_sources == ("fred",)
        assert summary.reports[0].failover_from_default is True
        assert summary.reports[0].fallback_sources == ("fred",)
        assert summary.reports[1].failover_from_default is False
        assert summary.reports[1].fallback_sources == ()

    def test_summary_carries_latest_revocation_context_for_attention_items(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "macro_indicators": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="macro_indicators",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/macro/pit",
                            revocation_reason="policy_regression",
                            notes="source health must surface maturity reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        summary = facade.get_source_health_summary(
            dataset_ids=("macro_indicators",),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )

        assert summary.revoked_promotion_count == 1
        assert summary.reports[0].latest_revocation_reason == "policy_regression"
        attention = summary.attention_required[0]
        assert attention.latest_revocation_reason == "policy_regression"
        assert attention.latest_revoked_by == "data-governance"
        assert attention.latest_revoked_at == datetime(2026, 6, 2, 9, 30, tzinfo=UTC)

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
