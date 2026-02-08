"""Tests for MacroService."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.macro.indicator.indicator_store import IndicatorStore
from ditto_datahub.domains.macro.indicator.metadata_store import IndicatorMetadataStore
from ditto_datahub.domains.macro.macro_service import MacroQuery, MacroService
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    return client


@pytest.fixture
def service(in_memory_db: SQLiteClient) -> MacroService:
    """创建 MacroService 实例."""
    indicator_store = IndicatorStore(in_memory_db)
    metadata_store = IndicatorMetadataStore(in_memory_db)
    return MacroService(
        indicator_store=indicator_store,
        metadata_store=metadata_store,
    )


def test_get_indicators_by_code(service: MacroService) -> None:
    """测试按 code 查询指标."""
    # 注册指标
    service._metadata_store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)
    indicator_id = service._metadata_store.get_by_code("CPI_YOY")["indicator_id"][0]

    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [indicator_id],
            "date": [date(2024, 1, 1)],
            "value": [2.5],
        }
    )
    service._indicator_store.write(df)

    # 查询
    query = MacroQuery(indicators=["CPI_YOY"])
    result = service.get_indicators(query)

    # 验证
    assert len(result) == 1
    assert result["code"][0] == "CPI_YOY"
    assert result["value"][0] == 2.5


def test_get_indicators_by_id(service: MacroService) -> None:
    """测试按 ID 查询指标."""
    # 注册指标
    indicator_id = service._metadata_store.upsert(
        "GDP_QOQ", "GDP环比", "economic", "quarterly", True
    )

    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [indicator_id],
            "date": [date(2024, 1, 1)],
            "value": [1.5],
        }
    )
    service._indicator_store.write(df)

    # 查询
    query = MacroQuery(indicators=[indicator_id])
    result = service.get_indicators(query)

    # 验证
    assert len(result) == 1
    assert result["indicator_id"][0] == indicator_id


def test_get_indicators_with_category_filter(service: MacroService) -> None:
    """测试按类别过滤."""
    # 注册多个指标
    service._metadata_store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)
    service._metadata_store.upsert(
        "SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False
    )

    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [1, 2],
            "date": [date(2024, 1, 1), date(2024, 1, 1)],
            "value": [2.5, 2.0],
        }
    )
    service._indicator_store.write(df)

    # 查询 economic 类别
    query = MacroQuery(category="economic")
    result = service.get_indicators(query)

    # 验证
    assert len(result) == 1
    assert result["category"][0] == "economic"


def test_get_indicators_with_pit_query(service: MacroService) -> None:
    """测试 PIT 查询."""
    # 注册 PIT 指标
    indicator_id = service._metadata_store.upsert(
        "CPI_YOY", "CPI同比", "economic", "monthly", True
    )

    # 写入带修正的数据
    df = pl.DataFrame(
        {
            "indicator_id": [indicator_id, indicator_id],
            "date": [date(2024, 1, 1), date(2024, 1, 1)],
            "value": [2.5, 2.6],
            "knowledge_date": [date(2024, 1, 2), date(2024, 1, 10)],
        }
    )
    service._indicator_store.write(df)

    # 查询 1月5日时的数据
    query = MacroQuery(indicators=["CPI_YOY"], asof="2024-01-05")
    result = service.get_indicators(query)

    # 验证 - 应该返回首次发布的版本
    assert len(result) == 1
    assert result["value"][0] == 2.5


def test_mixed_frequency_query(service: MacroService) -> None:
    """测试混合频率查询."""
    # 注册日度和月度指标
    service._metadata_store.upsert(
        "SHIBOR_1M", "SHIBOR 1个月", "interest_rate", "daily", False
    )
    service._metadata_store.upsert("CPI_YOY", "CPI同比", "economic", "monthly", True)

    # 写入数据
    df = pl.DataFrame(
        {
            "indicator_id": [1, 2],
            "date": [date(2024, 1, 1), date(2024, 1, 1)],
            "value": [2.0, 2.5],
        }
    )
    service._indicator_store.write(df)

    # 同时查询日度和月度指标
    query = MacroQuery(indicators=["SHIBOR_1M", "CPI_YOY"])
    result = service.get_indicators(query)

    # 验证 - 返回所有结果
    assert len(result) == 2


def test_empty_result_returns_empty_dataframe(service: MacroService) -> None:
    """测试查询不存在的指标返回空 DataFrame."""
    query = MacroQuery(indicators=["NONEXISTENT"])
    result = service.get_indicators(query)

    # 验证
    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_write_macro_indicators_via_service(service: MacroService) -> None:
    """测试通过 write() 统一入口写入宏观指标."""
    df = pl.DataFrame(
        {
            "indicator_code": ["CPI_YOY"],
            "indicator_name": ["CPI同比"],
            "category": ["economic"],
            "frequency": ["monthly"],
            "need_pit": [True],
            "date": [date(2024, 1, 1)],
            "value": [2.5],
            "knowledge_date": [date(2024, 1, 2)],
        }
    )

    write_result = service.write(df)
    assert write_result.dataset == "macro_indicators"
    assert write_result.records_written == 1

    result = service.query(MacroQuery(indicators=["CPI_YOY"]))
    assert len(result) == 1
    assert result["value"][0] == 2.5
    assert result["code"][0] == "CPI_YOY"


def test_write_raises_on_missing_required_columns(service: MacroService) -> None:
    """缺失必要列时 write() 抛出 ValueError."""
    invalid_df = pl.DataFrame(
        {
            "indicator_code": ["CPI_YOY"],
            # 缺少 indicator_name/category/frequency/need_pit/date/value
            "knowledge_date": [date(2024, 1, 2)],
        }
    )

    with pytest.raises(ValueError, match="缺少必要列"):
        service.write(invalid_df)


def test_invalid_code_raises_error(service: MacroService) -> None:
    """测试查询不存在的 code 应该返回空结果而非报错."""
    # 不注册任何指标，直接查询
    query = MacroQuery(indicators=["NONEXISTENT_CODE"])
    result = service.get_indicators(query)

    # 验证 - 返回空 DataFrame
    assert len(result) == 0
