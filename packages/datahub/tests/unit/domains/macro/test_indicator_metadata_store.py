"""Tests for IndicatorMetadataStore."""

import pytest
from ditto_datahub.stores.macro.indicator.metadata_store import IndicatorMetadataStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    # 创建表
    client.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            frequency TEXT NOT NULL,
            need_pit BOOLEAN NOT NULL,
            source TEXT,
            unit TEXT,
            description TEXT
        )
    """)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> IndicatorMetadataStore:
    """创建 IndicatorMetadataStore 实例."""
    return IndicatorMetadataStore(in_memory_db)


def test_register_new_indicator(store: IndicatorMetadataStore) -> None:
    """测试注册新指标."""
    # 执行
    indicator_id = store.upsert(
        code="CPI_YOY",
        name="CPI同比",
        category="economic",
        frequency="monthly",
        need_pit=True,
        source="tushare",
        unit="%",
        description="消费者价格指数同比",
    )

    # 验证
    assert indicator_id > 0

    # 查询验证
    result = store.get_by_id(indicator_id)
    assert len(result) == 1
    assert result["code"][0] == "CPI_YOY"
    assert result["name"][0] == "CPI同比"
    assert result["category"][0] == "economic"
    assert result["frequency"][0] == "monthly"
    assert result["need_pit"][0] == True  # noqa: E712 - SQLite returns 1/0 as int
    assert result["source"][0] == "tushare"
    assert result["unit"][0] == "%"


def test_upsert_existing_indicator(store: IndicatorMetadataStore) -> None:
    """测试更新已存在的指标."""
    # 先注册
    indicator_id = store.upsert(
        code="SHIBOR_1M",
        name="SHIBOR 1个月",
        category="interest_rate",
        frequency="daily",
        need_pit=False,
    )

    # 更新
    updated_id = store.upsert(
        code="SHIBOR_1M",
        name="SHIBOR 1个月(修订)",
        category="interest_rate",
        frequency="daily",
        need_pit=False,
        unit="%",
    )

    # 验证 - 应该返回相同的 ID
    assert updated_id == indicator_id

    # 验证更新后的值
    result = store.get_by_id(indicator_id)
    assert result["name"][0] == "SHIBOR 1个月(修订)"
    assert result["unit"][0] == "%"


def test_get_by_code(store: IndicatorMetadataStore) -> None:
    """测试按 code 查询."""
    # 注册
    store.upsert(
        code="GDP_QOQ",
        name="GDP环比",
        category="economic",
        frequency="quarterly",
        need_pit=True,
    )

    # 查询
    result = store.get_by_code("GDP_QOQ")

    # 验证
    assert len(result) == 1
    assert result["code"][0] == "GDP_QOQ"
    assert result["name"][0] == "GDP环比"


def test_get_by_id(store: IndicatorMetadataStore) -> None:
    """测试按 ID 查询."""
    # 注册
    indicator_id = store.upsert(
        code="USD_CNY",
        name="美元/人民币汇率",
        category="exchange_rate",
        frequency="daily",
        need_pit=False,
    )

    # 查询
    result = store.get_by_id(indicator_id)

    # 验证
    assert len(result) == 1
    assert result["indicator_id"][0] == indicator_id
    assert result["code"][0] == "USD_CNY"


def test_list_by_category(store: IndicatorMetadataStore) -> None:
    """测试按类别列出指标."""
    # 注册多个指标
    store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)
    store.upsert("PPI_YOY", "PPI同比", "economic", "monthly", True)
    store.upsert("SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False)
    store.upsert("LPR_1Y", "LPR 1年", "interest_rate", "monthly", False)

    # 查询 economic 类别
    result = store.list_by_category("economic")

    # 验证
    assert len(result) == 2
    codes = result["code"].to_list()
    assert "CPI_YOY" in codes
    assert "PPI_YOY" in codes

    # 查询 interest_rate 类别
    result = store.list_by_category("interest_rate")
    assert len(result) == 2


def test_list_by_category_none(store: IndicatorMetadataStore) -> None:
    """测试列出所有指标."""
    # 注册多个指标
    store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)
    store.upsert("SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False)

    # 查询全部
    result = store.list_by_category(None)

    # 验证
    assert len(result) == 2


def test_is_pit_indicator(store: IndicatorMetadataStore) -> None:
    """测试判断指标是否需要 PIT."""
    # 注册 PIT 指标
    pit_id = store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)

    # 注册非 PIT 指标
    non_pit_id = store.upsert(
        "SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False
    )

    # 验证
    assert store.is_pit_indicator(pit_id) is True
    assert store.is_pit_indicator(non_pit_id) is False


def test_get_frequency(store: IndicatorMetadataStore) -> None:
    """测试获取指标频率."""
    # 注册
    daily_id = store.upsert(
        "SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False
    )
    monthly_id = store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)
    quarterly_id = store.upsert("GDP_QOQ", "GDP环比", "economic", "quarterly", True)

    # 验证
    assert store.get_frequency(daily_id) == "daily"
    assert store.get_frequency(monthly_id) == "monthly"
    assert store.get_frequency(quarterly_id) == "quarterly"


def test_duplicate_code_raises_error(store: IndicatorMetadataStore) -> None:
    """测试重复 code 在同一事务中应被处理."""
    # 第一次注册
    store.upsert("TEST_CODE", "测试指标", "economic", "monthly", True)

    # 第二次注册（相同的 code）- 应该更新而非报错
    # 这是 upsert 的预期行为
    updated_id = store.upsert(
        "TEST_CODE", "测试指标(更新)", "economic", "monthly", True
    )
    assert updated_id > 0

    # 验证已更新
    result = store.get_by_code("TEST_CODE")
    assert result["name"][0] == "测试指标(更新)"
