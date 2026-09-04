"""Immutable-payload market-context source tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from ditto_application.queries.market_context_source import (
    ProviderPayloadMarketContextSource,
)
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext


class _SnapshotReader:
    def __init__(self, values: tuple[ProviderSnapshot, ...]) -> None:
        self._values = {value.snapshot_id: value for value in values}

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return self._values.get(snapshot_id)

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            value
            for value in self._values.values()
            if (dataset_id is None or value.dataset_id == dataset_id)
            and (source is None or value.source == source)
            and (canonical_asset is None or value.canonical_asset == canonical_asset)
        )


def _snapshot(
    *,
    dataset_id: str,
    frame: pl.DataFrame,
    store: FilesystemProviderPayloadStore,
    created_at: datetime,
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
                partition_keys=("month=2026-08",),
            ),
            request_parameters_hash="sha256:test-request",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=f"license:tushare:{dataset_id}:test",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=created_at,
        )
    )


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_excludes_future_rows_and_computes_core_facts(
    tmp_path: Path,
) -> None:
    timezone = UTC
    cutoff = datetime(2026, 8, 31, 8, 0, tzinfo=timezone)
    stock = pl.DataFrame(
        {
            "source_ticker": ["000001.SZ", "000002.SZ", "000003.SZ", "000001.SZ"],
            "event_time": [
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(days=1),
            ],
            "published_at": [
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(days=1),
            ],
            "available_at": [
                cutoff - timedelta(minutes=30),
                cutoff - timedelta(minutes=30),
                cutoff - timedelta(minutes=30),
                cutoff + timedelta(days=1),
            ],
            "pct_chg": [1.0, -0.5, 0.0, -99.0],
            "close": [10.0, 20.0, 30.0, 0.1],
        }
    )
    index_times = [cutoff - timedelta(days=20 - index) for index in range(21)]
    index = pl.DataFrame(
        {
            "source_ticker": ["000300.SH"] * 21,
            "event_time": index_times,
            "published_at": index_times,
            "available_at": index_times,
            "close": [100.0 + index for index in range(21)],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshots = (
        _snapshot(
            dataset_id="stock_daily",
            frame=stock,
            store=store,
            created_at=cutoff - timedelta(minutes=15),
        ),
        _snapshot(
            dataset_id="index_daily",
            frame=index,
            store=store,
            created_at=cutoff - timedelta(minutes=15),
        ),
    )
    context = PITQueryContext(
        as_of=cutoff,
        knowledge_cutoff=cutoff,
        publication_cutoff=cutoff,
        source_snapshots=tuple(
            DatasetSnapshot(
                dataset_id=snapshot.dataset_id,
                dataset_version=snapshot.schema_version,
                source_snapshot_ids=(snapshot.snapshot_id,),
                created_at=snapshot.created_at,
            )
            for snapshot in snapshots
        ),
    )
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader(snapshots),
        payload_reader=store,
    )

    facts = source.load(context)

    assert facts.regime_input.advancing_count == 1
    assert facts.regime_input.declining_count == 1
    assert facts.regime_input.universe_count == 3
    assert facts.regime_input.benchmark_return_20d == pytest.approx(0.20)
    assert facts.regime_input.realized_volatility_20d is not None
    assert facts.regime_input.realized_volatility_20d >= 0
    assert "market_context_source_unavailable" not in facts.uncertainties


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_source_normalizes_provider_dates_before_utc_cutoff(
    tmp_path: Path,
) -> None:
    """Provider-local date strings must compare by instant against UTC cutoffs."""
    cutoff = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    stock = pl.DataFrame(
        {
            "source_ticker": ["000001.SZ", "000002.SZ"],
            "trade_date": ["2026-08-31", "2026-08-31"],
            "knowledge_date": ["2026-08-31", "2026-08-31"],
            "pct_chg": [1.0, -0.5],
            "close": [10.0, 20.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        dataset_id="stock_daily",
        frame=stock,
        store=store,
        created_at=cutoff - timedelta(minutes=15),
    )
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

    facts = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader((snapshot,)),
        payload_reader=store,
    ).load(context)

    assert facts.regime_input.advancing_count == 1
    assert facts.regime_input.declining_count == 1
    assert facts.regime_input.universe_count == 2


@pytest.mark.unit
@pytest.mark.pit
def test_market_context_global_return_uses_visible_global_index_previous_close(
    tmp_path: Path,
) -> None:
    """A-share context must not substitute FX/commodity for global indices."""
    cutoff = datetime(2026, 8, 31, 1, 0, tzinfo=UTC)
    global_index = pl.DataFrame(
        {
            "source_ticker": ["SPX", "SPX"],
            "event_time": [
                cutoff - timedelta(hours=8),
                cutoff + timedelta(hours=16),
            ],
            "published_at": [
                cutoff - timedelta(hours=7, minutes=45),
                cutoff + timedelta(hours=16, minutes=15),
            ],
            "available_at": [
                cutoff - timedelta(hours=7, minutes=30),
                cutoff + timedelta(hours=16, minutes=30),
            ],
            "close": [101.5, 1.0],
            "pre_close": [100.0, 100.0],
        }
    )
    store = FilesystemProviderPayloadStore(tmp_path)
    snapshot = _snapshot(
        dataset_id="global_index_daily",
        frame=global_index,
        store=store,
        created_at=cutoff - timedelta(minutes=15),
    )
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
    source = ProviderPayloadMarketContextSource(
        snapshot_reader=_SnapshotReader((snapshot,)),
        payload_reader=store,
    )

    facts = source.load(context)

    assert facts.regime_input.global_return_1d == pytest.approx(0.015)
    assert "global_return_1d" not in facts.regime_input.declared_missing_inputs
