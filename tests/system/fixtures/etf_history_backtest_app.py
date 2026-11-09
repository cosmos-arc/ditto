"""Six ETF categories through the formal UI/API/engine over retained fixed inputs."""

import os
from datetime import UTC, date, datetime, timedelta
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
from ditto_data.sources.reference_config import EtfReferenceConfigSource
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from tests.system.fixtures.historical_backtest_app import app, retain_history_payload

_PERIOD = ("2020-06-01", "2020-10-02")
_ETFS = (
    (2008001, "159915.SZ", "2011-12-09", 2.0),
    (2008002, "511010.SH", "2013-03-25", 100.0),
    (2008003, "518880.SH", "2013-07-29", 4.0),
    (2008004, "510900.SH", "2012-10-22", 1.0),
    (2008005, "511880.SH", "2013-04-18", 100.0),
    (2008006, "159985.SZ", "2019-12-05", 1.0),
)


def _reference(*, repair: bool) -> None:
    frame = EtfReferenceConfigSource(
        Path(__file__).resolve().parents[3] / "config/default/etf_reference.json"
    ).fetch_etf_reference()
    if repair:
        frame = frame.with_columns(
            (pl.col("basis") + " ; synthetic repair receipt").alias("basis")
        )
    else:
        frame = frame.filter(
            ~(
                (pl.col("source_ticker") == "159985.SZ")
                & (pl.col("field") == "trading_category")
            )
        )
    today = datetime.now(UTC).date().isoformat()
    retain_history_payload(
        "etf_reference", frame, source="config", period=(today, today)
    )


def _seed() -> None:
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, listed, _ in _ETFS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="ETF六类固定样例",
                    exchange="SZSE" if ticker.endswith(".SZ") else "SSE",
                    asset_class="etf",
                    list_date=listed,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("etf_history_fixture", "ETF六类历史规则固定样例")
        universe.add_constituents(
            "etf_history_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": _PERIOD[0],
                    "source": "synthetic",
                }
                for iid, _, _, _ in _ETFS
            ],
        )
    finally:
        pool.close_all()
    days = pl.date_range(
        date.fromisoformat(_PERIOD[0]), date.fromisoformat(_PERIOD[1]), eager=True
    )
    retain_history_payload(
        "calendar",
        pl.DataFrame({"trade_date": days, "is_open": days.dt.weekday() <= 5}),
        period=_PERIOD,
    )
    rows = []
    for _, ticker, _, base in (*_ETFS, (0, "000300.SH", "2005-04-08", 10.0)):
        previous = base
        for i, day in enumerate(day for day in days if day.weekday() < 5):
            price = round(base * (1 + i * 0.001), 3)
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
                    "volume": 1e9,
                    "amount": 1e9 * price / 10,
                }
            )
            previous = price
    prices = pl.DataFrame(rows)
    etfs = prices.filter(pl.col("source_ticker") != "000300.SH")
    retain_history_payload("etf_daily", etfs, period=_PERIOD)
    retain_history_payload(
        "index_daily",
        prices.filter(pl.col("source_ticker") == "000300.SH"),
        period=_PERIOD,
    )
    retain_history_payload(
        "fund_adj",
        etfs.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.lit(1.0).alias("adj_factor")
        ),
        period=_PERIOD,
    )
    _reference(repair=False)
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_etf_industry_rotation", 1
        )
        assert record is not None
        governance = container.get(GovernanceService)
        for kind in ("market", "market_on_close"):
            strategy_id = f"etf_history_{kind}_fixture"
            spec = {
                **record.spec_json,
                "strategy_id": strategy_id,
                "name": "ETF六类历史规则固定样例",
                "universe": "etf_history_fixture",
                "signal_expressions": ["momentum_1m"],
                "signal_weights": [1.0],
            }
            spec["selector"] = {**spec["selector"], "params": {"k": 6}}
            spec["params"] = {**spec["params"], "top_k": 6, "rebalance_freq": "daily"}
            spec["execution"] = {
                **spec["execution"],
                "frequency": "D",
                "default_order_type": kind,
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


_seed()


@app.post("/system-fixture/etf-history/repair")
def repair_etf_reference() -> dict[str, bool]:
    _reference(repair=True)
    return {"repaired": True}
