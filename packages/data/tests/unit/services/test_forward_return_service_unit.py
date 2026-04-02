"""Unit tests for ForwardReturnService."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_data.services.forward_return_service import (
    ForwardReturnService,
    _extend_end_date,
)


def _make_bars(
    instrument_ids: list[int],
    trade_dates: list[str],
    close_prices: list[float],
) -> pl.DataFrame:
    """Helper: build a minimal bars DataFrame."""
    n = len(instrument_ids)
    assert len(trade_dates) == n
    assert len(close_prices) == n
    return pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "trade_date": trade_dates,
            "close": close_prices,
        },
    )


class TestForwardReturnService:
    """Tests for ForwardReturnService.compute()."""

    def test_stock_forward_return(self) -> None:
        """Stock forward returns use get_stock_bars and compute correctly."""
        market = MagicMock()
        bars = _make_bars(
            instrument_ids=[1, 1, 1, 1, 1],
            trade_dates=[
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
            ],
            close_prices=[10.0, 11.0, 12.0, 13.0, 14.0],
        )
        market.get_stock_bars.return_value = bars

        svc = ForwardReturnService(market)
        result = svc.compute("stock", "2024-01-02", "2024-01-08", holding_period=1)

        market.get_stock_bars.assert_called_once()
        # The extended end should be beyond 2024-01-08
        call_start, _call_end = market.get_stock_bars.call_args.args
        assert call_start == "2024-01-02"

        assert result.columns == ["instrument_id", "trade_date", "forward_return"]
        # With holding_period=1 and 5 dates, first 4 should have forward returns
        assert result.height == 4
        vals = result.sort("trade_date")["forward_return"].to_list()
        # (11/10 - 1), (12/11 - 1), (13/12 - 1), (14/13 - 1)
        expected = [
            (11.0 / 10.0 - 1),
            (12.0 / 11.0 - 1),
            (13.0 / 12.0 - 1),
            (14.0 / 13.0 - 1),
        ]
        for v, e in zip(vals, expected, strict=True):
            assert abs(v - e) < 1e-10

    def test_etf_forward_return(self) -> None:
        """ETF forward returns use get_etf_bars with adj parameter."""
        market = MagicMock()
        bars = _make_bars(
            instrument_ids=[100, 100, 100, 100, 100],
            trade_dates=[
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
            ],
            close_prices=[100.0, 102.0, 104.0, 106.0, 108.0],
        )
        market.get_etf_bars.return_value = bars

        svc = ForwardReturnService(market)
        result = svc.compute(
            "etf",
            "2024-01-02",
            "2024-01-08",
            holding_period=1,
            adj="hfq",
        )

        market.get_etf_bars.assert_called_once()
        call_args = market.get_etf_bars.call_args
        assert call_args.kwargs.get("adj") == "hfq" or call_args[0][2] == "hfq"

        assert result.height == 4

    def test_holding_period_greater_than_one(self) -> None:
        """Holding period of 2 drops the last 2 dates per instrument."""
        market = MagicMock()
        bars = _make_bars(
            instrument_ids=[1, 1, 1, 1, 1, 1],
            trade_dates=[
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
                "2024-01-09",
            ],
            close_prices=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
        )
        market.get_stock_bars.return_value = bars

        svc = ForwardReturnService(market)
        result = svc.compute("stock", "2024-01-02", "2024-01-09", holding_period=2)

        assert result.height == 4  # 6 - 2
        vals = result.sort("trade_date")["forward_return"].to_list()
        # close[t+2]/close[t] - 1
        expected = [
            (12.0 / 10.0 - 1),
            (13.0 / 11.0 - 1),
            (14.0 / 12.0 - 1),
            (15.0 / 13.0 - 1),
        ]
        for v, e in zip(vals, expected, strict=True):
            assert abs(v - e) < 1e-10

    def test_multiple_instruments(self) -> None:
        """Each instrument's trailing dates are independently dropped."""
        market = MagicMock()
        bars = _make_bars(
            instrument_ids=[1, 1, 1, 2, 2, 2],
            trade_dates=[
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
            ],
            close_prices=[10.0, 11.0, 12.0, 100.0, 101.0, 102.0],
        )
        market.get_stock_bars.return_value = bars

        svc = ForwardReturnService(market)
        result = svc.compute("stock", "2024-01-02", "2024-01-04", holding_period=1)

        # Each instrument has 3 rows; last 1 is dropped -> 2 per instrument
        assert result.height == 4
        instrument_counts = result.group_by("instrument_id").len()
        for row in instrument_counts.iter_rows(named=True):
            assert row["len"] == 2

    def test_empty_bars_returns_empty(self) -> None:
        """Empty market data returns empty DataFrame with correct schema."""
        market = MagicMock()
        market.get_stock_bars.return_value = pl.DataFrame()

        svc = ForwardReturnService(market)
        result = svc.compute("stock", "2024-01-02", "2024-01-10")

        assert result.is_empty()
        assert "forward_return" in result.columns

    def test_adj_parameter_passed_through(self) -> None:
        """The adj parameter is forwarded to get_etf_bars."""
        market = MagicMock()
        market.get_etf_bars.return_value = pl.DataFrame()

        svc = ForwardReturnService(market)
        svc.compute("etf", "2024-01-02", "2024-01-10", adj="qfq")

        market.get_etf_bars.assert_called_once()
        # adj should appear in the call
        call_kwargs = market.get_etf_bars.call_args.kwargs
        if "adj" in call_kwargs:
            assert call_kwargs["adj"] == "qfq"
        else:
            # Positional: start, extended_end, adj
            assert market.get_etf_bars.call_args.args[2] == "qfq"

    def test_date_range_trimming(self) -> None:
        """Result is trimmed to the original [start, end] range."""
        market = MagicMock()
        # Provide bars beyond the requested end date
        bars = _make_bars(
            instrument_ids=[1, 1, 1, 1, 1, 1, 1],
            trade_dates=[
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
                "2024-01-08",
                "2024-01-09",
                "2024-01-10",
            ],
            close_prices=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
        )
        market.get_stock_bars.return_value = bars

        svc = ForwardReturnService(market)
        result = svc.compute(
            "stock",
            "2024-01-02",
            "2024-01-08",
            holding_period=1,
        )

        dates = result["trade_date"].to_list()
        for d in dates:
            assert "2024-01-02" <= d <= "2024-01-08"


class TestExtendEndDate:
    """Tests for _extend_end_date helper."""

    def test_extends_by_calendar_buffer(self) -> None:
        """End date is extended beyond the holding period."""
        result = _extend_end_date("2024-01-15", 5)
        assert result > "2024-01-15"

    def test_handles_invalid_date(self) -> None:
        """Invalid date string is returned as-is."""
        result = _extend_end_date("not-a-date", 5)
        assert result == "not-a-date"
