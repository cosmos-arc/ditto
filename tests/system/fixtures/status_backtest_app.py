"""2014 status, missing-quote and immutable recovery through the formal engine."""

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

_PERIOD = ("2014-10-01", "2014-11-28")
retain_empty_dividends(_PERIOD)
_STOCKS = ((1007561, "000001.SZ"), (1007562, "002001.SZ"))


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    retain_history_payload(dataset, frame, period=_PERIOD)


def _seed() -> tuple[pl.DataFrame, pl.DataFrame]:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker in _STOCKS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="历史状态固定样例",
                    exchange="SZSE",
                    asset_class="stock",
                    list_date="2000-01-01",
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("status_fixture", "历史状态固定样例")
        universe.add_constituents(
            "status_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": _PERIOD[0],
                    "source": "synthetic",
                }
                for iid, _ in _STOCKS
            ],
        )
    finally:
        pool.close_all()
    calendar = pl.DataFrame(
        {"trade_date": pl.date_range(date(2014, 10, 1), date(2014, 11, 28), eager=True)}
    ).with_columns((pl.col("trade_date").dt.weekday() <= 5).alias("is_open"))
    _retain("calendar", calendar)
    days = calendar.filter(pl.col("is_open"))["trade_date"].to_list()
    prices = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "pre_close": 10.0,
                "volume": 0.0
                if ticker == "002001.SZ" and day == date(2014, 10, 23)
                else 1_000_000.0,
                "amount": 0.0
                if ticker == "002001.SZ" and day == date(2014, 10, 23)
                else 100_000.0,
            }
            for ticker in ("000001.SZ", "002001.SZ", "000300.SH")
            for day in days
        ]
    )
    _retain("index_daily", prices.filter(pl.col("source_ticker") == "000300.SH"))
    stocks = prices.filter(pl.col("source_ticker") != "000300.SH")
    halted = (pl.col("source_ticker") == "000001.SZ") & pl.col("trade_date").is_in(
        [date(2014, 10, 21), date(2014, 10, 22)]
    )
    status = stocks.select("source_ticker", "trade_date").with_columns(
        halted.alias("is_suspended"),
        pl.lit("").alias("suspend_timing"),
        (
            (pl.col("source_ticker") == "002001.SZ")
            & (pl.col("trade_date") >= date(2014, 10, 21))
        ).alias("is_st"),
        pl.lit("L").alias("list_status"),
    )
    _retain(
        "stock_status",
        status.filter(
            ~(
                (pl.col("source_ticker") == "000001.SZ")
                & (pl.col("trade_date") == date(2014, 10, 23))
            )
        ),
    )
    _retain(
        "stock_limit",
        status.filter(~pl.col("is_suspended")).select(
            "source_ticker",
            "trade_date",
            pl.when(pl.col("is_st")).then(10.5).otherwise(11.0).alias("up_limit"),
            pl.when(pl.col("is_st")).then(9.5).otherwise(9.0).alias("down_limit"),
        ),
    )
    _retain(
        "adj_factor",
        stocks.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
    )
    stocks = stocks.filter(~halted)
    _retain(
        "stock_daily",
        stocks.filter(
            ~(
                (pl.col("source_ticker") == "000001.SZ")
                & (pl.col("trade_date") == date(2014, 10, 24))
            )
        ),
    )
    income = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "report_date": date(2014, 6, 30),
                "knowledge_date": day,
                "net_profit": 40.0
                if (ticker == "000001.SZ") == (day < date(2014, 10, 20))
                else 10.0,
                "revenue": 100.0,
                "eps": 1.0,
            }
            for _, ticker in _STOCKS
            for day in days
        ]
    )
    _retain("income_statement", income)
    _retain(
        "balance_sheet",
        income.select("source_ticker", "report_date", "knowledge_date").with_columns(
            pl.lit(100.0).alias("net_assets")
        ),
    )
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None
        spec = {
            **record.spec_json,
            "strategy_id": "status_fixture",
            "name": "历史状态固定样例",
            "universe": "status_fixture",
            "signal_expressions": ["quality_roe"],
            "signal_weights": [1.0],
        }
        spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
        spec["execution"] = {
            **spec["execution"],
            "frequency": "D",
            "default_order_type": "market_on_close",
        }
        governance = container.get(GovernanceService)
        CreateStrategyHandler(governance).handle(
            CreateStrategyCommand(
                strategy_id="status_fixture", name=spec["name"], spec_json=spec
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(strategy_id="status_fixture", version=1)
        )
    finally:
        container.close()
    return status, stocks


_status, _prices = _seed()


@app.post("/system-fixture/status/repair-status")
def repair_status() -> dict[str, bool]:
    _retain("stock_status", _status)
    return {"retained": True}


@app.post("/system-fixture/status/repair-quote")
def repair_quote() -> dict[str, bool]:
    _retain("stock_daily", _prices)
    return {"retained": True}
