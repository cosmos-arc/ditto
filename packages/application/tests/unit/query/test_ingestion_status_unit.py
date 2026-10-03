"""Tests for ingestion status query facade."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import ditto_application.queries.ingestion_status as ingestion_status_module
from ditto_application.queries.ingestion_status import (
    DatasetStatus,
    IngestionStatusQueryFacade,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.models.ingestion import IngestionStatus


def _catalog_entry(
    dataset_id: str,
    *,
    storage_uri: str,
    freshness_at: datetime,
    row_count: int = 17,
) -> DataCatalogEntry:
    return (
        DataCatalogEntry(
            # #394:概览只消费数据集级 catalog 行。
            asset=DataAssetRef(dataset_id=dataset_id, namespace="market"),
        )
        if False
        else DataCatalogEntry(
            asset=DataAssetRef(
                dataset_id=dataset_id,
                namespace="market",
                partition_keys=(),
            ),
            storage_uri=storage_uri,
            schema=DataSchemaFingerprint(
                schema_hash=f"schema:{dataset_id}:v1",
                row_count=row_count,
                created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
            ),
            source="tushare",
            freshness_at=freshness_at,
        )
    )


def _log_store() -> MagicMock:
    store = MagicMock()
    store.get_stats.return_value = {"success_count": 1}
    store.get_last_success_date.return_value = "2026-06-01"
    store.list_ingested_dates.return_value = []
    return store


def _facade(
    catalog=None,
    *,
    now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
) -> IngestionStatusQueryFacade:
    return IngestionStatusQueryFacade(
        ingestion_log_store=_log_store(),
        data_catalog_reader=catalog if catalog is not None else InMemoryDataCatalog(),
        now=now,
    )


class TestIngestionStatusCatalogOverlay:
    def test_status_includes_latest_catalog_freshness_storage_schema_and_sla(
        self,
    ) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/older",
                freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                row_count=11,
            )
        )
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/newer",
                freshness_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
                row_count=23,
            )
        )
        catalog.upsert_asset(
            _catalog_entry(
                "etf_daily",
                storage_uri="etf_daily/newer",
                freshness_at=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
            )
        )
        facade = _facade(catalog)

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_at == datetime(2026, 6, 1, 10, 1, tzinfo=UTC)
        assert status.catalog_storage_uri == "stock_daily/newer"
        assert status.catalog_schema_hash == "schema:stock_daily:v1"
        assert status.catalog_row_count == 23
        assert status.catalog_freshness_sla_hours == 36
        assert status.catalog_freshness_status == "fresh"
        assert status.dataset_maturity == "initial-focus"
        assert status.dataset_maturity_warning is None

    def test_initial_focus_status_has_no_maturity_warning(
        self,
    ) -> None:
        facade = _facade()

        status = facade.get_status(["etf_daily"])[0]

        assert status.dataset_maturity == "initial-focus"
        assert status.dataset_maturity_warning is None

    def test_status_marks_catalog_asset_stale_when_freshness_exceeds_sla(
        self,
    ) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/stale",
                freshness_at=datetime(2026, 5, 30, 10, 1, tzinfo=UTC),
            )
        )
        facade = _facade(catalog)

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_status == "stale"
        assert status.catalog_freshness_sla_hours == 36

    def test_status_catalog_fields_are_none_when_dataset_has_no_catalog_asset(
        self,
    ) -> None:
        store = _log_store()
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=store,
            data_catalog_reader=InMemoryDataCatalog(),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_at is None
        assert status.catalog_storage_uri is None
        assert status.catalog_schema_hash is None
        assert status.catalog_row_count is None
        assert status.catalog_freshness_sla_hours == 36
        assert status.catalog_freshness_status == "missing"
        store.list_ingested_dates.assert_called_once_with(
            "stock_daily",
            status=IngestionStatus.FAIL,
        )

    def test_status_marks_newly_supported_dataset_missing_until_ingested(self) -> None:
        facade = _facade()

        status = facade.get_status(["index_weight"])[0]

        assert status.catalog_freshness_status == "missing"
        assert status.catalog_freshness_sla_hours == 36
        assert status.dataset_maturity == "initial-focus"


class TestIngestionStatusMaturitySummary:
    def test_groups_dataset_freshness_and_failure_counts_by_maturity(self) -> None:
        statuses = [
            DatasetStatus(
                dataset="stock_daily",
                latest_date="2026-06-01",
                latest_status="success",
                dataset_maturity="experimental",
                dataset_maturity_warning="experimental data requires research opt-in",
                record_count=1,
                last_attempt=None,
                catalog_freshness_status="fresh",
            ),
            DatasetStatus(
                dataset="etf_daily",
                latest_date="2026-06-01",
                latest_status="failed",
                dataset_maturity="initial-focus",
                record_count=0,
                last_attempt=None,
                catalog_freshness_status="missing",
            ),
            DatasetStatus(
                dataset="macro_indicators",
                latest_date="2026-06-01",
                latest_status="success",
                dataset_maturity="experimental",
                record_count=1,
                last_attempt=None,
                catalog_freshness_status="stale",
            ),
            DatasetStatus(
                dataset="unknown_future",
                latest_date=None,
                latest_status=None,
                dataset_maturity=None,
                record_count=0,
                last_attempt=None,
                catalog_freshness_status="not_applicable",
            ),
        ]

        summary = ingestion_status_module.summarize_status_by_maturity(statuses)

        assert [(item.maturity, item.dataset_count) for item in summary] == [
            ("initial-focus", 1),
            ("experimental", 2),
            ("unknown", 1),
        ]
        initial_focus = summary[0]
        assert initial_focus.fresh_count == 0
        assert initial_focus.missing_count == 1
        assert initial_focus.failed_count == 1
        experimental = summary[1]
        assert experimental.fresh_count == 1
        assert experimental.stale_count == 1
        assert experimental.warning_count == 1
        unknown = summary[2]
        assert unknown.not_applicable_count == 1


def test_default_dataset_metadata_remains_available_through_module() -> None:
    assert ingestion_status_module.default_dataset_metadata()["stock_daily"].maturity
