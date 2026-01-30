"""Unit tests for FundamentalStore."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> FundamentalStore:
    """创建 FundamentalStore 实例."""
    return FundamentalStore(sqlite_client=in_memory_db)


def test_fundamental_store_init(store: FundamentalStore) -> None:
    """测试 FundamentalStore 初始化."""
    assert store is not None
    assert store._client is not None


@pytest.fixture
def balance_sheet_table(in_memory_db: SQLiteClient) -> None:
    """创建 balance_sheet 表."""
    in_memory_db.execute("""
        CREATE TABLE IF NOT EXISTS balance_sheet (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            total_assets REAL,
            total_liabilities REAL,
            net_assets REAL,
            current_assets REAL,
            current_liabilities REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
    """)
    in_memory_db.commit()


def test_write_balance_sheet(
    balance_sheet_table: None, store: FundamentalStore
) -> None:
    """测试写入资产负债表数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [500000.0],
            "net_assets": [500000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )

    count = store.write_balance_sheet(df)
    assert count == 1


def test_get_balance_sheet_pit(
    balance_sheet_table: None, store: FundamentalStore
) -> None:
    """测试 PIT 查询资产负债表."""
    # 先写入数据
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [500000.0],
            "net_assets": [500000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )
    store.write_balance_sheet(df)

    # 查询
    result = store.get_balance_sheet("600000.SH", date(2024, 5, 1))
    assert len(result) == 1
    assert result["total_assets"][0] == 1000000.0
