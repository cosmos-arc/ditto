"""ParquetDataFeed unit tests — 5 scenarios with tmp_path parquet files."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_core.backtest.data_feed import ParquetDataFeed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_basic_parquet(
    path: Path,
    instrument_id: str,
    dates: list[str],
    *,
    suspended_indices: set[int] | None = None,
) -> None:
    """Write a minimal parquet file for the given instrument."""
    n = len(dates)
    suspended_indices = suspended_indices or set()
    pl.DataFrame(
        {
            "trade_date": dates,
            "open": [10.0 + i for i in range(n)],
            "high": [10.5 + i for i in range(n)],
            "low": [9.8 + i for i in range(n)],
            "close": [10.2 + i for i in range(n)],
            "prev_close": [9.9 + i for i in range(n)],
            "volume": [100_000.0 + i * 10_000 for i in range(n)],
            "amount": [1_020_000.0 + i * 102_000 for i in range(n)],
            "is_suspended": [i in suspended_indices for i in range(n)],
        },
    ).write_parquet(path / f"{instrument_id}.parquet")


def _make_feed(
    tmp_path: Path,
    instrument_ids: list[str],
    start_date: str = "2026-03-01",
    end_date: str = "2026-03-31",
) -> ParquetDataFeed:
    return ParquetDataFeed(
        data_dir=tmp_path,
        instrument_ids=instrument_ids,
        start_date=start_date,
        end_date=end_date,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTradingDaysReturnsSortedDates:
    """Scenario 1: Two parquet files with overlapping dates."""

    def test_trading_days_returns_sorted_dates(self, tmp_path: Path) -> None:
        """trading_days returns sorted unique dates filtered to [start, end]."""
        _write_basic_parquet(
            tmp_path,
            "ETF-001",
            ["2026-03-01", "2026-03-03", "2026-03-05"],
        )
        _write_basic_parquet(
            tmp_path,
            "ETF-002",
            ["2026-03-02", "2026-03-03", "2026-03-04"],
        )
        feed = _make_feed(
            tmp_path,
            ["ETF-001", "ETF-002"],
            start_date="2026-03-02",
            end_date="2026-03-04",
        )
        days = feed.trading_days()
        assert days == ["2026-03-02", "2026-03-03", "2026-03-04"]


class TestGetSliceReturnsCorrectBars:
    """Scenario 2: Single parquet file, verify snapshot values."""

    def test_get_slice_returns_correct_bars(self, tmp_path: Path) -> None:
        """get_slice returns Slice with correct MarketSnapshot values."""
        _write_basic_parquet(
            tmp_path,
            "ETF-001",
            ["2026-03-01"],
        )
        feed = _make_feed(tmp_path, ["ETF-001"])
        result = feed.get_slice("2026-03-01")

        assert result.trade_date == "2026-03-01"
        assert result.step_time.hour == 15
        assert result.step_time.minute == 0
        assert "ETF-001" in result.bars

        bar = result.bars["ETF-001"]
        assert bar.open == 10.0
        assert bar.high == 10.5
        assert bar.low == 9.8
        assert bar.close == 10.2
        assert bar.prev_close == 9.9
        assert bar.volume == 100_000.0
        assert bar.amount == 1_020_000.0
        assert bar.is_suspended is False
        # Optional columns should be None when not present
        assert bar.limit_up is None
        assert bar.limit_down is None
        assert bar.avg_volume_20d is None


class TestGetSliceMissingDate:
    """Scenario 3: Request a date that doesn't exist in data."""

    def test_get_slice_missing_date(self, tmp_path: Path) -> None:
        """get_slice for a non-existent date returns Slice with empty bars."""
        _write_basic_parquet(
            tmp_path,
            "ETF-001",
            ["2026-03-01"],
        )
        feed = _make_feed(tmp_path, ["ETF-001"])
        result = feed.get_slice("2026-03-10")

        assert result.trade_date == "2026-03-10"
        assert result.bars == {}


class TestGetSliceFiltersByDate:
    """Scenario 4: Three dates, verify slice for one date."""

    def test_get_slice_filters_by_date(self, tmp_path: Path) -> None:
        """get_slice for a specific date only includes that date's data."""
        dates = ["2026-03-01", "2026-03-02", "2026-03-03"]
        _write_basic_parquet(tmp_path, "ETF-001", dates)
        feed = _make_feed(tmp_path, ["ETF-001"])
        result = feed.get_slice("2026-03-02")

        assert result.trade_date == "2026-03-02"
        assert len(result.bars) == 1
        bar = result.bars["ETF-001"]
        # Date index 1: open = 10.0 + 1 = 11.0
        assert bar.open == 11.0
        assert bar.close == 11.2


class TestInstrumentWithNoDataForDate:
    """Scenario 5: Two files with different dates."""

    def test_instrument_with_no_data_for_date(self, tmp_path: Path) -> None:
        """get_slice for a date only present in one file includes that instrument."""
        _write_basic_parquet(
            tmp_path,
            "ETF-001",
            ["2026-03-01", "2026-03-02"],
        )
        _write_basic_parquet(
            tmp_path,
            "ETF-002",
            ["2026-03-03", "2026-03-04"],
        )
        feed = _make_feed(tmp_path, ["ETF-001", "ETF-002"])
        result = feed.get_slice("2026-03-01")

        assert "ETF-001" in result.bars
        assert "ETF-002" not in result.bars
        assert len(result.bars) == 1

        # Verify the reverse: ETF-002 has data on 2026-03-03
        result2 = feed.get_slice("2026-03-03")
        assert "ETF-001" not in result2.bars
        assert "ETF-002" in result2.bars
        assert result2.bars["ETF-002"].close == 10.2


class TestSuspendedInstrumentIncluded:
    """Scenario 6: Suspended instrument is still included in bars."""

    def test_suspended_instrument_included(self, tmp_path: Path) -> None:
        """is_suspended=True instrument is still included in Slice.bars."""
        _write_basic_parquet(
            tmp_path,
            "ETF-001",
            ["2026-03-01", "2026-03-02"],
            suspended_indices={1},
        )
        feed = _make_feed(tmp_path, ["ETF-001"])
        result = feed.get_slice("2026-03-02")

        assert "ETF-001" in result.bars
        assert result.bars["ETF-001"].is_suspended is True


class TestOptionalColumnsPreserved:
    """Scenario 7: Optional columns (limit_up, limit_down, avg_volume_20d)."""

    def test_optional_columns_preserved(self, tmp_path: Path) -> None:
        """Optional columns are included in MarketSnapshot when present."""
        pl.DataFrame(
            {
                "trade_date": ["2026-03-01"],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "prev_close": [9.9],
                "volume": [100_000.0],
                "amount": [1_020_000.0],
                "is_suspended": [False],
                "limit_up": [11.2],
                "limit_down": [9.0],
                "avg_volume_20d": [90_000.0],
            },
        ).write_parquet(tmp_path / "ETF-001.parquet")
        feed = _make_feed(tmp_path, ["ETF-001"])
        result = feed.get_slice("2026-03-01")

        bar = result.bars["ETF-001"]
        assert bar.limit_up == 11.2
        assert bar.limit_down == 9.0
        assert bar.avg_volume_20d == 90_000.0


class TestMissingParquetFile:
    """Scenario 8: Instrument file does not exist — gracefully skipped."""

    def test_missing_parquet_file(self, tmp_path: Path) -> None:
        """Non-existent parquet file is silently skipped."""
        feed = _make_feed(tmp_path, ["ETF-NONEXIST"])
        days = feed.trading_days()
        assert days == []

        result = feed.get_slice("2026-03-01")
        assert result.bars == {}
