"""真实写入、纠偏及资金消费者的时间资格回归 (#706)."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from ditto_application.queries.capital import CapitalQueryFacade
from ditto_apps.scripts.data_kd_stock_correction import apply_dataset, scan_dataset
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.capital import CapitalProvider
from ditto_data.observability.metrics import register_metrics
from ditto_data.services.capital_store import CapitalStore
from ditto_platform.foundation import FileLockManager, SQLiteClient, SQLitePool
from ditto_platform.foundation.storage.types import OnDuplicate


@pytest.mark.pit
def test_margin_correction_rejects_old_projection_after_restart(tmp_path: Path) -> None:
    register_metrics()
    pool = SQLitePool(str(tmp_path / "metadata.sqlite"))
    client = SQLiteClient(pool)
    client.conn.executescript("""
        CREATE TABLE trading_calendar (trade_date TEXT PRIMARY KEY, is_open BOOLEAN);
        INSERT INTO trading_calendar VALUES ('2024-09-30', 1), ('2024-10-08', 1);
        CREATE TABLE margin_trading (
            instrument_id INTEGER, trade_date TEXT, knowledge_date TEXT,
            effective_from TEXT, effective_to TEXT, margin_buy_balance REAL,
            short_sell_balance REAL, margin_buy_amount REAL, short_sell_volume REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from));
    """)
    settings = DataStoreSettings(data_root=tmp_path)
    provider = CapitalProvider()
    writers = provider.capital_writers(
        client, settings, FileLockManager(tmp_path / "locks")
    )

    store = CapitalStore(
        read_ports=provider.capital_readers(client, settings), write_ports=writers
    )
    store.save_margin_trading(
        pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 9, 30)],
                "knowledge_date": [date(2024, 10, 1)],
                "effective_from": [date(2024, 10, 1)],
                "effective_to": [None],
                "margin_buy_balance": [100.0],
            }
        )
    )
    for _ in range(2):
        apply_dataset(
            "margin_trading",
            scan_dataset("margin_trading", conn=client.conn, data_root=tmp_path),
            conn=client.conn,
            data_root=tmp_path,
            capital_store=store,
            log_store=MagicMock(),
            run_at=datetime(2026, 11, 7, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        reopened = SQLiteClient(SQLitePool(str(tmp_path / "metadata.sqlite")))
        facade = CapitalQueryFacade(
            capital_store=CapitalStore(
                read_ports=provider.capital_readers(reopened, settings),
                write_ports=writers,
            )
        )
        assert facade.get_margin_trading(
            1, date(2024, 10, 7), allow_experimental_data=True
        ).is_empty()
        visible = facade.get_margin_trading(
            1, date(2024, 10, 8), allow_experimental_data=True
        )
        assert visible["margin_buy_balance"].to_list() == [100.0]
    # 原错误投影未删除；显式证据重放与普通查询分开。
    assert client.conn.execute("SELECT COUNT(*) FROM margin_trading").fetchone()[0] == 2


def test_hsgt_correction_keeps_twenty_channel_facts(tmp_path: Path) -> None:
    register_metrics()
    client = SQLiteClient(SQLitePool(":memory:"))
    client.conn.executescript("""
        CREATE TABLE trading_calendar (trade_date TEXT PRIMARY KEY, is_open BOOLEAN);
        INSERT INTO trading_calendar VALUES ('2024-09-30', 1), ('2024-10-08', 1);
    """)
    settings = DataStoreSettings(data_root=tmp_path)
    provider = CapitalProvider()
    store = CapitalStore(
        read_ports=provider.capital_readers(client, settings),
        write_ports=provider.capital_writers(
            client, settings, FileLockManager(tmp_path / "locks")
        ),
    )
    frame = pl.DataFrame(
        {
            "instrument_id": list(range(1, 11)) * 2,
            "trade_date": [date(2024, 9, 30)] * 20,
            "knowledge_date": [date(2024, 10, 1)] * 20,
            "market_type": ["1"] * 10 + ["3"] * 10,
            "rank": list(range(1, 11)) * 2,
            "amount": [100.0] * 20,
            "buy": [None] * 20,
        }
    )
    store.save_hsgt_top10(frame, 2024)
    apply_dataset(
        "hsgt_top10",
        scan_dataset("hsgt_top10", conn=client.conn, data_root=tmp_path),
        conn=client.conn,
        data_root=tmp_path,
        capital_store=store,
        log_store=MagicMock(),
        run_at=datetime(2026, 11, 7, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    result = CapitalQueryFacade(capital_store=store).get_hsgt_top10s(
        "2024-09-30", "2024-09-30", allow_experimental_data=True
    )
    assert result.height == 20
    assert result["amount"].sum() == 2000.0
    assert result["buy"].null_count() == 20
    assert result["market_type"].n_unique() == 2
    client.conn.close()


def test_hk_official_different_value_survives_old_observation_anchor(
    tmp_path: Path,
) -> None:
    register_metrics()
    client = SQLiteClient(SQLitePool(":memory:"))
    client.conn.executescript("""
        CREATE TABLE trading_calendar (trade_date TEXT PRIMARY KEY, is_open BOOLEAN);
        CREATE TABLE provider_snapshots (
            dataset_id TEXT, source TEXT, row_count INTEGER,
            request_start TEXT, request_end TEXT, created_at TEXT);
    """)
    settings = DataStoreSettings(data_root=tmp_path)
    provider = CapitalProvider()
    store = CapitalStore(
        read_ports=provider.capital_readers(client, settings),
        write_ports=provider.capital_writers(
            client, settings, FileLockManager(tmp_path / "locks")
        ),
    )
    store.save_hk_hold(
        pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 9, 30)] * 2,
                "knowledge_date": [date(2026, 10, 14), date(2026, 11, 1)],
                "vol": [200.0, 100.0],
                "ratio": [None, None],
            }
        ),
        2026,
        OnDuplicate.KEEP_LAST,
    )
    for _ in range(2):
        apply_dataset(
            "hk_hold",
            scan_dataset("hk_hold", conn=client.conn, data_root=tmp_path),
            conn=client.conn,
            data_root=tmp_path,
            capital_store=store,
            log_store=MagicMock(),
            run_at=datetime(2026, 11, 7, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        result = CapitalQueryFacade(capital_store=store).get_hk_hold(
            1, "2026-09-30", "2026-09-30", allow_experimental_data=True
        )
        assert result["vol"].to_list() == [200.0]
    client.conn.close()
