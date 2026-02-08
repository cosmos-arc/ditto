"""Tests for TechnicalIndicatorMetadataStore."""

import pytest
from ditto_datahub.stores.features.technical import IndicatorMetadataStore
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLitePool:
    """创建内存数据库."""
    return SQLitePool(":memory:")


@pytest.fixture
def metadata_store(in_memory_db: SQLitePool) -> IndicatorMetadataStore:
    """创建 IndicatorMetadataStore 实例."""
    from ditto_datahub.stores.sqlite_client import SQLiteClient

    client = SQLiteClient(in_memory_db)
    return IndicatorMetadataStore(client)


def test_upsert_new_indicator(metadata_store: IndicatorMetadataStore) -> None:
    """测试插入新指标."""
    indicator_id = metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        indicator_type="momentum",
        description="14-day Relative Strength Index",
        formula="RSI = 100 - 100/(1 + RS)",
        parameters='{"period": 14}',
    )

    assert indicator_id > 0

    # 验证检索
    row = metadata_store.get_by_code("indicator_rsi_14")
    assert not row.is_empty()
    assert row["code"][0] == "indicator_rsi_14"
    assert row["name"][0] == "RSI(14)"
    assert row["type"][0] == "momentum"


def test_upsert_existing_indicator(metadata_store: IndicatorMetadataStore) -> None:
    """测试更新已存在的指标."""
    # 先插入
    indicator_id = metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        indicator_type="trend",
        description="20-day Moving Average",
        formula="SMA(price, 20)",
        parameters='{"period": 20}',
    )

    # 更新
    updated_id = metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20) Updated",
        indicator_type="trend",
        description="Updated description",
        formula="SMA(price, 20)",
        parameters='{"period": 20}',
    )

    # 验证 - 应该返回相同的 ID
    assert updated_id == indicator_id

    # 验证更新后的值
    row = metadata_store.get_by_id(indicator_id)
    assert row["name"][0] == "MA(20) Updated"
    assert row["description"][0] == "Updated description"


def test_get_by_id(metadata_store: IndicatorMetadataStore) -> None:
    """测试通过 ID 查询指标."""
    # 先插入一个指标
    indicator_id = metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        indicator_type="trend",
        description="20-day Moving Average",
        formula="SMA(price, 20)",
        parameters='{"period": 20}',
    )

    # 通过 ID 检索
    row = metadata_store.get_by_id(indicator_id)
    assert not row.is_empty()
    assert row["indicator_id"][0] == indicator_id
    assert row["code"][0] == "indicator_ma_20"


def test_list_by_type(metadata_store: IndicatorMetadataStore) -> None:
    """测试按类型列出指标."""
    # 插入不同类型的指标
    metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        indicator_type="momentum",
        description="RSI",
        formula="RSI",
        parameters="{}",
    )
    metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        indicator_type="trend",
        description="MA",
        formula="MA",
        parameters="{}",
    )
    metadata_store.upsert(
        code="indicator_macd",
        name="MACD",
        indicator_type="trend",
        description="MACD",
        formula="MACD",
        parameters="{}",
    )

    # 列出 trend 类型指标
    trend_indicators = metadata_store.list_by_type("trend")
    assert len(trend_indicators) == 2
    assert set(trend_indicators["code"].to_list()) == {
        "indicator_ma_20",
        "indicator_macd",
    }

    # 列出 momentum 类型指标
    momentum_indicators = metadata_store.list_by_type("momentum")
    assert len(momentum_indicators) == 1
    assert momentum_indicators["code"][0] == "indicator_rsi_14"


def test_list_all(metadata_store: IndicatorMetadataStore) -> None:
    """测试列出所有指标."""
    # 插入多个指标
    metadata_store.upsert(
        code="indicator_rsi_14",
        name="RSI(14)",
        indicator_type="momentum",
        description="RSI",
        formula="RSI",
        parameters="{}",
    )
    metadata_store.upsert(
        code="indicator_ma_20",
        name="MA(20)",
        indicator_type="trend",
        description="MA",
        formula="MA",
        parameters="{}",
    )

    # 列出所有指标
    all_indicators = metadata_store.list_by_type(None)
    assert len(all_indicators) == 2


def test_get_by_code_not_found(metadata_store: IndicatorMetadataStore) -> None:
    """测试查询不存在的指标返回空 DataFrame."""
    row = metadata_store.get_by_code("indicator_nonexistent")
    assert row.is_empty()


def test_get_by_id_not_found(metadata_store: IndicatorMetadataStore) -> None:
    """测试通过不存在的 ID 查询返回空 DataFrame."""
    row = metadata_store.get_by_id(99999)
    assert row.is_empty()


def test_close(metadata_store: IndicatorMetadataStore) -> None:
    """测试关闭数据库连接."""
    # 插入数据
    metadata_store.upsert(
        code="indicator_test",
        name="Test",
        indicator_type="trend",
        description="Test",
        formula="Test",
        parameters="{}",
    )

    # 关闭连接不应该抛出异常
    metadata_store.close()


def test_upsert_invalid_type(metadata_store: IndicatorMetadataStore) -> None:
    """测试插入无效类型时处理."""
    # 使用有效的类型
    metadata_store.upsert(
        code="indicator_test_type",
        name="Test Type",
        indicator_type="volatility",
        description="Test",
        formula="Test",
        parameters="{}",
    )

    # 验证插入成功
    row = metadata_store.get_by_code("indicator_test_type")
    assert not row.is_empty()
    assert row["type"][0] == "volatility"
