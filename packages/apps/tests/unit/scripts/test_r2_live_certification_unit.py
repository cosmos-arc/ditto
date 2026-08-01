"""Unit contract for the R2 live certification orchestrator."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, date, datetime

import orjson
import polars as pl
import pytest
from ditto_apps.scripts.r2_live_certification import (
    build_expected_dates,
    load_passing_recovery_evidence,
    probe_consumer_payload,
    select_current_snapshot_ids,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft

_NOW = datetime(2026, 8, 1, tzinfo=UTC)
_ASSET = DataAssetRef(
    dataset_id="dividend",
    namespace="fundamental",
    partition_keys=("start_date=2015-01-01", "end_date=2015-03-31"),
)


def _entry(
    *, schema_version: str, row_count: int, created_at: datetime
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=_ASSET,
        storage_uri="fundamental/dividend",
        schema=DataSchemaFingerprint(
            schema_hash="schema:sha256:current",
            row_count=row_count,
            created_at=created_at,
            schema_version=schema_version,
            columns=("instrument_id", "announcement_date"),
        ),
        source="tushare",
        freshness_at=created_at,
    )


def _snapshot(
    *,
    schema_version: str,
    row_count: int,
    created_at: datetime,
    checksum: str,
) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="dividend",
            source="tushare",
            request_start="2015-01-01",
            request_end="2015-03-31",
            schema_version=schema_version,
            checksum=checksum,
            canonical_asset=_ASSET,
            request_parameters_hash=f"sha256:{checksum}",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id="license:tushare:dividend:sha256:reviewed",
            row_count=row_count,
            payload_uri="fundamental/dividend",
            payload_retained=True,
            created_at=created_at,
        )
    )


@pytest.mark.unit
def test_select_current_snapshot_ids_excludes_superseded_schema() -> None:
    old = _snapshot(
        schema_version="fundamental.dividend.v1",
        row_count=3,
        created_at=datetime(2026, 7, 31, tzinfo=UTC),
        checksum="old",
    )
    current = _snapshot(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=_NOW,
        checksum="current",
    )

    selected = select_current_snapshot_ids(
        dataset_id="dividend",
        catalog_entries=(
            _entry(
                schema_version="fundamental.dividend.v1",
                row_count=3,
                created_at=datetime(2026, 7, 31, tzinfo=UTC),
            ),
            _entry(
                schema_version="fundamental.dividend.v2",
                row_count=5,
                created_at=_NOW,
            ),
        ),
        snapshots=(old, current),
    )

    assert selected == (current.snapshot_id,)


@pytest.mark.unit
def test_select_current_snapshot_ids_rejects_ambiguous_or_missing_binding() -> None:
    current = _snapshot(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=_NOW,
        checksum="current",
    )
    duplicate = _snapshot(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=_NOW,
        checksum="duplicate",
    )
    entry = _entry(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=_NOW,
    )

    with pytest.raises(ValueError, match="exactly one current provider snapshot"):
        select_current_snapshot_ids(
            dataset_id="dividend",
            catalog_entries=(entry,),
            snapshots=(current, duplicate),
        )

    with pytest.raises(ValueError, match="exactly one current provider snapshot"):
        select_current_snapshot_ids(
            dataset_id="dividend",
            catalog_entries=(entry,),
            snapshots=(),
        )


@pytest.mark.unit
def test_build_expected_dates_uses_trading_and_natural_schedules() -> None:
    trading = build_expected_dates(
        schedule="trading_days",
        target_from=date(2026, 7, 30),
        target_to=date(2026, 8, 1),
        trading_days_provider=lambda _start, _end: ["2026-07-30", "2026-07-31"],
    )
    natural = build_expected_dates(
        schedule="natural_days",
        target_from=date(2026, 7, 30),
        target_to=date(2026, 8, 1),
        trading_days_provider=lambda _start, _end: [],
    )
    source_defined = build_expected_dates(
        schedule="source_defined",
        target_from=date(2026, 7, 30),
        target_to=date(2026, 8, 1),
        trading_days_provider=lambda _start, _end: [],
    )

    assert trading == (date(2026, 7, 30), date(2026, 7, 31))
    assert natural == (
        date(2026, 7, 30),
        date(2026, 7, 31),
        date(2026, 8, 1),
    )
    assert source_defined == natural


@pytest.mark.unit
def test_probe_consumer_payload_reads_sqlite_and_parquet(tmp_path) -> None:
    sqlite_path = tmp_path / "metadata" / "metadata.sqlite"
    sqlite_path.parent.mkdir()
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("CREATE TABLE dividend (instrument_id INTEGER)")
        connection.executemany("INSERT INTO dividend VALUES (?)", [(1,), (2,)])
        connection.commit()
    parquet_root = tmp_path / "market" / "stock" / "bars"
    parquet_root.mkdir(parents=True)
    pl.DataFrame(
        {"instrument_id": [1, 2, 3], "trade_date": [date(2026, 7, 31)] * 3}
    ).write_parquet(parquet_root / "2026.parquet")

    dividend = probe_consumer_payload(tmp_path, "dividend")
    stock_daily = probe_consumer_payload(tmp_path, "stock_daily")

    assert dividend == {"kind": "sqlite", "object": "dividend", "row_count": 2}
    assert stock_daily == {
        "file_count": 1,
        "kind": "parquet",
        "object": "market/stock/bars",
        "row_count": 3,
    }


@pytest.mark.unit
def test_probe_consumer_payload_fails_closed_on_empty_payload(tmp_path) -> None:
    sqlite_path = tmp_path / "metadata" / "metadata.sqlite"
    sqlite_path.parent.mkdir()
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("CREATE TABLE dividend (instrument_id INTEGER)")
        connection.commit()

    with pytest.raises(ValueError, match="consumer payload is empty"):
        probe_consumer_payload(tmp_path, "dividend")


@pytest.mark.unit
def test_load_passing_recovery_evidence_accepts_addressed_gate_group(tmp_path) -> None:
    path = tmp_path / "recoverability.json"
    payload = orjson.dumps(
        {
            "schema": "ditto.r2-live-gate-artifact",
            "version": 1,
            "kind": "recoverability",
            "recoverability": {
                "passed": True,
                "reason_codes": [],
                "payload_root_sha256": "a" * 64,
                "sqlite_table_row_counts": {"provider_snapshots": 19},
            },
        },
        option=orjson.OPT_SORT_KEYS,
    )
    path.write_bytes(payload)

    resolved, digest = load_passing_recovery_evidence(path)

    assert resolved == path.resolve()
    assert digest == hashlib.sha256(payload).hexdigest()


@pytest.mark.unit
def test_load_passing_recovery_evidence_rejects_blocked_group(tmp_path) -> None:
    path = tmp_path / "recoverability.json"
    path.write_bytes(
        orjson.dumps(
            {
                "schema": "ditto.r2-live-gate-artifact",
                "version": 1,
                "kind": "recoverability",
                "recoverability": {"passed": False},
            }
        )
    )

    with pytest.raises(ValueError, match="passing recoverability"):
        load_passing_recovery_evidence(path)
