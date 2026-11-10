"""159941.SZ 1:4 split, a zero-volume session and resumption over the real engine.

Synthetic June prices warm the momentum window; the split session, carried
zero-volume row and resumed quote follow the retained production facts of the
2022-07-05 conversion (see docs/evidence/etf-share-conversions-762.md).
"""

import os
from datetime import date, datetime, timedelta
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
from ditto_data.sources.etf_share_conversions import EtfShareConversionsConfigSource
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import DataCache, SQLiteClient, SQLitePool
from ditto_strategy.governance.service import GovernanceService
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)

from tests.system.fixtures.backtest_nav_app import app
from tests.system.fixtures.historical_backtest_app import (
    retain_empty_dividends,
    retain_history_payload,
)

_PERIOD = ("2022-05-16", "2022-07-08")
_WINDOW = ("2022-07-01", "2022-07-08")
_SPLIT = date(2022, 7, 5)
_HALTED = date(2022, 7, 6)
_ETFS = (
    (2_008_941, "159941.SZ", "SZSE", "2014-12-15"),
    (2_008_901, "159901.SZ", "SZSE", "2006-04-17"),
)


def _reference() -> pl.DataFrame:
    """Dated secondary-market declarations for both fixture members."""
    rows = []
    for _, ticker, _, _ in _ETFS:
        for field, value, unit in (
            ("trading_category", "equity", "text"),
            ("trading_currency", "CNY", "text"),
            ("lot_size", "100", "count"),
            ("tick_size", "0.001", "price"),
            ("settlement_cycle", "1", "days"),
            ("price_limit_pct", "0.1", "ratio"),
        ):
            rows.append(
                {
                    "source_ticker": ticker,
                    "field": field,
                    "value": value,
                    "unit": unit,
                    "effective_from": "2014-01-01",
                    "effective_to": "2026-11-10",
                    "basis": "synthetic dated exchange declaration (#762 fixture)",
                }
            )
    return pl.DataFrame(rows)


def _declared_conversions() -> pl.DataFrame:
    """The maintainer declaration file itself, through its production loader."""
    return EtfShareConversionsConfigSource(
        Path(__file__).resolve().parents[3]
        / "config/default/etf_share_conversions.json"
    ).fetch_etf_share_conversions()


def _etf_price(ticker: str, days: list[date]) -> list[dict[str, object]]:
    """A June ramp into the split, the carried halt and the resumed quote."""
    rows: list[dict[str, object]] = []
    ramp_end = date(2022, 6, 24)
    previous = 4.0 if ticker == "159901.SZ" else 2.384
    ramp = [day for day in days if day <= ramp_end]
    for day in days:
        if ticker == "159901.SZ":
            price = 4.32 if day >= _HALTED else 4.0
        elif day > ramp_end and day < _SPLIT:
            price = 2.384
        elif day < _SPLIT:
            # Linear 2.240 -> 2.384 ramp through 06-24.
            progress = ramp.index(day) / max(len(ramp) - 1, 1)
            price = round(2.240 + (2.384 - 2.240) * progress, 3)
        else:
            price = 0.6 if day in (_SPLIT, _HALTED) else 0.61
        halted = ticker == "159941.SZ" and day == _HALTED
        rows.append(
            {
                "source_ticker": ticker,
                "trade_date": day,
                "knowledge_date": day + timedelta(days=1),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                # The split session publishes the exact converted reference.
                "pre_close": 0.596
                if ticker == "159941.SZ" and day == _SPLIT
                else previous,
                "volume": 0.0 if halted else 1_000_000.0,
                "amount": 0.0 if halted else price * 100_000.0,
            }
        )
        previous = price
    return rows


def _seed() -> None:
    retain_empty_dividends(_PERIOD)
    pool = SQLitePool(
        str(Path(os.environ["DITTO_STATE_ROOT"]) / "metadata/metadata.sqlite")
    )
    client = SQLiteClient(pool)
    try:
        for iid, ticker, exchange, listed in _ETFS:
            InstrumentWriter(client=client, cache=None).register(
                iid,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker[:6],
                    name="ETF折算固定样例",
                    exchange=exchange,
                    asset_class="etf",
                    list_date=listed,
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe("etf_share_conversions_fixture", "ETF折算固定样例")
        universe.add_constituents(
            "etf_share_conversions_fixture",
            [
                {
                    "instrument_id": iid,
                    "effective_from": _WINDOW[0],
                    "source": "synthetic",
                }
                for iid, _, _, _ in _ETFS
            ],
        )
    finally:
        pool.close_all()
    calendar = pl.date_range(date(2022, 5, 1), date(2022, 8, 31), eager=True)
    retain_history_payload(
        "calendar",
        pl.DataFrame({"trade_date": calendar}).with_columns(
            (pl.col("trade_date").dt.weekday() <= 5).alias("is_open")
        ),
        period=("2022-05-01", "2022-08-31"),
    )
    days = [day for day in calendar if day.weekday() < 5]
    etfs = pl.DataFrame(
        [row for _, ticker, _, _ in _ETFS for row in _etf_price(ticker, days)]
    )
    retain_history_payload("etf_daily", etfs, period=_PERIOD)
    retain_history_payload(
        "index_daily",
        pl.DataFrame(_etf_price("000300.SH", days)).with_columns(
            pl.lit(4.0).alias("close"),
            pl.lit(4.0).alias("open"),
            pl.lit(4.0).alias("high"),
            pl.lit(4.0).alias("low"),
            pl.lit(4.0).alias("pre_close"),
        ),
        period=_PERIOD,
    )
    retain_history_payload(
        "fund_adj",
        etfs.select("source_ticker", "trade_date", "knowledge_date").with_columns(
            pl.when(
                (pl.col("source_ticker") == "159941.SZ")
                & (pl.col("trade_date") >= _SPLIT)
            )
            .then(4.0)
            .otherwise(1.0)
            .alias("adj_factor")
        ),
        period=_PERIOD,
    )
    today = datetime.now().astimezone().date().isoformat()
    retain_history_payload(
        "etf_reference", _reference(), period=(today, today), source="config"
    )
    container = make_app_container()
    try:
        record = container.get(StrategyCatalogService).get_spec(
            "seed_etf_industry_rotation", 1
        )
        assert record is not None
        spec = {
            **record.spec_json,
            "strategy_id": "etf_share_conversions_fixture",
            "name": "ETF折算固定样例",
            "universe": "etf_share_conversions_fixture",
            "signal_expressions": ["momentum_1m"],
            "signal_weights": [1.0],
        }
        spec["selector"] = {**spec["selector"], "params": {"k": 1}}
        spec["params"] = {**spec["params"], "top_k": 1, "rebalance_freq": "daily"}
        # 0.30 weight keeps every post-conversion order inside the dated
        # 1,000,000-unit ceiling while still exercising a full position cycle.
        spec["constraints"] = [
            {"type": "max_weight_per_instrument", "params": {"max_weight": 0.3}},
            {"type": "max_turnover", "params": {"max_turnover": 1.0}},
        ]
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
                strategy_id="etf_share_conversions_fixture",
                name=spec["name"],
                spec_json=spec,
            )
        )
        PublishStrategyHandler(governance).handle(
            PublishStrategyCommand(
                strategy_id="etf_share_conversions_fixture", version=1
            )
        )
    finally:
        container.close()


_seed()


@app.post("/system-fixture/share-conversions/repair")
def repair_share_conversions() -> dict[str, bool]:
    """Retain the maintainer declaration the same way ingestion would."""
    today = datetime.now().astimezone().date().isoformat()
    retain_history_payload(
        "etf_share_conversions",
        _declared_conversions(),
        period=(today, today),
        source="config",
    )
    return {"repaired": True}
