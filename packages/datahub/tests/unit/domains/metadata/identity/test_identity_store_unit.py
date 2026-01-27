"""IdentityStore unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """创建临时数据库路径."""
    db_path = tmp_path / "test.db"
    # 初始化数据库表
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS identity_mapping (
        sid INTEGER NOT NULL,
        source TEXT NOT NULL,
        src_code TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_to TEXT,
        is_primary BOOLEAN DEFAULT 1,
        PRIMARY KEY (sid, source, src_code, effective_from)
    )"""
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db_path: Path) -> IdentityStore:
    """创建 IdentityStore 实例."""
    return IdentityStore(temp_db_path)


def test_identity_store_resolve_sid_current(store: IdentityStore) -> None:
    """测试解析当前有效的 src_code 到 sid."""
    # 注册测试数据
    store.register(
        sid=1,
        src_code="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 解析当前 sid
    sid = store.resolve_sid("600000.SH", "tushare", None)
    assert sid == 1


def test_identity_store_resolve_sid_historical(store: IdentityStore) -> None:
    """测试解析历史时间点的 src_code 到 sid."""
    # 注册测试数据 - 同一个 src_code 在不同时间映射到不同的 sid
    store.register(
        sid=1,
        src_code="000001.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        sid=2,
        src_code="000001.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 解析 2021 年的 sid（应该是 sid=1）
    sid_2021 = store.resolve_sid("000001.SZ", "tushare", "2021-06-01")
    assert sid_2021 == 1

    # 解析 2023 年的 sid（应该是 sid=2）
    sid_2023 = store.resolve_sid("000001.SZ", "tushare", "2023-06-01")
    assert sid_2023 == 2


def test_identity_store_resolve_sid_not_found(store: IdentityStore) -> None:
    """测试解析不存在的 src_code."""
    sid = store.resolve_sid("999999.SH", "tushare", None)
    assert sid is None


def test_identity_store_resolve_sids_batch(store: IdentityStore) -> None:
    """测试批量解析 src_codes 到 sids."""
    # 注册测试数据
    store.register(
        sid=1,
        src_code="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        sid=2,
        src_code="600001.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 批量解析
    result = store.resolve_sids_batch(
        ["600000.SH", "600001.SH", "999999.SH"],
        "tushare",
        None,
    )
    assert result == {"600000.SH": 1, "600001.SH": 2}
    # 不存在的代码不应该出现在结果中


def test_identity_store_get_src_code_current(store: IdentityStore) -> None:
    """测试反向查询：sid 到当前 src_code."""
    store.register(
        sid=1,
        src_code="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    src_code = store.get_src_code(1, "tushare", None)
    assert src_code == "600000.SH"


def test_identity_store_get_src_code_historical(store: IdentityStore) -> None:
    """测试反向查询历史时间点的 src_code."""
    store.register(
        sid=1,
        src_code="000001.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        sid=1,
        src_code="000001.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 查询 2021 年的 src_code
    src_code_2021 = store.get_src_code(1, "tushare", "2021-06-01")
    assert src_code_2021 == "000001.SZ"


def test_identity_store_get_src_code_not_found(store: IdentityStore) -> None:
    """测试查询不存在的 sid."""
    src_code = store.get_src_code(999, "tushare", None)
    assert src_code is None


def test_identity_store_register(store: IdentityStore) -> None:
    """测试注册 identity_mapping 记录."""
    # 注册记录
    store.register(
        sid=100,
        src_code="600519.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 验证记录已注册
    sid = store.resolve_sid("600519.SH", "tushare", None)
    assert sid == 100


def test_identity_store_pit_query_with_effective_to(store: IdentityStore) -> None:
    """测试 PIT 查询时正确处理 effective_to 字段."""
    # 注册第一条记录
    store.register(
        sid=1,
        src_code="000002.SZ",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 手动更新第一条记录的 effective_to（模拟记录过期）
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    conn.execute(
        "UPDATE identity_mapping SET effective_to = '2022-12-31' "
        "WHERE sid = 1 AND effective_from = '2020-01-01'"
    )
    conn.commit()
    conn.close()

    # 注册第二条记录
    store.register(
        sid=2,
        src_code="000002.SZ",
        source="tushare",
        effective_from="2023-01-01",
        is_primary=True,
    )

    # 查询 2021 年（第一条记录有效）
    sid_2021 = store.resolve_sid("000002.SZ", "tushare", "2021-06-01")
    assert sid_2021 == 1

    # 查询 2023 年（第二条记录有效）
    sid_2023 = store.resolve_sid("000002.SZ", "tushare", "2023-06-01")
    assert sid_2023 == 2

    # 查询当前（应该是第二条记录）
    sid_current = store.resolve_sid("000002.SZ", "tushare", None)
    assert sid_current == 2


def test_identity_store_different_sources(store: IdentityStore) -> None:
    """测试不同数据源的映射."""
    store.register(
        sid=1,
        src_code="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=True,
    )
    store.register(
        sid=1,
        src_code="SH600000",
        source="tdx",
        effective_from="2020-01-01",
        is_primary=True,
    )

    # 从不同数据源解析
    sid_tushare = store.resolve_sid("600000.SH", "tushare", None)
    sid_tdx = store.resolve_sid("SH600000", "tdx", None)

    assert sid_tushare == 1
    assert sid_tdx == 1


def test_identity_store_is_primary_flag(store: IdentityStore) -> None:
    """测试 is_primary 标志的处理."""
    # 注册非主标识符的映射
    store.register(
        sid=1,
        src_code="600000.SH",
        source="tushare",
        effective_from="2020-01-01",
        is_primary=False,
    )

    # 应该能解析到 sid（即使 is_primary=False）
    sid = store.resolve_sid("600000.SH", "tushare", None)
    assert sid == 1
