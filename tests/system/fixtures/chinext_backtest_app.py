"""Retained synthetic ChiNext reform and IPO windows through the formal engine."""

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

_PERIOD = ("2020-07-01", "2020-11-30")
retain_empty_dividends(_PERIOD)
_STOCKS = (
    (1003001, "300750.SZ", "2018-06-11"),
    (1003002, "300122.SZ", "2010-09-28"),
    (1003003, "300896.SZ", "2020-09-28"),
)


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    retain_history_payload(dataset, frame, period=_PERIOD)


def _seed() -> pl.DataFrame:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed in _STOCKS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="创业板历史规则固定样例",
                    exchange="SZSE",
                    asset_class="stock",
                    list_date=listed,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("chinext_fixture", "创业板历史规则固定样例")
        universe.add_constituents(
            "chinext_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": _PERIOD[0],
                    "source": "synthetic",
                }
                for iid, _, _ in _STOCKS
            ],
        )
    finally:
        pool.close_all()
    all_days = pl.date_range(date(2020, 7, 1), date(2020, 11, 30), eager=True)
    calendar = pl.DataFrame({"trade_date": all_days}).with_columns(
        (
            (pl.col("trade_date").dt.weekday() <= 5)
            & ~pl.col("trade_date").is_between(date(2020, 10, 1), date(2020, 10, 8))
        ).alias("is_open")
    )
    _retain("calendar", calendar)
    days = calendar.filter(pl.col("is_open"))["trade_date"].to_list()
    rows = []
    for _, ticker, listed in (*_STOCKS, (0, "000300.SH", "2000-01-01")):
        previous = 10.0
        for day in days:
            if day.isoformat() < listed:
                continue
            price = 10.0
            if ticker == "300750.SZ":
                price = {
                    date(2020, 8, 21): 11.0,
                    date(2020, 8, 24): 12.1,
                    date(2020, 8, 25): 14.52,
                }.get(day, 10.0 if day < date(2020, 8, 21) else 14.0)
            if ticker == "300122.SZ":
                price = (
                    10.0
                    if day < date(2020, 8, 21)
                    else (11.0 if day < date(2020, 8, 25) else 13.2)
                )
            if ticker == "300896.SZ":
                price = 12.0 if day < date(2020, 10, 13) else 14.4
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
    prices = pl.DataFrame(rows)
    stocks = prices.filter(pl.col("source_ticker") != "000300.SH")
    _retain("stock_daily", stocks)
    _retain("index_daily", prices.filter(pl.col("source_ticker") == "000300.SH"))
    _retain(
        "adj_factor",
        stocks.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
    )
    _retain(
        "stock_status",
        stocks.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_st"),
            pl.lit(False).alias("is_suspended"),
            pl.lit("L").alias("list_status"),
        ),
    )
    band = pl.when(pl.col("trade_date") < date(2020, 8, 24)).then(0.1).otherwise(0.2)
    limits = (
        stocks.select("source_ticker", "trade_date", "pre_close")
        .with_columns(
            (pl.col("pre_close") * (1 + band)).round(2).alias("up_limit"),
            (pl.col("pre_close") * (1 - band)).round(2).alias("down_limit"),
        )
        .drop("pre_close")
    )
    _retain(
        "stock_limit",
        limits.with_columns(
            pl.when(
                (pl.col("source_ticker") == "300750.SZ")
                & (pl.col("trade_date") == date(2020, 8, 24))
            )
            .then(12.1)
            .otherwise(pl.col("up_limit"))
            .alias("up_limit")
        ),
    )
    income = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "report_date": date(2020, 6, 30),
                "knowledge_date": day,
                "net_profit": (
                    40.0
                    if day < date(2020, 10, 9) or day >= date(2020, 10, 12)
                    else 5.0
                )
                if ticker == "300896.SZ"
                else (20.0 if (i + j) % 2 else 10.0),
                "revenue": 100.0,
                "eps": 1.0,
            }
            for j, (_, ticker, _) in enumerate(_STOCKS)
            for i, day in enumerate(days)
        ]
    )
    _retain("income_statement", income)
    _retain(
        "balance_sheet",
        income.select("source_ticker", "report_date", "knowledge_date").with_columns(
            pl.lit(100.0).alias("net_assets")
        ),
    )
    _publish_strategies()
    return limits


def _publish_strategies() -> None:
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None
        governance = container.get(GovernanceService)
        for order_type in ("market_on_close", "market"):
            strategy_id = f"chinext_{order_type}_fixture"
            spec = {
                **record.spec_json,
                "strategy_id": strategy_id,
                "name": "创业板历史规则固定样例",
                "universe": "chinext_fixture",
                "signal_expressions": ["quality_roe"],
                "signal_weights": [1.0],
            }
            spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
            spec["execution"] = {
                **spec["execution"],
                "frequency": "D",
                "default_order_type": order_type,
            }
            spec["execution"]["cost_model"] = {
                **spec["execution"]["cost_model"],
                "slippage_bps": 0.0,
            }
            CreateStrategyHandler(governance).handle(
                CreateStrategyCommand(
                    strategy_id=strategy_id, name=spec["name"], spec_json=spec
                )
            )
            PublishStrategyHandler(governance).handle(
                PublishStrategyCommand(strategy_id=strategy_id, version=1)
            )
    finally:
        container.close()


_limits = _seed()


@app.post("/system-fixture/chinext/repair")
def repair_chinext() -> dict[str, bool]:
    _retain("stock_limit", _limits)
    return {"repaired": True}
