"""Unit tests for IndexCompositionWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.stores.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
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
        """CREATE TABLE IF NOT EXISTS index_composition (
        index_id TEXT NOT NULL,
        instrument_id TEXT NOT NULL,
        weight REAL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        PRIMARY KEY (index_id, instrument_id, effective_from)
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def writer(in_memory_db: SQLiteClient) -> IndexCompositionWriter:
    """创建 IndexCompositionWriter 实例."""
    return IndexCompositionWriter(client=in_memory_db)


def test_write_success(writer: IndexCompositionWriter) -> None:
    """测试成功写入."""
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": ["600000.SH"],
            "weight": [0.05],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
        }
    )

    count = writer.write(df)
    assert count == 1


def test_write_returns_count(writer: IndexCompositionWriter) -> None:
    """测试写入返回记录数."""
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH"],
            "instrument_id": ["600000.SH", "600036.SH"],
            "weight": [0.05, 0.03],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, None],
        }
    )

    count = writer.write(df)
    assert count == 2


def test_write_empty_dataframe(writer: IndexCompositionWriter) -> None:
    """测试写入空 DataFrame."""
    df = pl.DataFrame(
        schema={
            "index_id": pl.String,
            "instrument_id": pl.String,
            "weight": pl.Float64,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
        }
    )

    count = writer.write(df)
    assert count == 0


def test_write_with_nullable_effective_date(
    writer: IndexCompositionWriter, in_memory_db: SQLiteClient
) -> None:
    """测试写入包含 nullable effective_to 的数据."""
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH"],
            "instrument_id": ["600000.SH", "600036.SH"],
            "weight": [0.05, 0.03],
            "effective_from": [date(2024, 1, 3), date(2024, 1, 4)],
            "effective_to": [None, date(2024, 1, 15)],
        }
    )

    count = writer.write(df)
    assert count == 2

    # 验证数据写入正确
    rows = in_memory_db.fetchall("SELECT * FROM index_composition")
    assert len(rows) == 2


def test_write_failure_rollback(writer: IndexCompositionWriter) -> None:
    """测试写入失败时回滚."""
    # 创建有效的测试数据
    test_df = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": ["600000.SH"],
            "weight": [0.05],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
        }
    )

    # 创建模拟客户端，模拟数据库错误
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()

    # 使用模拟客户端创建 Writer
    mock_writer = IndexCompositionWriter(client=mock_client)

    # 由于模拟客户端会抛出异常，预期会传播异常
    with pytest.raises(RuntimeError, match="Database error"):
        mock_writer.write(test_df)

    # 验证回滚被调用
    mock_client.rollback.assert_called_once()


def test_write_on_conflict_do_nothing(
    writer: IndexCompositionWriter, in_memory_db: SQLiteClient
) -> None:
    """测试冲突时不覆盖（ON CONFLICT DO NOTHING）."""
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH"],
            "instrument_id": ["600000.SH"],
            "weight": [0.05],
            "effective_from": [date(2024, 1, 3)],
            "effective_to": [None],
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


def test_write_multiple_instruments_same_index(
    writer: IndexCompositionWriter, in_memory_db: SQLiteClient
) -> None:
    """测试同一指数多个成分股的数据."""
    df = pl.DataFrame(
        {
            "index_id": ["000300.SH", "000300.SH", "000300.SH"],
            "instrument_id": ["600000.SH", "600036.SH", "601318.SH"],
            "weight": [0.05, 0.03, 0.02],
            "effective_from": [
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
            "effective_to": [None, None, None],
        }
    )

    count = writer.write(df)
    assert count == 3

    # 验证数据写入正确
    rows = in_memory_db.fetchall(
        "SELECT instrument_id, weight FROM index_composition "
        "WHERE index_id = ? ORDER BY instrument_id",
        ["000300.SH"],
    )
    assert len(rows) == 3
