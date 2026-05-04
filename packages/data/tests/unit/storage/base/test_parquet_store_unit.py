"""Unit tests for ParquetStore."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_platform.foundation.storage import ParquetStore


def test_parquet_store_write_and_read(tmp_path: Path) -> None:
    """测试 ParquetStore 的基本读写功能."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    result = store.write(
        dataset="test_dataset",
        data=test_df,
        year=2024,
    )

    assert result.file_path == str(data_root / "test_dataset" / "2024.parquet")
    assert result.added == 3
    assert result.updated == 0
    assert result.is_merge is False

    # 读取数据
    read_df = store.read(
        dataset="test_dataset",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert len(read_df) == 2
    assert read_df["instrument_id"].to_list() == [1, 1]


def test_parquet_store_write_with_keep_last(tmp_path: Path) -> None:
    """测试 ParquetStore 的 KEEP_LAST 去重策略."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    result1 = store.write(
        dataset="test_dataset",
        data=df1,
        year=2024,
    )
    assert result1.added == 2
    assert result1.updated == 0
    assert result1.is_merge is False

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

    result2 = store.write(
        dataset="test_dataset",
        data=df2,
        year=2024,
        on_duplicate="keep_last",
    )
    assert result2.added == 1  # 只有 instrument_id=3 是新增
    assert result2.updated == 1  # instrument_id=1 被更新
    assert result2.is_merge is True

    # 验证 instrument_id=1 的值被更新
    read_df = store.read(
        dataset="test_dataset",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-01",
    )

    assert len(read_df) == 1
    assert read_df["close"][0] == 15.0  # 应该是新值


def test_parquet_store_write_with_keep_first(tmp_path: Path) -> None:
    """测试 ParquetStore 的 KEEP_FIRST 去重策略."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    result1 = store.write(
        dataset="test_dataset",
        data=df1,
        year=2024,
    )
    assert result1.added == 2

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

    result2 = store.write(
        dataset="test_dataset",
        data=df2,
        year=2024,
        on_duplicate="keep_first",
    )
    # instrument_id=1 是重复的，只有 instrument_id=3 被写入
    assert result2.added == 1
    assert result2.updated == 0
    assert result2.is_merge is True

    # 验证 instrument_id=1 的值保持不变
    read_df = store.read(
        dataset="test_dataset",
        instrument_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-01",
    )

    assert len(read_df) == 1
    assert read_df["close"][0] == 10.0  # 应该是旧值


def test_parquet_store_write_with_error(tmp_path: Path) -> None:
    """测试 ParquetStore 的 ERROR 去重策略（默认）."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    store.write(
        dataset="test_dataset",
        data=df1,
        year=2024,
    )

    # 第二次写入（有重复，应该抛出错误）
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

    with pytest.raises(ValueError, match="Duplicate data"):
        store.write(
            dataset="test_dataset",
            data=df2,
            year=2024,
            on_duplicate="error",
        )


def test_parquet_store_delete_by_sid(tmp_path: Path) -> None:
    """测试 ParquetStore 按 instrument_id 删除数据."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    store.write(
        dataset="test_dataset",
        data=df,
        year=2024,
    )

    # 删除 instrument_id=1 的数据
    deleted_count = store.delete(
        dataset="test_dataset",
        instrument_ids=[1],
    )

    assert deleted_count == 2

    # 验证删除后的数据
    read_df = store.read(dataset="test_dataset")

    assert len(read_df) == 2
    assert read_df["instrument_id"].to_list() == [2, 2]


def test_parquet_store_delete_by_date_range(tmp_path: Path) -> None:
    """测试 ParquetStore 按日期范围删除数据."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    store.write(
        dataset="test_dataset",
        data=df,
        year=2024,
    )

    # 删除 2024-01-01 到 2024-01-02 的数据
    deleted_count = store.delete(
        dataset="test_dataset",
        start_date="2024-01-01",
        end_date="2024-01-02",
    )

    assert deleted_count == 2

    # 验证删除后的数据
    read_df = store.read(dataset="test_dataset")

    assert len(read_df) == 1
    assert read_df["trade_date"][0] == date(2024, 1, 3)


def test_parquet_store_read_filters(tmp_path: Path) -> None:
    """测试 ParquetStore 的各种过滤条件."""
    data_root = tmp_path / "data"
    store = ParquetStore(data_root)

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

    store.write(
        dataset="test_dataset",
        data=df,
        year=2024,
    )

    # 测试按 instrument_id 过滤
    result = store.read(
        dataset="test_dataset",
        instrument_ids=[1, 2],
    )
    assert len(result) == 4
    assert set(result["instrument_id"].to_list()) == {1, 2}

    # 测试按日期范围过滤
    result = store.read(
        dataset="test_dataset",
        start_date="2024-01-01",
        end_date="2024-01-01",
    )
    assert len(result) == 3
    assert all(d == date(2024, 1, 1) for d in result["trade_date"])

    # 测试组合过滤
    result = store.read(
        dataset="test_dataset",
        instrument_ids=[1],
        start_date="2024-01-02",
        end_date="2024-01-02",
    )
    assert len(result) == 1
    assert result["instrument_id"][0] == 1
    assert result["trade_date"][0] == date(2024, 1, 2)
