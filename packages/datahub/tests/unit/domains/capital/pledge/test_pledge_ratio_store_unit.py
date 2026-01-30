"""Unit tests for PledgeRatioStore."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.capital.pledge.pledge_ratio_store import (
    PledgeRatioStore,
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
        CREATE TABLE IF NOT EXISTS pledge_ratio (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            pledge_ratio REAL,
            pledge_shares REAL,
            total_shares REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
    """)
    client.commit()
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> PledgeRatioStore:
    """创建 PledgeRatioStore 实例."""
    return PledgeRatioStore(in_memory_db)


def test_write_pledge_ratio(store: PledgeRatioStore) -> None:
    """测试写入股权质押数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [0.15],
            "pledge_shares": [100000000.0],
            "total_shares": [1000000000.0],
        }
    )

    count = store.write(df)
    assert count == 1


def test_get_pledge_ratio_pit(store: PledgeRatioStore) -> None:
    """测试 PIT 查询股权质押."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [0.15],
            "pledge_shares": [100000000.0],
            "total_shares": [1000000000.0],
        }
    )
    store.write(df)

    result = store.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 1
    assert result["pledge_ratio"][0] == 0.15
    assert result["pledge_shares"][0] == 100000000.0
