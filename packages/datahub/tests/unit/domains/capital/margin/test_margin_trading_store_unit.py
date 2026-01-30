"""Unit tests for MarginTradingStore."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.capital.margin.margin_trading_store import (
    MarginTradingStore,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS margin_trading (
            instrument_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            margin_buy_balance REAL,
            short_sell_balance REAL,
            margin_buy_volume REAL,
            short_sell_volume REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
    """)
    client.commit()
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> MarginTradingStore:
    """创建 MarginTradingStore 实例."""
    return MarginTradingStore(in_memory_db)


def test_write_margin_trading(store: MarginTradingStore) -> None:
    """测试写入融资融券数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 5, 15)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "margin_buy_balance": [1000000.0],
            "short_sell_balance": [500000.0],
            "margin_buy_volume": [50000000.0],
            "short_sell_volume": [20000000.0],
        }
    )

    count = store.write(df)
    assert count == 1


def test_get_margin_trading_pit(store: MarginTradingStore) -> None:
    """测试 PIT 查询融资融券."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 5, 15)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "margin_buy_balance": [1000000.0],
            "short_sell_balance": [500000.0],
            "margin_buy_volume": [50000000.0],
            "short_sell_volume": [20000000.0],
        }
    )
    store.write(df)

    result = store.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 1
    assert result["margin_buy_balance"][0] == 1000000.0
    assert result["short_sell_balance"][0] == 500000.0
