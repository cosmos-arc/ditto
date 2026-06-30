"""Unit tests for DataCatalog dependency compatibility validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_application.processes.materialization.catalog_dependency_validation import (
    DependencyCatalogCompatibilityError,
    validate_dependency_catalog_compatibility,
)
from ditto_data.catalog import InMemoryDataCatalog
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_features.materialization.dependency_registry import dependency_contracts


def _stock_daily_entry_without_schema_version() -> DataCatalogEntry:
    timestamp = datetime(2026, 3, 10, 16, 0, tzinfo=UTC)
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-03-10",),
        ),
        storage_uri="lake://market/stock_daily/2026-03-10.parquet",
        schema=DataSchemaFingerprint(
            schema_hash="schema:stock_daily",
            row_count=2,
            created_at=timestamp,
            columns=(
                "instrument_id",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
                "amount",
            ),
        ),
        source="tushare",
        freshness_at=timestamp,
        source_snapshot_id="snapshot:tushare:stock_daily:2026-03-10:abc",
    )


def test_dependency_validation_rejects_missing_schema_version() -> None:
    """Materialization should fail closed when a contract has no catalog version."""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(_stock_daily_entry_without_schema_version())

    with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
        validate_dependency_catalog_compatibility(
            contracts=dependency_contracts(("market.close",)),
            catalog_reader=catalog,
            required_dates=("2026-03-10",),
        )

    issue = exc_info.value.issue
    assert issue.reason == "missing_schema_version"
    assert issue.expected_schema_version == "market.stock_daily.v1"
    assert issue.actual_schema_version is None
