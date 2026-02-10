"""Unit tests for FuturesWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.stores.capital.futures.futures_writer import FuturesWriter
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


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
def writer(in_memory_db: SQLiteClient) -> FuturesWriter:
    """创建 FuturesWriter 实例."""
    return FuturesWriter(client=in_memory_db)


def test_write_success(writer: FuturesWriter) -> None:
    """测试成功写入."""
    df = pl.DataFrame(
        {
            "instrument_id": ["IF2412"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "open_interest": [100000.0],
            "settlement_price": [3500.0],
            "volume": [50000.0],
            "turnover": [175000000.0],
        }
    )

    count = writer.write(df)
    assert count == 1


def test_write_returns_count(writer: FuturesWriter) -> None:
    """测试写入返回记录数."""
    df = pl.DataFrame(
        {
            "instrument_id": ["IF2412", "IH2412"],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, None],
            "open_interest": [100000.0, 80000.0],
            "settlement_price": [3500.0, 2800.0],
            "volume": [50000.0, 30000.0],
            "turnover": [175000000.0, 84000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2


def test_write_empty_dataframe(writer: FuturesWriter) -> None:
    """测试写入空 DataFrame."""
    df = pl.DataFrame(
        schema={
            "instrument_id": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "open_interest": pl.Float64,
            "settlement_price": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
        }
    )

    count = writer.write(df)
    assert count == 0


def test_write_with_nullable_effective_date(
    writer: FuturesWriter, in_memory_db: SQLiteClient
) -> None:
    """测试写入包含 nullable effective_to 的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["IF2412", "IH2412"],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, date(2024, 1, 15)],
            "open_interest": [100000.0, 80000.0],
            "settlement_price": [3500.0, 2800.0],
            "volume": [50000.0, 30000.0],
            "turnover": [175000000.0, 84000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2

    # 验证数据写入正确
    rows = in_memory_db.fetchall("SELECT * FROM futures")
    assert len(rows) == 2


def test_write_failure_rollback(writer: FuturesWriter) -> None:
    """测试写入失败时回滚."""
    # 创建有效的测试数据
    test_df = pl.DataFrame(
        {
            "instrument_id": ["IF2412"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "open_interest": [100000.0],
            "settlement_price": [3500.0],
            "volume": [50000.0],
            "turnover": [175000000.0],
        }
    )

    # 创建模拟客户端，模拟数据库错误
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()

    # 使用模拟客户端创建 Writer
    mock_writer = FuturesWriter(client=mock_client)

    # 由于模拟客户端会抛出异常，预期会传播异常
    with pytest.raises(RuntimeError, match="Database error"):
        mock_writer.write(test_df)

    # 验证回滚被调用
    mock_client.rollback.assert_called_once()


def test_write_on_conflict_do_nothing(
    writer: FuturesWriter, in_memory_db: SQLiteClient
) -> None:
    """测试冲突时不覆盖（ON CONFLICT DO NOTHING）."""
    df = pl.DataFrame(
        {
            "instrument_id": ["IF2412"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "open_interest": [100000.0],
            "settlement_price": [3500.0],
            "volume": [50000.0],
            "turnover": [175000000.0],
        }
    )

    # 第一次写入
    count1 = writer.write(df)
    assert count1 == 1

    # 尝试写入相同数据（冲突）
    count2 = writer.write(df)
    # ON CONFLICT DO NOTHING，所以不会插入新记录
    # 但由于我们的实现，仍然会返回尝试写入的记录数
    assert count2 == 1


def test_write_multiple_futures_same_instrument(
    writer: FuturesWriter, in_memory_db: SQLiteClient
) -> None:
    """测试同一期货多个交易日的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["IF2412", "IF2412", "IF2412"],
            "trade_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
            ],
            "knowledge_date": [
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
            ],
            "effective_from": [
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
            "effective_to": [None, None, None],
            "open_interest": [100000.0, 105000.0, 110000.0],
            "settlement_price": [3500.0, 3520.0, 3550.0],
            "volume": [50000.0, 52000.0, 55000.0],
            "turnover": [175000000.0, 183040000.0, 195250000.0],
        }
    )

    count = writer.write(df)
    assert count == 3

    # 验证数据写入正确
    rows = in_memory_db.fetchall(
        "SELECT trade_date, open_interest FROM futures "
        "WHERE instrument_id = ? ORDER BY trade_date",
        ["IF2412"],
    )
    assert len(rows) == 3
