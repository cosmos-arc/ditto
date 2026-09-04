"""Retained-provider-payload adapter tests for technical analysis."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.technical_analysis_source import (
    ProviderPayloadTechnicalAnalysisSource,
)
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_kernel.identity import InstrumentId


class _SnapshotReader:
    def __init__(self, value: ProviderSnapshot) -> None:
        self._value = value

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._value if snapshot_id == self._value.snapshot_id else None


def _snapshot(
    frame: pl.DataFrame,
    store: FilesystemProviderPayloadStore,
    *,
    created_at: datetime,
) -> ProviderSnapshot:
    artifact = store.retain_payload(
        dataset_id="stock_daily",
        source="tushare",
        payload=frame,
    )
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-08-01",
            request_end="2026-08-31",
            schema_version="market.stock_daily.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
            ),
            request_parameters_hash="sha256:technical-source-test",
            response_metadata=(),
            license_record_id="license:tushare:stock_daily:test",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=created_at,
        )
    )


@pytest.mark.pit
def test_source_reads_only_exact_instrument_and_visible_rows(tmp_path: Path) -> None:
    cutoff = datetime(2026, 8, 31, 7, tzinfo=UTC)
    times = [cutoff - timedelta(days=6 - index) for index in range(7)]
    frame = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"] * 6 + ["000001.SZ"],
            "event_time": [*times[:5], cutoff + timedelta(days=1), times[5]],
            "published_at": [*times[:5], cutoff + timedelta(days=1), times[5]],
            "available_at": [*times[:5], cutoff + timedelta(days=1), times[5]],
            "open": [99.0, 100.0, 101.0, 102.0, 103.0, 999_999.0, 10.0],
            "high": [102.0, 103.0, 104.0, 105.0, 106.0, 1_000_001.0, 12.0],
            "low": [98.0, 99.0, 100.0, 101.0, 102.0, 999_998.0, 9.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 1_000_000.0, 11.0],
            "vol": [100.0, 200.0, 300.0, 400.0, 500.0, 999.0, 100.0],
            "amount": [10_000.0, 20_000.0, 30_000.0, 40_000.0, 50_000.0, 999.0, 100.0],
            "adj_factor": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            "is_suspended": [False, False, False, False, True, False, False],
            "benchmark_close": [100.0] * 7,
            "industry_close": [100.0] * 7,
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=cutoff - timedelta(hours=1))
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )

    bars = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot),
        payload_reader=store,
    ).load(
        context,
        instrument_id=InstrumentId(600519),
        instrument_code="600519.SH",
    )

    assert [item.close for item in bars] == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert bars[-1].suspended is True
    assert {item.source_snapshot_id for item in bars} == {snapshot.snapshot_id}


@pytest.mark.pit
def test_source_normalizes_provider_dates_to_utc_before_pit_filter(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 8, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"],
            "trade_date": [date(2026, 8, 30)],
            "knowledge_date": [date(2026, 8, 31)],
            "open": [99.0],
            "high": [101.0],
            "low": [98.0],
            "close": [100.0],
            "vol": [100.0],
            "amount": [10_000.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=cutoff - timedelta(hours=2))
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )

    bars = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot),
        payload_reader=store,
    ).load(
        context,
        instrument_id=InstrumentId(600519),
        instrument_code="600519.SH",
    )

    assert bars[0].occurred_at == datetime(2026, 8, 30, 7, tzinfo=UTC)
    assert bars[0].knowledge_at == datetime(2026, 8, 31, 7, tzinfo=UTC)


def test_source_fails_closed_when_required_ohlc_columns_are_missing(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 7, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"],
            "event_time": [cutoff - timedelta(days=1)],
            "published_at": [cutoff - timedelta(days=1)],
            "available_at": [cutoff - timedelta(days=1)],
            "close": [100.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=cutoff - timedelta(hours=1))
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    source = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot),
        payload_reader=store,
    )

    with pytest.raises(AppQueryError, match="required_column_missing") as exc_info:
        source.load(
            context,
            instrument_id=InstrumentId(600519),
            instrument_code="600519.SH",
        )
    assert exc_info.value.details == {
        "code": "TECHNICAL_SOURCE_SCHEMA_INVALID",
        "reason": "required_column_missing",
        "field": "OHLC",
    }


def test_source_fails_closed_when_required_ohlc_values_are_null(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 8, 31, 7, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"],
            "event_time": [cutoff - timedelta(days=1)],
            "published_at": [cutoff - timedelta(days=1)],
            "available_at": [cutoff - timedelta(days=1)],
            "open": [99.0],
            "high": [101.0],
            "low": [98.0],
            "close": [None],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=cutoff - timedelta(hours=1))
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    source = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot),
        payload_reader=store,
    )

    with pytest.raises(AppQueryError, match="required_value_null") as exc_info:
        source.load(
            context,
            instrument_id=InstrumentId(600519),
            instrument_code="600519.SH",
        )
    assert exc_info.value.details == {
        "code": "TECHNICAL_SOURCE_VALUE_INVALID",
        "reason": "required_value_null",
        "field": "close",
    }
