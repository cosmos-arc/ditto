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

pytestmark = pytest.mark.pit

_DAY = date(2026, 9, 18)
_OTHER_DAY = date(2026, 9, 17)
_VISIBLE = datetime(2026, 9, 30, 9, tzinfo=UTC)


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-09-17",
            request_end="2026-09-18",
            schema_version="market.stock_daily.v1",
            checksum="a" * 32,
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash="a" * 32,
            response_metadata=(),
            row_count=4,
            payload_uri=(
                "provider_payloads/tushare/stock_daily/" + "a" * 32 + ".parquet"
            ),
            payload_retained=True,
            created_at=_VISIBLE,
        )
    )


def _lifecycle(snapshot: ProviderSnapshot):
    class _Lifecycle:
        def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
            raise AssertionError(f"reads must not inspect latest: {chunk_id}")

        def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
            raise AssertionError(f"reads must not inspect checkpoints: {chunk_id}")

        def list_incomplete(
            self,
            *,
            dataset_id: str | None = None,
            source: str | None = None,
        ) -> tuple[PartitionCheckpoint, ...]:
            raise AssertionError("reads must not list incomplete chunks")

        def list_complete(
            self,
            *,
            dataset_id: str | None = None,
            source: str | None = None,
        ) -> tuple[PartitionCheckpoint, ...]:
            checkpoint = PartitionCheckpoint(
                chunk_id="chunk-1",
                dataset_id=snapshot.dataset_id,
                source=snapshot.source,
                request_start=snapshot.request_start,
                request_end=snapshot.request_end,
                status=PartitionLifecycleStatus.COMPLETE,
                payload_id=(
                    f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"
                ),
                complete_evidence_id=snapshot.snapshot_id,
                error_code=None,
                updated_at=_VISIBLE,
            )
            return (checkpoint,)

        def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
            raise AssertionError(f"reads must not inspect events: {chunk_id}")

    return _Lifecycle()


def _service(frame: pl.DataFrame, snapshot: ProviderSnapshot) -> SnapshotReadService:
    class _Snapshots:
        def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
            return snapshot if snapshot_id == snapshot.snapshot_id else None

        def get_observed_at(self, snapshot_id: str) -> datetime | None:
            return _VISIBLE

        def get_predecessor(self, snapshot_id: str) -> str | None:
            return None

        def list_snapshots(
            self,
            *,
            dataset_id: str | None = None,
            source: str | None = None,
            canonical_asset: DataAssetRef | None = None,
        ) -> tuple[ProviderSnapshot, ...]:
            return (snapshot,)

    class _Payloads:
        def read_payload(self, artifact):
            return frame

    return SnapshotReadService(_Snapshots(), _Payloads(), _lifecycle(snapshot))


_TICKER_FRAME = pl.DataFrame(
    {
        "source_ticker": [
            "600000.Old",
            "000001.SZ",
            "600000.SH",
            "600000.SH",
        ],
        "trade_date": [_OTHER_DAY, _DAY, _OTHER_DAY, _DAY],
        "close": [9.0, 10.0, 11.0, 12.0],
        "volume": [1, 2, 3, 4],
    }
)

_INSTRUMENT_FRAME = pl.DataFrame(
    {
        "instrument_id": [1_000_001, 1_000_002],
        "trade_date": [_DAY, _DAY],
        "close": [10.0, 20.0],
    }
)


def _resolver(mapping_by_date, *, spy=None):
    def resolve(instrument_ids, *, source, asofs, cutoff):
        if spy is not None:
            spy["asofs"] = tuple(asofs)
            spy["cutoff"] = cutoff
        return {
            asof.isoformat(): {
                iid: ticker
                for iid, ticker in mapping_by_date.get(asof.isoformat(), {}).items()
                if iid in instrument_ids
            }
            for asof in asofs
        }

    return resolve


def test_ticker_keyed_payload_filters_per_qualified_date() -> None:
    """Ticker changes resolve per date; rows match the identity valid that day."""
    service = _service(_TICKER_FRAME, _snapshot())
    spy: dict[str, object] = {}
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close", "volume"),
        instrument_ids=(1_000_001,),
        date_range=(_OTHER_DAY, _DAY),
        knowledge_cutoff=_VISIBLE,
        ticker_resolver=_resolver(
            {
                "2026-09-17": {1_000_001: "600000.Old"},
                "2026-09-18": {1_000_001: "600000.SH"},
            },
            spy=spy,
        ),
    )
    assert frame.columns == ["source_ticker", "trade_date", "close", "volume"]
    assert frame["source_ticker"].to_list() == ["600000.Old", "600000.SH"]
    assert spy["cutoff"] == _VISIBLE
    assert set(spy["asofs"]) == {_OTHER_DAY, _DAY}  # type: ignore[arg-type]


def test_ticker_keyed_payload_without_resolver_fails_closed() -> None:
    """No resolver means the qualified instrument scope cannot be expressed."""
    service = _service(_TICKER_FRAME, _snapshot())
    with pytest.raises(ValueError, match="instrument/date/field"):
        service.read_fields(
            _snapshot().snapshot_id,
            ("close",),
            instrument_ids=(1_000_001,),
            date_range=(_OTHER_DAY, _DAY),
            knowledge_cutoff=_VISIBLE,
        )


def test_ticker_keyed_payload_without_cutoff_fails_closed() -> None:
    """Identity resolution is not PIT-defined without a knowledge cutoff."""
    service = _service(_TICKER_FRAME, _snapshot())
    with pytest.raises(ValueError, match="knowledge cutoff"):
        service.read_fields(
            _snapshot().snapshot_id,
            ("close",),
            instrument_ids=(1_000_001,),
            date_range=(_OTHER_DAY, _DAY),
            knowledge_cutoff=None,
            ticker_resolver=_resolver({"2026-09-18": {1_000_001: "000001.SZ"}}),
        )


def test_never_resolved_instrument_is_rejected() -> None:
    """An identity resolving on no qualified date must not silently shrink scope."""
    service = _service(_TICKER_FRAME, _snapshot())
    with pytest.raises(ValueError, match="cannot resolve instrument identities"):
        service.read_fields(
            _snapshot().snapshot_id,
            ("close",),
            instrument_ids=(1_000_001, 1_000_009),
            date_range=(_OTHER_DAY, _DAY),
            knowledge_cutoff=_VISIBLE,
            ticker_resolver=_resolver(
                {
                    "2026-09-17": {1_000_001: "600000.Old"},
                    "2026-09-18": {1_000_001: "600000.SH"},
                }
            ),
        )


def test_identity_valid_on_one_date_projects_only_that_date() -> None:
    """A listing that starts mid-interval reads rows only from its own dates."""
    service = _service(_TICKER_FRAME, _snapshot())
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close",),
        instrument_ids=(1_000_002,),
        date_range=(_OTHER_DAY, _DAY),
        knowledge_cutoff=_VISIBLE,
        ticker_resolver=_resolver({"2026-09-18": {1_000_002: "000001.SZ"}}),
    )
    assert frame["trade_date"].to_list() == [_DAY]


def test_instrument_keyed_payload_keeps_direct_filter() -> None:
    """Resolved-identity payloads filter directly and ignore the resolver."""
    service = _service(_INSTRUMENT_FRAME, _snapshot())
    frame = service.read_fields(
        _snapshot().snapshot_id,
        ("close",),
        instrument_ids=(1_000_001,),
        date_range=(_DAY, _DAY),
        knowledge_cutoff=_VISIBLE,
        ticker_resolver=_resolver({}),
    )
    assert frame.columns == ["instrument_id", "trade_date", "close"]
    assert frame.height == 1
