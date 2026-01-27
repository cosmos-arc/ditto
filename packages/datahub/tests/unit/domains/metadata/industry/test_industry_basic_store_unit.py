"""IndustryBasicStore unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_datahub.domains.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.domains.metadata.industry.models import IndustryBasic


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """创建临时数据库路径."""
    db_path = tmp_path / "test.db"
    # 初始化数据库表
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS industry_basic (
        industry_id TEXT PRIMARY KEY,
        industry_name TEXT NOT NULL,
        industry_level TEXT NOT NULL,
        parent_id TEXT,
        is_active INTEGER DEFAULT 1
    )"""
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db_path: Path) -> IndustryBasicStore:
    """创建 IndustryBasicStore 实例."""
    return IndustryBasicStore(temp_db_path)


def test_industry_basic_store_get_all_empty(store: IndustryBasicStore) -> None:
    """测试获取空的行业列表."""
    df = store.get_all()
    assert df.is_empty()


def test_industry_basic_store_register_and_get_all(store: IndustryBasicStore) -> None:
    """测试注册行业并获取所有行业."""
    # 注册测试数据
    industry1 = IndustryBasic(
        industry_id="801010",
        industry_name="农林牧渔",
        industry_level="一级",
        parent_id=None,
        is_active=True,
    )
    industry2 = IndustryBasic(
        industry_id="801020",
        industry_name="采掘",
        industry_level="一级",
        parent_id=None,
        is_active=True,
    )

    store.register(industry1)
    store.register(industry2)

    # 获取所有行业
    df = store.get_all()
    assert len(df) == 2
    assert set(df["industry_id"].to_list()) == {"801010", "801020"}


def test_industry_basic_store_get_by_id(store: IndustryBasicStore) -> None:
    """测试根据 ID 获取行业信息."""
    industry = IndustryBasic(
        industry_id="801010",
        industry_name="农林牧渔",
        industry_level="一级",
        parent_id=None,
        is_active=True,
    )
    store.register(industry)

    # 获取行业信息
    result = store.get_by_id("801010")
    assert result is not None
    assert result["industry_id"] == "801010"
    assert result["industry_name"] == "农林牧渔"


def test_industry_basic_store_get_by_id_not_found(store: IndustryBasicStore) -> None:
    """测试获取不存在的行业 ID."""
    result = store.get_by_id("999999")
    assert result is None


def test_industry_basic_store_filter_by_level(store: IndustryBasicStore) -> None:
    """测试按行业级别过滤."""
    # 注册测试数据
    industry1 = IndustryBasic(
        industry_id="801010",
        industry_name="农林牧渔",
        industry_level="一级",
        parent_id=None,
        is_active=True,
    )
    industry2 = IndustryBasic(
        industry_id="801010001",
        industry_name="种植业",
        industry_level="二级",
        parent_id="801010",
        is_active=True,
    )

    store.register(industry1)
    store.register(industry2)

    # 按一级过滤
    df_level1 = store.get_all(industry_level="一级")
    assert len(df_level1) == 1
    assert df_level1[0, "industry_id"] == "801010"

    # 按二级过滤
    df_level2 = store.get_all(industry_level="二级")
    assert len(df_level2) == 1
    assert df_level2[0, "industry_id"] == "801010001"


def test_industry_basic_store_filter_active(store: IndustryBasicStore) -> None:
    """测试按活跃状态过滤."""
    # 注册测试数据
    industry1 = IndustryBasic(
        industry_id="801010",
        industry_name="农林牧渔",
        industry_level="一级",
        parent_id=None,
        is_active=True,
    )
    industry2 = IndustryBasic(
        industry_id="801020",
        industry_name="采掘(已废弃)",
        industry_level="一级",
        parent_id=None,
        is_active=False,
    )

    store.register(industry1)
    store.register(industry2)

    # 只获取活跃行业
    df_active = store.get_all(is_active=True)
    assert len(df_active) == 1
    assert df_active[0, "industry_id"] == "801010"

    # 获取所有行业
    df_all = store.get_all(is_active=False)
    assert len(df_all) == 2
