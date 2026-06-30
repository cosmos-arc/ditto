"""Tests for DataCatalog-backed source snapshot provenance resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from ditto_application.processes.materialization.catalog_dependency_validation import (
    DependencyCatalogCompatibilityError,
)
from ditto_application.processes.materialization.source_snapshot_resolver import (
    CatalogSourceSnapshotResolver,
    UniverseSourceTickersRequest,
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


def _entry(
    *,
    dataset_id: str,
    namespace: str = "market",
    trade_date: str,
    source_ticker: str | None = None,
    schema_version: str,
    columns: tuple[str, ...],
    source_snapshot_id: str,
) -> DataCatalogEntry:
    timestamp = datetime(2026, 3, 11, 16, 0, tzinfo=UTC)
    partition_keys = (
        (
            f"source_ticker={source_ticker}",
            f"start_date={trade_date}",
            f"end_date={trade_date}",
        )
        if source_ticker is not None
        else (f"trade_date={trade_date}",)
    )
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        ),
        storage_uri=f"lake://{namespace}/{dataset_id}/{trade_date}.parquet",
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}:{trade_date}",
            row_count=2,
            created_at=timestamp,
            schema_version=schema_version,
            columns=columns,
        ),
        source="tushare",
        freshness_at=timestamp,
        source_snapshot_id=source_snapshot_id,
    )


def _context(
    *,
    universe_id: str | None = None,
    dependencies: tuple[str, ...] = ("market.close", "market.adj_factor"),
) -> InputContext:
    request = MagicMock()
    request.source_snapshot_id = None
    return InputContext(
        spec=DerivedSpec(
            id="factor.snapshot_resolved",
            version=3,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression="market.close * market.adj_factor",
            universe_id=universe_id,
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


def test_catalog_source_snapshot_resolver_returns_selected_snapshot_set() -> None:
    """Resolver should return exact snapshots used by selected catalog assets."""
    catalog = InMemoryDataCatalog()
    stock_columns = (
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
    adj_columns = ("instrument_id", "trade_date", "adj_factor")
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-10",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:2026-03-10:a",
        )
    )
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-11",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:2026-03-11:b",
        )
    )
    catalog.upsert_asset(
        _entry(
            dataset_id="adj_factor",
            trade_date="2026-03-10",
            schema_version="market.adj_factor.v1",
            columns=adj_columns,
            source_snapshot_id="snapshot:tushare:adj_factor:2026-03-10:c",
        )
    )
    catalog.upsert_asset(
        _entry(
            dataset_id="adj_factor",
            trade_date="2026-03-11",
            schema_version="market.adj_factor.v1",
            columns=adj_columns,
            source_snapshot_id="snapshot:tushare:adj_factor:2026-03-11:d",
        )
    )
    resolver = CatalogSourceSnapshotResolver(
        data_catalog_reader=catalog,
        catalog_coverage_dates_provider=lambda _start, _end: (
            "2026-03-10",
            "2026-03-11",
        ),
    )

    provenance = resolver.resolve(_context())

    assert provenance.source_snapshot_ids == (
        "snapshot:tushare:adj_factor:2026-03-10:c",
        "snapshot:tushare:adj_factor:2026-03-11:d",
        "snapshot:tushare:stock_daily:2026-03-10:a",
        "snapshot:tushare:stock_daily:2026-03-11:b",
    )
    assert provenance.source_snapshot_id is not None
    assert provenance.source_snapshot_id.startswith("snapshot-set:sha256:")


def test_catalog_source_snapshot_resolver_proves_universe_ticker_coverage() -> None:
    """Resolver should require every universe ticker/date partition when configured."""
    catalog = InMemoryDataCatalog()
    stock_columns = (
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
    for source_ticker in ("000001.SZ", "000002.SZ"):
        for trade_date in ("2026-03-10", "2026-03-11"):
            catalog.upsert_asset(
                _entry(
                    dataset_id="stock_daily",
                    trade_date=trade_date,
                    source_ticker=source_ticker,
                    schema_version="market.stock_daily.v1",
                    columns=stock_columns,
                    source_snapshot_id=(
                        "snapshot:tushare:stock_daily:"
                        f"{source_ticker}:{trade_date}:checksum"
                    ),
                )
            )
    resolver = CatalogSourceSnapshotResolver(
        data_catalog_reader=catalog,
        catalog_coverage_dates_provider=lambda _start, _end: (
            "2026-03-10",
            "2026-03-11",
        ),
        universe_source_tickers_provider=lambda _request: (
            "000001.SZ",
            "000002.SZ",
        ),
    )

    provenance = resolver.resolve(
        _context(universe_id="cn_stock_test", dependencies=("market.close",)),
    )

    assert provenance.source_snapshot_ids == (
        "snapshot:tushare:stock_daily:000001.SZ:2026-03-10:checksum",
        "snapshot:tushare:stock_daily:000001.SZ:2026-03-11:checksum",
        "snapshot:tushare:stock_daily:000002.SZ:2026-03-10:checksum",
        "snapshot:tushare:stock_daily:000002.SZ:2026-03-11:checksum",
    )
    assert provenance.source_snapshot_id is not None
    assert provenance.source_snapshot_id.startswith("snapshot-set:sha256:")


def test_resolver_uses_date_varying_universe_ticker_coverage() -> None:
    """Resolver should require each date's own universe source-ticker set."""
    catalog = InMemoryDataCatalog()
    stock_columns = (
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
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-10",
            source_ticker="000001.SZ",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:000001.SZ:2026-03-10:a",
        )
    )
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-11",
            source_ticker="000002.SZ",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:000002.SZ:2026-03-11:b",
        )
    )

    def source_tickers(request: UniverseSourceTickersRequest) -> tuple[str, ...]:
        if request.asof == "2026-03-10":
            return ("000001.SZ",)
        if request.asof == "2026-03-11":
            return ("000002.SZ",)
        return ()

    resolver = CatalogSourceSnapshotResolver(
        data_catalog_reader=catalog,
        catalog_coverage_dates_provider=lambda _start, _end: (
            "2026-03-10",
            "2026-03-11",
        ),
        universe_source_tickers_provider=source_tickers,
    )

    provenance = resolver.resolve(
        _context(universe_id="cn_stock_dynamic", dependencies=("market.close",)),
    )

    assert provenance.source_snapshot_ids == (
        "snapshot:tushare:stock_daily:000001.SZ:2026-03-10:a",
        "snapshot:tushare:stock_daily:000002.SZ:2026-03-11:b",
    )
    assert provenance.source_snapshot_id is not None
    assert provenance.source_snapshot_id.startswith("snapshot-set:sha256:")


def test_resolver_passes_contract_source_to_universe_ticker_provider() -> None:
    """Resolver should derive the ticker source from dependency catalog policy."""
    catalog = InMemoryDataCatalog()
    stock_columns = (
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
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-10",
            source_ticker="TS:000001",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:TS:000001:2026-03-10:a",
        )
    )
    seen_requests: list[tuple[str, str, str | None, str, str]] = []

    def source_tickers(request: UniverseSourceTickersRequest) -> tuple[str, ...]:
        seen_requests.append(
            (
                request.universe_id,
                request.source,
                request.asof,
                request.catalog_dataset_id,
                request.dependency_ref,
            )
        )
        return ("TS:000001",)

    resolver = CatalogSourceSnapshotResolver(
        data_catalog_reader=catalog,
        catalog_coverage_dates_provider=lambda _start, _end: ("2026-03-10",),
        universe_source_tickers_provider=source_tickers,
    )

    provenance = resolver.resolve(
        _context(universe_id="cn_stock_source", dependencies=("market.close",)),
    )

    assert seen_requests == [
        (
            "cn_stock_source",
            "tushare",
            "2026-03-10",
            "stock_daily",
            "market.stock_daily",
        )
    ]
    assert provenance.source_snapshot_ids == (
        "snapshot:tushare:stock_daily:TS:000001:2026-03-10:a",
    )


def test_resolver_rejects_missing_universe_ticker_coverage() -> None:
    """Resolver should identify the exact missing source-ticker/date partition."""
    catalog = InMemoryDataCatalog()
    stock_columns = (
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
    catalog.upsert_asset(
        _entry(
            dataset_id="stock_daily",
            trade_date="2026-03-10",
            source_ticker="000001.SZ",
            schema_version="market.stock_daily.v1",
            columns=stock_columns,
            source_snapshot_id="snapshot:tushare:stock_daily:000001.SZ:2026-03-10:a",
        )
    )
    resolver = CatalogSourceSnapshotResolver(
        data_catalog_reader=catalog,
        catalog_coverage_dates_provider=lambda _start, _end: ("2026-03-10",),
        universe_source_tickers_provider=lambda _request: (
            "000001.SZ",
            "000002.SZ",
        ),
    )

    with pytest.raises(DependencyCatalogCompatibilityError) as exc_info:
        resolver.resolve(
            _context(universe_id="cn_stock_test", dependencies=("market.close",))
        )

    assert exc_info.value.reason == "missing_source_ticker_coverage"
    assert exc_info.value.missing_source_ticker_dates == ("000002.SZ@2026-03-10",)
