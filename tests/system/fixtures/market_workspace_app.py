"""Market workspace journey fixture: post-market observation over isolated real state.

The production app runs without mocks. Deterministic metadata, retained
calendar/price payloads, ETF NAV rows, and a calendar ingestion success log are
seeded so the post-market journey (observation anchor -> watchlist quotes ->
anchored instrument chart -> back) can be accepted through the real UI and API.
"""

from __future__ import annotations

import importlib
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.runtime.ingestion.ingestion_log_reader import IngestionLogReader
from ditto_data.storage.runtime.ingestion.ingestion_log_writer import IngestionLogWriter
from ditto_platform.foundation import (
    OnDuplicate,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)

from tests.system.fixtures.retained_payload import retain_fixture_payload

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("market workspace fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("market workspace fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

STOCK_ID = 4_000_001
STOCK_NAME = "盘后样本股"
ETF_ID = 4_100_001
ETF_NAME = "盘后样本ETF"
DELISTED_ID = 4_000_002
DELISTED_NAME = "盘后退市样本"

# 固定最近完整交易日 2026-11-10（周二）。价格/日历证据自锚点日前一整年
# （2025-11-10，周一）起全覆盖，使观察日锚定的图表窗口（锚点-1 年 →
# 锚点）没有前置缺失交易日；锚点早于任何真实运行时刻，之后不再延伸。
ANCHOR_DATE = date(2026, 11, 10)
FIRST_TRADE_DATE = date(2025, 11, 10)
_TRADING_DAYS: list[date] = []
_cursor = FIRST_TRADE_DATE
while _cursor <= ANCHOR_DATE:
    if _cursor.weekday() < 5:
        _TRADING_DAYS.append(_cursor)
    _cursor += timedelta(days=1)


def _bars_frame(instrument_id: int, base: float) -> pl.DataFrame:
    rows = []
    previous_close = base
    for index, day in enumerate(_TRADING_DAYS):
        close = round(base + ((index * 7) % 11) * 0.4 + index * 0.15, 2)
        open_ = round(previous_close + (close - previous_close) * 0.4, 2)
        high = round(max(open_, close) + 0.9, 2)
        low = round(min(open_, close) - 0.8, 2)
        volume = (
            6_000 + ((index * 29) % 19) * 300 + (200 if close >= previous_close else 0)
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
                "turnover_rate": round((volume % 700) / 10_000, 4),
            }
        )
        previous_close = close
    return pl.DataFrame(rows)


def _seed(root: Path) -> None:
    create_fresh_runtime(root / "state")
    pool = SQLitePool(str(root / "state/metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    writer = InstrumentWriter(client=client, cache=None)
    writer.register(
        STOCK_ID,
        InstrumentRegistration(
            source_ticker="600779.SH",
            ticker="600779",
            name=STOCK_NAME,
            exchange="SSE",
            asset_class="stock",
            list_date="2001-02-26",
        ),
    )
    writer.register(
        ETF_ID,
        InstrumentRegistration(
            source_ticker="510888.SH",
            ticker="510888",
            name=ETF_NAME,
            exchange="SSE",
            asset_class="etf",
            list_date="2013-03-25",
        ),
    )
    # 退市样本：保留在目录中且本地行情库无可见日 K（行情不可得的诚实路径）。
    writer.register(
        DELISTED_ID,
        InstrumentRegistration(
            source_ticker="600780.SH",
            ticker="600780",
            name=DELISTED_NAME,
            exchange="SSE",
            asset_class="stock",
            list_date="2001-03-12",
            delist_date="2026-06-30",
        ),
    )

    # 行情证据走与生产一致的 retained payload 链（etf_daily/stock_daily）。
    stock_ticker = "600779.SH"
    etf_ticker = "510888.SH"
    for dataset, frame, ticker in (
        ("stock_daily", _bars_frame(STOCK_ID, 60.0), stock_ticker),
        ("etf_daily", _bars_frame(ETF_ID, 3.5), etf_ticker),
    ):
        payload = frame.with_columns(
            pl.lit(ticker).alias("source_ticker"),
            pl.col("trade_date").alias("event_time"),
        )
        retain_fixture_payload(
            client,
            root / "state",
            dataset_id=dataset,
            source="tushare",
            payload=payload,
            created_at=datetime(2026, 11, 10, 15, 30, tzinfo=UTC),
        )

    # ETF 净值走本地净值库（披露口径），覆盖至锚点日：价格与净值各自日期可见。
    disclosed_store = ParquetStore(
        root / "state",
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    nav_rows = [
        {
            "instrument_id": ETF_ID,
            "trade_date": day.isoformat(),
            "unit_nav": round(3.4 + ((index * 13) % 17) * 0.015, 4),
        }
        for index, day in enumerate(_TRADING_DAYS)
    ]
    disclosed_store.write(
        "market/etf/nav",
        pl.DataFrame(nav_rows).with_columns(
            pl.col("trade_date").str.to_date(),
            pl.lit(None, dtype=pl.Date).alias("knowledge_date"),
        ),
        OnDuplicate.ERROR.value,
        year=2026,
    )

    # 日历：自然日全覆盖（周末闭市）至锚点日，与生产 trade_cal 形状一致；
    # 起点前移两周，为图表窗口的日历权威留出边界余量。
    calendar_days: list[str] = []
    calendar_open: list[bool] = []
    open_days = {day.isoformat() for day in _TRADING_DAYS}
    day_cursor = _TRADING_DAYS[0] - timedelta(days=14)
    while day_cursor <= ANCHOR_DATE:
        calendar_days.append(day_cursor.isoformat())
        calendar_open.append(day_cursor.isoformat() in open_days)
        day_cursor += timedelta(days=1)
    retain_fixture_payload(
        client,
        root / "state",
        dataset_id="calendar",
        source="recorded",
        payload=pl.DataFrame({"trade_date": calendar_days, "is_open": calendar_open}),
        created_at=datetime(2026, 11, 10, 15, 30, tzinfo=UTC),
    )
    client.executemany(
        "INSERT OR IGNORE INTO trading_calendar (trade_date, is_open) VALUES (?, 1)",
        [[day] for day in sorted(open_days)],
    )
    # 最近完整交易日的摄取证据：calendar 数据集在锚点日成功摄取，
    # /api/v1/ingestion/status 以真实结果报告 latest_date/latest_status。
    # 状态读取按默认 source（tushare）查询日志，证据行使用同一 source。
    log_store = IngestionLogStore(
        IngestionLogReader(client), IngestionLogWriter(client)
    )
    log_store.save_log(
        IngestionLog(
            dataset="calendar",
            source="tushare",
            trade_date=ANCHOR_DATE.isoformat(),
            status=IngestionStatus.SUCCESS,
            checksum=f"fixture:calendar:{ANCHOR_DATE.isoformat()}",
            rows=len(calendar_days),
            first_attempt_at="2026-11-10T15:30:00Z",
            last_attempt_at="2026-11-10T15:30:00Z",
        )
    )
    client.commit()
    pool.close_all()


_seed(_root)

app = importlib.import_module("ditto_apps.main").app
