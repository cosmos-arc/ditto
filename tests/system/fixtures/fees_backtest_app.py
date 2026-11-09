"""Synthetic ordinary stock runs straddling verified fee effective dates."""

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

__all__ = ["app"]

_STOCKS = ((1_002_001, "600000.SH", "SSE"), (1_002_002, "000001.SZ", "SZSE"))
_PERIODS = [
    ("2014-01-01", "2014-02-28"),
    ("2015-06-01", "2015-09-30"),
    ("2022-03-01", "2022-06-30"),
    ("2023-07-01", "2023-09-30"),
]


def _retain_period(period: tuple[str, str]) -> None:
    days = pl.date_range(
        date.fromisoformat(period[0]), date.fromisoformat(period[1]), eager=True
    )
    calendar = pl.DataFrame({"trade_date": days}).with_columns(
        (
            (pl.col("trade_date").dt.weekday() <= 5)
            & ~pl.col("trade_date").is_in(
                [
                    date(2014, 1, 1),
                    date(2014, 1, 31),
                    date(2022, 4, 4),
                    date(2022, 4, 5),
                    date(2022, 5, 2),
                    date(2022, 5, 3),
                    date(2022, 5, 4),
                ]
            )
        ).alias("is_open")
    )

    def retain(dataset: str, frame: pl.DataFrame) -> None:
        retain_history_payload(dataset, frame, period=period)

    retain("calendar", calendar)
    open_days = calendar.filter(pl.col("is_open"))["trade_date"].to_list()
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
                "volume": 10000000.0,
                "amount": 1000000.0,
            }
            for ticker in ("600000.SH", "000001.SZ", "000300.SH")
            for day in open_days
        ]
    )
    retain("stock_daily", prices.filter(pl.col("source_ticker") != "000300.SH"))
    retain("index_daily", prices.filter(pl.col("source_ticker") == "000300.SH"))
    stocks = prices.filter(pl.col("source_ticker") != "000300.SH")
    retain(
        "adj_factor",
        stocks.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
    )
    retain(
        "stock_status",
        stocks.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_st"),
            pl.lit(False).alias("is_suspended"),
            pl.lit("L").alias("list_status"),
        ),
    )
    retain(
        "stock_limit",
        stocks.select("source_ticker", "trade_date").with_columns(
            pl.lit(11.0).alias("up_limit"), pl.lit(9.0).alias("down_limit")
        ),
    )
    income = pl.DataFrame(
        [
            {
                "source_ticker": ticker,
                "report_date": date(day.year - 1, 9, 30),
                "knowledge_date": day,
                "net_profit": 20.0 if (i + j) % 2 else 10.0,
                "revenue": 100.0,
                "eps": 1.0,
            }
            for j, (_, ticker, _) in enumerate(_STOCKS)
            for i, day in enumerate(open_days)
        ]
    )
    retain("income_statement", income)
    retain(
        "balance_sheet",
        income.select("source_ticker", "report_date", "knowledge_date").with_columns(
            pl.lit(100.0).alias("net_assets")
        ),
    )


def _seed() -> None:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, exchange in _STOCKS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="历史费用固定样例",
                    exchange=exchange,
                    asset_class="stock",
                    list_date="2000-01-04",
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("historical_fees_fixture", "历史费用固定样例")
        universe.add_constituents(
            "historical_fees_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": "2014-01-01",
                    "source": "synthetic",
                }
                for iid, _, _ in _STOCKS
            ],
        )
    finally:
        pool.close_all()
    for period in _PERIODS:
        _retain_period(period)
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None
        spec = {
            **record.spec_json,
            "strategy_id": "historical_fees_fixture",
            "name": "历史费用固定样例",
            "universe": "historical_fees_fixture",
            "signal_expressions": ["quality_roe"],
            "signal_weights": [1.0],
        }
        spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
        spec["execution"] = {
            **spec["execution"],
            "frequency": "D",
            "default_order_type": "market",
        }
        spec["execution"]["cost_model"] = {
            **spec["execution"]["cost_model"],
            "commission_rate": 0.0003,
            "slippage_bps": 0.0,
        }
        governance = container.get(GovernanceService)
        CreateStrategyHandler(governance).handle(
            CreateStrategyCommand(
                strategy_id="historical_fees_fixture",
                name="历史费用固定样例",
                spec_json=spec,
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(strategy_id="historical_fees_fixture", version=1)
        )
    finally:
        container.close()


_seed()
