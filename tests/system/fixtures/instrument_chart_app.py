"""Production app over a seeded isolated market store; no mocks inside the app."""

from __future__ import annotations

import importlib
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
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


def _seed_retained_charts(
    payload_store: FilesystemProviderPayloadStore,
    snapshot_store: SQLiteProviderSnapshotStore,
    license_store: SQLiteDatasetLicenseStore,
) -> None:
    # Chart candles and adjustment use the same retained provider evidence as
    # production, rather than the unversioned market read model above.
    for dataset, frames in (
        ("etf_daily", [_bars_frame(ETF_ID, 4.0), _bars_frame(ETF_NO_NAV_ID, 3.0)]),
        ("stock_daily", [_bars_frame(STOCK_ID, 1500.0)]),
        ("adj_factor", [_adj_frame(STOCK_ID)]),
    ):
        frame = pl.concat(frames).with_columns(
            pl.when(pl.col("instrument_id") == ETF_ID)
            .then(pl.lit("510300.SH"))
            .when(pl.col("instrument_id") == ETF_NO_NAV_ID)
            .then(pl.lit("159915.SZ"))
            .otherwise(pl.lit("600519.SH"))
            .alias("source_ticker"),
            pl.col("trade_date").alias("event_time"),
        )
        if dataset == "etf_daily":
            # Same trading date as a deliberate gap, but unknowable at the
            # browser decision cutoff. PIT must hide this extreme value.
            frame = pl.concat(
                [
                    frame,
                    pl.DataFrame(
                        {
                            "instrument_id": [ETF_ID],
                            "trade_date": ["2026-03-04"],
                            "event_time": ["2026-03-04"],
                            "source_ticker": ["510300.SH"],
                            "open": [999_999.0],
                            "high": [1_000_000.0],
                            "low": [999_998.0],
                            "close": [999_999.0],
                            "volume": [1.0],
                            "amount": [999_999.0],
                            "available_at": ["2099-01-01T00:00:00Z"],
                            "published_at": ["2099-01-01T00:00:00Z"],
                        }
                    ),
                ],
                how="diagonal_relaxed",
            )
        license_record = DatasetLicenseRecord.create(
            DatasetLicenseDraft(
                dataset_id=dataset,
                source="tushare",
                terms_version="isolated-test-v1",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                local_cache="allowed",
                derivative_compute="allowed",
                display="allowed",
                redistribution="prohibited",
                notes="isolated recorded acceptance data",
                reviewed_by="fixture",
                reviewed_at=datetime(2026, 5, 21, 9, tzinfo=UTC),
            )
        )
        license_store.append_license(license_record)
        artifact = payload_store.retain_payload(
            dataset_id=dataset, source="tushare", payload=frame
        )
        snapshot_store.append_snapshot(
            ProviderSnapshot.create(
                ProviderSnapshotDraft(
                    dataset_id=dataset,
                    source="tushare",
                    request_start=_TRADING_DAYS[0].isoformat(),
                    request_end=_TRADING_DAYS[-1].isoformat(),
                    schema_version=f"fixture.{dataset}.v1",
                    checksum=artifact.checksum,
                    canonical_asset=DataAssetRef(
                        dataset_id=dataset, namespace="market"
                    ),
                    request_parameters_hash=f"fixture:{dataset}:instrument-chart",
                    response_metadata=(("fixture", "instrument-chart"),),
                    license_record_id=license_record.record_id,
                    row_count=artifact.row_count,
                    payload_uri=artifact.uri,
                    payload_retained=True,
                    created_at=datetime(2026, 5, 21, 9, tzinfo=UTC),
                )
            )
        )


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
        (ETF_ID, "tracking_index", "000300.SH", "index", "2025-01-01"),
        (ETF_NO_NAV_ID, "tracking_index", "000300.SH", "index", "2025-01-01"),
        (ETF_CROSS_BORDER_ID, "tracking_index", "NDX", "index", "2025-01-01"),
        (ETF_ID, "asset_class", "A股宽基", "text", "2026-01-01"),
        (ETF_NO_NAV_ID, "asset_class", "A股宽基", "text", "2026-01-01"),
        (ETF_CROSS_BORDER_ID, "asset_class", "跨境股票", "text", "2026-01-01"),
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
    tracking_days: list[date] = []
    day = date(2026, 5, 20)
    while len(tracking_days) < 253:
        if day.weekday() < 5:
            tracking_days.append(day)
        day -= timedelta(days=1)
    tracking_days.reverse()
    client.executemany(
        "INSERT OR IGNORE INTO trading_calendar (trade_date, is_open) VALUES (?, 1)",
        [[day.isoformat()] for day in tracking_days],
    )
    client.executemany(
        """INSERT INTO etf_reference_observation
           (instrument_id, field, value, unit, observed_on, published_at,
            effective_from, source, source_snapshot_id)
           VALUES (?, ?, ?, ?, ?, '2026-05-21T09:00:00Z', ?, 'recorded', ?)""",
        [
            [
                ETF_ID,
                field,
                str(100 * 1.01**index),
                unit,
                day.isoformat(),
                day.isoformat(),
                reference,
            ]
            for index, day in enumerate(tracking_days)
            for field, unit in (
                ("nav_total_return", "CNY:nav_total_return"),
                ("benchmark_total_return", "CNY:index_total_return:000300.SH"),
            )
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
    payload_store = FilesystemProviderPayloadStore(root / "state")
    snapshot_store = SQLiteProviderSnapshotStore(client)
    _seed_retained_charts(
        payload_store, snapshot_store, SQLiteDatasetLicenseStore(client)
    )
    # ETF candidate comparison and chart use the same retained calendar.
    calendar_license = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id="calendar",
            source="recorded",
            terms_version="isolated-test-v1",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            local_cache="allowed",
            derivative_compute="allowed",
            display="allowed",
            redistribution="prohibited",
            notes="isolated recorded acceptance data",
            reviewed_by="fixture",
            reviewed_at=datetime(2026, 5, 21, 9, tzinfo=UTC),
        )
    )
    SQLiteDatasetLicenseStore(client).append_license(calendar_license)
    open_days = {day.isoformat() for day in tracking_days}
    # 页面默认研究日期是"今天"：把已排期交易日延伸到今天，日历才覆盖研究日。
    cursor = tracking_days[-1] + timedelta(days=1)
    while cursor <= date.today():
        if cursor.weekday() < 5:
            open_days.add(cursor.isoformat())
        cursor += timedelta(days=1)
    # 与生产 trade_cal 一致，payload 覆盖区间内每个自然日（周末为闭市行）。
    calendar_days: list[str] = []
    calendar_open: list[bool] = []
    day_cursor = tracking_days[0]
    while day_cursor <= date.today():
        calendar_days.append(day_cursor.isoformat())
        calendar_open.append(day_cursor.isoformat() in open_days)
        day_cursor += timedelta(days=1)
    artifact = payload_store.retain_payload(
        dataset_id="calendar",
        source="recorded",
        payload=pl.DataFrame({"trade_date": calendar_days, "is_open": calendar_open}),
    )
    snapshot_store.append_snapshot(
        ProviderSnapshot.create(
            ProviderSnapshotDraft(
                dataset_id="calendar",
                source="recorded",
                request_start=calendar_days[0],
                request_end=calendar_days[-1],
                schema_version="fixture.calendar.v1",
                checksum=artifact.checksum,
                canonical_asset=DataAssetRef(dataset_id="calendar", namespace="market"),
                request_parameters_hash="fixture:calendar:tracking-window",
                response_metadata=(("fixture", "instrument-chart"),),
                license_record_id=calendar_license.record_id,
                row_count=artifact.row_count,
                payload_uri=artifact.uri,
                payload_retained=True,
                created_at=datetime(2026, 5, 21, 9, tzinfo=UTC),
            )
        )
    )
    client.commit()
    pool.close_all()


_seed(_root)

app = importlib.import_module("ditto_apps.main").app
