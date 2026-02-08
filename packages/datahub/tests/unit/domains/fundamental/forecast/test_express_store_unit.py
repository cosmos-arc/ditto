"""Unit tests for ExpressStore."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.stores.fundamental.forecast.express_store import ExpressStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS express (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            type TEXT,
            profit_range_min REAL,
            profit_range_max REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
    """)
    client.commit()
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> ExpressStore:
    """创建 ExpressStore 实例."""
    return ExpressStore(in_memory_db)


def test_write_express(store: ExpressStore) -> None:
    """测试写入业绩快报数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 10)],
            "effective_from": [date(2024, 4, 11)],
            "effective_to": [None],
            "type": ["预增"],
            "profit_range_min": [1500000.0],
            "profit_range_max": [1700000.0],
        }
    )

    count = store.write(df)
    assert count == 1


def test_get_express_pit(store: ExpressStore) -> None:
    """测试 PIT 查询业绩快报."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 10)],
            "effective_from": [date(2024, 4, 11)],
            "effective_to": [None],
            "type": ["预增"],
            "profit_range_min": [1500000.0],
            "profit_range_max": [1700000.0],
        }
    )
    store.write(df)

    result = store.get("600000.SH", date(2024, 4, 15))
    assert len(result) == 1
    assert result["type"][0] == "预增"
