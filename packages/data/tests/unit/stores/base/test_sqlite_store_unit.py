"""Unit tests for SQLiteStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
from ditto_data.stores.base import SQLiteStore


def test_sqlite_store_write_and_read(tmp_path: Path) -> None:
    """测试 SQLiteStore 的基本读写功能."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    test_df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 1),
            ],
            "close": [10.0, 11.0, 20.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=test_df,
        on_duplicate="keep_last",
    )

    # 读取数据
    read_df = store.read(
        dataset="test_table",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert len(read_df) == 2
    assert read_df["instrument_id"].to_list() == [1, 1]


def test_sqlite_store_write_dataframe_with_keep_last(tmp_path: Path) -> None:
    """测试 SQLiteStore 的 KEEP_LAST 去重策略."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 第一次写入
    df1 = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [10.0, 20.0],
        }
    )

    result1 = store.write_dataframe(
        table="test_table",
        df=df1,
        on_duplicate="keep_last",
    )
    assert result1.added == 2
    assert result1.updated == 0

    # 第二次写入（有重复）
    df2 = pl.DataFrame(
        {
            "instrument_id": [1, 3],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [15.0, 30.0],  # instrument_id=1 的值更新为 15.0
        }
    )

    result2 = store.write_dataframe(
        table="test_table",
        df=df2,
        on_duplicate="keep_last",
    )
    assert result2.added == 1  # 只有 instrument_id=3 是新增
    assert result2.updated == 1  # instrument_id=1 被更新

    # 验证 instrument_id=1 的值被更新
    read_df = store.read(
        dataset="test_table",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-01",
    )

    assert len(read_df) == 1
    assert read_df["close"][0] == 15.0  # 应该是新值


def test_sqlite_store_write_dataframe_with_keep_first(tmp_path: Path) -> None:
    """测试 SQLiteStore 的 KEEP_FIRST 去重策略."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 第一次写入
    df1 = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [10.0, 20.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df1,
        on_duplicate="keep_last",
    )

    # 第二次写入（有重复，应该被忽略）
    df2 = pl.DataFrame(
        {
            "instrument_id": [1, 3],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [15.0, 30.0],
        }
    )

    result2 = store.write_dataframe(
        table="test_table",
        df=df2,
        on_duplicate="keep_first",
    )
    # instrument_id=1 是重复的，只有 instrument_id=3 被写入
    assert result2.added == 1
    assert result2.updated == 0

    # 验证 instrument_id=1 的值保持不变
    read_df = store.read(
        dataset="test_table",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-01",
    )

    assert len(read_df) == 1
    assert read_df["close"][0] == 10.0  # 应该是旧值


def test_sqlite_store_delete_by_sid(tmp_path: Path) -> None:
    """测试 SQLiteStore 按 instrument_id 删除数据."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 1),
                date(2024, 1, 2),
            ],
            "close": [10.0, 11.0, 20.0, 21.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df,
        on_duplicate="keep_last",
    )

    # 删除 instrument_id=1 的数据
    deleted_count = store.delete(
        dataset="test_table",
        instrument_ids=[1],
    )

    assert deleted_count == 2

    # 验证删除后的数据
    read_df = store.read(dataset="test_table")

    assert len(read_df) == 2
    assert read_df["instrument_id"].to_list() == [2, 2]


def test_sqlite_store_delete_by_date_range(tmp_path: Path) -> None:
    """测试 SQLiteStore 按日期范围删除数据."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 1],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
            "close": [10.0, 11.0, 12.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df,
        on_duplicate="keep_last",
    )

    # 删除 2024-01-01 到 2024-01-02 的数据
    deleted_count = store.delete(
        dataset="test_table",
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert deleted_count == 2

    # 验证删除后的数据
    read_df = store.read(dataset="test_table")

    assert len(read_df) == 1
    assert read_df["trade_date"][0] == date(2024, 1, 3)


def test_sqlite_store_read_filters(tmp_path: Path) -> None:
    """测试 SQLiteStore 的各种过滤条件."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    df = pl.DataFrame(
        {
            "instrument_id": [1, 1, 2, 2, 3],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 1),
            ],
            "close": [10.0, 11.0, 20.0, 21.0, 30.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df,
        on_duplicate="keep_last",
    )

    # 测试按 instrument_id 过滤
    result = store.read(
        dataset="test_table",
        instrument_ids=[1, 2],
    )
    assert len(result) == 4
    assert set(result["instrument_id"].to_list()) == {1, 2}

    # 测试按日期范围过滤
    result = store.read(
        dataset="test_table",
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    assert len(result) == 3
    assert all(d == date(2024, 1, 1) for d in result["trade_date"])

    # 测试组合过滤
    result = store.read(
        dataset="test_table",
        instrument_ids=[1],
        start_date="2024-01-02",
        end_date="2024-01-02",
    )
    assert len(result) == 1
    assert result["instrument_id"][0] == 1
    assert result["trade_date"][0] == date(2024, 1, 2)


def test_sqlite_store_execute_and_fetch(tmp_path: Path) -> None:
    """测试 SQLiteStore 的 SQL 执行和查询功能."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    df = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [10.0, 20.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df,
        on_duplicate="keep_last",
    )

    # 测试 fetchone
    row = store.fetchone("SELECT * FROM test_table WHERE instrument_id = ?", [1])
    assert row is not None
    assert row["instrument_id"] == 1
    assert row["close"] == 10.0

    # 测试 fetchall
    rows = store.fetchall("SELECT * FROM test_table ORDER BY instrument_id")
    assert len(rows) == 2
    assert rows[0]["instrument_id"] == 1
    assert rows[1]["instrument_id"] == 2


def test_sqlite_store_count_rows(tmp_path: Path) -> None:
    """测试 SQLiteStore 的行数统计功能."""
    db_path = tmp_path / "test.sqlite"
    store = SQLiteStore(db_path)

    # 创建测试表
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS test_table (
            instrument_id INTEGER,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (instrument_id, trade_date)
        )
    """
    )

    # 写入测试数据
    df = pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "trade_date": [
                date(2024, 1, 1),
                date(2024, 1, 1),
                date(2024, 1, 1),
            ],
            "close": [10.0, 20.0, 30.0],
        }
    )

    store.write_dataframe(
        table="test_table",
        df=df,
        on_duplicate="keep_last",
    )

    # 测试统计行数
    count = store._count_rows("test_table")
    assert count == 3
