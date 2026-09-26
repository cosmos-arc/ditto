"""Real retained-payload chart read with a trading-calendar cutoff."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import polars as pl
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.market_chart import (
    MarketChartQueryFacade,
    MarketChartRequest,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes.market import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    ProviderSnapshotReader,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


class _Snapshots:
    def __init__(self, values: tuple[ProviderSnapshot, ...]) -> None:
        self._values = values

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (item for item in self._values if item.snapshot_id == snapshot_id), None
        )

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: object = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            item
            for item in self._values
            if (dataset_id is None or item.dataset_id == dataset_id)
            and (source is None or item.source == source)
        )


def _snapshot(
    store: FilesystemProviderPayloadStore,
    dataset: str,
    frame: pl.DataFrame,
    created: datetime,
) -> ProviderSnapshot:
    artifact = store.retain_payload(dataset_id=dataset, source="tushare", payload=frame)
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset,
            source="tushare",
            request_start="2026-03-09",
            request_end="2026-03-15",
            schema_version=f"{dataset}.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(dataset_id=dataset, namespace="market"),
            request_parameters_hash="sha256:market-chart-test",
            response_metadata=(),
            license_record_id=f"license:tushare:{dataset}:test",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=created,
        )
    )


def _chart(
    tmp_path: Path, *, poisoned: bool = True
) -> tuple[MarketChartQueryFacade, ProviderSnapshot, MetadataQueryFacade]:
    store = FilesystemProviderPayloadStore(tmp_path)
    visible = datetime(2026, 3, 10, 7, tzinfo=UTC)
    rows = [
        ("2026-03-09", 10.0, 10.5, 9.5, 10.2, 100.0, 1000.0),
        ("2026-03-10", 10.2, 11.0, 10.0, 10.8, 200.0, 2200.0),
    ]
    if poisoned:
        rows.append(
            ("2026-03-12", 999_999.0, 1_000_000.0, 999_998.0, 999_999.0, 300.0, 3000.0)
        )
    bars = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"] * len(rows),
            "event_time": [
                datetime.fromisoformat(day).replace(hour=7, tzinfo=UTC)
                for day, *_ in rows
            ],
            "published_at": [
                visible if day != "2026-03-12" else visible + timedelta(days=2)
                for day, *_ in rows
            ],
            "available_at": [
                visible if day != "2026-03-12" else visible + timedelta(days=2)
                for day, *_ in rows
            ],
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [row[5] for row in rows],
            "amount": [row[6] for row in rows],
        }
    )
    calendar_days = [date(2026, 3, day).isoformat() for day in range(9, 16)]
    calendar = pl.DataFrame(
        {
            "trade_date": calendar_days,
            "is_open": [day < "2026-03-14" for day in calendar_days],
        }
    )
    bar_snapshot = _snapshot(store, "stock_daily", bars, visible)
    factors = pl.DataFrame(
        {
            "source_ticker": ["600519.SH"] * 3,
            "trade_date": ["2026-03-09", "2026-03-10", "2026-03-12"],
            "published_at": [visible, visible, visible + timedelta(days=2)],
            "available_at": [visible, visible, visible + timedelta(days=2)],
            "adj_factor": [1.0, 1.1, 99.0],
        }
    )
    factor_snapshot = _snapshot(store, "adj_factor", factors, visible)
    calendar_snapshot = _snapshot(
        store, "calendar", calendar, visible - timedelta(days=1)
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots((bar_snapshot, calendar_snapshot, factor_snapshot)),
    )
    metadata = cast(
        MetadataQueryFacade,
        SimpleNamespace(
            get_source_ticker=lambda *args, **kwargs: "600519.SH",
            get_instrument=lambda instrument_id: (
                {"asset_class": "stock", "list_date": "2001-08-27"}
                if instrument_id == 1000001
                else None
            ),
        ),
    )
    market = cast(
        MarketQueryFacade,
        SimpleNamespace(
            assert_bars_allowed=lambda **kwargs: None,
            assert_adjustment_allowed=lambda **kwargs: None,
        ),
    )
    return (
        MarketChartQueryFacade(reader, store, metadata, market),
        bar_snapshot,
        metadata,
    )


@pytest.mark.pit
def test_chart_uses_real_sessions_and_excludes_future_price(tmp_path: Path) -> None:
    chart, snapshot, _ = _chart(tmp_path)
    request = MarketChartRequest(
        instrument_id=1000001,
        asset_class="stock",
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
        period="weekly",
        adjustment="none",
        allow_experimental_data=False,
        now=datetime(2026, 3, 11, 6, tzinfo=UTC),
    )
    result = chart.get_chart(request)
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert (
        bar.first_trade_date,
        bar.last_trade_date,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.amount,
    ) == ("2026-03-09", "2026-03-10", 10.0, 11.0, 9.5, 10.8, 300.0, 3200.0)
    assert bar.partial is True
    assert bar.source_snapshot_ids == (snapshot.snapshot_id,)
    assert result.latest_price_date == "2026-03-10"
    assert (
        result.stale_reason is None
    )  # Wednesday's close is not yet required at this cutoff.
    assert result.missing_sessions == ()
    assert result.calendar_snapshot_ids
    assert chart.get_chart(request).bars == result.bars
    later = chart.get_chart(
        MarketChartRequest(
            **{**vars(request), "now": datetime(2026, 3, 13, 6, tzinfo=UTC)}
        )
    )
    assert later.bars[0].close == 999_999.0
    assert later.missing_sessions == ("2026-03-11",)


@pytest.mark.pit
def test_chart_adjustment_uses_visible_exact_factors(tmp_path: Path) -> None:
    chart, _, _ = _chart(tmp_path)
    base = MarketChartRequest(
        instrument_id=1000001,
        asset_class="stock",
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
        period="weekly",
        adjustment="qfq",
        allow_experimental_data=False,
        now=datetime(2026, 3, 11, 6, tzinfo=UTC),
    )
    adjusted = chart.get_chart(base)
    assert adjusted.bars[0].open == pytest.approx(10 / 1.1)
    assert adjusted.bars[0].close == pytest.approx(10.8)
    assert adjusted.bars[0].high == pytest.approx(11.0)
    assert len(adjusted.bars[0].source_snapshot_ids) == 2
    assert chart.get_chart(
        MarketChartRequest(**{**vars(base), "adjustment": "hfq"})
    ).bars[0].close == pytest.approx(11.88)


def test_chart_fails_closed_without_calendar(tmp_path: Path) -> None:
    chart, _, _ = _chart(tmp_path)
    chart._snapshots = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                item
                for item in chart._snapshots.list_snapshots()
                if item.dataset_id != "calendar"
            )
        ),
    )
    with pytest.raises(AppQueryError, match="calendar is unavailable"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 15),
                period="daily",
                adjustment="none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 11, 8, tzinfo=UTC),
            )
        )


@pytest.mark.integration
def test_chart_http_journey_keeps_exact_identity_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise FastAPI, Dishka, retained payloads, and serialized chart response."""
    chart, price_snapshot, metadata = _chart(tmp_path)

    class ChartProvider(Provider):
        scope = Scope.APP

        @provide
        def chart_facade(self) -> MarketChartQueryFacade:
            return chart

        @provide
        def metadata_facade(self) -> MetadataQueryFacade:
            return metadata

    app = FastAPI()
    configure_exception_handlers(app)
    setup_dishka(container=make_async_container(ChartProvider()), app=app)
    app.include_router(router, prefix="/api/v1")
    body = {
        "instrument_id": 1000001,
        "start_date": "2026-03-09",
        "end_date": "2026-03-10",
        "period": "weekly",
        "adjustment": "none",
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/market/chart", json=body)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["bars"][0]["close"] == 10.8
        assert data["bars"][0]["partial"] is True
        assert data["bars"][0]["source_snapshot_ids"] == [price_snapshot.snapshot_id]
        assert data["calendar_snapshot_ids"]
        assert data["as_of"] == data["knowledge_cutoff"] == data["publication_cutoff"]
        assert data["latest_price_date"] == "2026-03-10"

        class DecisionClock(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:
                return datetime(2026, 3, 11, 6, tzinfo=UTC)

        monkeypatch.setattr("ditto_apps.api.routes.market.datetime", DecisionClock)
        sentinel = client.post(
            "/api/v1/market/chart",
            json={**body, "end_date": "2026-03-15"},
        )
        assert sentinel.status_code == 200
        assert sentinel.json()["data"]["bars"][0]["high"] == 11.0

        previous = chart._snapshots
        chart._snapshots = cast(
            ProviderSnapshotReader,
            _Snapshots(
                tuple(
                    item
                    for item in previous.list_snapshots()
                    if item.dataset_id != "calendar"
                )
            ),
        )
        assert client.post("/api/v1/market/chart", json=body).status_code == 422
        chart._snapshots = previous
        assert client.post("/api/v1/market/chart", json=body).status_code == 200
        assert (
            client.post(
                "/api/v1/market/chart", json={**body, "instrument_id": 999}
            ).status_code
            == 404
        )
