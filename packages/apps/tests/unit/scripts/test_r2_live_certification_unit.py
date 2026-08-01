"""Unit contract for the R2 live certification orchestrator."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, date, datetime
from types import SimpleNamespace

import orjson
import polars as pl
import pytest
from ditto_apps.scripts.r2_live_certification import (
    ReusableCertificationRequest,
    build_expected_dates,
    load_passing_recovery_evidence,
    probe_consumer_payload,
    resolve_reusable_certification,
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
def test_probe_consumer_payload_reads_basic_assets_from_base_instrument(
    tmp_path,
) -> None:
    sqlite_path = tmp_path / "metadata" / "metadata.sqlite"
    sqlite_path.parent.mkdir()
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            "CREATE TABLE instrument (instrument_id INTEGER, asset_class TEXT)"
        )
        connection.executemany(
            "INSERT INTO instrument VALUES (?, ?)",
            [(1, "stock"), (2, "etf"), (3, "etf"), (4, "index")],
        )
        connection.execute(
            "CREATE TABLE instrument_etf (instrument_id INTEGER PRIMARY KEY)"
        )
        connection.commit()

    result = probe_consumer_payload(tmp_path, "etf_basic")

    assert result == {
        "kind": "sqlite",
        "object": "instrument[asset_class=etf]",
        "row_count": 2,
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


@pytest.mark.unit
def test_resolve_reusable_certification_requires_exact_addressed_inputs(
    tmp_path,
) -> None:
    data_root = tmp_path / "live-data"
    evidence_root = tmp_path / "evidence"
    snapshot_ids = ("snapshot:tushare:dividend:sha256:current",)
    payload = {
        "schema": "ditto.r2-live-consumer-evidence.v1",
        "dataset_id": "dividend",
        "data_root": str(data_root.resolve()),
        "generated_at": _NOW.isoformat(),
        "probe": {"kind": "sqlite", "object": "dividend", "row_count": 5},
        "snapshot_ids": list(snapshot_ids),
    }
    content = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    digest = hashlib.sha256(content).hexdigest()
    consumer_path = (
        evidence_root
        / "products"
        / "dividend"
        / f"consumer-read-smoke.sha256-{digest}.json"
    )
    consumer_path.parent.mkdir(parents=True)
    consumer_path.write_bytes(content)
    recovery_uri = "artifact+sha256://recovery/current"
    active = SimpleNamespace(
        dataset_id="dividend",
        profile="r2-modern-a-share-v1",
        coverage=SimpleNamespace(
            target_from=date(2015, 1, 1),
            target_to=date(2026, 7, 31),
            is_complete=True,
        ),
        evidence=SimpleNamespace(
            snapshot_ids=snapshot_ids,
            recovery_results=(
                SimpleNamespace(
                    name="isolated_backup_restore_hash_parity",
                    evidence_uri=recovery_uri,
                    passed=True,
                ),
            ),
            consumer_results=(
                SimpleNamespace(
                    name="production_consumer_read_smoke",
                    evidence_uri=(
                        "artifact+sha256://r2-live/consumer/dividend/" + digest
                    ),
                    passed=True,
                ),
            ),
        ),
    )

    resolved_path, resolved_hash = resolve_reusable_certification(
        active_report=active,
        request=ReusableCertificationRequest(
            dataset_id="dividend",
            profile="r2-modern-a-share-v1",
            target_from=date(2015, 1, 1),
            target_to=date(2026, 7, 31),
            snapshot_ids=snapshot_ids,
            recovery_evidence_uri=recovery_uri,
            data_root=data_root,
            evidence_root=evidence_root,
        ),
    )

    assert resolved_path == consumer_path.resolve()
    assert resolved_hash == digest


@pytest.mark.unit
def test_resolve_reusable_certification_rejects_snapshot_drift(tmp_path) -> None:
    active = SimpleNamespace(
        dataset_id="dividend",
        profile="r2-modern-a-share-v1",
        coverage=SimpleNamespace(
            target_from=date(2015, 1, 1),
            target_to=date(2026, 7, 31),
            is_complete=True,
        ),
        evidence=SimpleNamespace(snapshot_ids=("snapshot:stale",)),
    )

    with pytest.raises(ValueError, match="snapshot binding drift"):
        resolve_reusable_certification(
            active_report=active,
            request=ReusableCertificationRequest(
                dataset_id="dividend",
                profile="r2-modern-a-share-v1",
                target_from=date(2015, 1, 1),
                target_to=date(2026, 7, 31),
                snapshot_ids=("snapshot:current",),
                recovery_evidence_uri="artifact+sha256://recovery/current",
                data_root=tmp_path / "live-data",
                evidence_root=tmp_path / "evidence",
            ),
        )
