"""ProviderBackedDataFeed.get_history() unit tests."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_backtest.data_feed import ProviderBackedDataFeed
from ditto_data.provider import BarQuery
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars_df(
    rows: list[dict[str, Any]],
) -> pl.DataFrame:
    """Build a bars DataFrame from explicit row dicts."""
    return pl.DataFrame(rows)


def _row(
    instrument_id: int,
    trade_date: str,
    close: float = 10.0,
) -> dict[str, Any]:
    """Single bar row with sensible defaults."""
    return {
        "instrument_id": instrument_id,
        "trade_date": trade_date,
        "open": close - 0.1,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "prev_close": close - 0.2,
        "volume": 100_000.0,
        "amount": 1_000_000.0,
    }


class _StubProvider:
    """Stub DataProvider for testing."""

    def __init__(self, bars_df: pl.DataFrame | None = None) -> None:
        self._bars_df = bars_df if bars_df is not None else pl.DataFrame()

    def get_bars(self, query: BarQuery) -> Any:
        return self._bars_df

    def get_instruments(self, query: Any) -> Any:
        return pl.DataFrame()

    def get_schedule(self, start: str, end: str) -> Any:
        return pl.DataFrame({"trade_date": []})

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> Any:
        return pl.DataFrame()


def _make_feed(bars_df: pl.DataFrame) -> ProviderBackedDataFeed:
    """Create a ProviderBackedDataFeed with the given bars data."""
    return ProviderBackedDataFeed(
        provider=_StubProvider(bars_df=bars_df),
        tickers=("000001.SZ", "600000.SH"),
        start_date="2026-01-01",
        end_date="2026-12-31",
        id_map={"000001.SZ": InstrumentId(1), "600000.SH": InstrumentId(2)},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetHistoryBasicWindow:
    """test_basic_window -- normal window, verify most recent N days."""

    def test_returns_last_n_rows(self) -> None:
        """Should return exactly the most recent lookback_days rows."""
        dates = [f"2026-03-{d:02d}" for d in range(1, 11)]  # 01..10
        rows = [
            _row(instrument_id=1, trade_date=d, close=10.0 + i)
            for i, d in enumerate(dates)
        ]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-11",
            lookback_days=3,
        )

        assert len(result) == 3
        expected_dates = ["2026-03-08", "2026-03-09", "2026-03-10"]
        assert result["trade_date"].to_list() == expected_dates

    def test_lookback_exceeds_available(self) -> None:
        """When lookback_days > available data, return all matching rows."""
        dates = ["2026-03-01", "2026-03-02"]
        rows = [_row(instrument_id=1, trade_date=d) for d in dates]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=10,
        )

        assert len(result) == 2


class TestGetHistoryEmptyData:
    """test_empty_data -- empty bars_df returns empty DataFrame."""

    def test_empty_bars_returns_empty(self) -> None:
        """Empty _bars_df should produce an empty result."""
        feed = _make_feed(pl.DataFrame())

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=5,
        )

        assert result.is_empty()


class TestGetHistoryLookbackZero:
    """test_lookback_zero -- lookback_days <= 0 returns empty DataFrame."""

    def test_zero_lookback(self) -> None:
        """lookback_days=0 should return empty DataFrame."""
        rows = [_row(instrument_id=1, trade_date="2026-03-01")]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=0,
        )

        assert result.is_empty()

    def test_negative_lookback(self) -> None:
        """lookback_days=-1 should return empty DataFrame."""
        rows = [_row(instrument_id=1, trade_date="2026-03-01")]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=-1,
        )

        assert result.is_empty()


class TestGetHistoryMultipleInstruments:
    """test_multiple_instruments -- each instrument gets its own window."""

    def test_two_instruments_independent_windows(self) -> None:
        """Each instrument should independently keep its own last N rows."""
        rows = [
            _row(instrument_id=1, trade_date="2026-03-01", close=10.0),
            _row(instrument_id=1, trade_date="2026-03-02", close=11.0),
            _row(instrument_id=1, trade_date="2026-03-03", close=12.0),
            _row(instrument_id=1, trade_date="2026-03-04", close=13.0),
            _row(instrument_id=2, trade_date="2026-03-01", close=20.0),
            _row(instrument_id=2, trade_date="2026-03-02", close=21.0),
        ]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1), InstrumentId(2)],
            as_of_date="2026-03-05",
            lookback_days=2,
        )

        iid1 = result.filter(pl.col("instrument_id") == 1)
        iid2 = result.filter(pl.col("instrument_id") == 2)

        assert len(iid1) == 2
        assert iid1["trade_date"].to_list() == ["2026-03-03", "2026-03-04"]

        assert len(iid2) == 2
        assert iid2["trade_date"].to_list() == ["2026-03-01", "2026-03-02"]

    def test_single_instrument_requested(self) -> None:
        """Requesting only one instrument should not return data for others."""
        rows = [
            _row(instrument_id=1, trade_date="2026-03-01", close=10.0),
            _row(instrument_id=2, trade_date="2026-03-01", close=20.0),
        ]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=5,
        )

        assert result["instrument_id"].unique().to_list() == [1]


class TestGetHistoryAsOfBoundary:
    """test_as_of_boundary -- as_of_date data is excluded (strict less-than)."""

    def test_as_of_date_excluded(self) -> None:
        """Rows where trade_date == as_of_date should not appear."""
        rows = [
            _row(instrument_id=1, trade_date="2026-03-03", close=10.0),
            _row(instrument_id=1, trade_date="2026-03-04", close=11.0),
            _row(instrument_id=1, trade_date="2026-03-05", close=12.0),
        ]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=5,
        )

        assert "2026-03-05" not in result["trade_date"].to_list()
        assert len(result) == 2
        assert result["trade_date"].to_list() == ["2026-03-03", "2026-03-04"]

    def test_exact_as_of_date_not_in_result(self) -> None:
        """Even with lookback_days=1, as_of_date itself is never included."""
        rows = [
            _row(instrument_id=1, trade_date="2026-03-04", close=11.0),
            _row(instrument_id=1, trade_date="2026-03-05", close=12.0),
        ]
        feed = _make_feed(_make_bars_df(rows))

        result = feed.get_history(
            instrument_ids=[InstrumentId(1)],
            as_of_date="2026-03-05",
            lookback_days=1,
        )

        assert len(result) == 1
        assert result["trade_date"][0] == "2026-03-04"
