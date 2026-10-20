"""Market-wide scoping of the completed snapshot coverage index (#583 F2)."""

from datetime import UTC, datetime

from ditto_application.providers_selection import completed_snapshot_index
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleEvent,
    PartitionLifecycleStatus,
)

_OBSERVED = datetime(2026, 10, 19, tzinfo=UTC)


class _SnapshotReader:
    def __init__(self, *snapshots: ProviderSnapshot) -> None:
        self._snapshots = snapshots

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (item for item in self._snapshots if item.snapshot_id == snapshot_id),
            None,
        )

    def get_observed_at(self, snapshot_id: str) -> datetime | None:
        return None

    def get_predecessor(self, snapshot_id: str) -> str | None:
        return None

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            item
            for item in self._snapshots
            if dataset_id is None or item.dataset_id == dataset_id
        )


class _LifecycleReader:
    def __init__(self, *checkpoints: PartitionCheckpoint) -> None:
        self._checkpoints = checkpoints

    def list_complete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            item
            for item in self._checkpoints
            if item.status is PartitionLifecycleStatus.COMPLETE
            and (dataset_id is None or item.dataset_id == dataset_id)
        )

    def list_incomplete(
        self, *, dataset_id: str | None = None, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        return ()

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return next(
            (item for item in self._checkpoints if item.chunk_id == chunk_id), None
        )

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self.get_latest_checkpoint(chunk_id)

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        return ()


def _block(
    chunk_id: str,
    *,
    request_start: str = "2026-10-08",
    request_end: str = "2026-10-19",
    response_metadata: tuple[tuple[str, str], ...] = (),
) -> tuple[ProviderSnapshot, PartitionCheckpoint]:
    """One retained completed snapshot with its matching checkpoint."""
    checksum = f"sha256:{chunk_id}"
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start=request_start,
            request_end=request_end,
            schema_version="market.stock_daily.v1",
            checksum=checksum,
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash=f"sha256:request:{chunk_id}",
            response_metadata=response_metadata,
            row_count=100,
            payload_uri=f"evidence://retained/{chunk_id}",
            payload_retained=True,
            created_at=_OBSERVED,
        )
    )
    return snapshot, PartitionCheckpoint(
        chunk_id=chunk_id,
        dataset_id="stock_daily",
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        status=PartitionLifecycleStatus.COMPLETE,
        payload_id=f"payload:{checksum}:{chunk_id}:{snapshot.snapshot_id}",
        complete_evidence_id=snapshot.snapshot_id,
        error_code=None,
        updated_at=_OBSERVED,
    )


def test_restricted_scope_snapshots_never_attest_market_coverage() -> None:
    market, market_cp = _block("market-wide", request_end="2026-10-16")
    per_ticker, per_ticker_cp = _block(
        "per-ticker",
        response_metadata=(("source_ticker", "000001.SZ"),),
    )
    index = completed_snapshot_index(
        _LifecycleReader(market_cp, per_ticker_cp), _SnapshotReader(market, per_ticker)
    )

    # 按标的回补的窗口即便覆盖今天且有行，也不得进入全市场证据索引
    # （与 covering_snapshots 的受限请求过滤同一规则，#583 F2）。
    assert index.snapshot_ids("stock_daily") == (market.snapshot_id,)
