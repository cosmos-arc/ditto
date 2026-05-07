"""Unit tests for MarginTradingWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_data.storage.capital.specs import MARGIN_TRADING_SPEC
from ditto_platform.foundation import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute(
        """CREATE TABLE IF NOT EXISTS margin_trading (
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
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def writer(in_memory_db: SQLiteClient) -> MarginTradingWriter:
    """创建 MarginTradingWriter 实例."""
    return MarginTradingWriter(MARGIN_TRADING_SPEC, in_memory_db)


def test_write_success(writer: MarginTradingWriter) -> None:
    """测试成功写入."""
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

    count = writer.write(df)
    assert count == 1


def test_write_returns_count(writer: MarginTradingWriter) -> None:
    """测试写入返回记录数."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "trade_date": [date(2024, 5, 15), date(2024, 5, 16)],
            "knowledge_date": [date(2024, 5, 15), date(2024, 5, 16)],
            "effective_from": [date(2024, 5, 16), date(2024, 5, 17)],
            "effective_to": [None, None],
            "margin_buy_balance": [1000000.0, 800000.0],
            "short_sell_balance": [500000.0, 400000.0],
            "margin_buy_volume": [50000000.0, 40000000.0],
            "short_sell_volume": [20000000.0, 16000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2


def test_write_empty_dataframe(writer: MarginTradingWriter) -> None:
    """测试写入空 DataFrame."""
    df = pl.DataFrame(
        schema={
            "instrument_id": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "margin_buy_balance": pl.Float64,
            "short_sell_balance": pl.Float64,
            "margin_buy_volume": pl.Float64,
            "short_sell_volume": pl.Float64,
        }
    )

    count = writer.write(df)
    assert count == 0


def test_write_with_nullable_effective_date(
    writer: MarginTradingWriter, in_memory_db: SQLiteClient
) -> None:
    """测试写入包含 nullable effective_to 的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "trade_date": [date(2024, 5, 15), date(2024, 5, 16)],
            "knowledge_date": [date(2024, 5, 15), date(2024, 5, 16)],
            "effective_from": [date(2024, 5, 16), date(2024, 5, 17)],
            "effective_to": [None, date(2024, 5, 25)],
            "margin_buy_balance": [1000000.0, 800000.0],
            "short_sell_balance": [500000.0, 400000.0],
            "margin_buy_volume": [50000000.0, 40000000.0],
            "short_sell_volume": [20000000.0, 16000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2

    # 验证数据写入正确
    rows = in_memory_db.fetchall("SELECT * FROM margin_trading")
    assert len(rows) == 2


def test_write_failure_rollback(writer: MarginTradingWriter) -> None:
    """测试写入失败时回滚."""
    # 创建有效的测试数据
    test_df = pl.DataFrame(
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

    # 创建模拟客户端，模拟数据库错误
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()

    # 使用模拟客户端创建 Writer
    mock_writer = MarginTradingWriter(MARGIN_TRADING_SPEC, mock_client)

    # 由于模拟客户端会抛出异常，预期会传播异常
    with pytest.raises(RuntimeError, match="Database error"):
        mock_writer.write(test_df)

    # 验证回滚被调用
    mock_client.rollback.assert_called_once()


def test_write_on_conflict_do_nothing(
    writer: MarginTradingWriter, in_memory_db: SQLiteClient
) -> None:
    """测试冲突时不覆盖（ON CONFLICT DO NOTHING）."""
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

    # 第一次写入
    count1 = writer.write(df)
    assert count1 == 1

    # 尝试写入相同数据（冲突）
    count2 = writer.write(df)
    # ON CONFLICT DO NOTHING，所以不会插入新记录
    # 但由于我们的实现，仍然会返回尝试写入的记录数
    assert count2 == 1


def test_write_multiple_records_same_instrument(
    writer: MarginTradingWriter, in_memory_db: SQLiteClient
) -> None:
    """测试同一证券多个交易日的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": [
                "600000.SH",
                "600000.SH",
                "600000.SH",
            ],
            "trade_date": [
                date(2024, 5, 15),
                date(2024, 5, 16),
                date(2024, 5, 17),
            ],
            "knowledge_date": [
                date(2024, 5, 15),
                date(2024, 5, 16),
                date(2024, 5, 17),
            ],
            "effective_from": [
                date(2024, 5, 16),
                date(2024, 5, 17),
                date(2024, 5, 18),
            ],
            "effective_to": [None, None, None],
            "margin_buy_balance": [1000000.0, 1100000.0, 1200000.0],
            "short_sell_balance": [500000.0, 550000.0, 600000.0],
            "margin_buy_volume": [50000000.0, 55000000.0, 60000000.0],
            "short_sell_volume": [20000000.0, 22000000.0, 24000000.0],
        }
    )

    count = writer.write(df)
    assert count == 3

    # 验证数据写入正确
    rows = in_memory_db.fetchall(
        "SELECT trade_date, margin_buy_balance FROM margin_trading "
        "WHERE instrument_id = ? ORDER BY trade_date",
        ["600000.SH"],
    )
    assert len(rows) == 3
