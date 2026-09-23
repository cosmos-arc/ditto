"""Production app over a seeded isolated market store; no mocks inside the app."""

from __future__ import annotations

import importlib
import os
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_platform.foundation import (
    OnDuplicate,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("instrument chart fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("instrument chart fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

ETF_ID = 2_000_001
ETF_NO_NAV_ID = 2_000_002
ETF_CROSS_BORDER_ID = 2_000_003
STOCK_ID = 1_000_001
# 固定日历：2026-01-05 起 95 个交易日（跳过周末），索引 40–45 挖空演示断口。
_TRADING_DAYS: list[date] = []
_cursor = date(2026, 1, 5)
while len(_TRADING_DAYS) < 95:
    if _cursor.weekday() < 5:
        _TRADING_DAYS.append(_cursor)
    _cursor += timedelta(days=1)


def _bars_frame(instrument_id: int, base: float) -> pl.DataFrame:
    rows = []
    previous_close = base
    for index, day in enumerate(_TRADING_DAYS):
        # 索引 40–45 的交易日整体缺席（API Bar 合同不携带 null OHLC，
        # partial 以日历缺口表达）。
        if 40 <= index <= 45:
            continue
        close = round(base + ((index * 13) % 17) * 0.35 + index * 0.2, 2)
        open_ = round(previous_close + (close - previous_close) * 0.3, 2)
        high = round(max(open_, close) + 1.2, 2)
        low = round(min(open_, close) - 1.1, 2)
        volume = (
            8_000 + ((index * 37) % 23) * 400 + (300 if close >= previous_close else 0)
        )
        rows.append(
            {
                "instrument_id": instrument_id,
                "trade_date": day.isoformat(),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "pre_close": previous_close,
                "volume": volume,
                "amount": round(volume * close, 2),
                "turnover_rate": round((volume % 900) / 10_000, 4),
            }
        )
        previous_close = close
    return pl.DataFrame(rows)


def _adj_frame(instrument_id: int) -> pl.DataFrame:
    # 2026-03-02 起因子 1.0 → 1.05：qfq 会把此前的价格整体下修 ~4.76%。
    rows = []
    for day in _TRADING_DAYS:
        factor = 1.05 if day >= date(2026, 3, 2) else 1.0
        rows.append(
            {
                "instrument_id": instrument_id,
                "trade_date": day.isoformat(),
                "adj_factor": factor,
                "knowledge_date": day.isoformat(),
            }
        )
    return pl.DataFrame(rows)


def _seed(root: Path) -> None:
    create_fresh_runtime(root / "state")
    pool = SQLitePool(str(root / "state/metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    writer = InstrumentWriter(client=client, cache=None)
    writer.register(
        ETF_ID,
        InstrumentRegistration(
            source_ticker="510300.SH",
            ticker="510300",
            name="沪深300ETF-图表验收",
            exchange="SSE",
            asset_class="etf",
            list_date="2012-05-28",
        ),
    )
    writer.register(
        STOCK_ID,
        InstrumentRegistration(
            source_ticker="600519.SH",
            ticker="600519",
            name="贵州茅台-图表验收",
            exchange="SSE",
            asset_class="stock",
            list_date="2001-08-27",
        ),
    )
    writer.register(
        ETF_NO_NAV_ID,
        InstrumentRegistration(
            source_ticker="159915.SZ",
            ticker="159915",
            name="创业板ETF-无净值验收",
            exchange="SZSE",
            asset_class="etf",
            list_date="2011-12-09",
        ),
    )
    writer.register(
        ETF_CROSS_BORDER_ID,
        InstrumentRegistration(
            source_ticker="513100.SH",
            ticker="513100",
            name="跨境ETF-比较验收",
            exchange="SSE",
            asset_class="etf",
            list_date="2020-01-01",
        ),
    )
    reference = "snapshot:recorded:etf-system"
    rows = [
        (ETF_ID, "tracking_index", "000300.SH", "index", "2026-01-01"),
        (ETF_NO_NAV_ID, "tracking_index", "000300.SH", "index", "2026-01-01"),
        (ETF_CROSS_BORDER_ID, "tracking_index", "NDX", "index", "2026-01-01"),
        (ETF_ID, "management_fee", "0.5", "%/year", "2026-01-01"),
        (ETF_NO_NAV_ID, "management_fee", "0.2", "%/year", "2026-01-01"),
        (ETF_ID, "aum", "500000000", "CNY", "2026-05-20"),
        (ETF_CROSS_BORDER_ID, "price_close", "1.2", "CNY", "2026-05-20"),
        (ETF_CROSS_BORDER_ID, "nav", "1.1", "CNY", "2026-05-18"),
    ]
    client.executemany(
        """INSERT INTO etf_reference_observation
           (instrument_id, field, value, unit, observed_on, published_at,
            effective_from, source, source_snapshot_id)
           VALUES (?, ?, ?, ?, ?, '2026-05-21T09:00:00Z', ?,
                   'recorded', ?)""",
        [
            [instrument_id, field, value, unit, observed_on, observed_on, reference]
            for instrument_id, field, value, unit, observed_on in rows
        ],
    )
    client.commit()
    store = ParquetStore(
        root / "state",
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    store.write(
        "market/etf/bars",
        pl.concat(
            [_bars_frame(ETF_ID, base=4.0), _bars_frame(ETF_NO_NAV_ID, base=3.0)]
        ),
        OnDuplicate.ERROR.value,
        year=2026,
    )
    store.write(
        "market/stock/bars",
        _bars_frame(STOCK_ID, base=1500.0),
        OnDuplicate.ERROR.value,
        year=2026,
    )
    adj_store = ParquetStore(
        root / "state",
        key_columns=("instrument_id", "trade_date", "knowledge_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    adj_store.write(
        "market/stock/adj", _adj_frame(STOCK_ID), OnDuplicate.ERROR.value, year=2026
    )
    # 第一只 ETF 有净值(可得路径), 第二只不播净值(不可得降级路径)
    nav_rows = [
        {
            "instrument_id": ETF_ID,
            "trade_date": day.isoformat(),
            "nav": round(3.8 + ((index * 11) % 19) * 0.02, 4),
        }
        for index, day in enumerate(_TRADING_DAYS)
    ]
    store.write(
        "market/etf/nav",
        pl.DataFrame(nav_rows).with_columns(pl.col("trade_date").str.to_date()),
        OnDuplicate.ERROR.value,
        year=2026,
    )


_seed(_root)

app = importlib.import_module("ditto_apps.main").app
