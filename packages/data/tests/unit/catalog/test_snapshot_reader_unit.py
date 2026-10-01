"""Qualified field projection over retained snapshot payload identities."""

from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.snapshot_completion import PartitionLifecycleStatus
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
)

_DAY = date(2026, 9, 18)
_VISIBLE = datetime(2026, 9, 30, 9, tzinfo=UTC)


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-09-18",
            request_end="2026-09-18",
            schema_version="market.stock_daily.v1",
            checksum="a" * 32,
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="a" * 64,
            response_metadata=(),
            license_record_id="license:1",
            row_count=4,
            payload_uri="provider_payloads/tushare/stock_daily/"
            + "a" * 32
            + ".parquet",
            payload_retained=True,
            created_at=_VISIBLE,
        )
    )


def _lifecycle(snapshot: ProviderSnapshot):
    class _Lifecycle:
        def list_complete(self, *, dataset_id=None, source=None):
            checkpoint = PartitionCheckpoint(
                chunk_id="chunk-1",
                dataset_id=snapshot.dataset_id,
                source=snapshot.source,
                request_start=snapshot.request_start,
                request_end=snapshot.request_end,
                status=PartitionLifecycleStatus.COMPLETE,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=(
                    f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"
                ),
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=_VISIBLE,
            )
            return (checkpoint,)

        def list_events(self, chunk_id):
            return (
                PartitionLifecycleEvent(
                    event_id=1,
                    chunk_id=chunk_id,
                    from_status=None,
                    to_status=PartitionLifecycleStatus.COMPLETE,
                    attempt=1,
                    evidence_id=snapshot.snapshot_id,
                    error_code=None,
                    occurred_at=_VISIBLE,
                ),
            )

    return _Lifecycle()


def _service(frame: pl.DataFrame, snapshot: ProviderSnapshot) -> SnapshotReadService:
    class _Snapshots:
        def get_snapshot(self, snapshot_id):
            return snapshot if snapshot_id == snapshot.snapshot_id else None

        def get_observed_at(self, snapshot_id):
            return _VISIBLE

        def get_predecessor(self, snapshot_id):
            return None

        def list_snapshots(self, *, dataset_id=None):
            return (snapshot,)

    class _Payloads:
        def read_payload(self, artifact):
            return frame

    return SnapshotReadService(_Snapshots(), _Payloads(), _lifecycle(snapshot))


_TICKER_FRAME = pl.DataFrame(
    {
        "source_ticker": ["000001.SZ", "600519.SH", "300750.SZ"],
        "trade_date": [_DAY, _DAY, _DAY],
        "close": [10.0, 1500.0, 200.0],
        "volume": [100, 200, 300],
    }
)

_INSTRUMENT_FRAME = _TICKER_FRAME.rename(
    {"source_ticker": "instrument_id"}
).with_columns(
    pl.col("instrument_id").str.replace_all(r"\D", "").cast(pl.Int64) + 1_000_000
)


def test_ticker_keyed_payload_filters_through_resolver() -> None:
    """Provider-grain payloads project the qualified scope via resolved tickers."""
    service = _service(_TICKER_FRAME, _snapshot())
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close", "volume"),
        instrument_ids=(1_000_001, 1_000_002),
        date_range=(_DAY, _DAY),
        ticker_resolver=lambda ids, *, source, asof: {
            1_000_001: "000001.SZ",
            1_000_002: "600519.SH",
        },
    )
    assert frame.columns == ["source_ticker", "trade_date", "close", "volume"]
    assert frame["source_ticker"].to_list() == ["000001.SZ", "600519.SH"]


def test_ticker_keyed_payload_without_resolver_fails_closed() -> None:
    """No resolver means the qualified instrument scope cannot be expressed."""
    service = _service(_TICKER_FRAME, _snapshot())
    with pytest.raises(ValueError, match="instrument/date/field"):
        service.read_fields(
            _snapshot().snapshot_id,
            ("close",),
            instrument_ids=(1_000_001,),
            date_range=(_DAY, _DAY),
        )


def test_unresolved_instruments_project_no_rows() -> None:
    """Identities the mapping cannot resolve read as an empty qualified scope."""
    service = _service(_TICKER_FRAME, _snapshot())
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close",),
        instrument_ids=(1_000_009,),
        date_range=(_DAY, _DAY),
        ticker_resolver=lambda ids, *, source, asof: {},
    )
    assert frame.height == 0


def test_instrument_keyed_payload_keeps_direct_filter() -> None:
    """Resolved-identity payloads filter directly and ignore the resolver."""
    service = _service(_INSTRUMENT_FRAME, _snapshot())
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close",),
        instrument_ids=(1_000_001,),
        date_range=(_DAY, _DAY),
        ticker_resolver=lambda ids, *, source, asof: {1_000_001: "000001.SZ"},
    )
    assert frame.columns == ["instrument_id", "trade_date", "close"]
    assert frame.height == 1
