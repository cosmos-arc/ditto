"""Unit tests for MarginTradingReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

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
        margin_buy_amount REAL,
        short_sell_volume REAL,
        PRIMARY KEY (instrument_id, trade_date, effective_from)
    )"""
    )
    client.commit()
    return client


@pytest.fixture
def reader(in_memory_db: SQLiteClient, tmp_path: Path) -> MarginTradingReader:
    """创建 MarginTradingReader 实例."""
    return MarginTradingReader(MARGIN_TRADING_SPEC, in_memory_db, tmp_path)


def test_get_returns_data(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """测试查询返回数据."""
    # 插入测试数据
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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


def test_get_respects_calibrated_disclosure_boundary(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """#658 B1E 发布前后对照：周五数据的可知边界=下周一开市前.

    交易所规则（深交所问答/tushare doc_id=59）：交易日开市前公布前一
    交易日数据，深市周五数据下周一上午更新。写入路径已把周五行的
    knowledge_date 校准为下周一（自然日 T+1=周六是 PIT 泄漏）——
    as_of 周六/周日不可见、下周一可见。
    """
    in_memory_db.execute(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            "000001.SZ",
            date(2024, 11, 1),  # 周五
            date(2024, 11, 4),  # 校准后 knowledge=下周一
            date(2024, 11, 4),
            None,
            800000.0,
            400000.0,
            40000000.0,
            16000000.0,
        ],
    )
    in_memory_db.commit()

    # 发布前（周六/周日）：不可见
    assert reader.get("000001.SZ", date(2024, 11, 2)).height == 0
    assert reader.get("000001.SZ", date(2024, 11, 3)).height == 0
    # 发布后（下周一）：可见
    visible = reader.get("000001.SZ", date(2024, 11, 4))
    assert visible.height == 1
    assert visible["margin_buy_balance"][0] == 800000.0


def test_get_transition_dual_version_baseline(
    reader: MarginTradingReader, in_memory_db: SQLiteClient
) -> None:
    """#658 B1E correctness F5 过渡态基线（批次2 存量纠正的盘点对象）.

    存量占位行（自然日 T+1）与新校准行（下一交易日）冲突键不同
    （effective_from 参与 KEEP_LAST 判定），共存为双开区间版本行：
    as_of 落在占位与校准之间（周六）仍读旧行——泄漏窗口延续到批次2
    重写存量；as_of ≥ 校准日收敛到新行。本测试固化现状语义供批次2 对照。
    """
    in_memory_db.executemany(
        """INSERT INTO margin_trading
        (instrument_id, trade_date, knowledge_date, effective_from, effective_to,
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            # 存量占位行（旧自然日 T+1 语义，周六生效）
            (
                "000001.SZ",
                date(2024, 11, 1),
                date(2024, 11, 2),
                date(2024, 11, 2),
                None,
                700000.0,
                350000.0,
                35000000.0,
                14000000.0,
            ),
            # 新校准行（下一交易日，周一生效）
            (
                "000001.SZ",
                date(2024, 11, 1),
                date(2024, 11, 4),
                date(2024, 11, 4),
                None,
                800000.0,
                400000.0,
                40000000.0,
                16000000.0,
            ),
        ],
    )
    in_memory_db.commit()

    # 周六：仅占位行可知（过渡态泄漏窗口，批次2 重写存量后关闭）
    saturday = reader.get("000001.SZ", date(2024, 11, 3))
    assert saturday.height == 1
    assert saturday["margin_buy_balance"][0] == 700000.0
    # 周一起：收敛到校准行
    monday = reader.get("000001.SZ", date(2024, 11, 4))
    assert monday.height == 1
    assert monday["margin_buy_balance"][0] == 800000.0


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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
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
         margin_buy_balance, short_sell_balance, margin_buy_amount, short_sell_volume)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
        ["600000.SH", date(2024, 5, 15), date(2024, 5, 15), date(2024, 5, 16), None],
    )
    in_memory_db.commit()

    result = reader.get("600000.SH", date(2024, 5, 20))
    assert len(result) == 1
    # polars 会将 NULL 转换为 None
    assert result["margin_buy_balance"][0] is None
