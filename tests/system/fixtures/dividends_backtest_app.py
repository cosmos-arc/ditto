"""Synthetic cash distributions exercise the ordinary retained-input pipeline."""

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
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

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
    etfs = frame.with_columns(
        pl.col("source_ticker").replace_strict(
            {"600000.SH": "510300.SH", "000001.SZ": "510500.SH"}
        )
    )
    _retain("etf_daily", etfs)
    _retain(
        "fund_adj",
        etfs.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.when(pl.col("trade_date") < _EX)
            .then(1.0)
            .otherwise(1.1111)
            .alias("adj_factor")
        ),
    )

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


def _dividends(*, complete: bool, etf: bool = False) -> None:
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
            for ticker in (
                ("510300.SH", "510500.SH") if etf else ("600000.SH", "000001.SZ")
            )
        ]
    ).with_columns(pl.col("pay_date").cast(pl.Date))
    # Duplicate provider rows must not create duplicate economic rights.
    retain_history_payload(
        "etf_dividend" if etf else "dividend",
        pl.concat([frame, frame]),
        period=("1990-01-01", _PERIOD[1]),
    )


_seed_prices()
_dividends(complete=False)
_dividends(complete=False, etf=True)


@app.post("/system-fixture/dividends/repair")
def repair_dividends() -> dict[str, bool]:
    """Install complete synthetic facts; the UI still submits the accepted run."""
    _dividends(complete=True)
    return {"repaired": True}


@app.post("/system-fixture/etf-dividends/repair")
def repair_etf_dividends() -> dict[str, bool]:
    """Install independently observed ETF dates, without changing the failed run."""
    _dividends(complete=True, etf=True)
    return {"repaired": True}


def _etf_strategy() -> None:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    try:
        universe = UniverseWriter(SQLiteClient(pool), DataCache())
        universe.create_universe("etf_dividends_fixture", "ETF分红固定样例")
        universe.add_constituents(
            "etf_dividends_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": "2014-01-01",
                    "source": "synthetic",
                }
                for iid in (2_001_001, 2_001_002)
            ],
        )
    finally:
        pool.close_all()
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_etf_industry_rotation", 1
        )
        assert record is not None
        spec = {
            **record.spec_json,
            "strategy_id": "etf_dividends_fixture",
            "name": "ETF分红固定样例",
            "universe": "etf_dividends_fixture",
            "signal_expressions": ["reversal_3d"],
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
                strategy_id="etf_dividends_fixture",
                name="ETF分红固定样例",
                spec_json=spec,
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(strategy_id="etf_dividends_fixture", version=1)
        )
    finally:
        container.close()


_etf_strategy()
