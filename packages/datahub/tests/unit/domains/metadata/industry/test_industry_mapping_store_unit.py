"""IndustryMappingStore unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_datahub.stores.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """创建临时数据库路径."""
    db_path = tmp_path / "test.db"
    # 初始化数据库表
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS industry_mapping (
        instrument_id INTEGER NOT NULL,
        industry_id TEXT NOT NULL,
        source TEXT DEFAULT 'sw',
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        entry_reason TEXT,
        PRIMARY KEY (instrument_id, effective_from)
    )"""
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db_path: Path) -> IndustryMappingStore:
    """创建 IndustryMappingStore 实例."""
    return IndustryMappingStore(temp_db_path)


def test_industry_mapping_store_get_stock_industry_empty(
    store: IndustryMappingStore,
) -> None:
    """测试获取不存在的股票行业映射."""
    result = store.get_stock_industry(instrument_id=1)
    assert result is None


def test_industry_mapping_store_update_and_get_stock_industry(
    store: IndustryMappingStore,
) -> None:
    """测试更新并获取股票行业映射."""
    # 更新映射
    store.update_mapping(
        instrument_id=1,
        industry_id="801010",
        effective_from="2024-01-01",
        entry_reason="首次入选",
    )

    # 获取映射
    result = store.get_stock_industry(instrument_id=1)
    assert result is not None
    assert result["instrument_id"] == 1
    assert result["industry_id"] == "801010"
    assert result["source"] == "sw"


def test_industry_mapping_store_get_stocks(store: IndustryMappingStore) -> None:
    """测试获取行业的所有成分股."""
    # 添加多个股票到同一行业
    store.update_mapping(
        instrument_id=1, industry_id="801010", effective_from="2024-01-01"
    )
    store.update_mapping(
        instrument_id=2, industry_id="801010", effective_from="2024-01-01"
    )
    store.update_mapping(
        instrument_id=3, industry_id="801020", effective_from="2024-01-01"
    )

    # 获取行业的成分股
    stocks_801010 = store.get_stocks("801010")
    assert set(stocks_801010) == {1, 2}

    stocks_801020 = store.get_stocks("801020")
    assert set(stocks_801020) == {3}


def test_industry_mapping_store_pit_query(store: IndustryMappingStore) -> None:
    """测试 Point-in-Time 查询."""
    # 添加映射历史
    store.update_mapping(
        instrument_id=1, industry_id="801010", effective_from="2024-01-01"
    )
    store.update_mapping(
        instrument_id=1, industry_id="801020", effective_from="2024-06-01"
    )

    # 查询 2024-03-01 的映射（应该是 801010）
    result_mar = store.get_stock_industry(instrument_id=1, asof="2024-03-01")
    assert result_mar is not None
    assert result_mar["industry_id"] == "801010"

    # 查询 2024-07-01 的映射（应该是 801020）
    result_jul = store.get_stock_industry(instrument_id=1, asof="2024-07-01")
    assert result_jul is not None
    assert result_jul["industry_id"] == "801020"

    # 查询当前映射（应该是 801020）
    result_current = store.get_stock_industry(instrument_id=1)
    assert result_current is not None
    assert result_current["industry_id"] == "801020"


def test_industry_mapping_store_get_stocks_pit(store: IndustryMappingStore) -> None:
    """测试 Point-in-Time 查询行业成分股."""
    # 添加映射历史
    store.update_mapping(
        instrument_id=1, industry_id="801010", effective_from="2024-01-01"
    )
    store.update_mapping(
        instrument_id=2, industry_id="801010", effective_from="2024-01-01"
    )
    store.update_mapping(
        instrument_id=1, industry_id="801020", effective_from="2024-06-01"
    )

    # 查询 2024-03-01 的成分股
    stocks_mar = store.get_stocks("801010", asof="2024-03-01")
    assert set(stocks_mar) == {1, 2}

    # 查询 2024-07-01 的成分股（instrument_id=1 已移出）
    stocks_jul = store.get_stocks("801010", asof="2024-07-01")
    assert set(stocks_jul) == {2}
