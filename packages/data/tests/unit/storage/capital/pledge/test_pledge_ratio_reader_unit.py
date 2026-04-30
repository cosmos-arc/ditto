"""Unit tests for PledgeRatioReader."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_data.storage.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_data.storage.capital.specs import PLEDGE_RATIO_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import SQLitePool


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
def reader(in_memory_db: SQLiteClient) -> PledgeRatioReader:
    """创建 PledgeRatioReader 实例."""
    return PledgeRatioReader(PLEDGE_RATIO_SPEC, in_memory_db)


def test_get_returns_data(
    reader: PledgeRatioReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            None,
            15.5,
            100000000.0,
            500000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 1
    assert result["pledge_ratio"][0] == 15.5


def test_get_empty_table(reader: PledgeRatioReader) -> None:
    """测试空表返回空 DataFrame."""
    result = reader.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_no_data(reader: PledgeRatioReader, in_memory_db: SQLiteClient) -> None:
    """测试查询不存在的证券返回空 DataFrame."""
    # 插入其他证券的数据
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "000001.SZ",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            None,
            20.0,
            80000000.0,
            400000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 0


def test_get_pit_query(reader: PledgeRatioReader, in_memory_db: SQLiteClient) -> None:
    """测试 PIT 查询返回有效数据."""
    # 插入多个版本
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            date(2024, 5, 15),
            15.5,
            100000000.0,
            500000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 5, 20),
            date(2024, 5, 21),
            None,
            14.0,
            95000000.0,
            500000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询第一个版本有效期间的数据
    result = reader.get("600000.SH", date(2024, 5, 10))
    assert len(result) == 1
    assert result["pledge_ratio"][0] == 15.5


def test_get_pit_query_excludes_expired_version(
    reader: PledgeRatioReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询排除已过期版本."""
    # 插入已过期的版本
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            date(2024, 5, 15),
            15.5,
            100000000.0,
            500000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询过期后的日期
    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 0


def test_get_ordering_by_report_date(
    reader: PledgeRatioReader, in_memory_db: SQLiteClient
) -> None:
    """测试结果按 report_date 降序排列."""
    # 插入多条记录
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            None,
            15.5,
            100000000.0,
            500000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 2, 29),
            date(2024, 3, 31),
            date(2024, 4, 1),
            None,
            16.0,
            105000000.0,
            500000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 2
    # 验证降序排列
    assert result["report_date"][0] == "2024-03-31"
    assert result["report_date"][1] == "2024-02-29"


def test_get_handles_null_values(
    reader: PledgeRatioReader, in_memory_db: SQLiteClient
) -> None:
    """测试处理空值."""
    in_memory_db.execute(
        """INSERT INTO pledge_ratio
        (instrument_id, report_date, knowledge_date, effective_from, effective_to,
         pledge_ratio, pledge_shares, total_shares)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)""",
        ["600000.SH", date(2024, 3, 31), date(2024, 4, 30), date(2024, 5, 1), None],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 15))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["pledge_ratio"][0] is None
