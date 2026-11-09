"""Extend the retained-history fixture with a synthetic main-board IPO boundary."""

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

from tests.system.fixtures.historical_backtest_app import app, retain_history_payload

_PERIOD = ("2026-09-01", "2026-11-30")
_IIDS = (1_001_001, 1_001_002)
_TICKERS = ("000001.SZ", "001246.SZ")


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    retain_history_payload(dataset, frame, period=_PERIOD)


def _prices(ticker: str, days: list[date]) -> pl.DataFrame:
    rows = []
    previous = 10.0
    for day in days:
        if ticker == "001246.SZ" and day < date(2026, 9, 30):
            continue
        price = 10.0
        if ticker == "001246.SZ" and day >= date(2026, 10, 8):
            price = (
                12.0
                if day < date(2026, 10, 14)
                else (13.2 if day == date(2026, 10, 14) else 13.0)
            )
        rows.append(
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "pre_close": previous,
                "volume": 10000000.0,
                "amount": 1000000.0,
            }
        )
        previous = price
    return pl.DataFrame(rows)


def _seed() -> pl.DataFrame:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed in zip(
            _IIDS, _TICKERS, ("1991-04-03", "2026-09-30"), strict=True
        ):
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="主板制度固定样例",
                    exchange="SZSE",
                    asset_class="stock",
                    list_date=listed,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("mainboard_ipo_fixture", "主板规则固定样例")
        universe.add_constituents(
            "mainboard_ipo_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": "2026-09-01",
                    "source": "synthetic",
                }
                for iid in _IIDS
            ],
        )
    finally:
        pool.close_all()
    all_days = pl.date_range(date(2026, 9, 1), date(2026, 11, 30), eager=True)
    calendar = pl.DataFrame({"trade_date": all_days}).with_columns(
        (
            (pl.col("trade_date").dt.weekday() <= 5)
            & ~pl.col("trade_date").is_between(date(2026, 10, 1), date(2026, 10, 7))
        ).alias("is_open")
    )
    _retain("calendar", calendar)
    days = calendar.filter(pl.col("is_open"))["trade_date"].to_list()
    prices = pl.concat([_prices(ticker, days) for ticker in _TICKERS])
    _retain("stock_daily", prices)
    _retain("index_daily", _prices("000300.SH", days))
    _retain(
        "adj_factor",
        prices.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
    )
    _retain(
        "stock_status",
        prices.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_st"),
            pl.lit(False).alias("is_suspended"),
            pl.lit("L").alias("list_status"),
        ),
    )
    income = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "report_date": date(2026, 6, 30),
                "knowledge_date": day,
                "net_profit": profit,
                "revenue": 100.0,
                "eps": 1.0,
            }
            for ticker, day, profit in [
                ("000001.SZ", date(2026, 9, 1), 10.0),
                ("001246.SZ", date(2026, 9, 1), 20.0),
                ("001246.SZ", date(2026, 10, 12), 5.0),
                ("001246.SZ", date(2026, 10, 13), 30.0),
            ]
        ]
    )
    _retain("income_statement", income)
    _retain(
        "balance_sheet",
        income.select("source_ticker", "report_date", "knowledge_date").with_columns(
            pl.lit(100.0).alias("net_assets")
        ),
    )
    limits = (
        prices.select("source_ticker", "trade_date", "pre_close")
        .with_columns(
            (pl.col("pre_close") * 1.1).round(2).alias("up_limit"),
            (pl.col("pre_close") * 0.9).round(2).alias("down_limit"),
        )
        .drop("pre_close")
    )
    # Retain an explicit bad sixth-day limit; repair must create a new frozen run.
    broken = limits.with_columns(
        pl.when(pl.col("source_ticker") == "001246.SZ")
        .then(999999.999)
        .otherwise(pl.col("up_limit"))
        .alias("up_limit")
    )
    _retain("stock_limit", broken)
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None, "the published stock seed must exist"
        spec = {
            **record.spec_json,
            "strategy_id": "mainboard_ipo_fixture",
            "name": "主板制度固定样例",
            "universe": "mainboard_ipo_fixture",
            "signal_expressions": ["quality_roe"],
            "signal_weights": [1.0],
        }
        spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
        spec["execution"] = {**spec["execution"], "frequency": "D"}
        governance = container.get(GovernanceService)
        CreateStrategyHandler(governance).handle(
            CreateStrategyCommand(
                strategy_id="mainboard_ipo_fixture",
                name="主板制度固定样例",
                spec_json=spec,
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(strategy_id="mainboard_ipo_fixture", version=1)
        )
    finally:
        container.close()
    return limits


_limits = _seed()


@app.post("/system-fixture/mainboard/repair")
def repair_mainboard() -> dict[str, bool]:
    _retain("stock_limit", _limits)
    return {"repaired": True}
