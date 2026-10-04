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
            partition_keys=(),
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


def _stock_daily_storage_identity_entry() -> DataCatalogEntry:
    """真实摄取形态的目录行：存储列以 source_ticker 记录身份."""
    timestamp = datetime(2026, 3, 10, 16, 0, tzinfo=UTC)
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=(),
        ),
        storage_uri="lake://market/stock_daily/2026-03-10.parquet",
        schema=DataSchemaFingerprint(
            schema_hash="schema:stock_daily",
            row_count=2,
            created_at=timestamp,
            schema_version="market.stock_daily.v1",
            columns=(
                "source_ticker",
                "trade_date",
                "knowledge_date",
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


def test_dependency_validation_accepts_storage_identity_alias() -> None:
    """#418: 存储目录以 source_ticker 记录身份时，契约实体键由读层满足."""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(_stock_daily_storage_identity_entry())

    from packages.application.tests.unit.process.ingestion import (
        snapshot_evidence_support as _evidence_support,
    )

    with _evidence_support.evidence_stores() as stores:
        report = validate_dependency_catalog_compatibility(
            contracts=dependency_contracts(("market.close",)),
            catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            required_dates=(),
        )
    assert report.source_snapshot_ids == ()


def test_dependency_validation_rejects_missing_value_column_with_alias() -> None:
    """身份别名只豁免实体键：数值列缺失仍然 fail closed."""
    entry = _stock_daily_storage_identity_entry()
    stripped = DataCatalogEntry(
        asset=entry.asset,
        storage_uri=entry.storage_uri,
        schema=DataSchemaFingerprint(
            schema_hash=entry.schema.schema_hash,
            row_count=entry.schema.row_count,
            created_at=entry.schema.created_at,
            schema_version="market.stock_daily.v1",
            columns=tuple(
                column for column in entry.schema.columns if column != "close"
            ),
        ),
        source=entry.source,
        freshness_at=entry.freshness_at,
        source_snapshot_id=entry.source_snapshot_id,
    )
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(stripped)

    from packages.application.tests.unit.process.ingestion import (
        snapshot_evidence_support as _evidence_support,
    )

    with (
        _evidence_support.evidence_stores() as stores,
        pytest.raises(DependencyCatalogCompatibilityError) as exc_info,
    ):
        validate_dependency_catalog_compatibility(
            contracts=dependency_contracts(("market.close",)),
            catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            required_dates=(),
        )

    issue = exc_info.value.issue
    assert issue.reason == "schema_columns_mismatch"
    assert issue.missing_columns == ("close",)


def test_dependency_validation_rejects_missing_schema_version() -> None:
    """Materialization should fail closed when a contract has no catalog version."""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(_stock_daily_entry_without_schema_version())

    from packages.application.tests.unit.process.ingestion import (
        snapshot_evidence_support as _evidence_support,
    )

    with (
        _evidence_support.evidence_stores() as stores,
        pytest.raises(DependencyCatalogCompatibilityError) as exc_info,
    ):
        validate_dependency_catalog_compatibility(
            contracts=dependency_contracts(("market.close",)),
            catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            required_dates=("2026-03-10",),
        )

    issue = exc_info.value.issue
    assert issue.reason == "missing_schema_version"
    assert issue.expected_schema_version == "market.stock_daily.v1"
    assert issue.actual_schema_version is None
