"""Unit tests for ValuationMetricsWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS valuation_metrics (
            instrument_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            pe_ratio REAL,
            pb_ratio REAL,
            ps_ratio REAL,
            dividend_yield REAL,
            market_cap REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
    """)
    client.commit()
    return client


@pytest.fixture
def writer(in_memory_db: SQLiteClient) -> ValuationMetricsWriter:
    """创建 ValuationMetricsWriter 实例."""
    return ValuationMetricsWriter(client=in_memory_db)


def test_write_success(writer: ValuationMetricsWriter) -> None:
    """测试成功写入."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "pe_ratio": [15.5],
            "pb_ratio": [2.3],
            "ps_ratio": [3.1],
            "dividend_yield": [0.02],
            "market_cap": [1000000.0],
        }
    )

    count = writer.write(df)
    assert count == 1


def test_write_returns_count(writer: ValuationMetricsWriter) -> None:
    """测试写入返回记录数."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, None],
            "pe_ratio": [15.5, 20.0],
            "pb_ratio": [2.3, 2.5],
            "ps_ratio": [3.1, 3.5],
            "dividend_yield": [0.02, 0.03],
            "market_cap": [1000000.0, 500000.0],
        }
    )

    count = writer.write(df)
    assert count == 2


def test_write_empty_dataframe(writer: ValuationMetricsWriter) -> None:
    """测试写入空 DataFrame."""
    df = pl.DataFrame(
        schema={
            "instrument_id": pl.String,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "pe_ratio": pl.Float64,
            "pb_ratio": pl.Float64,
            "ps_ratio": pl.Float64,
            "dividend_yield": pl.Float64,
            "market_cap": pl.Float64,
        }
    )

    count = writer.write(df)
    assert count == 0


def test_write_with_nullable_effective_date(
    writer: ValuationMetricsWriter, in_memory_db: SQLiteClient
) -> None:
    """测试写入包含 nullable effective_to 的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "trade_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 3)],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, date(2024, 1, 15)],
            "pe_ratio": [15.5, 20.0],
            "pb_ratio": [2.3, 2.5],
            "ps_ratio": [3.1, 3.5],
            "dividend_yield": [0.02, 0.03],
            "market_cap": [1000000.0, 500000.0],
        }
    )

    count = writer.write(df)
    assert count == 2

    # 验证数据写入正确
    rows = in_memory_db.fetchall("SELECT * FROM valuation_metrics")
    assert len(rows) == 2


def test_write_failure_rollback(writer: ValuationMetricsWriter) -> None:
    """测试写入失败时回滚."""
    # 创建有效的测试数据
    test_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "pe_ratio": [15.5],
            "pb_ratio": [2.3],
            "ps_ratio": [3.1],
            "dividend_yield": [0.02],
            "market_cap": [1000000.0],
        }
    )

    # 创建模拟客户端，模拟数据库错误
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()

    # 使用模拟客户端创建 Writer
    mock_writer = ValuationMetricsWriter(client=mock_client)

    # 由于模拟客户端会抛出异常，预期会传播异常
    with pytest.raises(RuntimeError, match="Database error"):
        mock_writer.write(test_df)

    # 验证回滚被调用
    mock_client.rollback.assert_called_once()


def test_write_on_conflict_do_nothing(
    writer: ValuationMetricsWriter, in_memory_db: SQLiteClient
) -> None:
    """测试冲突时不覆盖（ON CONFLICT DO NOTHING）."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 1, 2)],
            "knowledge_date": [date(2024, 1, 2)],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
            "pe_ratio": [15.5],
            "pb_ratio": [2.3],
            "ps_ratio": [3.1],
            "dividend_yield": [0.02],
            "market_cap": [1000000.0],
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


def test_write_multiple_metrics_same_instrument(
    writer: ValuationMetricsWriter, in_memory_db: SQLiteClient
) -> None:
    """测试同一证券多个交易日的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "600000.SH", "600000.SH"],
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
            "pe_ratio": [15.0, 15.5, 16.0],
            "pb_ratio": [2.0, 2.3, 2.5],
            "ps_ratio": [3.0, 3.1, 3.2],
            "dividend_yield": [0.02, 0.025, 0.03],
            "market_cap": [1000000.0, 1050000.0, 1100000.0],
        }
    )

    count = writer.write(df)
    assert count == 3

    # 验证数据写入正确
    rows = in_memory_db.fetchall(
        "SELECT trade_date, pe_ratio FROM valuation_metrics "
        "WHERE instrument_id = ? ORDER BY trade_date",
        ["600000.SH"],
    )
    assert len(rows) == 3
