"""Technical-analysis exact query route tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock, patch

from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisFacade,
    TechnicalAnalysisQueryService,
)
from ditto_apps.api.routes.technical_analysis import query_technical_analysis
from ditto_apps.models.technical_analysis import (
    TechnicalAnalysisQueryBody,
    TechnicalAnalysisSpecRequest,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_features.technical_analysis.service import TechnicalAnalysisService
from ditto_kernel.identity import InstrumentId

_AS_OF = datetime(2026, 8, 31, 7, tzinfo=UTC)


class _Source:
    def load(self, context, *, instrument_id, instrument_code):
        del instrument_id, instrument_code
        return tuple(
            TechnicalBar(
                occurred_at=_AS_OF - timedelta(days=day),
                knowledge_at=_AS_OF - timedelta(days=day),
                publication_at=_AS_OF - timedelta(days=day),
                source_snapshot_id=context.source_snapshot_ids[0],
                open=100 + day,
                high=103 + day,
                low=99 + day,
                close=102 + day,
                volume=1_000,
                turnover=100_000,
                adjustment_factor=1,
                suspended=False,
                benchmark_close=100 + day,
                industry_close=100 + day,
            )
            for day in range(6, 0, -1)
        )


def _snapshot() -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id="snapshot-stock",
        dataset_id="stock_daily",
        source="tushare",
        request_start="2026-01-01",
        request_end="2026-08-30",
        schema_version="v1",
        checksum="abc",
        canonical_asset=DataAssetRef(dataset_id="stock_daily", namespace="market"),
        request_parameters_hash="request",
        response_metadata=(),
        license_record_id="license",
        row_count=6,
        payload_uri="artifact://snapshot-stock",
        payload_retained=True,
        created_at=_AS_OF - timedelta(days=1),
    )


def _body() -> TechnicalAnalysisQueryBody:
    return TechnicalAnalysisQueryBody(
        instrument_id=InstrumentId(600519),
        instrument_name="贵州茅台",
        instrument_code="600519.SH",
        as_of=_AS_OF,
        knowledge_cutoff=_AS_OF,
        publication_cutoff=_AS_OF,
        source_snapshot_ids=("snapshot-stock",),
        spec=TechnicalAnalysisSpecRequest(
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


def test_request_contract_accepts_json_arrays_emitted_by_openapi_clients() -> None:
    payload = _body().model_dump(mode="json")

    decoded = TechnicalAnalysisQueryBody.model_validate(payload)

    assert decoded.source_snapshot_ids == ("snapshot-stock",)
    assert decoded.spec.timeframes == ("daily",)


async def _inline(function: Callable[..., object], /, *args, **kwargs):
    return function(*args, **kwargs)


def test_route_returns_exact_snapshot_with_indicator_and_level_evidence() -> None:
    reader = MagicMock(spec=ProviderSnapshotReader)
    reader.get_snapshot.return_value = _snapshot()
    facade = TechnicalAnalysisFacade(
        snapshot_reader=reader,
        query=TechnicalAnalysisQueryService(_Source(), TechnicalAnalysisService()),
    )
    handler = cast(
        Callable[..., object],
        query_technical_analysis.__dict__["__dishka_orig_func__"],
    )

    with patch(
        "ditto_apps.api.routes.technical_analysis.asyncio.to_thread",
        side_effect=_inline,
    ):
        response = asyncio.run(handler(body=_body(), facade=facade))

    assert response.data.instrument_id == InstrumentId(600519)
    assert response.data.selection_run_id == "selection-run:sha256:a"
    assert response.data.source_snapshot_ids == ("snapshot-stock",)
    assert {item.name for item in response.data.readings} >= {"rsi", "macd", "atr"}
    assert response.data.levels
