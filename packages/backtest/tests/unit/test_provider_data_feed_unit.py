"""ProviderBackedDataFeed unit tests — DataFeed via DataProvider Protocol."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import polars as pl
import pytest
from ditto_backtest.data_feed import ProviderBackedDataFeed, SnapshotProviders
from ditto_data.provider import BarQuery
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars_df(
    instrument_id: int = 1,
    dates: list[str] | None = None,
    *,
    suspended_dates: set[str] | None = None,
    with_optional: bool = False,
) -> pl.DataFrame:
    """Build a minimal bars DataFrame matching MarketService output schema."""
    dates = dates or ["2026-03-01", "2026-03-02", "2026-03-03"]
    suspended_dates = suspended_dates or set()
    n = len(dates)

    data: dict[str, list[Any]] = {
        "instrument_id": [instrument_id] * n,
        "trade_date": [d.encode().decode() for d in dates],
        "open": [10.0 + i for i in range(n)],
        "high": [10.5 + i for i in range(n)],
        "low": [9.8 + i for i in range(n)],
        "close": [10.2 + i for i in range(n)],
        "prev_close": [9.9 + i for i in range(n)],
        "volume": [100_000.0 + i * 10_000 for i in range(n)],
        "amount": [1_020_000.0 + i * 102_000 for i in range(n)],
        "is_suspended": [d in suspended_dates for d in dates],
    }
    if with_optional:
        data["limit_up"] = [11.2 + i for i in range(n)]
        data["limit_down"] = [9.0 + i for i in range(n)]
        data["avg_volume_20d"] = [90_000.0 + i * 1000 for i in range(n)]

    return pl.DataFrame(data)


def _make_schedule_df(dates: list[str]) -> pl.DataFrame:
    """Build a schedule DataFrame matching get_schedule output."""
    return pl.DataFrame({"trade_date": dates})


class _StubProvider:
    """Stub DataProvider for testing."""

    def __init__(
        self,
        bars_df: pl.DataFrame | None = None,
        schedule_df: pl.DataFrame | None = None,
    ) -> None:
        self._bars_df = bars_df if bars_df is not None else pl.DataFrame()
        self._schedule_df = (
            schedule_df if schedule_df is not None else _make_schedule_df([])
        )

    def get_bars(self, query: BarQuery) -> Any:
        return self._bars_df

    def get_instruments(self, query: Any) -> Any:
        return pl.DataFrame()

    def get_schedule(self, start: str, end: str) -> Any:
        return self._schedule_df

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> Any:
        return pl.DataFrame()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProviderBackedDataFeedTradingDays:
    """trading_days() from DataProvider.get_schedule()."""

    def test_trading_days_from_schedule(self) -> None:
        """trading_days 应从 get_schedule 获取."""
        schedule = _make_schedule_df(["2026-03-02", "2026-03-03", "2026-03-04"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-02",
            end_date="2026-03-04",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        assert feed.trading_days() == ["2026-03-02", "2026-03-03", "2026-03-04"]

    def test_trading_days_empty(self) -> None:
        """无交易日应返回空列表."""
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        assert feed.trading_days() == []

    def test_trading_days_cached(self) -> None:
        """重复调用应返回同一对象（缓存）."""
        schedule = _make_schedule_df(["2026-03-02"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-02",
            end_date="2026-03-02",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        result1 = feed.trading_days()
        result2 = feed.trading_days()
        assert result1 is result2


class TestProviderBackedDataFeedGetSlice:
    """get_slice() from pre-loaded bar data."""

    def test_get_slice_single_instrument(self) -> None:
        """单标的单日切片."""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        result = feed.get_slice("2026-03-01")

        assert result.trade_date == "2026-03-01"
        assert result.step_time.hour == 15
        assert InstrumentId(1) in result.bars

        bar = result.bars[InstrumentId(1)]
        assert bar.open == 10.0
        assert bar.close == 10.2
        assert bar.is_suspended is False

    def test_get_slice_accepts_date_typed_trade_date(self) -> None:
        """Parquet 读出的 Date 型 trade_date 应可用字符串日期切片。"""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"]).with_columns(
            pl.col("trade_date").str.to_date()
        )
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1)},
        )

        result = feed.get_slice("2026-03-01")

        assert InstrumentId(1) in result.bars
        assert result.bars[InstrumentId(1)].close == 10.2

    def test_get_slice_multi_instrument(self) -> None:
        """多标的切片."""
        bars1 = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        bars2 = _make_bars_df(instrument_id=2, dates=["2026-03-01"])
        bars = pl.concat([bars1, bars2])
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ", "600000.SH"),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1), "600000.SH": InstrumentId(2)},
        )
        result = feed.get_slice("2026-03-01")

        assert len(result.bars) == 2
        assert InstrumentId(1) in result.bars
        assert InstrumentId(2) in result.bars

    def test_get_slice_missing_date(self) -> None:
        """不存在的日期应返回空 bars."""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        schedule = _make_schedule_df(["2026-03-01", "2026-03-05"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-05",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        result = feed.get_slice("2026-03-05")

        assert result.trade_date == "2026-03-05"
        assert result.bars == {}

    def test_get_slice_suspended_included(self) -> None:
        """停牌标的仍应包含在 bars 中."""
        bars = _make_bars_df(
            instrument_id=1,
            dates=["2026-03-01", "2026-03-02"],
            suspended_dates={"2026-03-02"},
        )
        schedule = _make_schedule_df(["2026-03-01", "2026-03-02"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-02",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        result = feed.get_slice("2026-03-02")
        bar = result.bars[InstrumentId(1)]
        assert bar.is_suspended is True

    def test_get_slice_optional_columns(self) -> None:
        """可选列应正确传递到 MarketSnapshot."""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"], with_optional=True)
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        result = feed.get_slice("2026-03-01")
        bar = result.bars[InstrumentId(1)]
        assert bar.limit_up == 11.2
        assert bar.limit_down == 9.0
        assert bar.avg_volume_20d == 90_000.0

    def test_get_slice_benchmark_close(self) -> None:
        """benchmark_close 应从 benchmark 标的获取."""
        bars_iid1 = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        bars_iid2 = _make_bars_df(instrument_id=2, dates=["2026-03-01"])
        bars = pl.concat([bars_iid1, bars_iid2])
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ", "000300.SH"),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1), "000300.SH": InstrumentId(2)},
            benchmark_id=InstrumentId(2),
        )
        result = feed.get_slice("2026-03-01")
        # iid=2 close = 10.2 (first date)
        assert result.benchmark_close == 10.2

    def test_satisfies_data_feed_protocol(self) -> None:
        """ProviderBackedDataFeed 应满足 DataFeed Protocol."""
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        assert hasattr(feed, "trading_days")
        assert hasattr(feed, "get_slice")
        assert callable(feed.trading_days)
        assert callable(feed.get_slice)


class TestProviderBackedDataFeedSourceSnapshots:
    """ProviderBackedDataFeed exposes upstream source snapshot provenance."""

    def test_source_snapshot_ids_from_bars_column(self) -> None:
        """source_snapshot_id 列应进入 feed 与 Slice provenance."""
        snapshot_id = "snapshot:tushare:stock_daily:2026-03-01:abc"
        bars = _make_bars_df(
            instrument_id=1,
            dates=["2026-03-01", "2026-03-02"],
        ).with_columns(pl.lit(snapshot_id).alias("source_snapshot_id"))
        schedule = _make_schedule_df(["2026-03-01", "2026-03-02"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-02",
            id_map={"000001.SZ": InstrumentId(1)},
        )

        assert feed.source_snapshot_ids() == {InstrumentId(1): snapshot_id}
        assert feed.get_slice("2026-03-01").source_snapshot_ids == {
            InstrumentId(1): snapshot_id,
        }

    def test_source_snapshot_ids_empty_without_column(self) -> None:
        """当前 provider 未暴露 snapshot 时不伪造来源 ID."""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        schedule = _make_schedule_df(["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1)},
        )

        assert feed.source_snapshot_ids() == {}
        assert feed.get_slice("2026-03-01").source_snapshot_ids == {}

    def test_required_source_snapshot_lineage_fails_closed(self) -> None:
        """Research/context-bound runs cannot silently erase bar provenance."""
        bars = _make_bars_df(instrument_id=1, dates=["2026-03-01"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={"000001.SZ": InstrumentId(1)},
            snapshot_providers=SnapshotProviders(require_source_snapshot_lineage=True),
        )

        with pytest.raises(ValueError, match="source snapshot lineage is incomplete"):
            feed.source_snapshot_ids()

    def test_required_source_snapshot_lineage_accepts_every_instrument(self) -> None:
        """One exact upstream snapshot per requested instrument closes the boundary."""
        bars = pl.concat(
            (
                _make_bars_df(instrument_id=1, dates=["2026-03-01"]),
                _make_bars_df(instrument_id=2, dates=["2026-03-01"]),
            )
        ).with_columns(
            pl.lit("snapshot:tushare:bars:exact").alias("source_snapshot_id")
        )
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars),
            tickers=("000001.SZ", "600000.SH"),
            start_date="2026-03-01",
            end_date="2026-03-01",
            id_map={
                "000001.SZ": InstrumentId(1),
                "600000.SH": InstrumentId(2),
            },
            snapshot_providers=SnapshotProviders(require_source_snapshot_lineage=True),
        )

        assert feed.source_snapshot_ids() == {
            InstrumentId(1): "snapshot:tushare:bars:exact",
            InstrumentId(2): "snapshot:tushare:bars:exact",
        }

    def test_multiple_snapshot_ids_are_aggregated_stably(self) -> None:
        """同一标的跨多源快照时使用稳定 snapshot-set 聚合 ID."""
        bars = _make_bars_df(
            instrument_id=1,
            dates=["2026-03-01", "2026-03-02"],
        ).with_columns(
            pl.Series(
                "source_snapshot_id",
                (
                    "snapshot:tushare:stock_daily:2026-03-01:abc",
                    "snapshot:tushare:stock_daily:2026-03-02:def",
                ),
            ),
        )
        schedule = _make_schedule_df(["2026-03-01", "2026-03-02"])
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(bars_df=bars, schedule_df=schedule),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-02",
            id_map={"000001.SZ": InstrumentId(1)},
        )

        snapshot_id = feed.source_snapshot_ids()[InstrumentId(1)]
        assert snapshot_id.startswith("snapshot-set:sha256:")


class TestProviderBackedDataFeedFundamentalSnapshot:
    """get_fundamental_snapshot — 委托注入的 fundamental_snapshot_fn（纯数据通道）."""

    def test_no_fn_returns_empty_with_schema(self) -> None:
        """未注入 fn 时返回空 DataFrame（含正确 schema），不抛错."""
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        df = feed.get_fundamental_snapshot([InstrumentId(1)], date(2024, 1, 2))
        assert df.is_empty()
        assert set(df.columns) == {"instrument_id", "roe", "net_margin", "eps"}

    def test_delegates_to_injected_fn_with_correct_args(self) -> None:
        """注入 fn 时委托调用，instrument_ids 与 as_of_date 正确透传."""
        captured: dict[str, object] = {}

        def fn(
            instrument_ids: Sequence[InstrumentId],
            as_of_date: date,
        ) -> pl.DataFrame:
            captured["instrument_ids"] = list(instrument_ids)
            captured["as_of"] = as_of_date
            return pl.DataFrame({"instrument_id": [1], "roe": [0.1]})

        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
            snapshot_providers=SnapshotProviders(fundamental=fn),
        )
        df = feed.get_fundamental_snapshot([InstrumentId(1)], date(2024, 6, 1))

        assert df.height == 1
        assert df["roe"][0] == 0.1
        assert captured["as_of"] == date(2024, 6, 1)
        assert captured["instrument_ids"] == [InstrumentId(1)]

    def test_empty_instrument_ids_delegates_to_fn(self) -> None:
        """空标的列表也委托给 fn（由 fn 决定返回空 schema）."""
        called = {"count": 0}

        def fn(
            instrument_ids: Sequence[InstrumentId],
            as_of_date: date,
        ) -> pl.DataFrame:
            called["count"] += 1
            return pl.DataFrame(schema={"instrument_id": pl.Int64, "roe": pl.Float64})

        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
            snapshot_providers=SnapshotProviders(fundamental=fn),
        )
        df = feed.get_fundamental_snapshot([], date(2024, 6, 1))

        assert df.is_empty()
        assert called["count"] == 1


class TestProviderBackedDataFeedClassificationSnapshot:
    """get_classification_snapshot — 委托注入的 classification_snapshot_fn."""

    def test_no_fn_returns_empty_with_schema(self) -> None:
        """未注入 fn 时返回空 DataFrame（含 sector_id schema），不抛错."""
        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
        )
        df = feed.get_classification_snapshot([InstrumentId(1)], date(2024, 1, 2))
        assert df.is_empty()
        assert set(df.columns) == {"instrument_id", "sector_id"}

    def test_delegates_to_injected_fn_with_correct_args(self) -> None:
        """注入 fn 时委托调用，instrument_ids 与 as_of_date 正确透传."""
        captured: dict[str, object] = {}

        def fn(
            instrument_ids: Sequence[InstrumentId],
            as_of_date: date,
        ) -> pl.DataFrame:
            captured["instrument_ids"] = list(instrument_ids)
            captured["as_of"] = as_of_date
            return pl.DataFrame({"instrument_id": [1], "sector_id": ["801010"]})

        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
            snapshot_providers=SnapshotProviders(classification=fn),
        )
        df = feed.get_classification_snapshot([InstrumentId(1)], date(2024, 6, 1))

        assert df.height == 1
        assert df["sector_id"][0] == "801010"
        assert captured["as_of"] == date(2024, 6, 1)
        assert captured["instrument_ids"] == [InstrumentId(1)]

    def test_empty_instrument_ids_delegates_to_fn(self) -> None:
        """空标的列表也委托给 fn（由 fn 决定返回空 schema）."""
        called = {"count": 0}

        def fn(
            instrument_ids: Sequence[InstrumentId],
            as_of_date: date,
        ) -> pl.DataFrame:
            called["count"] += 1
            return pl.DataFrame(
                schema={"instrument_id": pl.Int64, "sector_id": pl.Utf8},
            )

        feed = ProviderBackedDataFeed(
            provider=_StubProvider(),
            tickers=("000001.SZ",),
            start_date="2026-03-01",
            end_date="2026-03-31",
            id_map={"000001.SZ": InstrumentId(1)},
            snapshot_providers=SnapshotProviders(classification=fn),
        )
        df = feed.get_classification_snapshot([], date(2024, 6, 1))

        assert df.is_empty()
        assert called["count"] == 1
