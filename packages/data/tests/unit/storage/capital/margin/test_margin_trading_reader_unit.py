"""Unit tests for MarginTradingReader."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_data.storage.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.storage.capital.specs import MARGIN_TRADING_SPEC
from ditto_platform.foundation import SQLiteClient, SQLitePool


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
def reader(in_memory_db: SQLiteClient) -> MarginTradingReader:
    """创建 MarginTradingReader 实例."""
    return MarginTradingReader(MARGIN_TRADING_SPEC, in_memory_db)


def test_get_returns_data(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 15),
            date(2024, 5, 15),
            date(2024, 5, 16),
            None,
            1000000.0,
            500000.0,
            50000000.0,
            20000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 1
    assert result["margin_buy_balance"][0] == 1000000.0


def test_get_empty_table(reader: MarginTradingReader) -> None:
    """测试空表返回空 DataFrame."""
    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_no_data(reader: MarginTradingReader, in_memory_db: SQLiteClient) -> None:
    """测试查询不存在的证券返回空 DataFrame."""
    # 插入其他证券的数据
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "000001.SZ",
            date(2024, 5, 15),
            date(2024, 5, 15),
            date(2024, 5, 16),
            None,
            800000.0,
            400000.0,
            40000000.0,
            16000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 0


def test_get_pit_query(reader: MarginTradingReader, in_memory_db: SQLiteClient) -> None:
    """测试 PIT 查询返回有效数据."""
    # 插入多个版本
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 15),
            date(2024, 5, 15),
            date(2024, 5, 16),
            date(2024, 5, 20),
            1000000.0,
            500000.0,
            50000000.0,
            20000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 15),
            date(2024, 5, 21),
            date(2024, 5, 22),
            None,
            1100000.0,
            550000.0,
            55000000.0,
            22000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询第一个版本有效期间的数据
    result = reader.get("600000.SH", date(2024, 5, 18))
    assert len(result) == 1
    assert result["margin_buy_balance"][0] == 1000000.0


def test_get_pit_query_excludes_expired_version(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """测试 PIT 查询排除已过期版本."""
    # 插入已过期的版本
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 15),
            date(2024, 5, 15),
            date(2024, 5, 16),
            date(2024, 5, 20),
            1000000.0,
            500000.0,
            50000000.0,
            20000000.0,
        ],
    )
    in_memory_db.commit()

    # 查询过期后的日期
    result = reader.get("600000.SH", date(2024, 5, 25))
    assert len(result) == 0


def test_get_ordering_by_trade_date(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """测试结果按 trade_date 降序排列."""
    # 插入多条记录
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 15),
            date(2024, 5, 15),
            date(2024, 5, 16),
            None,
            1000000.0,
            500000.0,
            50000000.0,
            20000000.0,
        ],
    )
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "600000.SH",
            date(2024, 5, 10),
            date(2024, 5, 10),
            date(2024, 5, 11),
            None,
            950000.0,
            480000.0,
            48000000.0,
            19000000.0,
        ],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 2
    # 验证降序排列
    assert result["trade_date"][0] == "2024-05-15"
    assert result["trade_date"][1] == "2024-05-10"


def test_get_handles_null_values(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """测试处理空值."""
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_volume, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
        ["600000.SH", date(2024, 5, 15), date(2024, 5, 15), date(2024, 5, 16), None],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["margin_buy_balance"][0] is None
