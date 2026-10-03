"""Tests for snapshot-fact-backed source snapshot provenance resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.processes.materialization.catalog_dependency_validation import (
    DependencyCatalogCompatibilityError,
)
from ditto_application.processes.materialization.source_snapshot_resolver import (
    CatalogSourceSnapshotResolver,
)
from ditto_application.processes.materialization.types import InputContext
from ditto_data.catalog import InMemoryDataCatalog
from ditto_data.catalog.contracts import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.materialization import DerivedExecutionPlan
from ditto_features.materialization.models import DerivedRunMode
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)

_STOCK_COLUMNS = (
    "instrument_id",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
)


def _entry(*, dataset_id: str, schema_version: str, columns: tuple[str, ...]):
    timestamp = datetime(2026, 3, 11, 16, 0, tzinfo=UTC)
    return DataCatalogEntry(
        # #394:catalog 只有数据集级 schema 描述行。
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace="market",
            partition_keys=(),
        ),
        storage_uri=f"lake://market/{dataset_id}/latest.parquet",
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}",
            row_count=2,
            created_at=timestamp,
            schema_version=schema_version,
            columns=columns,
        ),
        source="tushare",
        freshness_at=timestamp,
    )


def _seed_dates(
    stores: _evidence_support.EvidenceStores,
    *,
    dataset_id: str,
    schema_version: str,
    dates: tuple[str, ...],
) -> list[str]:
    return [
        _evidence_support.commit_snapshot(
            stores,
            dataset=dataset_id,
            request_start=date,
            request_end=date,
            checksum=f"{index}-{dataset_id}".ljust(32, "0")[:32],
            row_count=2,
            schema_version=schema_version,
        ).snapshot_id
        for index, date in enumerate(dates)
    ]


def _context(
    *,
    dependencies: tuple[str, ...] = ("market.close", "market.adj_factor"),
    source_snapshot_id: str | None = None,
) -> InputContext:
    request = MagicMock()
    request.source_snapshot_id = source_snapshot_id
    return InputContext(
        spec=DerivedSpec(
            id="factor.snapshot_resolved",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close * market.adj_factor",
            universe_id=None,
        ),
        request=request,
        plan=DerivedExecutionPlan(
            derived_id="factor.snapshot_resolved",
            version=3,
            profile=MaterializationProfile.SERIES,
            mode=DerivedRunMode.FULL,
            request_start="2026-03-10",
            request_end="2026-03-11",
            compute_start="2026-03-10",
            compute_end="2026-03-11",
            partitions=("2026",),
            lookback=0,
            requires_full_day=False,
        ),
        dependencies=dependencies,
    )


def test_resolver_returns_selected_snapshot_set() -> None:
    """Resolver 应返回覆盖每个依赖日期的 completed snapshot 集合。"""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            columns=_STOCK_COLUMNS,
        )
    )
    catalog.upsert_asset(
        _entry(
            dataset_id="adj_factor",
            schema_version="market.adj_factor.v1",
            columns=("instrument_id", "trade_date", "adj_factor"),
        )
    )
    with _evidence_support.evidence_stores() as stores:
        expected_ids = [
            *_seed_dates(
                stores,
                dataset_id="adj_factor",
                schema_version="market.adj_factor.v1",
                dates=("2026-03-10", "2026-03-11"),
            ),
            *_seed_dates(
                stores,
                dataset_id="stock_daily",
                schema_version="market.stock_daily.v1",
                dates=("2026-03-10", "2026-03-11"),
            ),
        ]
        resolver = CatalogSourceSnapshotResolver(
            data_catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            catalog_coverage_dates_provider=lambda _start, _end: (
                "2026-03-10",
                "2026-03-11",
            ),
        )

        provenance = resolver.resolve(_context())

    assert provenance.source_snapshot_ids == tuple(sorted(expected_ids))
    assert provenance.source_snapshot_id is not None
    assert provenance.source_snapshot_id.startswith("snapshot-set:sha256:")


def test_resolver_rejects_missing_date_coverage() -> None:
    """未完成覆盖的日期必须 fail closed。"""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            columns=_STOCK_COLUMNS,
        )
    )
    with _evidence_support.evidence_stores() as stores:
        _seed_dates(
            stores,
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            dates=("2026-03-10",),
        )
        resolver = CatalogSourceSnapshotResolver(
            data_catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            catalog_coverage_dates_provider=lambda _start, _end: (
                "2026-03-10",
                "2026-03-11",
            ),
        )

        with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
            resolver.resolve(_context(dependencies=("market.close",)))

    assert exc_info.value.reason == "missing_catalog_coverage"
    assert exc_info.value.missing_dates == ("2026-03-11",)


def test_resolver_rejects_expected_snapshot_mismatch() -> None:
    """请求声明的快照 id 不在覆盖集合内时必须拒绝。"""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            columns=_STOCK_COLUMNS,
        )
    )
    with _evidence_support.evidence_stores() as stores:
        seeded = _seed_dates(
            stores,
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            dates=("2026-03-10", "2026-03-11"),
        )
        resolver = CatalogSourceSnapshotResolver(
            data_catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
            catalog_coverage_dates_provider=lambda _start, _end: (
                "2026-03-10",
                "2026-03-11",
            ),
        )

        with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
            resolver.resolve(
                _context(
                    dependencies=("market.close",),
                    source_snapshot_id="snapshot:tushare:stock_daily:v2",
                )
            )

    assert exc_info.value.reason == "source_snapshot_mismatch"
    assert exc_info.value.expected_source_snapshot_id == (
        "snapshot:tushare:stock_daily:v2"
    )
    assert exc_info.value.actual_source_snapshot_id in seeded


def test_resolver_falls_back_to_request_snapshot_without_dates() -> None:
    """无覆盖日期要求时,来源身份回落到请求声明的快照。"""
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            schema_version="market.stock_daily.v1",
            columns=_STOCK_COLUMNS,
        )
    )
    with _evidence_support.evidence_stores() as stores:
        resolver = CatalogSourceSnapshotResolver(
            data_catalog_reader=catalog,
            snapshots=stores.snapshots,
            lifecycle=stores.lifecycle,
        )

        provenance = resolver.resolve(
            _context(
                dependencies=("market.close",),
                source_snapshot_id="snapshot:tushare:stock_daily:declared",
            )
        )

    assert provenance.source_snapshot_ids == ("snapshot:tushare:stock_daily:declared",)
    assert provenance.source_snapshot_id == "snapshot:tushare:stock_daily:declared"
