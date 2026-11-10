"""ETF termination holdings, exit facts and missing evidence over the engine.

Journey A mirrors the retained production facts of 159917.SZ (国泰中小板300
成长ETF, listed 2012-04-06): its retained etf_daily/fund_adj/fund_share all
stop on 2015-08-26 with the final close 1.770; the fixture master records the
termination fact 2015-08-27 (the first session after the last quote) the way
an ingestion refresh would — production's retained etf_basic only carries the
undated list_status=D flag, so the exit DATE itself is the fixture's recorded
fact. Journey B mirrors 159927.SZ (鹏华沪深300ETF, listed 2013-08-16, quotes
stop 2018-02-13, final close 3.850) with the exit fact withheld until the
repair endpoint records it. The June-2015/Nov-2017 warmup ramps, volumes and
the weekday calendar are synthetic.
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

from tests.system.fixtures.historical_backtest_app import app, retain_history_payload

_PERIOD_A = ("2015-06-01", "2015-08-31")
_PERIOD_B = ("2017-11-01", "2018-02-28")
_RUN_A = ("2015-08-20", "2015-08-28")
_RUN_B = ("2018-02-09", "2018-02-14")
_EXIT_A = "2015-08-27"
_EXIT_B = "2018-02-14"
_RULE_FIELDS = (
    ("trading_category", "equity", "text"),
    ("trading_currency", "CNY", "text"),
    ("lot_size", "100", "count"),
    ("tick_size", "0.001", "price"),
    ("settlement_cycle", "1", "days"),
    ("price_limit_pct", "0.1", "ratio"),
)
# (iid, ticker, listed, delist recorded at seed, ramp base, pinned final closes)
_ETFS = (
    (
        2_009_171,
        "159917.SZ",
        "2012-04-06",
        _EXIT_A,
        1.7,
        {date(2015, 8, 24): 1.746, date(2015, 8, 25): 1.615, date(2015, 8, 26): 1.77},
    ),
    (
        2_008_801,
        "510880.SH",
        "2007-01-18",
        None,
        4.0,
        {},
    ),
    (
        2_009_271,
        "159927.SZ",
        "2013-08-16",
        None,
        3.8,
        {date(2018, 2, 12): 3.784, date(2018, 2, 13): 3.85},
    ),
)


def _trading_days(start: date, end: date) -> list[date]:
    return [
        day
        for day in (start + timedelta(days=i) for i in range((end - start).days + 1))
        if day.weekday() < 5
    ]


def _prices(ticker: str, days: list[date], base: float, final: dict[date, float]):
    """Ramped closes with the production final sessions pinned to real quotes."""
    rows: list[dict[str, object]] = []
    previous = base
    for i, day in enumerate(days):
        price = final.get(day, round(base * (1 + i * 0.001), 3))
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
                "volume": 1_000_000.0,
                "amount": price * 1_000_000.0,
            }
        )
        previous = price
    return rows


def _bars(period: tuple[str, str], tickers: tuple[str, ...]) -> pl.DataFrame:
    """ETF quotes stop on their real final session; the survivor runs the period."""
    start, end = (date.fromisoformat(day) for day in period)
    days = _trading_days(start, end)
    lookup = {row[1]: row for row in _ETFS}
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        if ticker == "000300.SH":
            rows += _prices(ticker, days, 10.0, {})
            continue
        *_, base, final = lookup[ticker]
        last = max(final) if final else days[-1]
        rows += _prices(ticker, [day for day in days if day <= last], base, final)
    return pl.DataFrame(rows)


def _reference() -> None:
    rows = [
        {
            "source_ticker": ticker,
            "field": field,
            "value": value,
            "unit": unit,
            "effective_from": listed,
            "effective_to": None,
            "basis": "synthetic dated exchange declaration (fixture)",
        }
        for iid, ticker, listed, _, _, _ in _ETFS
        for field, value, unit in _RULE_FIELDS
    ]
    frame = pl.DataFrame(
        rows,
        schema={
            "source_ticker": pl.String,
            "field": pl.String,
            "value": pl.String,
            "unit": pl.String,
            "effective_from": pl.String,
            "effective_to": pl.String,
            "basis": pl.String,
        },
    )
    today = date.today().isoformat()
    retain_history_payload(
        "etf_reference", frame, source="config", period=(today, today)
    )


def _seed() -> None:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed, delisted, _, _ in _ETFS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="ETF终止上市固定样例",
                    exchange="SZSE" if ticker.endswith(".SZ") else "SSE",
                    asset_class="etf",
                    list_date=listed,
                    delist_date=delisted,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("etf_delisting_fixture", "ETF终止上市固定样例")
        universe.add_constituents(
            "etf_delisting_fixture",
            [
                {
                    "instrument_id": 2_009_171,
                    "effective_from": _PERIOD_A[0],
                    "source": "synthetic",
                },
                {
                    "instrument_id": 2_008_801,
                    "effective_from": _PERIOD_A[0],
                    "source": "synthetic",
                },
            ],
        )
        universe.create_universe("etf_delisting_exit_fact_fixture", "ETF退出缺证样例")
        universe.add_constituents(
            "etf_delisting_exit_fact_fixture",
            [
                {
                    "instrument_id": 2_009_271,
                    "effective_from": _PERIOD_B[0],
                    "source": "synthetic",
                }
            ],
        )
    finally:
        pool.close_all()
    calendar_days = [
        date(2015, 1, 1) + timedelta(days=i)
        for i in range((date(2018, 12, 31) - date(2015, 1, 1)).days + 1)
    ]
    retain_history_payload(
        "calendar",
        pl.DataFrame(
            {
                "trade_date": calendar_days,
                "is_open": [day.weekday() < 5 for day in calendar_days],
            }
        ),
        period=("2015-01-01", "2018-12-31"),
    )
    for period, tickers in (
        (_PERIOD_A, ("159917.SZ", "510880.SH", "000300.SH")),
        (_PERIOD_B, ("159927.SZ", "000300.SH")),
    ):
        frame = _bars(period, tickers)
        etfs = frame.filter(pl.col("source_ticker") != "000300.SH")
        retain_history_payload("etf_daily", etfs, period=period)
        retain_history_payload(
            "index_daily",
            frame.filter(pl.col("source_ticker") == "000300.SH"),
            period=period,
        )
        retain_history_payload(
            "fund_adj",
            etfs.select("source_ticker", "trade_date", "knowledge_date").with_columns(
                pl.lit(1.0).alias("adj_factor")
            ),
            period=period,
        )
    _reference()
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_etf_industry_rotation", 1
        )
        assert record is not None
        for strategy_id, universe, k in (
            ("etf_delisting_fixture", "etf_delisting_fixture", 2),
            ("etf_delisting_exit_fact_fixture", "etf_delisting_exit_fact_fixture", 1),
        ):
            spec = {
                **record.spec_json,
                "strategy_id": strategy_id,
                "name": "ETF终止上市固定样例",
                "universe": universe,
                "signal_expressions": ["momentum_1m"],
                "signal_weights": [1.0],
            }
            spec["selector"] = {**spec["selector"], "params": {"k": k}}
            spec["params"] = {**spec["params"], "top_k": k, "rebalance_freq": "daily"}
            spec["execution"] = {
                **spec["execution"],
                "frequency": "D",
                "default_order_type": "market",
            }
            governance = container.get(GovernanceService)
            CreateStrategyHandler(governance).handle(
                CreateStrategyCommand(
                    strategy_id=strategy_id,
                    name="ETF终止上市固定样例",
                    spec_json=spec,
                )
            )
            PublishStrategyHandler(governance).handle(
                PublishStrategyCommand(strategy_id=strategy_id, version=1)
            )
    finally:
        container.close()


_seed()


@app.post("/system-fixture/etf-delisting/repair-exit-fact")
def repair_etf_exit_fact() -> dict[str, bool]:
    """Record the withheld termination in the master the way ingestion would."""
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    try:
        InstrumentWriter(client=SQLiteClient(pool), cache=None).apply_delisting(
            2_009_271, _EXIT_B
        )
    finally:
        pool.close_all()
    return {"recorded": True}
