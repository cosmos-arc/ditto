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


@pytest.mark.pit
def test_etf_paper_market_excludes_future_publication_and_wrong_instrument(
    tmp_path: Path,
) -> None:
    cutoff = datetime(2026, 9, 2, 8, tzinfo=UTC)
    visible = datetime(2026, 9, 2, 7, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2],
            "source_ticker": ["510300.SH", "510300.SH", "159919.SZ"],
            "event_time": [visible] * 3,
            "published_at": [visible, cutoff + timedelta(seconds=1), visible],
            "available_at": [visible] * 3,
            "open": [10.0, 999_999.0, 20.0],
            "high": [10.2, 1_000_000.0, 20.2],
            "low": [9.9, 999_998.0, 19.9],
            "close": [10.1, 999_999.0, 20.1],
            "pre_close": [10.0, 999_999.0, 20.0],
            "volume": [1000.0, 1000.0, 1000.0],
            "amount": [10_000.0, 1000.0, 20_000.0],
            "up_limit": [11.0, 1_000_000.0, 22.0],
            "down_limit": [9.0, 999_998.0, 18.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=visible, dataset_id="etf_daily")
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id="etf_daily",
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    source = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot), payload_reader=store
    )
    market = source.load_paper_market(
        context,
        instrument_id=InstrumentId(1),
        instrument_code="510300.SH",
        trade_date="2026-09-02",
    )
    assert market.close == 10.1
    assert market.source_snapshot_id == snapshot.snapshot_id


@pytest.mark.pit
def test_etf_paper_market_accepts_ticker_only_retained_payload(tmp_path: Path) -> None:
    """Ordinary ingestion retains the adapter frame before FK enrichment."""
    cutoff = datetime(2026, 9, 2, 8, tzinfo=UTC)
    visible = datetime(2026, 9, 2, 7, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "source_ticker": ["510300.SH", "159919.SZ"],
            "event_time": [visible] * 2,
            "published_at": [visible] * 2,
            "available_at": [visible] * 2,
            "open": [10.0, 20.0],
            "high": [10.2, 20.2],
            "low": [9.9, 19.9],
            "close": [10.1, 20.1],
            "pre_close": [10.0, 20.0],
            "volume": [1000.0, 1000.0],
            "amount": [10_000.0, 20_000.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(frame, store, created_at=visible, dataset_id="etf_daily")
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id="etf_daily",
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    market = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot), payload_reader=store
    ).load_paper_market(
        context,
        instrument_id=InstrumentId(1),
        instrument_code="510300.SH",
        trade_date="2026-09-02",
    )
    assert market.close == 10.1
    assert market.limit_up is None
    assert market.limit_down is None


@pytest.mark.pit
def test_etf_paper_bar_visible_under_producer_next_day_knowledge_stamp(
    tmp_path: Path,
) -> None:
    """DAILY_OHLCV_MAPPING stamps knowledge_date = trade_date + 1."""
    trade_day = date(2026, 9, 2)
    cutoff = datetime(2026, 9, 3, 8, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"],
            "trade_date": [trade_day],
            "knowledge_date": [trade_day + timedelta(days=1)],
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.1],
            "pre_close": [10.0],
            "volume": [1000.0],
            "amount": [10_000.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        frame, store, created_at=cutoff - timedelta(hours=1), dataset_id="etf_daily"
    )
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=(
            DatasetSnapshot(
                dataset_id="etf_daily",
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            ),
        ),
    )
    market = ProviderPayloadTechnicalAnalysisSource(
        snapshot_reader=_SnapshotReader(snapshot), payload_reader=store
    ).load_paper_market(
        context,
        instrument_id=InstrumentId(1),
        instrument_code="510300.SH",
        trade_date="2026-09-02",
    )
    assert market.close == 10.1
    assert market.observed_at == datetime(2026, 9, 2, 7, tzinfo=UTC)
    assert market.publication_cutoff == datetime(2026, 9, 3, 7, tzinfo=UTC)


def _snapshot(
    frame: pl.DataFrame,
    store: FilesystemProviderPayloadStore,
    *,
    created_at: datetime,
    dataset_id: str = "stock_daily",
) -> ProviderSnapshot:
    artifact = store.retain_payload(
        dataset_id=dataset_id,
        source="tushare",
        payload=frame,
    )
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="tushare",
            request_start="2026-08-01",
            request_end="2026-08-31",
            schema_version=f"market.{dataset_id}.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(
                dataset_id=dataset_id,
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
def test_source_requires_id_and_ticker_to_agree_instead_of_mixing_rows(
    tmp_path: Path,
) -> None:
    """A corrected mapping must not value instrument A with B's rows."""
    cutoff = datetime(2026, 8, 31, 7, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            # Instrument 1 stored under its own ticker, and instrument 600519
            # stored under the ticker a later correction now returns for 1.
            "instrument_id": [1, 600519],
            "source_ticker": ["000001.SZ", "600519.SH"],
            "event_time": [cutoff - timedelta(days=1)] * 2,
            "published_at": [cutoff - timedelta(days=1)] * 2,
            "available_at": [cutoff - timedelta(days=1)] * 2,
            "open": [10.0, 99.0],
            "high": [11.0, 100.0],
            "low": [9.0, 98.0],
            "close": [10.5, 99.5],
            "vol": [100.0, 100.0],
            "amount": [1_000.0, 10_000.0],
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
        snapshot_reader=_SnapshotReader(snapshot), payload_reader=store
    )

    # The stale-ID row and the other instrument's ticker row must not merge:
    # the disagreement resolves to zero rows instead of a mixed price series.
    assert (
        source.load(context, instrument_id=InstrumentId(1), instrument_code="600519.SH")
        == ()
    )
    # Agreeing identifiers still resolve normally in both directions.
    assert (
        source.load(
            context, instrument_id=InstrumentId(600519), instrument_code="600519.SH"
        )[0].close
        == 99.5
    )


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
