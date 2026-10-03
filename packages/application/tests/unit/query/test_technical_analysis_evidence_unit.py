"""Exact technical-analysis evidence facade tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisRequest,
)
from ditto_application.queries.technical_analysis_evidence import (
    InstrumentTechnicalEvidenceQuery,
    InstrumentTechnicalEvidenceQueryFacade,
)
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
from ditto_features.technical_analysis.contracts import (
    TechnicalAnalysisSnapshot,
    TechnicalLevel,
    TechnicalLevelKind,
    TechnicalTimeframe,
)
from ditto_kernel.identity import InstrumentId


def _provider_snapshot(suffix: str, *, created_at: datetime) -> ProviderSnapshot:
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="tushare",
            request_start="2026-08-01",
            request_end="2026-08-31",
            schema_version="market.stock_daily.v1",
            checksum=f"checksum-{suffix}",
            canonical_asset=DataAssetRef("stock_daily", "market"),
            request_parameters_hash=f"params-{suffix}",
            response_metadata=(),
            license_record_id="synthetic-license",
            row_count=10,
            payload_uri=f"evidence://retained/{suffix}",
            payload_retained=True,
            created_at=created_at,
        )
    )


def _checkpoint(snapshot: ProviderSnapshot) -> PartitionCheckpoint:
    return PartitionCheckpoint(
        chunk_id=f"chunk-{snapshot.checksum}",
        dataset_id=snapshot.dataset_id,
        source=snapshot.source,
        request_start=snapshot.request_start,
        request_end=snapshot.request_end,
        status=PartitionLifecycleStatus.COMPLETE,
        last_successful_stage=PartitionLifecycleStatus.COMPLETE,
        attempt=1,
        retry_budget=3,
        payload_id=f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}",
        catalog_asset_id=None,
        lineage_run_id=None,
        ingestion_log_id=None,
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

    def get_latest_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self._checkpoint_for(chunk_id)

    def get_checkpoint(self, chunk_id: str) -> PartitionCheckpoint | None:
        return self._checkpoint_for(chunk_id)

    def list_incomplete(
        self, *, dataset_id: str, source: str | None = None
    ) -> tuple[PartitionCheckpoint, ...]:
        del source
        return tuple(
            checkpoint
            for snapshot in self._snapshots
            if snapshot.dataset_id == dataset_id
            and (checkpoint := _checkpoint(snapshot)).status
            is not PartitionLifecycleStatus.COMPLETE
        )

    def list_complete(self, *, dataset_id: str) -> tuple[PartitionCheckpoint, ...]:
        return tuple(
            _checkpoint(snapshot)
            for snapshot in self._snapshots
            if snapshot.dataset_id == dataset_id
        )

    def list_events(self, chunk_id: str) -> tuple[PartitionLifecycleEvent, ...]:
        checkpoint = self._checkpoint_for(chunk_id)
        if checkpoint is None:
            return ()
        snapshot = next(
            item
            for item in self._snapshots
            if item.request_start == checkpoint.request_start
            and item.request_end == checkpoint.request_end
        )
        return (
            PartitionLifecycleEvent(
                event_id=1,
                chunk_id=chunk_id,
                from_status=PartitionLifecycleStatus.SUCCESS_RECORDED,
                to_status=PartitionLifecycleStatus.COMPLETE,
                attempt=1,
                evidence_id=snapshot.snapshot_id,
                error_code=None,
                occurred_at=checkpoint.updated_at,
            ),
        )

    def _checkpoint_for(self, chunk_id: str) -> PartitionCheckpoint | None:
        return next(
            (
                _checkpoint(snapshot)
                for snapshot in self._snapshots
                if _checkpoint(snapshot).chunk_id == chunk_id
            ),
            None,
        )


def _snapshot(request: TechnicalAnalysisRequest) -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        snapshot_id="technical-analysis:sha256:" + "a" * 64,
        input_hash="b" * 64,
        spec_hash="c" * 64,
        registry_version="technical-indicator-registry.v1",
        instrument_id=request.instrument_id,
        instrument_name=request.instrument_name,
        as_of=request.as_of,
        knowledge_cutoff=request.knowledge_cutoff,
        publication_cutoff=request.publication_cutoff,
        source_snapshot_ids=request.source_snapshot_ids,
        status="ready",
        last_visible_bar_at=request.as_of,
        last_computed_bar_at=request.as_of,
        readings=(),
        levels=(
            TechnicalLevel(
                timeframe=TechnicalTimeframe.DAILY,
                kind=TechnicalLevelKind.SUPPORT,
                price=97.5,
                confidence=0.75,
                touches=3,
                window=60,
                algorithm_version="support-resistance.v1",
            ),
        ),
        timeframe_summaries=(),
        conflicts=(),
        missing_inputs=(),
        warnings=(),
        selection_run_id=request.selection_run_id,
        research_case_id=request.research_case_id,
        portfolio_snapshot_id=request.portfolio_snapshot_id,
    )


class _TechnicalFacade:
    def __init__(self) -> None:
        self.requests: list[TechnicalAnalysisRequest] = []

    def get_snapshot(
        self,
        request: TechnicalAnalysisRequest,
    ) -> TechnicalAnalysisSnapshot:
        self.requests.append(request)
        return _snapshot(request)


def _context(snapshot_set_id: str) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
        publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
        source_snapshot_id=snapshot_set_id,
    )


def _facade(
    snapshots: tuple[ProviderSnapshot, ...],
) -> tuple[InstrumentTechnicalEvidenceQueryFacade, _TechnicalFacade]:
    technical = _TechnicalFacade()
    return (
        InstrumentTechnicalEvidenceQueryFacade(
            snapshots=_Snapshots(snapshots),
            lifecycle=_Lifecycle(snapshots),
            technical_analysis=technical,
        ),
        technical,
    )


def test_evidence_computes_exact_snapshot_and_preserves_only_recorded_levels() -> None:
    snapshots = (
        _provider_snapshot("stock", created_at=datetime(2026, 8, 31, 6, tzinfo=UTC)),
    )
    facade, technical = _facade(snapshots)
    snapshot_set_id = aggregate_source_snapshot_ids((snapshots[0].snapshot_id,))
    assert snapshot_set_id is not None

    result = facade.get_evidence(
        query=InstrumentTechnicalEvidenceQuery(
            instrument_id=InstrumentId(600519),
            instrument_name="贵州茅台",
            instrument_code="600519.SH",
            selection_run_id="selection-run:sha256:" + "e" * 64,
        ),
        context=_context(snapshot_set_id),
    )

    assert result.snapshot_id == "technical-analysis:sha256:" + "a" * 64
    assert result.payload.value["levels"] == (
        {
            "algorithm_version": "support-resistance.v1",
            "confidence": 0.75,
            "kind": "support",
            "price": 97.5,
            "timeframe": "daily",
            "touches": 3,
            "window": 60,
        },
    )
    assert tuple(item.artifact_kind for item in result.artifact_refs) == (
        "technical_analysis_snapshot",
    )
    assert technical.requests[0].source_snapshot_ids == (snapshots[0].snapshot_id,)
    assert technical.requests[0].spec.timeframes == ("daily", "weekly")


def test_evidence_rejects_host_snapshot_mismatch_before_computation() -> None:
    facade, technical = _facade(
        (_provider_snapshot("stock", created_at=datetime(2026, 8, 31, 6, tzinfo=UTC)),)
    )

    with pytest.raises(AppQueryError, match="snapshot"):
        facade.get_evidence(
            query=InstrumentTechnicalEvidenceQuery(
                instrument_id=InstrumentId(600519),
                instrument_name="贵州茅台",
                instrument_code="600519.SH",
            ),
            context=_context("snapshot-future"),
        )

    assert technical.requests == []


def test_evidence_ignores_snapshots_created_after_the_knowledge_cutoff() -> None:
    historical = _provider_snapshot(
        "historical", created_at=datetime(2026, 8, 31, 5, tzinfo=UTC)
    )
    late = _provider_snapshot(
        "latest", created_at=datetime(2026, 8, 31, 8, 30, tzinfo=UTC)
    )
    technical = _TechnicalFacade()
    facade = InstrumentTechnicalEvidenceQueryFacade(
        snapshots=_Snapshots((historical, late)),
        lifecycle=_Lifecycle((historical, late)),
        technical_analysis=technical,
    )
    historical_set = aggregate_source_snapshot_ids((historical.snapshot_id,))
    assert historical_set is not None

    result = facade.get_evidence(
        query=InstrumentTechnicalEvidenceQuery(
            instrument_id=InstrumentId(600519),
            instrument_name="贵州茅台",
            instrument_code="600519.SH",
        ),
        context=_context(historical_set),
    )

    assert technical.requests[0].source_snapshot_ids == (historical.snapshot_id,)
    assert result.source_snapshot_ids == (historical.snapshot_id,)
