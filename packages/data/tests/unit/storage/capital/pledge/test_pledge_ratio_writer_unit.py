"""Unit tests for PledgeRatioWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_data.storage.capital.specs import PLEDGE_RATIO_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute(
        """CREATE TABLE IF NOT EXISTS pledge_ratio (
        instrument_id TEXT NOT NULL,
        report_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        pledge_ratio REAL,
        pledge_shares REAL,
        total_shares REAL,
        PRIMARY KEY (instrument_id, report_date, effective_from)
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def writer(in_memory_db: SQLiteClient) -> PledgeRatioWriter:
    """创建 PledgeRatioWriter 实例."""
    return PledgeRatioWriter(PLEDGE_RATIO_SPEC, in_memory_db)


def test_write_success(writer: PledgeRatioWriter) -> None:
    """测试成功写入."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [15.5],
            "pledge_shares": [100000000.0],
            "total_shares": [500000000.0],
        }
    )

    count = writer.write(df)
    assert count == 1


def test_write_returns_count(writer: PledgeRatioWriter) -> None:
    """测试写入返回记录数."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "report_date": [date(2024, 3, 31), date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30), date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1), date(2024, 5, 1)],
            "effective_to": [None, None],
            "pledge_ratio": [15.5, 20.0],
            "pledge_shares": [100000000.0, 80000000.0],
            "total_shares": [500000000.0, 400000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2


def test_write_empty_dataframe(writer: PledgeRatioWriter) -> None:
    """测试写入空 DataFrame."""
    df = pl.DataFrame(
        schema={
            "instrument_id": pl.String,
            "report_date": pl.Date,
            "knowledge_date": pl.Date,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "pledge_ratio": pl.Float64,
            "pledge_shares": pl.Float64,
            "total_shares": pl.Float64,
        }
    )

    count = writer.write(df)
    assert count == 0


def test_write_with_nullable_effective_date(
    writer: PledgeRatioWriter, in_memory_db: SQLiteClient
) -> None:
    """测试写入包含 nullable effective_to 的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "000001.SZ"],
            "report_date": [date(2024, 3, 31), date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30), date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1), date(2024, 5, 1)],
            "effective_to": [None, date(2024, 5, 20)],
            "pledge_ratio": [15.5, 20.0],
            "pledge_shares": [100000000.0, 80000000.0],
            "total_shares": [500000000.0, 400000000.0],
        }
    )

    count = writer.write(df)
    assert count == 2

    # 验证数据写入正确
    rows = in_memory_db.fetchall("SELECT * FROM pledge_ratio")
    assert len(rows) == 2


def test_write_failure_rollback(writer: PledgeRatioWriter) -> None:
    """测试写入失败时回滚."""
    # 创建有效的测试数据
    test_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [15.5],
            "pledge_shares": [100000000.0],
            "total_shares": [500000000.0],
        }
    )

    # 创建模拟客户端，模拟数据库错误
    mock_client = Mock(spec=SQLiteClient)
    mock_client.executemany.side_effect = RuntimeError("Database error")
    mock_client.commit = Mock()
    mock_client.rollback = Mock()

    # 使用模拟客户端创建 Writer
    mock_writer = PledgeRatioWriter(PLEDGE_RATIO_SPEC, mock_client)

    # 由于模拟客户端会抛出异常，预期会传播异常
    with pytest.raises(RuntimeError, match="Database error"):
        mock_writer.write(test_df)

    # 验证回滚被调用
    mock_client.rollback.assert_called_once()


def test_write_on_conflict_do_nothing(
    writer: PledgeRatioWriter, in_memory_db: SQLiteClient
) -> None:
    """测试冲突时不覆盖（ON CONFLICT DO NOTHING）."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [15.5],
            "pledge_shares": [100000000.0],
            "total_shares": [500000000.0],
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
    writer: PledgeRatioWriter, in_memory_db: SQLiteClient
) -> None:
    """测试同一证券多个报告期的数据."""
    df = pl.DataFrame(
        {
            "instrument_id": [
                "600000.SH",
                "600000.SH",
                "600000.SH",
            ],
            "report_date": [
                date(2024, 3, 31),
                date(2024, 2, 29),
                date(2024, 1, 31),
            ],
            "knowledge_date": [
                date(2024, 4, 30),
                date(2024, 3, 31),
                date(2024, 2, 29),
            ],
            "effective_from": [
                date(2024, 5, 1),
                date(2024, 4, 1),
                date(2024, 3, 1),
            ],
            "effective_to": [None, None, None],
            "pledge_ratio": [15.5, 16.0, 16.5],
            "pledge_shares": [100000000.0, 105000000.0, 110000000.0],
            "total_shares": [500000000.0, 500000000.0, 500000000.0],
        }
    )

    count = writer.write(df)
    assert count == 3

    # 验证数据写入正确
    rows = in_memory_db.fetchall(
        "SELECT report_date, pledge_ratio FROM pledge_ratio "
        "WHERE instrument_id = ? ORDER BY report_date",
        ["600000.SH"],
    )
    assert len(rows) == 3
