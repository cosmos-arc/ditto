"""Delisted holdings, exit facts and missing evidence over the real engine.

The 2017-07 window mirrors the retained production facts of 000033.SZ (新都退:
delisted 2017-07-07, last close 1.70 on 07-06, no daily status rows for its
final consolidation sessions); the 2016-05 window mirrors 600656.SH (delisted
2016-05-13) with the exit fact withheld until the repair endpoint records it
in the instrument master the way a stock_basic refresh would. June/May ramps
and the 600656 quotes through 05-12 are synthetic warmup data.
"""

import os
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from ditto_application.commands.strategy import (
    CreateStrategyCommand,
    CreateStrategyHandler,
    PublishStrategyCommand,
    PublishStrategyHandler,
)
from ditto_apps.registry.container import make_app_container
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from tests.system.fixtures.historical_backtest_app import (
    app,
    retain_empty_dividends,
    retain_history_payload,
)

_PERIOD_A = ("2017-06-01", "2017-07-10")
_PERIOD_B = ("2016-04-01", "2016-05-16")
_DATA_A = ("2017-06-01", "2017-07-10")
_DATA_B = ("2016-04-01", "2016-05-12")
_EXIT_FACT_A = "2017-07-07"
_EXIT_FACT_B = "2016-05-13"
_STATUS_GAP = (date(2017, 7, 5), date(2017, 7, 6))
_STOCKS_A = (
    (1005603, "000033.SZ", "1994-01-03", _EXIT_FACT_A),
    (1007561, "000001.SZ", "1991-04-03", None),
)
_STOCK_B = (1005762, "600656.SH", "1990-12-19", None)


def _retain(dataset: str, frame: pl.DataFrame, period: tuple[str, str]) -> None:
    retain_history_payload(dataset, frame, period=period)


def _trading_days(start: date, end: date) -> list[date]:
    return [
        day
        for day in (start + timedelta(days=i) for i in range((end - start).days + 1))
        if day.weekday() < 5
    ]


def _stock_prices(ticker: str, days: list[date]) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    closes: dict[date, float] = {}
    for day in days:
        if ticker == "000033.SZ":
            price = {
                date(2017, 7, 3): 1.48,
                date(2017, 7, 4): 1.48,
                date(2017, 7, 5): 1.63,
                date(2017, 7, 6): 1.70,
            }.get(day, 1.40)
            volume = {
                date(2017, 7, 3): 1594.17,
                date(2017, 7, 4): 1942.62,
                date(2017, 7, 5): 2876.94,
                date(2017, 7, 6): 3880.43,
            }.get(day, 2000.0)
        elif ticker == "600656.SH":
            price, volume = 4.40, 3000.0
        else:
            price, volume = 10.0, 1_000_000.0
        rows.append(
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "pre_close": closes.get(day - timedelta(days=1), price),
                "volume": volume,
                "amount": price * volume,
            }
        )
        closes[day] = price
    return pl.DataFrame(rows)


def _limits(bars: pl.DataFrame) -> pl.DataFrame:
    frame = bars.with_columns(
        (pl.col("pre_close") * 1.1).round(2).alias("up_limit"),
        (pl.col("pre_close") * 0.9).round(2).alias("down_limit"),
        (pl.col("trade_date") + timedelta(days=1)).alias("knowledge_date"),
    )
    # The production rows round the band onto the 0.01 tick exactly this way
    # (e.g. 000033 2017-07-05: 1.48 -> 1.63/1.33).
    return frame.select(
        "source_ticker", "trade_date", "knowledge_date", "up_limit", "down_limit"
    )


def _status(bars: pl.DataFrame, *, complete: bool) -> pl.DataFrame:
    keep = (
        (pl.col("source_ticker") != "000033.SZ")
        | pl.lit(complete)
        | ~pl.col("trade_date").is_in(_STATUS_GAP)
    )
    return (
        bars.select("source_ticker", "trade_date")
        .with_columns(
            pl.lit(False).alias("is_suspended"),
            pl.lit("").alias("suspend_timing"),
            pl.lit(False).alias("is_st"),
            pl.lit(None, dtype=pl.String).alias("st_type"),
            pl.lit("L").alias("list_status"),
        )
        .filter(keep)
    )


def _fundamentals(
    tickers: tuple[str, ...], days: list[date], report_date: date
) -> tuple[pl.DataFrame, pl.DataFrame]:
    rows = [
        {
            "source_ticker": ticker,
            "report_date": report_date,
            "knowledge_date": day,
            "net_profit": 40.0 if ticker == "000033.SZ" else 10.0,
            "revenue": 100.0,
            "eps": 1.0,
        }
        for ticker in tickers
        for day in days
    ]
    income = pl.DataFrame(rows)
    balance = income.select(
        "source_ticker", "report_date", "knowledge_date"
    ).with_columns(pl.lit(100.0).alias("net_assets"))
    return income, balance


def _seed() -> None:
    retain_empty_dividends(_PERIOD_A)
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed, delisted in (*_STOCKS_A, _STOCK_B):
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="退市固定样例",
                    exchange="SSE" if ticker.endswith(".SH") else "SZSE",
                    asset_class="stock",
                    list_date=listed,
                    delist_date=delisted,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("delisting_fixture", "退市固定样例")
        universe.add_constituents(
            "delisting_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": _DATA_A[0],
                    "source": "synthetic",
                }
                for iid, *_ in _STOCKS_A
            ],
        )
        universe.create_universe("delisting_exit_fact_fixture", "退出事实缺证样例")
        universe.add_constituents(
            "delisting_exit_fact_fixture",
            [
                {
                    "instrument_id": _STOCK_B[0],
                    "effective_from": _DATA_B[0],
                    "source": "synthetic",
                }
            ],
        )
    finally:
        pool.close_all()
    calendar_days = [
        date(2016, 3, 1) + timedelta(days=i)
        for i in range((date(2017, 9, 30) - date(2016, 3, 1)).days + 1)
    ]
    _retain(
        "calendar",
        pl.DataFrame(
            {
                "trade_date": calendar_days,
                "is_open": [day.weekday() < 5 for day in calendar_days],
            }
        ),
        ("2016-03-01", "2017-09-30"),
    )
    _retain(
        "index_daily",
        _stock_prices("000300.SH", calendar_days),
        ("2016-03-01", "2017-07-31"),
    )
    days_a = _trading_days(date(2017, 6, 1), date(2017, 7, 10))
    tickers_a = tuple(row[1] for row in _STOCKS_A)
    bars_a = pl.concat([_stock_prices(ticker, days_a) for ticker in tickers_a])
    bars_a = bars_a.filter(
        (pl.col("source_ticker") != "000033.SZ")
        | (pl.col("trade_date") <= date(2017, 7, 6))
    )
    days_b = _trading_days(date(2016, 4, 1), date(2016, 5, 12))
    bars_b = _stock_prices("600656.SH", days_b)
    _retain("stock_daily", bars_a, _DATA_A)
    _retain("stock_daily", bars_b, _DATA_B)
    _retain(
        "adj_factor",
        bars_a.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
        _DATA_A,
    )
    _retain(
        "adj_factor",
        bars_b.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
        _DATA_B,
    )
    _retain("stock_limit", _limits(bars_a), _DATA_A)
    _retain("stock_limit", _limits(bars_b), _DATA_B)
    _retain("stock_status", _status(bars_a, complete=False), _DATA_A)
    _retain("stock_status", _status(bars_b, complete=True), _DATA_B)
    income_a, balance_a = _fundamentals(tickers_a, days_a, date(2017, 6, 30))
    _retain("income_statement", income_a, _DATA_A)
    _retain("balance_sheet", balance_a, _DATA_A)
    income_b, balance_b = _fundamentals(("600656.SH",), days_b, date(2016, 4, 30))
    _retain("income_statement", income_b, _DATA_B)
    _retain("balance_sheet", balance_b, _DATA_B)
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None
        for strategy_id, universe, name, order_type in (
            (
                "delisting_fixture",
                "delisting_fixture",
                "退市持仓固定样例",
                "market_on_close",
            ),
            (
                "delisting_exit_fact_fixture",
                "delisting_exit_fact_fixture",
                "退出事实缺证样例",
                # SSE had no closing auction before 2018-08-20; plain market
                # orders were the supported intraday type in 2016 (#753).
                "market",
            ),
        ):
            spec = {
                **record.spec_json,
                "strategy_id": strategy_id,
                "name": name,
                "universe": universe,
                "signal_expressions": ["quality_roe"],
                "signal_weights": [1.0],
            }
            spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
            spec["execution"] = {
                **spec["execution"],
                "frequency": "D",
                "default_order_type": order_type,
            }
            governance = container.get(GovernanceService)
            CreateStrategyHandler(governance).handle(
                CreateStrategyCommand(
                    strategy_id=strategy_id, name=name, spec_json=spec
                )
            )
            PublishStrategyHandler(governance).handle(
                PublishStrategyCommand(strategy_id=strategy_id, version=1)
            )
    finally:
        container.close()


_seed()


@app.post("/system-fixture/delisting/repair-status")
def repair_status() -> dict[str, bool]:
    """Backfill the final consolidation sessions' daily status rows."""
    days = _trading_days(date(2017, 6, 1), date(2017, 7, 10))
    bars = pl.concat(
        [
            _stock_prices(ticker, days).filter(
                (pl.col("source_ticker") != "000033.SZ")
                | (pl.col("trade_date") <= date(2017, 7, 6))
            )
            for ticker in ("000033.SZ", "000001.SZ")
        ]
    )
    _retain("stock_status", _status(bars, complete=True), _DATA_A)
    return {"retained": True}


@app.post("/system-fixture/delisting/repair-exit-fact")
def repair_exit_fact() -> dict[str, bool]:
    """Record the withheld delisting in the master the way ingestion would."""
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    try:
        InstrumentWriter(client=SQLiteClient(pool), cache=None).apply_delisting(
            _STOCK_B[0], _EXIT_FACT_B
        )
    finally:
        pool.close_all()
    return {"recorded": True}
