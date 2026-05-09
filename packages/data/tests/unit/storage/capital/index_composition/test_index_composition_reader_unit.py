"""Unit tests for IndexCompositionReader."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.specs import INDEX_COMPOSITION_SPEC
from ditto_platform.foundation import SQLiteClient, SQLitePool


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
def reader(in_memory_db: SQLiteClient) -> IndexCompositionReader:
    """创建 IndexCompositionReader 实例."""
    return IndexCompositionReader(INDEX_COMPOSITION_SPEC, in_memory_db)


def test_get_returns_data(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", 0.05, date(2024, 1, 2), None],
    )
    in_memory_db.commit()

    result = reader.get("000300.SH", date(2024, 1, 5))
    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"


def test_get_empty_table(reader: IndexCompositionReader) -> None:
    """测试空表返回空 DataFrame."""
    result = reader.get("000300.SH", date(2024, 1, 5))
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_no_data(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询不存在的指数返回空 DataFrame."""
    # 插入其他指数的数据
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000905.SH", "600000.SH", 0.03, date(2024, 1, 2), None],
    )
    in_memory_db.commit()

    result = reader.get("000300.SH", date(2024, 1, 5))
    assert len(result) == 0


def test_get_pit_query(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询返回有效数据."""
    # 插入多个版本
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", 0.05, date(2024, 1, 3), date(2024, 1, 10)],
    )
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", 0.06, date(2024, 1, 12), None],
    )
    in_memory_db.commit()

    # 查询第一个版本有效期间的数据
    result = reader.get("000300.SH", date(2024, 1, 5))
    assert len(result) == 1
    assert result["weight"][0] == 0.05


def test_get_pit_query_excludes_expired_version(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询排除已过期版本."""
    # 插入已过期的版本
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", 0.05, date(2024, 1, 3), date(2024, 1, 10)],
    )
    in_memory_db.commit()

    # 查询过期后的日期
    result = reader.get("000300.SH", date(2024, 1, 15))
    assert len(result) == 0


def test_get_ordering_by_instrument_id(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试结果按 instrument_id 排序."""
    # 插入多条记录
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600036.SH", 0.03, date(2024, 1, 3), None],
    )
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", 0.05, date(2024, 1, 3), None],
    )
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "601318.SH", 0.02, date(2024, 1, 3), None],
    )
    in_memory_db.commit()

    result = reader.get("000300.SH", date(2024, 1, 15))
    assert len(result) == 3
    # 验证按 instrument_id 降序排列
    assert result["instrument_id"][0] == "601318.SH"
    assert result["instrument_id"][1] == "600036.SH"
    assert result["instrument_id"][2] == "600000.SH"


def test_get_handles_null_values(
    reader: IndexCompositionReader, in_memory_db: SQLiteClient
) -> None:
    """测试处理空值."""
    in_memory_db.execute(
        """INSERT INTO index_composition
        (index_id, instrument_id, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)""",
        ["000300.SH", "600000.SH", None, date(2024, 1, 3), None],
    )
    in_memory_db.commit()

    result = reader.get("000300.SH", date(2024, 1, 5))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["weight"][0] is None
