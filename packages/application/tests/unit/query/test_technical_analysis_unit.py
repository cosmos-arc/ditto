"""Application tests for exact PIT technical-analysis queries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisQueryService,
    TechnicalAnalysisRequest,
    TechnicalAnalysisSourcePort,
    TechnicalAnalysisSpecDraft,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_features.technical_analysis.service import TechnicalAnalysisService
from ditto_kernel.identity import InstrumentId

_AS_OF = datetime(2026, 8, 31, 7, tzinfo=UTC)


def _snapshot(
    snapshot_id: str = "snapshot-stock",
    *,
    created_at: datetime = datetime(2026, 8, 30, 7, tzinfo=UTC),
) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-01-01",
        request_end="2026-08-30",
        schema_version="v1",
        checksum=f"checksum-{snapshot_id}",
        canonical_asset=DataAssetRef(dataset_id="stock_daily", namespace="market"),
        request_parameters_hash=f"request-{snapshot_id}",
        response_metadata=(),
        license_record_id="license-tushare",
        row_count=100,
        payload_uri=f"artifact://{snapshot_id}",
        payload_retained=True,
        created_at=created_at,
    )


def _bar(day: int, close: float) -> TechnicalBar:
    occurred_at = datetime(2026, 8, day, 7, tzinfo=UTC)
    return TechnicalBar(
        occurred_at=occurred_at,
        knowledge_at=occurred_at + timedelta(minutes=5),
        publication_at=occurred_at,
        source_snapshot_id="snapshot-stock",
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=1_000,
        turnover=100_000,
        adjustment_factor=1,
        suspended=False,
        benchmark_close=100 + day,
        industry_close=99 + day,
    )


def _request() -> TechnicalAnalysisRequest:
    return TechnicalAnalysisRequest(
        instrument_id=InstrumentId(600519),
        instrument_name="贵州茅台",
        instrument_code="600519.SH",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("snapshot-stock",),
        spec=TechnicalAnalysisSpecDraft(
            spec_id="technical-core",
            spec_version="1",
            timeframes=("daily",),
            return_window=3,
            trend_window=3,
            slope_window=3,
            rsi_window=3,
            macd_fast=2,
            macd_slow=3,
            macd_signal=2,
            atr_window=3,
            volatility_window=3,
            volume_window=3,
            donchian_window=3,
            support_resistance_window=5,
        ),
        selection_run_id="selection-run:sha256:a",
    )


@dataclass
class _Source:
    bars: tuple[TechnicalBar, ...]
    calls: list[tuple[PITQueryContext, InstrumentId, str]]

    def load(
        self,
        context: PITQueryContext,
        *,
        instrument_id: InstrumentId,
        instrument_code: str,
    ) -> tuple[TechnicalBar, ...]:
        self.calls.append((context, instrument_id, instrument_code))
        return self.bars


def _facade(source: TechnicalAnalysisSourcePort) -> TechnicalAnalysisFacade:
    reader = MagicMock(spec=ProviderSnapshotReader)
    reader.get_snapshot.side_effect = {"snapshot-stock": _snapshot()}.get
    query = TechnicalAnalysisQueryService(source, TechnicalAnalysisService())
    return TechnicalAnalysisFacade(snapshot_reader=reader, query=query)


@pytest.mark.pit
def test_query_resolves_exact_snapshots_and_computes_replayable_view() -> None:
    source = _Source(tuple(_bar(day, 100 + day) for day in range(1, 7)), [])

    snapshot = _facade(source).get_snapshot(_request())

    assert snapshot.instrument_id == InstrumentId(600519)
    assert snapshot.source_snapshot_ids == ("snapshot-stock",)
    assert snapshot.selection_run_id == "selection-run:sha256:a"
    assert snapshot.status == "ready"
    assert source.calls[0][0].source_snapshot_ids == ("snapshot-stock",)
    assert source.calls[0][1:] == (InstrumentId(600519), "600519.SH")


def test_query_maps_source_lineage_drift_to_application_error() -> None:
    drifted = _Source(
        (replace(_bar(1, 100), source_snapshot_id="snapshot-other"),),
        [],
    )

    with pytest.raises(AppQueryError, match="source snapshot"):
        _facade(drifted).get_snapshot(_request())


@pytest.mark.parametrize(
    ("provider_snapshot", "message"),
    [
        (None, "not found"),
        (
            _snapshot(created_at=datetime(2026, 9, 1, tzinfo=UTC)),
            "not visible",
        ),
    ],
)
def test_facade_fails_closed_without_exact_visible_snapshot(
    provider_snapshot: ProviderSnapshot | None,
    message: str,
) -> None:
    reader = MagicMock(spec=ProviderSnapshotReader)
    reader.get_snapshot.return_value = provider_snapshot
    facade = TechnicalAnalysisFacade(snapshot_reader=reader, query=MagicMock())

    with pytest.raises(AppQueryError, match=message):
        facade.get_snapshot(_request())
