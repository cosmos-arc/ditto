"""Tests for IndicatorStore."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.stores.macro.indicator.indicator_store import IndicatorStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicator_data (
            indicator_id INTEGER NOT NULL,
            date DATE NOT NULL,
            value REAL NOT NULL,
            knowledge_date DATE,
            effective_from DATE NOT NULL,
            effective_to DATE,
            PRIMARY KEY (indicator_id, date, effective_from)
        )
    """)
    # 创建索引
    client.execute("""
        CREATE INDEX IF NOT EXISTS idx_indicator_pit
        ON macro_indicator_data(indicator_id, effective_from, effective_to)
    """)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> IndicatorStore:
    """创建 IndicatorStore 实例."""
    return IndicatorStore(in_memory_db)


def test_write_single_indicator(store: IndicatorStore) -> None:
    """测试写入单个指标数据."""
    # 准备数据
    df = pl.DataFrame(
        {
            "indicator_id": [1],
            "date": [date(2024, 1, 1)],
            "value": [2.5],
        }
    )

    # 执行
    count = store.write(df)

    # 验证
    assert count == 1


def test_write_multiple_indicators(store: IndicatorStore) -> None:
    """测试写入多个指标数据."""
    # 准备数据
    df = pl.DataFrame(
        {
            "indicator_id": [1, 2, 3],
            "date": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2)],
            "value": [2.5, 3.0, 100.0],
        }
    )

    # 执行
    count = store.write(df)

    # 验证
    assert count == 3


def test_write_pit_indicator_with_knowledge_date(store: IndicatorStore) -> None:
    """测试写入带 knowledge_date 的 PIT 指标."""
    # 准备数据（带 knowledge_date）
    df = pl.DataFrame(
        {
            "indicator_id": [1, 1],
            "date": [date(2024, 1, 1), date(2024, 1, 1)],
            "value": [2.5, 2.6],  # 第一次发布 2.5，修正后 2.6
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 10)],
        }
    )

    # 执行
    count = store.write(df)

    # 验证
    assert count == 2


def test_get_by_indicator_id(store: IndicatorStore) -> None:
    """测试按指标 ID 查询."""
    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [1, 1, 2],
            "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 1)],
            "value": [2.5, 2.6, 3.0],
        }
    )
    store.write(df)

    # 查询指标 1
    result = store.get(indicator_ids=[1])

    # 验证
    assert len(result) == 2
    assert result["indicator_id"].to_list() == [1, 1]


def test_get_by_date_range(store: IndicatorStore) -> None:
    """测试按日期范围查询."""
    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [1, 1, 1, 1],
            "date": [
                date(2023, 12, 1),
                date(2024, 1, 1),
                date(2024, 1, 15),
                date(2024, 2, 1),
            ],
            "value": [2.0, 2.5, 2.6, 2.7],
        }
    )
    store.write(df)

    # 查询 2024年1月数据
    result = store.get(
        indicator_ids=[1],
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    # 验证
    assert len(result) == 2
    assert result["date"][0] == date(2024, 1, 1)
    assert result["date"][1] == date(2024, 1, 15)


def test_pit_query_with_asof_date(store: IndicatorStore) -> None:
    """测试 PIT 时点查询."""
    # 写入数据（带修正）
    # 1月1日数据：1月2日首次发布 2.5，1月10日修正为 2.6
    df = pl.DataFrame(
        {
            "indicator_id": [1, 1],
            "date": [date(2024, 1, 1), date(2024, 1, 1)],
            "value": [2.5, 2.6],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 10)],
        }
    )
    store.write(df)

    # 查询 1月5日时的数据（应该得到 2.5）
    result = store.get(
        indicator_ids=[1],
        as_of_date="2024-01-05",
    )

    # 验证 - 应该只返回 1月2日发布的版本
    assert len(result) == 1
    assert result["value"][0] == 2.5

    # 查询 1月15日时的数据（应该得到 2.6）
    result = store.get(
        indicator_ids=[1],
        as_of_date="2024-01-15",
    )

    # 验证 - 应该返回修正后的版本
    assert len(result) == 1
    assert result["value"][0] == 2.6


def test_upsert_replaces_existing_data(store: IndicatorStore) -> None:
    """测试更新已存在的数据."""
    # 写入初始数据
    df = pl.DataFrame(
        {
            "indicator_id": [1],
            "date": [date(2024, 1, 1)],
            "value": [2.5],
        }
    )
    store.write(df)

    # 更新数据
    df2 = pl.DataFrame(
        {
            "indicator_id": [1],
            "date": [date(2024, 1, 1)],
            "value": [2.6],
        }
    )
    count = store.write(df2)

    # 验证 - 新数据应该覆盖旧数据
    assert count == 1
    result = store.get(indicator_ids=[1])
    # 应该只有一条记录（最新的）
    assert len(result) == 1
