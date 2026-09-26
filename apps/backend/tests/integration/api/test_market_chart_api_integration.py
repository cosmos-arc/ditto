"""Real retained-payload chart read with a trading-calendar cutoff."""

from __future__ import annotations

from dataclasses import replace
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
from ditto_data.services.market_service import MarketService
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


class _ChartMetadata(SimpleNamespace):
    def get_source_tickers(self, instrument_id, *, source, asofs, cutoff):
        return {
            day: self.get_source_ticker(
                instrument_id, source=source, asof=day, cutoff=cutoff
            )
            for day in asofs
        }


def _snapshot(
    store: FilesystemProviderPayloadStore,
    dataset: str,
    frame: pl.DataFrame,
    created: datetime,
    *,
    source: str = "tushare",
) -> ProviderSnapshot:
    artifact = store.retain_payload(dataset_id=dataset, source=source, payload=frame)
    return ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset,
            source=source,
            request_start="2026-03-09",
            request_end="2026-03-15",
            schema_version=f"{dataset}.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(dataset_id=dataset, namespace="market"),
            request_parameters_hash="sha256:market-chart-test",
            response_metadata=(),
            license_record_id=f"license:{source}:{dataset}:test",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=created,
        )
    )


def _chart(
    tmp_path: Path,
    *,
    poisoned: bool = True,
    suspended: bool = False,
    renamed: bool = False,
    price_source: str = "tushare",
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
            "source_ticker": [
                "OLD.SH" if renamed and row[0] == "2026-03-09" else "600519.SH"
                for row in rows
            ],
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
    bar_snapshot = _snapshot(store, "stock_daily", bars, visible, source=price_source)
    factors = pl.DataFrame(
        {
            "source_ticker": [
                "OLD.SH" if renamed and day == "2026-03-09" else "600519.SH"
                for day in ["2026-03-09", "2026-03-10", "2026-03-12"]
            ],
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
    status_snapshots = ()
    if suspended:
        status_snapshots = (
            _snapshot(
                store,
                "stock_status",
                pl.DataFrame(
                    {
                        "source_ticker": ["600519.SH", "600519.SH"],
                        "trade_date": ["2026-03-11", "2026-03-12"],
                        "is_suspended": [True, True],
                        "available_at": [visible, datetime(2099, 1, 1, tzinfo=UTC)],
                        "published_at": [visible, visible],
                    }
                ),
                visible,
            ),
        )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (bar_snapshot, calendar_snapshot, factor_snapshot, *status_snapshots)
        ),
    )
    metadata = cast(
        MetadataQueryFacade,
        _ChartMetadata(
            get_source_ticker=lambda *args, **kwargs: (
                "OLD.SH" if renamed and kwargs["asof"] < "2026-03-10" else "600519.SH"
            ),
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
            allows_suspension_evidence=lambda **kwargs: True,
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


@pytest.mark.pit
def test_chart_lifecycle_and_status_bound_expected_sessions(tmp_path: Path) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True)
    base = MarketChartRequest(
        instrument_id=1000001,
        asset_class="stock",
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 15),
        period="weekly",
        adjustment="none",
        allow_experimental_data=False,
        now=datetime(2026, 3, 13, 8, tzinfo=UTC),
        delisted_on=date(2026, 3, 13),
    )
    result = chart.get_chart(base)
    # Known full-day suspension is not a gap; future status cannot hide a gap.
    assert result.missing_sessions == ("2026-03-12",)
    assert result.stale_reason == "missing_expected_session"
    assert len(result.source_snapshot_ids) == 2
    closed = chart.get_chart(
        MarketChartRequest(**{**vars(base), "delisted_on": date(2026, 3, 11)})
    )
    assert closed.missing_sessions == ()
    assert closed.stale_reason is None
    assert closed.bars[0].partial is False
    # A retained bar on the exclusive delisting date must not be displayed.
    day_before = chart.get_chart(
        MarketChartRequest(**{**vars(base), "delisted_on": date(2026, 3, 10)})
    )
    assert day_before.latest_price_date == "2026-03-09"
    assert day_before.bars[0].close == 10.2
    assert day_before.missing_sessions == ()


@pytest.mark.pit
def test_chart_maps_prices_and_factors_at_each_effective_date(tmp_path: Path) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, renamed=True)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 10),
            period="daily",
            adjustment="qfq",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    assert [bar.trade_date for bar in result.bars] == ["2026-03-09", "2026-03-10"]
    assert result.missing_sessions == ()


@pytest.mark.pit
def test_chart_preserves_queried_lineage_when_no_visible_price(tmp_path: Path) -> None:
    chart, snapshot, _ = _chart(tmp_path)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 11),
            end_date=date(2026, 3, 11),
            period="daily",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    assert result.bars == ()
    assert result.stale_reason == "no_visible_price"
    assert result.missing_sessions == ("2026-03-11",)
    assert result.source_snapshot_ids == (snapshot.snapshot_id,)
    assert result.sources == ("tushare",)


@pytest.mark.pit
def test_chart_does_not_use_unapproved_status_to_hide_gaps(tmp_path: Path) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True)
    # Use the real catalog gate: stock_status is experimental independently of prices.
    market = MarketQueryFacade(cast(MarketService, SimpleNamespace()))
    chart._market = cast(
        MarketQueryFacade,
        SimpleNamespace(
            assert_bars_allowed=lambda **kwargs: None,
            allows_suspension_evidence=market.allows_suspension_evidence,
        ),
    )
    request = MarketChartRequest(
        instrument_id=1000001,
        asset_class="stock",
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 11),
        period="daily",
        adjustment="none",
        allow_experimental_data=False,
        now=datetime(2026, 3, 11, 8, tzinfo=UTC),
    )
    assert chart.get_chart(request).missing_sessions == ("2026-03-11",)
    assert (
        chart.get_chart(
            MarketChartRequest(**{**vars(request), "allow_experimental_data": True})
        ).missing_sessions
        == ()
    )


@pytest.mark.pit
@pytest.mark.parametrize(
    "revision", ["omitted", "other_request", "reobserved", "empty"]
)
def test_chart_snapshot_authority_is_bound_to_exact_request(
    tmp_path: Path, revision: str
) -> None:
    chart, original, metadata = _chart(tmp_path, poisoned=False)
    store = cast(FilesystemProviderPayloadStore, chart._payloads)
    observed = datetime(2026, 3, 10, 8, tzinfo=UTC)
    newer = _snapshot(
        store,
        "stock_daily",
        pl.DataFrame(
            {
                "source_ticker": [
                    "OTHER.SH" if revision == "other_request" else "600519.SH"
                ],
                "trade_date": ["2026-03-09"],
                "open": [99.0],
                "high": [100.0],
                "low": [98.0],
                "close": [99.0],
                "volume": [10.0],
                "amount": [100.0],
            }
        ),
        observed,
    )
    if revision == "other_request":
        newer = replace(newer, request_parameters_hash="sha256:other-ticker-request")
    if revision == "empty":
        newer = replace(
            newer,
            row_count=0,
            payload_retained=False,
            payload_uri=None,
            response_metadata=(
                ("snapshot_layer", "verified_empty_provider_observation"),
            ),
        )
    values = tuple(chart._snapshots.list_snapshots())
    if revision == "reobserved":
        original = replace(
            original, observations=(datetime(2026, 3, 11, 7, tzinfo=UTC),)
        )
        values = tuple(
            original if item.snapshot_id == original.snapshot_id else item
            for item in values
        )
    reader = cast(ProviderSnapshotReader, _Snapshots((*values, newer)))
    chart = MarketChartQueryFacade(reader, store, metadata, chart._market)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 10),
            period="daily",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    if revision == "omitted":
        assert [bar.close for bar in result.bars] == [99.0]
        assert result.missing_sessions == ("2026-03-10",)
    elif revision == "empty":
        assert result.bars == ()
        assert result.stale_reason == "no_visible_price"
        assert result.source_snapshot_ids == (newer.snapshot_id,)
    else:
        assert [bar.close for bar in result.bars] == [10.2, 10.8]
        assert result.missing_sessions == ()


@pytest.mark.pit
def test_chart_reports_sessions_before_retained_price_coverage(tmp_path: Path) -> None:
    chart, original, metadata = _chart(tmp_path, poisoned=False)
    store = cast(FilesystemProviderPayloadStore, chart._payloads)
    shard = _snapshot(
        store,
        "stock_daily",
        pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": ["2026-03-10"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.8],
                "volume": [10.0],
                "amount": [100.0],
            }
        ),
        datetime(2026, 3, 10, 7, tzinfo=UTC),
    )
    shard = replace(shard, request_start="2026-03-10")
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                shard if item.snapshot_id == original.snapshot_id else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    chart = MarketChartQueryFacade(reader, store, metadata, chart._market)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 10),
            period="daily",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    assert result.missing_sessions == ("2026-03-09",)
    assert result.latest_price_date == "2026-03-10"
    assert result.source_snapshot_ids == (shard.snapshot_id,)


@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["stock_daily", "adj_factor", "stock_status"])
def test_chart_ignores_unrelated_ticker_schema_authority(
    tmp_path: Path, dataset: str
) -> None:
    chart, _, metadata = _chart(tmp_path, poisoned=False)
    store = cast(FilesystemProviderPayloadStore, chart._payloads)
    other = _snapshot(
        store,
        dataset,
        pl.DataFrame(
            {
                "source_ticker": ["OTHER.SH"],
                "trade_date": ["2026-03-09"],
                "open": [99.0],
                "high": [100.0],
                "low": [98.0],
                "close": [99.0],
                "volume": [10.0],
                "amount": [100.0],
                "adj_factor": [99.0],
                "is_suspended": [True],
            }
        ),
        datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    other = replace(
        other,
        schema_version=f"{dataset}.v2",
        canonical_asset=DataAssetRef(
            dataset_id=dataset,
            namespace="market",
            partition_keys=("source_ticker=OTHER.SH",),
        ),
    )
    reader = cast(
        ProviderSnapshotReader, _Snapshots((*chart._snapshots.list_snapshots(), other))
    )
    chart = MarketChartQueryFacade(reader, store, metadata, chart._market)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 10),
            period="daily",
            adjustment="qfq" if dataset == "adj_factor" else "none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    assert [bar.trade_date for bar in result.bars] == ["2026-03-09", "2026-03-10"]
    assert other.snapshot_id not in result.source_snapshot_ids
    assert result.missing_sessions == ()


@pytest.mark.pit
@pytest.mark.parametrize("trade_day", ["2026-03-10", "20260310", date(2026, 3, 10)])
def test_daily_date_only_price_is_invisible_before_close(
    tmp_path: Path, trade_day: str | date
) -> None:
    chart, original, metadata = _chart(tmp_path, poisoned=False)
    store = cast(FilesystemProviderPayloadStore, chart._payloads)
    intraday = _snapshot(
        store,
        "stock_daily",
        pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": [trade_day],
                "open": [99.0],
                "high": [100.0],
                "low": [98.0],
                "close": [99.0],
                "volume": [10.0],
                "amount": [100.0],
            }
        ),
        datetime(2026, 3, 10, 5, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                intraday if item.snapshot_id == original.snapshot_id else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    chart = MarketChartQueryFacade(reader, store, metadata, chart._market)
    request = MarketChartRequest(
        instrument_id=1000001,
        asset_class="stock",
        start_date=date(2026, 3, 10),
        end_date=date(2026, 3, 10),
        period="daily",
        adjustment="none",
        allow_experimental_data=False,
        now=datetime(2026, 3, 10, 6, tzinfo=UTC),
    )
    assert chart.get_chart(request).bars == ()
    after_close = chart.get_chart(
        MarketChartRequest(
            **{**vars(request), "now": datetime(2026, 3, 10, 8, tzinfo=UTC)}
        )
    )
    assert after_close.bars[0].close == 99.0
    assert after_close.bars[0].partial is False


@pytest.mark.pit
def test_chart_calendar_authority_only_requires_active_lifetime(tmp_path: Path) -> None:
    chart, _, metadata = _chart(tmp_path, poisoned=False)
    store = cast(FilesystemProviderPayloadStore, chart._payloads)
    calendar = _snapshot(
        store,
        "calendar",
        pl.DataFrame(
            {
                "trade_date": ["2026-03-10"],
                "is_open": [True],
            }
        ),
        datetime(2026, 3, 9, 7, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                calendar if item.dataset_id == "calendar" else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    chart = MarketChartQueryFacade(reader, store, metadata, chart._market)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 15),
            period="weekly",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
            listed_on=date(2026, 3, 10),
            delisted_on=date(2026, 3, 11),
        )
    )
    assert result.bars[0].first_trade_date == "2026-03-10"
    assert result.bars[0].partial is False
    assert result.missing_sessions == ()
    assert result.calendar_snapshot_ids == (calendar.snapshot_id,)


@pytest.mark.pit
@pytest.mark.parametrize("day", [9, 12])
def test_chart_outside_lifecycle_returns_empty_without_calendar_query(
    tmp_path: Path, day: int
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False)
    chart._market = MarketQueryFacade(cast(MarketService, SimpleNamespace()))
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, day),
            end_date=date(2026, 3, day),
            period="daily",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
            listed_on=date(2026, 3, 10),
            delisted_on=date(2026, 3, 11),
        )
    )
    assert result.bars == ()
    assert result.missing_sessions == ()
    assert result.stale_reason is None
    assert result.source_snapshot_ids == ()
    assert result.calendar_snapshot_ids == ()


@pytest.mark.pit
@pytest.mark.parametrize("listed_on", [None, date(2026, 3, 14)])
def test_chart_closed_only_window_preserves_calendar_without_ingestion_failure(
    tmp_path: Path,
    listed_on: date | None,
) -> None:
    chart, snapshot, _ = _chart(tmp_path, poisoned=False)
    chart._snapshots = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                replace(item, request_end="2026-03-13")
                if item.snapshot_id == snapshot.snapshot_id
                else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9 if listed_on else 14),
            end_date=date(2026, 3, 15),
            period="daily",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
            listed_on=listed_on,
        )
    )
    assert result.bars == ()
    assert result.missing_sessions == ()
    assert result.stale_reason is None
    assert result.calendar_snapshot_ids
    assert result.source_snapshot_ids == ()


@pytest.mark.pit
@pytest.mark.parametrize("end_day", [10, 11])
def test_chart_aggregate_carries_suspension_observation_clocks(
    tmp_path: Path, end_day: int
) -> None:
    chart, price, _ = _chart(tmp_path, poisoned=False, suspended=True)
    status = _snapshot(
        FilesystemProviderPayloadStore(tmp_path),
        "stock_status",
        pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": ["2026-03-11"],
                "is_suspended": [True],
                "available_at": [datetime(2026, 3, 12, 8, tzinfo=UTC)],
                "published_at": [datetime(2026, 3, 12, 7, tzinfo=UTC)],
            }
        ),
        datetime(2026, 3, 12, 8, tzinfo=UTC),
    )
    chart._snapshots = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    item
                    for item in chart._snapshots.list_snapshots()
                    if item.dataset_id != "stock_status"
                ),
                status,
            )
        ),
    )
    chart = MarketChartQueryFacade(
        chart._snapshots, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, end_day),
            period="weekly",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
            delisted_on=date(2026, 3, 12),
        )
    )
    bar = result.bars[0]
    assert bar.partial is False
    assert set(bar.source_snapshot_ids) == {price.snapshot_id, status.snapshot_id}
    assert bar.available_at == status.created_at
    assert bar.published_at == datetime(2026, 3, 12, 7, tzinfo=UTC)


@pytest.mark.pit
@pytest.mark.parametrize(
    "late_dataset", ["stock_daily", "adj_factor", "stock_status", "calendar"]
)
def test_chart_availability_includes_late_snapshot_observation(
    tmp_path: Path, late_dataset: str
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True)
    observed = datetime(2026, 3, 12, 8, tzinfo=UTC)
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                replace(item, created_at=observed, observations=(observed,))
                if item.dataset_id == late_dataset
                else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 11),
            period="weekly",
            adjustment="qfq",
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
            delisted_on=date(2026, 3, 12),
        )
    )
    assert result.bars[0].available_at == observed
    assert result.bars[0].published_at < observed


@pytest.mark.pit
@pytest.mark.parametrize("adjustment", ["qfq", "hfq"])
def test_chart_qfq_earlier_bar_carries_late_baseline_factor(
    tmp_path: Path, adjustment: str
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False)
    observed = datetime(2026, 3, 12, 8, tzinfo=UTC)
    baseline = _snapshot(
        FilesystemProviderPayloadStore(tmp_path),
        "adj_factor",
        pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": ["2026-03-10"],
                "adj_factor": [1.2],
                "available_at": [observed],
                "published_at": [observed],
            }
        ),
        observed,
    )
    baseline = replace(baseline, request_start="2026-03-10", request_end="2026-03-10")
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    replace(item, request_start="2026-03-09", request_end="2026-03-09")
                    if item.dataset_id == "adj_factor"
                    else item
                    for item in chart._snapshots.list_snapshots()
                ),
                baseline,
            )
        ),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 10),
            period="daily",
            adjustment=adjustment,
            allow_experimental_data=False,
            now=datetime(2026, 3, 16, 8, tzinfo=UTC),
        )
    )
    earlier = result.bars[0]
    if adjustment == "qfq":
        assert baseline.snapshot_id in earlier.source_snapshot_ids
        assert earlier.available_at == observed
        assert earlier.published_at == observed
    else:
        assert baseline.snapshot_id not in earlier.source_snapshot_ids
        assert earlier.available_at < observed


@pytest.mark.pit
@pytest.mark.parametrize("start_date", [date(2026, 3, 9), date(2026, 4, 1)])
def test_chart_future_range_uses_only_cutoff_calendar(
    tmp_path: Path, start_date: date
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False)
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=start_date,
            end_date=date(2027, 3, 15),
            period="weekly",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 6, tzinfo=UTC),
        )
    )
    if start_date == date(2026, 3, 9):
        assert result.bars[0].last_trade_date == "2026-03-10"
        assert result.bars[0].partial is True
        assert result.missing_sessions == ()
    else:
        assert result.bars == ()
        assert result.calendar_snapshot_ids == ()
        assert result.source_snapshot_ids == ()


@pytest.mark.pit
def test_chart_qfq_uses_visible_factor_even_when_its_price_is_missing(
    tmp_path: Path,
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False)
    observed = datetime(2026, 3, 11, 8, tzinfo=UTC)
    baseline = _snapshot(
        FilesystemProviderPayloadStore(tmp_path),
        "adj_factor",
        pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "trade_date": ["2026-03-11"],
                "adj_factor": [2.0],
                "available_at": [observed],
                "published_at": [observed],
            }
        ),
        observed,
    )
    baseline = replace(baseline, request_start="2026-03-11", request_end="2026-03-11")
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots((*chart._snapshots.list_snapshots(), baseline)),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 11),
            period="daily",
            adjustment="qfq",
            allow_experimental_data=False,
            now=datetime(2026, 3, 12, 8, tzinfo=UTC),
        )
    )
    assert result.bars[0].close == pytest.approx(10.2 / 2.0)
    assert result.missing_sessions == ("2026-03-11",)
    assert baseline.snapshot_id in result.bars[0].source_snapshot_ids
    assert result.bars[0].available_at == observed


@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["stock_daily", "adj_factor", "stock_status"])
def test_chart_mixed_schema_shards_fail_explicitly_instead_of_false_gaps(
    tmp_path: Path, dataset: str
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True)
    original = chart._snapshots.list_snapshots(dataset_id=dataset)[0]
    older = replace(original, request_start="2026-03-09", request_end="2026-03-09")
    newer = replace(
        original,
        snapshot_id="new-schema-shard",
        schema_version=f"{dataset}.v2",
        request_start="2026-03-10",
        request_end="2026-03-10",
        created_at=datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    older if item.snapshot_id == original.snapshot_id else item
                    for item in chart._snapshots.list_snapshots()
                ),
                newer,
            )
        ),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    with pytest.raises(AppQueryError, match="incompatible schemas"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 10),
                period="daily",
                adjustment="qfq" if dataset == "adj_factor" else "none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 11, 8, tzinfo=UTC),
            )
        )


@pytest.mark.pit
def test_chart_mixed_price_sources_fail_instead_of_false_gaps(tmp_path: Path) -> None:
    chart, price, _ = _chart(tmp_path, poisoned=False)
    older = replace(price, request_end="2026-03-09")
    fallback = replace(
        price,
        snapshot_id="fuyao-fallback",
        source="fuyao",
        request_start="2026-03-10",
        request_end="2026-03-10",
        created_at=datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    older if item.snapshot_id == price.snapshot_id else item
                    for item in chart._snapshots.list_snapshots()
                ),
                fallback,
            )
        ),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    with pytest.raises(AppQueryError, match="incompatible sources"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 10),
                period="daily",
                adjustment="none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 11, 8, tzinfo=UTC),
            )
        )


@pytest.mark.pit
def test_chart_fallback_prices_use_independent_factor_and_status_sources(
    tmp_path: Path,
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True, price_source="fuyao")
    reader = chart._snapshots
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 11),
            period="daily",
            adjustment="qfq",
            allow_experimental_data=False,
            now=datetime(2026, 3, 11, 8, tzinfo=UTC),
        )
    )
    assert result.bars[0].close == pytest.approx(10.2 / 1.1)
    assert result.missing_sessions == ()
    assert result.sources == ("fuyao", "tushare")
    assert {
        item.snapshot_id for item in reader.list_snapshots(dataset_id="adj_factor")
    } <= set(result.source_snapshot_ids)
    assert {
        item.snapshot_id for item in reader.list_snapshots(dataset_id="stock_status")
    } <= set(result.source_snapshot_ids)


@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["stock_daily", "adj_factor", "stock_status"])
@pytest.mark.parametrize("outside_day", [9, 11])
def test_chart_ignores_conflicting_shards_outside_active_lifetime(
    tmp_path: Path, dataset: str, outside_day: int
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True)
    original = chart._snapshots.list_snapshots(dataset_id=dataset)[0]
    outside = replace(
        original,
        snapshot_id="outside-lifetime-shard",
        request_start=f"2026-03-{outside_day:02}",
        request_end=f"2026-03-{outside_day:02}",
        source="fuyao",
        schema_version=f"{dataset}.v2",
        created_at=datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots((*chart._snapshots.list_snapshots(), outside)),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 11),
            period="daily",
            adjustment="qfq" if dataset == "adj_factor" else "none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 12, 8, tzinfo=UTC),
            listed_on=date(2026, 3, 10),
            delisted_on=date(2026, 3, 11),
        )
    )
    assert [bar.trade_date for bar in result.bars] == ["2026-03-10"]
    assert outside.snapshot_id not in result.source_snapshot_ids
    assert result.missing_sessions == ()


@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["stock_daily", "adj_factor", "stock_status"])
@pytest.mark.parametrize("has_row", [True, False])
def test_chart_missing_effective_ticker_mapping_fails_instead_of_false_gap(
    tmp_path: Path, dataset: str, has_row: bool
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True, price_source="fuyao")
    missing_source = "fuyao" if dataset == "stock_daily" else "tushare"
    missing_day = (
        ("2026-03-11" if has_row else "2026-03-10")
        if dataset == "stock_status"
        else ("2026-03-09" if has_row else "2026-03-11")
    )
    metadata = cast(
        MetadataQueryFacade,
        _ChartMetadata(
            get_source_ticker=lambda *args, **kwargs: (
                None
                if kwargs["source"] == missing_source and kwargs["asof"] == missing_day
                else "600519.SH"
            ),
        ),
    )
    chart = MarketChartQueryFacade(
        chart._snapshots, chart._payloads, metadata, chart._market
    )
    with pytest.raises(AppQueryError, match="ticker mapping is unavailable"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 11),
                period="daily",
                adjustment="qfq" if dataset == "adj_factor" else "none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 12, 8, tzinfo=UTC),
            )
        )


@pytest.mark.pit
def test_chart_scoped_shard_missing_mapping_fails_before_snapshot_filtering(
    tmp_path: Path,
) -> None:
    chart, original, _ = _chart(tmp_path, poisoned=False)
    scoped = replace(
        original,
        request_start="2026-03-09",
        request_end="2026-03-09",
        canonical_asset=DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("source_ticker=600519.SH",),
        ),
    )
    valid = replace(
        scoped,
        snapshot_id="valid-day-shard",
        request_start="2026-03-10",
        request_end="2026-03-10",
        created_at=datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    scoped if item.snapshot_id == original.snapshot_id else item
                    for item in chart._snapshots.list_snapshots()
                ),
                valid,
            )
        ),
    )
    metadata = cast(
        MetadataQueryFacade,
        _ChartMetadata(
            get_source_ticker=lambda *args, **kwargs: (
                None if kwargs["asof"] == "2026-03-09" else "600519.SH"
            ),
        ),
    )
    chart = MarketChartQueryFacade(reader, chart._payloads, metadata, chart._market)
    with pytest.raises(AppQueryError, match="ticker mapping is unavailable"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 10),
                period="daily",
                adjustment="none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 11, 8, tzinfo=UTC),
            )
        )


@pytest.mark.pit
def test_chart_partial_candle_carries_late_empty_revision_evidence(
    tmp_path: Path,
) -> None:
    chart, price, _ = _chart(tmp_path, poisoned=False)
    observed = datetime(2026, 3, 12, 8, tzinfo=UTC)
    history = replace(price, request_end="2026-03-10")
    empty = replace(
        price,
        snapshot_id="late-empty-price-shard",
        request_start="2026-03-11",
        request_end="2026-03-11",
        row_count=0,
        payload_retained=False,
        payload_uri=None,
        created_at=observed,
        observations=(observed,),
        response_metadata=(("snapshot_layer", "verified_empty_provider_observation"),),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            (
                *(
                    history if item.snapshot_id == price.snapshot_id else item
                    for item in chart._snapshots.list_snapshots()
                ),
                empty,
            )
        ),
    )
    chart = MarketChartQueryFacade(
        reader, chart._payloads, chart._metadata, chart._market
    )
    result = chart.get_chart(
        MarketChartRequest(
            instrument_id=1000001,
            asset_class="stock",
            start_date=date(2026, 3, 9),
            end_date=date(2026, 3, 11),
            period="weekly",
            adjustment="none",
            allow_experimental_data=False,
            now=datetime(2026, 3, 12, 9, tzinfo=UTC),
            delisted_on=date(2026, 3, 12),
        )
    )
    assert result.bars[0].partial is True
    assert result.missing_sessions == ("2026-03-11",)
    assert empty.snapshot_id in result.bars[0].source_snapshot_ids
    assert result.bars[0].available_at == observed


@pytest.mark.pit
@pytest.mark.parametrize("dataset", ["adj_factor", "stock_status"])
def test_chart_empty_auxiliary_evidence_still_requires_effective_mapping(
    tmp_path: Path, dataset: str
) -> None:
    chart, _, _ = _chart(tmp_path, poisoned=False, suspended=True, price_source="fuyao")
    original = chart._snapshots.list_snapshots(dataset_id=dataset)[0]
    empty = replace(
        original,
        row_count=0,
        payload_retained=False,
        payload_uri=None,
        response_metadata=(("snapshot_layer", "verified_empty_provider_observation"),),
    )
    reader = cast(
        ProviderSnapshotReader,
        _Snapshots(
            tuple(
                empty if item.snapshot_id == original.snapshot_id else item
                for item in chart._snapshots.list_snapshots()
            )
        ),
    )
    metadata = cast(
        MetadataQueryFacade,
        _ChartMetadata(
            get_source_ticker=lambda *args, **kwargs: (
                None
                if kwargs["source"] == "tushare" and kwargs["asof"] == "2026-03-11"
                else "600519.SH"
            ),
        ),
    )
    chart = MarketChartQueryFacade(reader, chart._payloads, metadata, chart._market)
    with pytest.raises(AppQueryError, match="ticker mapping is unavailable"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 11),
                period="daily",
                adjustment="qfq" if dataset == "adj_factor" else "none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 12, 8, tzinfo=UTC),
            )
        )


@pytest.mark.pit
def test_chart_daily_scoped_shards_batch_identity_resolution(tmp_path: Path) -> None:
    chart, original, _ = _chart(tmp_path, poisoned=False)
    shards = tuple(
        replace(
            original,
            snapshot_id=f"daily-{day}",
            request_start=day,
            request_end=day,
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=("source_ticker=600519.SH",),
            ),
        )
        for day in ["2026-03-09", "2026-03-10", "2026-03-11"]
    )
    calls = []

    def batch(instrument_id, *, source, asofs, cutoff):
        calls.append((instrument_id, source, asofs, cutoff))
        return dict.fromkeys(asofs, "600519.SH")

    metadata = cast(MetadataQueryFacade, SimpleNamespace(get_source_tickers=batch))
    chart = MarketChartQueryFacade(
        cast(ProviderSnapshotReader, _Snapshots(shards)),
        chart._payloads,
        metadata,
        chart._market,
    )
    assert (
        chart._select_snapshots(
            "stock_daily",
            date(2026, 3, 9),
            date(2026, 3, 11),
            datetime(2026, 3, 12, 8, tzinfo=UTC),
            instrument_id=1000001,
        )
        == shards
    )
    assert len(calls) == 1
    assert calls[0][2] == ["2026-03-09", "2026-03-10", "2026-03-11"]


@pytest.mark.pit
def test_chart_rejects_hybrid_calendar_authority(tmp_path: Path) -> None:
    chart, _, store = _chart(tmp_path, poisoned=False)
    fallback = _snapshot(
        store,
        "calendar",
        pl.DataFrame({"trade_date": ["2026-03-10"], "is_open": [False]}),
        datetime(2026, 3, 11, 8, tzinfo=UTC),
        source="fallback",
    )
    fallback = replace(fallback, request_start="2026-03-10", request_end="2026-03-10")
    chart._snapshots = cast(
        ProviderSnapshotReader,
        _Snapshots((*chart._snapshots.list_snapshots(), fallback)),
    )
    with pytest.raises(AppQueryError, match="calendar has incompatible sources"):
        chart.get_chart(
            MarketChartRequest(
                instrument_id=1000001,
                asset_class="stock",
                start_date=date(2026, 3, 9),
                end_date=date(2026, 3, 11),
                period="daily",
                adjustment="none",
                allow_experimental_data=False,
                now=datetime(2026, 3, 12, 8, tzinfo=UTC),
            )
        )
