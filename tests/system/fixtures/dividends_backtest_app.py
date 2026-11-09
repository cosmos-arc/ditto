"""Synthetic cash distributions exercise the ordinary retained-input pipeline."""

from datetime import date, timedelta

import polars as pl

from tests.system.fixtures.fees_backtest_app import app
from tests.system.fixtures.historical_backtest_app import retain_history_payload

_PERIOD = ("2014-01-01", "2014-02-28")
_RECORD = date(2014, 1, 21)
_EX = date(2014, 1, 22)
_PAY = date(2014, 1, 27)


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    retain_history_payload(dataset, frame, period=_PERIOD)


def _seed_prices() -> None:
    days = pl.date_range(date(2014, 1, 1), date(2014, 2, 28), eager=True)
    frame = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": 10.0 if day < _EX else 9.0,
                "high": 10.0 if day < _EX else 9.0,
                "low": 10.0 if day < _EX else 9.0,
                "close": 10.0 if day < _EX else 9.0,
                "pre_close": 10.0 if day < _EX else 9.0,
                "volume": 10000000.0,
                "amount": 1000000.0,
            }
            for ticker in ("600000.SH", "000001.SZ")
            for day in days
            if day.weekday() < 5 and day not in (date(2014, 1, 1), date(2014, 1, 31))
        ]
    )
    _retain("stock_daily", frame)
    _retain(
        "adj_factor",
        frame.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.when(pl.col("trade_date") < _EX)
            .then(1.0)
            .otherwise(10 / 9)
            .alias("adj_factor")
        ),
    )
    _retain(
        "stock_limit",
        frame.select("source_ticker", "trade_date").with_columns(
            pl.when(pl.col("trade_date") < _EX)
            .then(11.0)
            .otherwise(9.9)
            .alias("up_limit"),
            pl.when(pl.col("trade_date") < _EX)
            .then(9.0)
            .otherwise(8.1)
            .alias("down_limit"),
        ),
    )


def _dividends(*, complete: bool) -> None:
    frame = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "knowledge_date": date(2014, 1, 10),
                "implementation_date": date(2014, 1, 17),
                "div_proc": "实施",
                "record_date": _RECORD,
                "ex_dividend_date": _EX,
                "pay_date": _PAY if complete else None,
                "gross_dividend_per_share": 1.0,
                "stock_dividend_ratio": 0.0,
            }
            for ticker in ("600000.SH", "000001.SZ")
        ]
    ).with_columns(pl.col("pay_date").cast(pl.Date))
    # Duplicate provider rows must not create duplicate economic rights.
    _retain("dividend", pl.concat([frame, frame]))


_seed_prices()
_dividends(complete=False)


@app.post("/system-fixture/dividends/repair")
def repair_dividends() -> dict[str, bool]:
    """Install complete synthetic facts; the UI still submits the accepted run."""
    _dividends(complete=True)
    return {"repaired": True}
