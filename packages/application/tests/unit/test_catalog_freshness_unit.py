"""Fail-closed catalog freshness and persisted PIT evidence tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from ditto_application.catalog_freshness import (
    PersistedIngestionEvidenceVerifier,
    aggregate_source_snapshot_ids,
    assess_catalog_freshness,
    catalog_asof_snapshot,
    catalog_repair_priority,
    catalog_snapshot_has_quality_logs,
    catalog_source_snapshot_id,
    dataset_namespace,
    latest_catalog_entry_for_dataset,
    latest_catalog_entry_on_or_before,
    select_ingestion_source,
)
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.models.ingestion import IngestionLog, IngestionStatus

pytestmark = [pytest.mark.unit, pytest.mark.pit]


@dataclass(frozen=True)
class _Catalog:
    entries: tuple[DataCatalogEntry, ...] = ()

    def get_asset(self, asset: DataAssetRef) -> DataCatalogEntry | None:
        return next((entry for entry in self.entries if entry.asset == asset), None)

    def list_assets(
        self,
        namespace: str | None = None,
    ) -> tuple[DataCatalogEntry, ...]:
        if namespace is None:
            return self.entries
        return tuple(
            entry for entry in self.entries if entry.asset.namespace == namespace
        )


@dataclass(frozen=True)
class _Logs:
    logs: tuple[IngestionLog, ...] = ()

    def get_log(
        self,
        dataset: str,
        source: str,
        trade_date: str,
    ) -> IngestionLog | None:
        return next(
            (
                log
                for log in self.logs
                if (log.dataset, log.source, log.trade_date)
                == (dataset, source, trade_date)
            ),
            None,
        )


def _entry(
    trade_date: str,
    *,
    dataset: str = "balance_sheet",
    namespace: str = "fundamental",
    source: str = "tushare",
    snapshot_id: str | None = None,
    row_count: int | None = 1,
    freshness_at: datetime = datetime(2026, 7, 1, tzinfo=UTC),
    partition_keys: tuple[str, ...] | None = None,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset,
            namespace=namespace,
            partition_keys=partition_keys or (f"trade_date={trade_date}",),
        ),
        storage_uri=f"{dataset}/{trade_date}.parquet",
        schema=DataSchemaFingerprint(schema_hash="schema:v1", row_count=row_count),
        source=source,
        freshness_at=freshness_at,
        source_snapshot_id=snapshot_id,
    )


def _attested_id(
    trade_date: str,
    checksum: str,
    *,
    dataset: str = "balance_sheet",
    source: str = "tushare",
) -> str:
    return catalog_source_snapshot_id(
        dataset=dataset,
        trade_date=trade_date,
        source=source,
        checksum=checksum,
        l1_l2_attested=True,
    )


def _success_log(
    trade_date: str,
    checksum: str,
    *,
    rows: int | None = 1,
) -> IngestionLog:
    return IngestionLog(
        dataset="balance_sheet",
        source="tushare",
        trade_date=trade_date,
        status=IngestionStatus.SUCCESS,
        checksum=checksum,
        rows=rows,
    )


def test_freshness_statuses_observe_sla_boundary_and_unknown_dataset() -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=UTC)
    at_boundary = _entry(
        "2026-07-01",
        dataset="stock_daily",
        namespace="market",
        freshness_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    stale = _entry(
        "2026-06-30",
        dataset="stock_daily",
        namespace="market",
        freshness_at=datetime(2026, 6, 30, 23, 59, 59),
    )

    assert (
        assess_catalog_freshness(
            dataset="stock_daily", catalog_entry=at_boundary, now=lambda: now
        ).status
        == "fresh"
    )
    assert (
        assess_catalog_freshness(
            dataset="stock_daily", catalog_entry=stale, now=lambda: now
        ).status
        == "stale"
    )
    assert (
        assess_catalog_freshness(dataset="stock_daily", catalog_entry=None).status
        == "missing"
    )
    unknown = assess_catalog_freshness(dataset="private_dataset", catalog_entry=stale)
    assert (unknown.status, unknown.sla_hours, unknown.entry) == (
        "not_applicable",
        None,
        stale,
    )


def test_latest_catalog_queries_filter_identity_date_and_source() -> None:
    older = _entry(
        "2026-06-01",
        freshness_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    newer_partition = _entry(
        "2026-06-15",
        freshness_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    future = _entry("2026-08-01")
    wrong_source = _entry("2026-06-20", source="other")
    other_dataset = _entry(
        "2026-06-30",
        dataset="cash_flow",
        freshness_at=datetime(2026, 7, 3, tzinfo=UTC),
    )
    catalog = _Catalog((older, newer_partition, future, wrong_source, other_dataset))

    assert latest_catalog_entry_for_dataset(catalog, "balance_sheet") is older
    assert (
        latest_catalog_entry_on_or_before(
            reader=catalog,
            dataset="balance_sheet",
            source="tushare",
            trade_date="2026-06-30",
        )
        is newer_partition
    )
    assert (
        latest_catalog_entry_on_or_before(
            reader=catalog,
            dataset="balance_sheet",
            source="missing",
            trade_date="2026-06-30",
        )
        is None
    )
    assert (
        latest_catalog_entry_on_or_before(
            reader=catalog,
            dataset="balance_sheet",
            source="tushare",
            trade_date="not-a-date",
        )
        is None
    )


def test_asof_snapshot_rejects_bad_cutoff_staleness_duplicates_and_rows() -> None:
    checksum = "sha256:one"
    valid_id = _attested_id("2026-06-01", checksum)
    valid = _entry("2026-06-01", snapshot_id=valid_id)

    assert (
        catalog_asof_snapshot(
            reader=_Catalog((valid,)),
            dataset="balance_sheet",
            source="tushare",
            signal_date="invalid",
        )
        is None
    )
    assert (
        catalog_asof_snapshot(
            reader=_Catalog(),
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
        )
        is None
    )
    assert (
        catalog_asof_snapshot(
            reader=_Catalog((_entry("2025-01-01", snapshot_id=valid_id),)),
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
        )
        is None
    )

    duplicate_id_entries = (
        valid,
        _entry("2026-06-15", snapshot_id=valid_id),
    )
    assert (
        catalog_asof_snapshot(
            reader=_Catalog(duplicate_id_entries),
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
        )
        is None
    )
    invalid_rows = _entry(
        "2026-06-01",
        snapshot_id=valid_id,
        row_count=-1,
    )
    assert (
        catalog_asof_snapshot(
            reader=_Catalog((invalid_rows,)),
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-01",
        )
        is None
    )
    assert (
        catalog_asof_snapshot(
            reader=_Catalog(
                (
                    _entry(
                        "2026-06-01",
                        dataset="private_dataset",
                        namespace="data",
                        snapshot_id=valid_id,
                    ),
                )
            ),
            dataset="private_dataset",
            source="tushare",
            signal_date="2026-07-01",
        )
        is None
    )


def test_aggregate_snapshot_identity_is_empty_singleton_or_order_invariant() -> None:
    assert aggregate_source_snapshot_ids(()) is None
    assert aggregate_source_snapshot_ids(("snapshot:a",)) == "snapshot:a"
    assert aggregate_source_snapshot_ids(("snapshot:b", "snapshot:a")) == (
        aggregate_source_snapshot_ids(("snapshot:a", "snapshot:b", "snapshot:a"))
    )


@pytest.mark.parametrize(
    "partition_keys",
    [
        ("end_date=2026-06-30",),
        (
            "start_date=2026-06-01",
            "start_date=2026-06-02",
            "end_date=2026-06-30",
        ),
    ],
)
def test_quality_log_verification_rejects_noncanonical_range_partitions(
    partition_keys: tuple[str, ...],
) -> None:
    snapshot_id = "snapshot:range:quality=l1-l2"
    entry = _entry(
        "2026-06-30",
        snapshot_id=snapshot_id,
        partition_keys=partition_keys,
    )

    assert not catalog_snapshot_has_quality_logs(
        reader=_Catalog((entry,)),
        ingestion_logs=_Logs(),
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-01",
        expected_snapshot_ids=(snapshot_id,),
        expected_row_count=1,
    )


def test_quality_log_verification_accepts_canonical_instrument_range() -> None:
    checksum = "sha256:range"
    snapshot_id = (
        "snapshot:tushare:balance_sheet:000001.SZ:"
        f"2026-06-01:2026-06-30:{checksum}:quality=l1-l2"
    )
    entry = _entry(
        "2026-06-30",
        snapshot_id=snapshot_id,
        partition_keys=(
            "source_ticker=000001.SZ",
            "start_date=2026-06-01",
            "end_date=2026-06-30",
        ),
    )
    logs = _Logs((_success_log("2026-06-01", checksum),))
    verifier = PersistedIngestionEvidenceVerifier(_Catalog((entry,)), logs)

    assert verifier.verify_asof_snapshot(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-01",
        expected_snapshot_ids=(snapshot_id,),
        expected_row_count=1,
    )
    assert not verifier.verify_asof_snapshot(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-01",
        expected_snapshot_ids=("snapshot:unexpected",),
        expected_row_count=1,
    )
    assert not verifier.verify_asof_snapshot(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-01",
        expected_snapshot_ids=(snapshot_id,),
        expected_row_count=2,
    )


def test_source_selection_and_priority_are_deterministic() -> None:
    now = datetime(2026, 7, 1, tzinfo=UTC)
    fred = _entry(
        "2026-07-01",
        dataset="macro_indicators",
        namespace="macro",
        source="fred",
        freshness_at=now,
    )
    catalog = _Catalog((fred,))

    with pytest.raises(ValueError, match="available_sources must not be empty"):
        select_ingestion_source(
            dataset="stock_daily",
            trade_date="2026-07-01",
            available_sources=(),
        )
    assert (
        select_ingestion_source(
            dataset="macro_indicators",
            trade_date="2026-07-01",
            available_sources=("FRED", "TUSHARE", "fred"),
            catalog_reader=catalog,
            now=lambda: now,
        )
        == "fred"
    )
    assert (
        select_ingestion_source(
            dataset="macro_indicators",
            trade_date="2026-07-01",
            available_sources=("fred", "tushare"),
        )
        == "tushare"
    )
    assert (
        select_ingestion_source(
            dataset="stock_daily",
            trade_date="2026-07-01",
            available_sources=("local",),
        )
        == "local"
    )
    assert (
        catalog_repair_priority(
            reader=_Catalog(),
            dataset="stock_daily",
            source="tushare",
            trade_date="2026-07-01",
            now=lambda: now,
        )
        == 0
    )
    assert dataset_namespace("balance_sheet") == "fundamental"
    assert dataset_namespace("private_dataset") == "data"


def test_invalid_partition_shapes_are_never_visible_as_of_cutoff() -> None:
    invalid = (
        _entry(
            "2026-06-01",
            partition_keys=(
                "trade_date=2026-06-01",
                "end_date=2026-06-01",
            ),
        ),
        _entry("2026-06-01", partition_keys=("trade_date=invalid",)),
        _entry("2026-06-01", dataset="cash_flow"),
        _entry("2026-06-01", source="other"),
    )

    assert (
        latest_catalog_entry_on_or_before(
            reader=_Catalog(invalid),
            dataset="balance_sheet",
            source="tushare",
            trade_date="2026-07-01",
        )
        is None
    )
