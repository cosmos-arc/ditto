"""Visual screener journey fixture: conditions and factor weights (#740).

The production app runs without mocks. Deterministic instrument registry,
a whole-market universe, retained stock_daily/adj_factor/status/basic and
calendar evidence with completed partition lifecycle are seeded so the
visual screening journey (catalog -> conditions -> weights -> saved fixed
run -> replay same identity -> exclusion reasons) can be accepted through
the real UI, real API and real persistence.
"""

from __future__ import annotations

import importlib
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    schema_fingerprint,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_data.storage.metadata.universe.universe_writer import UniverseWriter
from ditto_platform.foundation import (
    DataCache,
    OnDuplicate,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("selection screener fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("selection screener fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

# 固定最近完整交易日 2026-11-10（周二）；证据自 2026-08-03 起覆盖
# （约 70 个交易日，满足 20 日动量窗口与 20 日均额窗口）。
ANCHOR_DATE = date(2026, 11, 10)
FIRST_TRADE_DATE = date(2026, 8, 3)
UNIVERSE_ID = "screener-fixture-market"
UNIVERSE_NAME = "筛选固定样例全市场"

# 三只样本股以 20 日动量严格分层：A 强动量、B 居中、C 下跌。
STOCKS: tuple[tuple[int, str, str, float], ...] = (
    (1_420_001, "600791.SH", "筛选样本A", 10.0),  # 上涨趋势
    (1_420_002, "600792.SH", "筛选样本B", 10.0),  # 温和
    (1_420_003, "600793.SH", "筛选样本C", 10.0),  # 下跌趋势
)

_TRADING_DAYS: list[date] = []
_cursor = FIRST_TRADE_DATE
while _cursor <= ANCHOR_DATE:
    if _cursor.weekday() < 5:
        _TRADING_DAYS.append(_cursor)
    _cursor += timedelta(days=1)


def _close_series(index: int, base: float) -> list[float]:
    """Deterministic per-stock closes with clearly separated 20d momentum."""
    closes: list[float] = []
    previous = base
    for _ in range(len(_TRADING_DAYS)):
        if index == 0:  # A: 每交易日 +0.7%（约 20 日 +15%）
            close = round(previous * 1.007, 4)
        elif index == 1:  # B: 每交易日 +0.1%（约 20 日 +2%）
            close = round(previous * 1.001, 4)
        else:  # C: 每交易日 -0.6%（约 20 日 -11%）
            close = round(previous * 0.994, 4)
        closes.append(close)
        previous = close
    return closes


def _bars_frame() -> pl.DataFrame:
    records: list[dict[str, object]] = []
    for stock_index, (instrument_id, ticker, _name, base) in enumerate(STOCKS):
        closes = _close_series(stock_index, base)
        previous_close = base
        for day, close in zip(_TRADING_DAYS, closes, strict=True):
            open_ = round((previous_close + close) / 2, 4)
            high = round(max(open_, close) * 1.004, 4)  # 不贴收盘极值：避免涨跌停分类
            low = round(min(open_, close) * 0.996, 4)
            volume = 1_000_000.0
            records.append(
                {
                    "instrument_id": instrument_id,
                    "source_ticker": ticker,
                    "trade_date": day.isoformat(),
                    "knowledge_date": day.isoformat(),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "pre_close": previous_close,
                    "volume": volume,
                    "amount": round(volume * close / 1000.0, 2),  # 千元单位（万元存储）
                    "source": "tushare",
                }
            )
            previous_close = close
    return pl.DataFrame(records)


def _retain(dataset: str, frame: pl.DataFrame) -> None:
    """Retain payload + snapshot + completed partition lifecycle."""
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    try:
        now = datetime(2026, 11, 10, 15, 30, tzinfo=UTC)
        dates = frame.get_column("trade_date").cast(pl.String).to_list()
        payload = FilesystemProviderPayloadStore(_state).retain_payload(
            dataset_id=dataset, source="tushare", payload=frame
        )
        snapshot = ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id=dataset,
                source="tushare",
                request_start=min(dates),
                request_end=max(dates),
                schema_version=f"fixture.{dataset}.v1",
                checksum=payload.checksum,
                canonical_asset=DataAssetRef(dataset, "market"),
                request_parameters_hash=f"fixture:{dataset}:screener",
                response_metadata=(("fixture", "screener-isolated"),),
                row_count=frame.height,
                payload_uri=payload.uri,
                payload_retained=True,
                created_at=now,
                schema_fingerprint=schema_fingerprint(frame),
            )
        )
        snapshots = SQLiteProviderSnapshotStore(client)
        if snapshots.get_snapshot(snapshot.snapshot_id) is None:
            snapshots.append_snapshot(snapshot)
            lifecycle = SQLitePartitionLifecycleStore(client)
            lifecycle.plan_partition(
                PartitionCheckpoint(
                    chunk_id=snapshot.snapshot_id,
                    dataset_id=dataset,
                    source="tushare",
                    request_start=min(dates),
                    request_end=max(dates),
                    status=PartitionLifecycleStatus.PLANNED,
                    payload_id=None,
                    complete_evidence_id=None,
                    error_code=None,
                    updated_at=now,
                )
            )
            lifecycle.advance_partition(
                snapshot.snapshot_id,
                PartitionLifecycleStatus.PAYLOAD_COMMITTED,
                occurred_at=now,
                # 完成匹配要求 payload 证据钉住精确快照身份：
                # payload:{checksum}:{snapshot_id}。
                evidence_id=f"payload:{snapshot.checksum}:{snapshot.snapshot_id}",
            )
            lifecycle.advance_partition(
                snapshot.snapshot_id,
                PartitionLifecycleStatus.COMPLETE,
                occurred_at=now,
                evidence_id=snapshot.snapshot_id,
            )
    finally:
        pool.close_all()


def _seed() -> None:
    create_fresh_runtime(_state)
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    try:
        writer = InstrumentWriter(client=client, cache=None)
        for instrument_id, ticker, name, _base in STOCKS:
            writer.register(
                instrument_id,
                InstrumentRegistration(
                    source_ticker=ticker,
                    ticker=ticker.partition(".")[0],
                    name=name,
                    exchange="SSE",
                    asset_class="stock",
                    list_date="2015-03-10",
                ),
            )
        universe = UniverseWriter(client, DataCache())
        universe.create_universe(UNIVERSE_ID, UNIVERSE_NAME)
        universe.add_constituents(
            UNIVERSE_ID,
            [
                {
                    "instrument_id": instrument_id,
                    "effective_from": "2026-08-01",
                    "source": "synthetic",
                }
                for instrument_id, *_ in STOCKS
            ],
        )
        insert_calendar = (
            "INSERT OR IGNORE INTO trading_calendar (trade_date, is_open) VALUES (?, 1)"
        )
        client.executemany(
            insert_calendar,
            [[day.isoformat()] for day in sorted(_TRADING_DAYS)],
        )
        client.commit()
    finally:
        pool.close_all()

    bars = _bars_frame()
    tickers = [ticker for _iid, ticker, _n, _b in STOCKS]
    # Live 读模型（ServiceBackedDataProvider）读本地行情 parquet；catalog
    # payload 只承担 lineage/attestation。两条链写同一份事实。
    market_store = ParquetStore(
        _state,
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    parquet_bars = bars.select(
        "instrument_id",
        pl.col("trade_date").str.to_date().alias("trade_date"),
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        pl.col("knowledge_date").str.to_date().alias("knowledge_date"),
        "source_ticker",
        "source",
    )
    market_store.write(
        "market/stock/bars", parquet_bars, OnDuplicate.ERROR.value, year=2026
    )
    market_store.write(
        "market/stock/adj",
        parquet_bars.select(
            "instrument_id",
            "trade_date",
            "knowledge_date",
            "source_ticker",
        ).with_columns(
            pl.lit(1.0).alias("adj_factor"),
            pl.lit("tushare").alias("source"),
        ),
        OnDuplicate.ERROR.value,
        year=2026,
    )
    _retain("stock_daily", bars)
    _retain(
        "adj_factor",
        bars.select("source_ticker", "trade_date").with_columns(
            pl.col("trade_date").alias("knowledge_date"),
            pl.lit(1.0).alias("adj_factor"),
        ),
    )
    _retain(
        "stock_status",
        bars.select("source_ticker", "trade_date").with_columns(
            pl.lit(False).alias("is_suspended"),
            pl.lit("").alias("suspend_timing"),
            pl.lit(False).alias("is_st"),
            pl.lit(None, dtype=pl.String).alias("st_type"),
            pl.lit("L").alias("list_status"),
        ),
    )
    _retain(
        "stock_basic",
        pl.DataFrame(
            {
                "source_ticker": tickers,
                "name": [name for _iid, _t, name, _b in STOCKS],
                "exchange": ["SSE"] * len(tickers),
                "list_date": ["2015-03-10"] * len(tickers),
                "delist_date": [None] * len(tickers),
                "list_status": ["L"] * len(tickers),
            }
        ).with_columns(
            pl.lit(ANCHOR_DATE.isoformat()).alias("trade_date"),
        ),
    )
    # 日历快照：自然日全覆盖（周末闭市），覆盖全部交易日。
    calendar_days: list[str] = []
    calendar_open: list[bool] = []
    open_days = {day.isoformat() for day in _TRADING_DAYS}
    cursor = FIRST_TRADE_DATE - timedelta(days=14)
    while cursor <= ANCHOR_DATE:
        calendar_days.append(cursor.isoformat())
        calendar_open.append(cursor.isoformat() in open_days)
        cursor += timedelta(days=1)
    _retain(
        "calendar",
        pl.DataFrame({"trade_date": calendar_days, "is_open": calendar_open}),
    )


_seed()

app = importlib.import_module("ditto_apps.main").app
