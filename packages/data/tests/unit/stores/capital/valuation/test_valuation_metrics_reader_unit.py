"""Unit tests for ValuationMetricsReader."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_data.stores.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_data.stores.sqlite_client import SQLiteClient
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
def reader(in_memory_db: SQLiteClient) -> ValuationMetricsReader:
    """创建 ValuationMetricsReader 实例."""
    return ValuationMetricsReader(client=in_memory_db)


def test_get_returns_data(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            None,
            15.5,
            2.3,
            3.1,
            0.02,
            1000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 1, 5))
    assert len(result) == 1
    assert result["pe_ratio"][0] == 15.5


def test_get_empty_table(reader: ValuationMetricsReader) -> None:
    """测试空表返回空 DataFrame."""
    result = reader.get("600000.SH", date(2024, 1, 5))
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_no_data(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询不存在的证券返回空 DataFrame."""
    # 插入其他证券的数据
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "000001.SZ",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            None,
            20.0,
            2.5,
            3.5,
            0.03,
            500000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 1, 5))
    assert len(result) == 0


def test_get_pit_query(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询返回有效数据."""
    # 插入多个版本
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 10),
            15.0,
            2.0,
            3.0,
            0.02,
            1000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 2),
            date(2024, 1, 11),
            date(2024, 1, 12),
            None,
            16.0,
            2.1,
            3.1,
            0.025,
            1100000.0,
        ],
    )
    in_memory_db.commit()

    # 查询第一个版本有效期间的数据
    result = reader.get("600000.SH", date(2024, 1, 5))
    assert len(result) == 1
    assert result["pe_ratio"][0] == 15.0


def test_get_pit_query_excludes_expired_version(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询排除已过期版本."""
    # 插入已过期的版本
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 2),
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 10),
            15.0,
            2.0,
            3.0,
            0.02,
            1000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询过期后的日期
    result = reader.get("600000.SH", date(2024, 1, 15))
    assert len(result) == 0


def test_get_ordering_by_trade_date(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试结果按 trade_date 降序排列."""
    # 插入多条记录
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 5),
            date(2024, 1, 5),
            date(2024, 1, 6),
            None,
            15.0,
            2.0,
            3.0,
            0.02,
            1000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 10),
            date(2024, 1, 10),
            date(2024, 1, 11),
            None,
            16.0,
            2.1,
            3.1,
            0.025,
            1100000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 1, 3),
            date(2024, 1, 3),
            date(2024, 1, 4),
            None,
            14.0,
            1.9,
            2.9,
            0.015,
            900000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 1, 15))
    assert len(result) == 3
    # 验证降序排列（polars 从原始行构造时返回日期字符串）
    assert result["trade_date"][0] == "2024-01-10"
    assert result["trade_date"][1] == "2024-01-05"
    assert result["trade_date"][2] == "2024-01-03"


def test_get_handles_null_values(
    reader: ValuationMetricsReader, in_memory_db: SQLiteClient
) -> None:
    """测试处理空值."""
    in_memory_db.execute(
        """INSERT INTO valuation_metrics
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)""",
        ["600000.SH", date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3), None],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 1, 5))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["pe_ratio"][0] is None
