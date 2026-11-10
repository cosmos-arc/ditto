"""Ordinary historical stock run consuming financial factors by publication time.

Synthetic 2014-style disclosures are retained now (2026 receipts): one stock
announces before the run window, the other announces, is revised, and carries a
future-dated sentinel inside the window. The seed stock multi-factor strategy
(quality_roe) must consume the then-visible disclosure version per session.
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

_PERIOD = ("2026-09-01", "2026-11-30")
retain_empty_dividends(_PERIOD)
_IIDS = (1_003_001, 1_003_002)
_TICKERS = ("000001.SZ", "600001.SH")
_REPORT = date(2026, 6, 30)
# 公告（披露锚）日历：A 运行前已披露；B 首披 10-13、修订 10-20；
# 哨兵披露锚 12-31 晚于运行终点 11-13；补证晚到修订 10-23。
_B_ANNOUNCE = date(2026, 10, 13)
_B_REVISION = date(2026, 10, 20)
_B_SENTINEL = date(2026, 12, 31)
_B_LATE_ARRIVAL = date(2026, 10, 23)


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    retain_history_payload(dataset, frame, period=_PERIOD)


def _income(extra_b_rows: list[dict[str, object]] | None = None) -> pl.DataFrame:
    rows: list[dict[str, object]] = [
        # A：运行窗口前已披露，全窗口可见 roe = 10 / 100 = 0.1。
        {
            "source_ticker": _TICKERS[0],
            "report_date": _REPORT,
            "knowledge_date": date(2026, 9, 1),
            "net_profit": 10.0,
            "revenue": 100.0,
            "eps": 1.0,
        },
        # B：首披 10-13（roe 0.2 > A），修订 10-20（roe 0.05 < A）。
        {
            "source_ticker": _TICKERS[1],
            "report_date": _REPORT,
            "knowledge_date": _B_ANNOUNCE,
            "net_profit": 20.0,
            "revenue": 100.0,
            "eps": 1.0,
        },
        {
            "source_ticker": _TICKERS[1],
            "report_date": _REPORT,
            "knowledge_date": _B_REVISION,
            "net_profit": 5.0,
            "revenue": 100.0,
            "eps": 1.0,
        },
        # 未来哨兵：披露锚在运行终点之后，任何会话都不可见。
        {
            "source_ticker": _TICKERS[1],
            "report_date": _REPORT,
            "knowledge_date": _B_SENTINEL,
            "net_profit": 999.0,
            "revenue": 100.0,
            "eps": 1.0,
        },
        *(extra_b_rows or []),
    ]
    return pl.DataFrame(
        rows,
        schema={
            "source_ticker": pl.String,
            "report_date": pl.Date,
            "knowledge_date": pl.Date,
            "net_profit": pl.Float64,
            "revenue": pl.Float64,
            "eps": pl.Float64,
        },
    )


def _balance() -> pl.DataFrame:
    rows = [
        {
            "source_ticker": ticker,
            "report_date": _REPORT,
            "knowledge_date": knowledge,
            "net_assets": 100.0,
        }
        for ticker, knowledge in (
            (_TICKERS[0], date(2026, 9, 1)),
            (_TICKERS[1], _B_ANNOUNCE),
            (_TICKERS[1], _B_REVISION),
            (_TICKERS[1], _B_SENTINEL),
        )
    ]
    return pl.DataFrame(
        rows,
        schema={
            "source_ticker": pl.String,
            "report_date": pl.Date,
            "knowledge_date": pl.Date,
            "net_assets": pl.Float64,
        },
    )


def _prices(ticker: str, days: list[date]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": [ticker] * len(days),
            "trade_date": days,
            "knowledge_date": [day + timedelta(days=1) for day in days],
            "open": [10.0] * len(days),
            "high": [10.0] * len(days),
            "low": [10.0] * len(days),
            "close": [10.0] * len(days),
            "pre_close": [10.0] * len(days),
            "volume": [10000000.0] * len(days),
            "amount": [1000000.0] * len(days),
        }
    )


def _seed() -> None:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed in zip(
            _IIDS, _TICKERS, ("1991-04-03", "1990-12-19"), strict=True
        ):
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="财务因子固定样例",
                    exchange="SZSE" if ticker.endswith(".SZ") else "SSE",
                    asset_class="stock",
                    list_date=listed,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("financial_factors_fixture", "财务因子固定样例")
        universe.add_constituents(
            "financial_factors_fixture",
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
    all_days = pl.date_range(date(2026, 9, 1), date(2026, 12, 31), eager=True)
    calendar = pl.DataFrame({"trade_date": all_days}).with_columns(
        (
            (pl.col("trade_date").dt.weekday() <= 5)
            & ~pl.col("trade_date").is_between(date(2026, 10, 1), date(2026, 10, 7))
        ).alias("is_open")
    )
    # 冻结日历按快照请求窗解析逐日 lineage；日历快照窗必须覆盖运行终点
    # 之后 31 天（prepare_calendar 的扩展终点）。
    retain_history_payload("calendar", calendar, period=("2026-09-01", "2026-12-31"))
    days = calendar.filter(pl.col("is_open"))["trade_date"].to_list()
    prices = pl.concat([_prices(ticker, days) for ticker in (*_TICKERS, "000300.SH")])
    stock_prices = prices.filter(pl.col("source_ticker").is_in(_TICKERS))
    _retain("stock_daily", stock_prices)
    _retain("index_daily", prices.filter(pl.col("source_ticker") == "000300.SH"))
    _retain(
        "adj_factor",
        prices.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
    )
    _retain(
        "stock_status",
        stock_prices.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_st"),
            pl.lit(False).alias("is_suspended"),
            pl.lit("L").alias("list_status"),
        ),
    )
    _retain(
        "stock_limit",
        stock_prices.select("source_ticker", "trade_date").with_columns(
            pl.lit(11.0).alias("up_limit"), pl.lit(9.0).alias("down_limit")
        ),
    )
    _retain("income_statement", _income())
    _retain("balance_sheet", _balance())
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_stock_selection_rotation", 1
        )
        assert record is not None, "the published stock seed must exist"
        spec = {
            **record.spec_json,
            "strategy_id": "financial_factors_fixture",
            "name": "财务因子固定样例",
            "universe": "financial_factors_fixture",
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
                strategy_id="financial_factors_fixture",
                name="财务因子固定样例",
                spec_json=spec,
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(strategy_id="financial_factors_fixture", version=1)
        )
    finally:
        container.close()


_seed()


@app.post("/system-fixture/financial-factors/repair")
def repair_financial_factors() -> dict[str, bool]:
    """Retain a late-arriving B revision; old frozen runs must stay unchanged."""
    _retain(
        "income_statement",
        _income(
            [
                {
                    "source_ticker": _TICKERS[1],
                    "report_date": _REPORT,
                    "knowledge_date": _B_LATE_ARRIVAL,
                    "net_profit": 30.0,
                    "revenue": 100.0,
                    "eps": 1.0,
                }
            ]
        ),
    )
    return {"repaired": True}
