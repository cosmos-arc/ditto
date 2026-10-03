from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.market_context import (
    MarketContextMetric,
    MarketContextRequest,
    MarketContextView,
)
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
)
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)


def _snapshot(
    dataset_id: str,
    suffix: str,
    *,
    created_at: datetime,
    payload_retained: bool = True,
) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="tushare",
            request_start="2026-08-01",
            request_end="2026-08-31",
            schema_version=f"market.{dataset_id}.v1",
            checksum=f"checksum-{suffix}",
            canonical_asset=DataAssetRef(dataset_id, "market"),
            request_parameters_hash=f"params-{suffix}",
            response_metadata=(),
            row_count=10,
            payload_uri=f"evidence://retained/{suffix}" if payload_retained else None,
            payload_retained=payload_retained,
            created_at=created_at,
        )
    )


def _complete_checkpoint(snapshot: ProviderSnapshot) -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id=f"chunk-{snapshot.dataset_id}",
        dataset_id=snapshot.dataset_id,
        source=snapshot.source,
        request_start=snapshot.request_start,
        request_end=snapshot.request_end,
        status=PartitionLifecycleStatus.COMPLETE,
        last_successful_stage=PartitionLifecycleStatus.COMPLETE,
        attempt=1,
        retry_budget=3,
        payload_id=(f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"),
        complete_evidence_id=snapshot.snapshot_id,
        error_code=None,
        updated_at=snapshot.created_at,
    )


class _Snapshots:
    def __init__(self, snapshots: tuple[ProviderSnapshot, ...]) -> None:
        self._snapshots = snapshots

    def list_snapshots(self, *, dataset_id: str) -> tuple[ProviderSnapshot, ...]:
        return tuple(item for item in self._snapshots if item.dataset_id == dataset_id)

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (item for item in self._snapshots if item.snapshot_id == snapshot_id),
            None,
        )


class _Lifecycle:
    def __init__(self, snapshots: tuple[ProviderSnapshot, ...]) -> None:
        self._snapshots = snapshots
        self._checkpoints = tuple(
            _complete_checkpoint(snapshot) for snapshot in snapshots
        )

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return next(
            (item for item in self._checkpoints if item.chunk_id == chunk_id), None
        )

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self.get_latest_checkpoint(chunk_id)

    def list_incomplete(
        self, *, dataset_id: str, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        del source
        return tuple(
            item
            for item in self._checkpoints
            if item.dataset_id == dataset_id
            and item.status is not PartitionLifecycleStatus.COMPLETE
        )

    def list_complete(self, *, dataset_id: str) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            item
            for item in self._checkpoints
            if item.dataset_id == dataset_id
            and item.status is PartitionLifecycleStatus.COMPLETE
        )


class _MarketContextFacade:
    def __init__(self) -> None:
        self.requests: list[MarketContextRequest] = []

    def get_context(self, request: MarketContextRequest) -> MarketContextView:
        self.requests.append(request)
        snapshot_set_id = aggregate_source_snapshot_ids(request.source_snapshot_ids)
        assert snapshot_set_id is not None
        return MarketContextView(
            as_of=request.as_of,
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshot_ids=request.source_snapshot_ids,
            source_snapshot_set_id=snapshot_set_id,
            status="ready",
            feature_set_id="market-regime:sha256:test",
            feature_version="market-regime.v1",
            regime_label="risk_on",
            regime_score=0.28,
            drivers=(),
            metrics=(
                MarketContextMetric(
                    name="advance_decline_breadth",
                    category="a_share",
                    value=0.42,
                    unit="ratio",
                    trend="rising",
                    freshness="fresh",
                    evidence_ref="dataset://stock_daily/breadth@2026-08-31",
                ),
            ),
            impacts=(),
            missing_inputs=(),
            data_conflicts=(),
            uncertainties=(),
            evidence_refs=("dataset://stock_daily/breadth@2026-08-31",),
        )


def _context(source_snapshot_id: str) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id=source_snapshot_id,
    )


def _evidence(
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[MarketContextEvidenceQueryFacade, _MarketContextFacade]:
    market = _MarketContextFacade()
    facade = MarketContextEvidenceQueryFacade(
        snapshots=_Snapshots(snapshots),
        lifecycle=_Lifecycle(snapshots),
        market_context=market,
    )
    return facade, market


def test_market_context_evidence_resolves_only_snapshots_observed_by_cutoff() -> None:
    snapshots = (
        _snapshot(
            "stock_daily", "stock", created_at=datetime(2026, 8, 31, 6, tzinfo=UTC)
        ),
        _snapshot(
            "index_daily", "index", created_at=datetime(2026, 8, 31, 6, 10, tzinfo=UTC)
        ),
        _snapshot(
            "global_index_daily",
            "global",
            created_at=datetime(2026, 8, 31, 6, 20, tzinfo=UTC),
        ),
        # Created after the knowledge cutoff: must stay invisible.
        _snapshot(
            "macro_indicators",
            "future-macro",
            created_at=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
        ),
    )
    facade, market = _evidence(snapshots)
    source_ids = tuple(
        sorted(
            item.snapshot_id
            for item in snapshots
            if item.created_at <= datetime(2026, 8, 31, 8, tzinfo=UTC)
        )
    )
    snapshot_set_id = aggregate_source_snapshot_ids(source_ids)
    assert snapshot_set_id is not None

    result = facade.get_evidence(context=_context(snapshot_set_id))

    assert result.status == "ready"
    assert result.source_snapshot_ids == source_ids
    assert result.payload.value["regime_label"] == "risk_on"
    assert result.payload.value["metrics"] == (
        {
            "category": "a_share",
            "evidence_ref": "dataset://stock_daily/breadth@2026-08-31",
            "freshness": "fresh",
            "name": "advance_decline_breadth",
            "trend": "rising",
            "unit": "ratio",
            "value": 0.42,
        },
    )
    assert market.requests == [
        MarketContextRequest(
            as_of=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_ids=source_ids,
        )
    ]


def test_market_context_evidence_rejects_host_snapshot_set_mismatch() -> None:
    facade, market = _evidence(
        (
            _snapshot(
                "stock_daily", "stock", created_at=datetime(2026, 8, 31, 6, tzinfo=UTC)
            ),
            _snapshot(
                "index_daily", "index", created_at=datetime(2026, 8, 31, 6, tzinfo=UTC)
            ),
        )
    )

    with pytest.raises(AppQueryError, match="snapshot_set"):
        facade.get_evidence(context=_context("snapshot-set:sha256:wrong"))

    assert market.requests == []


def test_market_context_evidence_fails_closed_without_core_dataset_snapshots() -> None:
    facade, market = _evidence(
        (
            _snapshot(
                "macro_indicators",
                "macro",
                created_at=datetime(2026, 8, 31, 6, tzinfo=UTC),
            ),
        )
    )

    with pytest.raises(AppQueryError, match="core_dataset_snapshot_missing"):
        facade.get_evidence(context=_context("snapshot-set:sha256:whatever"))

    assert market.requests == []
