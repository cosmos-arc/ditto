"""Unit tests for FuturesReader."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.stores.capital.futures_position.futures_reader import (
    FuturesReader,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute(
        """CREATE TABLE IF NOT EXISTS futures (
        instrument_id TEXT NOT NULL,
        trade_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        open_interest REAL,
        settlement_price REAL,
        volume REAL,
        turnover REAL,
        PRIMARY KEY (instrument_id, trade_date, effective_from)
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def reader(in_memory_db: SQLiteClient) -> FuturesReader:
    """创建 FuturesReader 实例."""
    return FuturesReader(client=in_memory_db)


def test_get_returns_data(reader: FuturesReader, in_memory_db: SQLiteClient) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            None,
            100000.0,
            3500.0,
            50000.0,
            175000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("IF2412", date(2024, 1, 5))
    assert len(result) == 1
    assert result["open_interest"][0] == 100000.0


def test_get_empty_table(reader: FuturesReader) -> None:
    """测试空表返回空 DataFrame."""
    result = reader.get("IF2412", date(2024, 1, 5))
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_no_data(reader: FuturesReader, in_memory_db: SQLiteClient) -> None:
    """测试查询不存在的证券返回空 DataFrame."""
    # 插入其他期货的数据
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IH2412",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            None,
            80000.0,
            2800.0,
            30000.0,
            84000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("IF2412", date(2024, 1, 5))
    assert len(result) == 0


def test_get_pit_query(reader: FuturesReader, in_memory_db: SQLiteClient) -> None:
    """测试 PIT 查询返回有效数据."""
    # 插入多个版本
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 10),
            100000.0,
            3500.0,
            50000.0,
            175000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 2),
            date(2024, 1, 11),
            date(2024, 1, 12),
            None,
            110000.0,
            3550.0,
            55000.0,
            195250000.0,
        ],
    )
    in_memory_db.commit()

    # 查询第一个版本有效期间的数据
    result = reader.get("IF2412", date(2024, 1, 5))
    assert len(result) == 1
    assert result["open_interest"][0] == 100000.0


def test_get_pit_query_excludes_expired_version(
    reader: FuturesReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询排除已过期版本."""
    # 插入已过期的版本
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 10),
            100000.0,
            3500.0,
            50000.0,
            175000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询过期后的日期
    result = reader.get("IF2412", date(2024, 1, 15))
    assert len(result) == 0


def test_get_ordering_by_trade_date(
    reader: FuturesReader, in_memory_db: SQLiteClient
) -> None:
    """测试结果按 trade_date 降序排列."""
    # 插入多条记录
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 5),
            date(2024, 1, 5),
            date(2024, 1, 6),
            None,
            100000.0,
            3500.0,
            50000.0,
            175000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 10),
            date(2024, 1, 10),
            date(2024, 1, 11),
            None,
            110000.0,
            3600.0,
            55000.0,
            198000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "IF2412",
            date(2024, 1, 3),
            date(2024, 1, 3),
            date(2024, 1, 4),
            None,
            90000.0,
            3400.0,
            45000.0,
            153000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("IF2412", date(2024, 1, 15))
    assert len(result) == 3
    # 验证降序排列（polars 从原始行构造时返回日期字符串）
    assert result["trade_date"][0] == "2024-01-10"
    assert result["trade_date"][1] == "2024-01-05"
    assert result["trade_date"][2] == "2024-01-03"


def test_get_handles_null_values(
    reader: FuturesReader, in_memory_db: SQLiteClient
) -> None:
    """测试处理空值."""
    in_memory_db.execute(
        """INSERT INTO futures
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         open_interest, settlement_price, volume, turnover)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
        ["IF2412", date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3), None],
    )
    in_memory_db.commit()

    result = reader.get("IF2412", date(2024, 1, 5))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["open_interest"][0] is None
