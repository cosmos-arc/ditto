"""IdentityStore unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_datahub.stores.metadata.identity.identity_store import IdentityStore


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """创建临时数据库路径."""
    db_path = tmp_path / "test.db"
    # 初始化数据库表
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS identity_mapping (
        instrument_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        source_ticker TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        is_primary BOOLEAN DEFAULT 1,
        PRIMARY KEY (instrument_id, source, source_ticker, effective_from)
    )"""
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db_path: Path) -> IdentityStore:
    """创建 IdentityStore 实例."""
    return IdentityStore(temp_db_path)


def test_identity_store_resolve_instrument_id_current(store: IdentityStore) -> None:
    """测试解析当前有效的 source_ticker 到 instrument_id."""
    # 注册测试数据
    store.register(
        instrument_id=1,
        source_ticker="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 解析当前 instrument_id
    instrument_id = store.resolve_instrument_id("600000.SH", "tushare", None)
    assert instrument_id == 1


def test_identity_store_resolve_instrument_id_historical(store: IdentityStore) -> None:
    """测试解析历史时间点的 source_ticker 到 instrument_id."""
    # 注册测试数据 - 同一个 source_ticker 在不同时间映射到不同的 instrument_id
    store.register(
        instrument_id=1,
        source_ticker="000001.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        instrument_id=2,
        source_ticker="000001.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 解析 2021 年的 instrument_id（应该是 instrument_id=1）
    sid_2021 = store.resolve_instrument_id("000001.SZ", "tushare", "2021-06-01")
    assert sid_2021 == 1

    # 解析 2023 年的 instrument_id（应该是 instrument_id=2）
    sid_2023 = store.resolve_instrument_id("000001.SZ", "tushare", "2023-06-01")
    assert sid_2023 == 2


def test_identity_store_resolve_instrument_id_not_found(store: IdentityStore) -> None:
    """测试解析不存在的 source_ticker."""
    instrument_id = store.resolve_instrument_id("999999.SH", "tushare", None)
    assert instrument_id is None


def test_identity_store_resolve_instrument_ids_batch(store: IdentityStore) -> None:
    """测试批量解析 source_tickers 到 instrument_ids."""
    # 注册测试数据
    store.register(
        instrument_id=1,
        source_ticker="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        instrument_id=2,
        source_ticker="600001.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 批量解析
    result = store.resolve_instrument_ids_batch(
        ["600000.SH", "600001.SH", "999999.SH"],
        "tushare",
        None,
    )
    assert result == {"600000.SH": 1, "600001.SH": 2}
    # 不存在的代码不应该出现在结果中


def test_identity_store_get_source_ticker_current(store: IdentityStore) -> None:
    """测试反向查询：instrument_id 到当前 source_ticker."""
    store.register(
        instrument_id=1,
        source_ticker="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    source_ticker = store.get_source_ticker(1, "tushare", None)
    assert source_ticker == "600000.SH"


def test_identity_store_get_source_ticker_historical(store: IdentityStore) -> None:
    """测试反向查询历史时间点的 source_ticker."""
    store.register(
        instrument_id=1,
        source_ticker="000001.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        instrument_id=1,
        source_ticker="000001.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 查询 2021 年的 source_ticker
    source_ticker_2021 = store.get_source_ticker(1, "tushare", "2021-06-01")
    assert source_ticker_2021 == "000001.SZ"


def test_identity_store_get_source_ticker_not_found(store: IdentityStore) -> None:
    """测试查询不存在的 instrument_id."""
    source_ticker = store.get_source_ticker(999, "tushare", None)
    assert source_ticker is None


def test_identity_store_register(store: IdentityStore) -> None:
    """测试注册 identity_mapping 记录."""
    # 注册记录
    store.register(
        instrument_id=100,
        source_ticker="600519.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 验证记录已注册
    instrument_id = store.resolve_instrument_id("600519.SH", "tushare", None)
    assert instrument_id == 100


def test_identity_store_pit_query_with_effective_to(store: IdentityStore) -> None:
    """测试 PIT 查询时正确处理 effective_to 字段."""
    # 注册第一条记录
    store.register(
        instrument_id=1,
        source_ticker="000002.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 手动更新第一条记录的 effective_to（模拟记录过期）
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    conn.execute(
        "UPDATE identity_mapping SET effective_to = '2022-12-31' "
        "WHERE instrument_id = 1 AND effective_from = '2020-01-01'"
    )
    conn.commit()
    conn.close()

    # 注册第二条记录
    store.register(
        instrument_id=2,
        source_ticker="000002.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 查询 2021 年（第一条记录有效）
    instrument_id_2021 = store.resolve_instrument_id(
        "000002.SZ", "tushare", "2021-06-01"
    )
    assert instrument_id_2021 == 1

    # 查询 2023 年（第二条记录有效）
    instrument_id_2023 = store.resolve_instrument_id(
        "000002.SZ", "tushare", "2023-06-01"
    )
    assert instrument_id_2023 == 2

    # 查询当前（应该是第二条记录）
    instrument_id_current = store.resolve_instrument_id("000002.SZ", "tushare", None)
    assert instrument_id_current == 2


def test_identity_store_different_sources(store: IdentityStore) -> None:
    """测试不同数据源的映射."""
    store.register(
        instrument_id=1,
        source_ticker="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        instrument_id=1,
        source_ticker="SH600000",
        source="tdx",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 从不同数据源解析
    sid_tushare = store.resolve_instrument_id("600000.SH", "tushare", None)
    sid_tdx = store.resolve_instrument_id("SH600000", "tdx", None)

    assert sid_tushare == 1
    assert sid_tdx == 1


def test_identity_store_is_primary_flag(store: IdentityStore) -> None:
    """测试 is_primary 标志的处理."""
    # 注册非主标识符的映射
    store.register(
        instrument_id=1,
        source_ticker="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=False,
    )

    # 应该能解析到 instrument_id（即使 is_primary=False）
    instrument_id = store.resolve_instrument_id("600000.SH", "tushare", None)
    assert instrument_id == 1
