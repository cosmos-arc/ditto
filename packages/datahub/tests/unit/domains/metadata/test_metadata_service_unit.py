"""MetadataService unit tests."""

from __future__ import annotations

from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.domains.metadata.instrument.models import InstrumentRegistration
from ditto_datahub.domains.metadata.metadata_service import MetadataService


@pytest.fixture
def mock_stores_and_allocator() -> dict[str, Mock]:
    """创建所有必需的 Store 和 Allocator Mock 对象."""
    return {
        "instrument_store": Mock(),
        "identity_store": Mock(),
        "calendar_store": Mock(),
        "industry_basic_store": Mock(),
        "industry_mapping_store": Mock(),
        "universe_store": Mock(),
        "instrument_id_allocator": Mock(),
    }


@pytest.fixture
def service(
    mock_stores_and_allocator: dict[str, Mock],
) -> MetadataService:
    """创建 MetadataService 实例."""
    return MetadataService(**mock_stores_and_allocator)


def test_metadata_service_resolve_instrument_id(service: MetadataService) -> None:
    """测试解析 source_ticker 到 instrument_id."""
    # 设置 mock
    service._identity_store.resolve_instrument_id.return_value = 123

    # 调用方法
    result = service.resolve_instrument_id("600000.SH", "tushare", None)

    # 验证
    assert result == 123
    service._identity_store.resolve_instrument_id.assert_called_once_with(
        "600000.SH", "tushare", None
    )


def test_metadata_service_resolve_instrument_ids_batch(
    service: MetadataService,
) -> None:
    """测试批量解析 source_tickers 到 instrument_ids."""
    # 设置 mock
    service._identity_store.resolve_instrument_ids_batch.return_value = {
        "600000.SH": 1,
        "600001.SH": 2,
    }

    # 调用方法
    result = service.resolve_instrument_ids_batch(
        ["600000.SH", "600001.SH", "999999.SH"], "tushare", None
    )

    # 验证
    assert result == {"600000.SH": 1, "600001.SH": 2}
    service._identity_store.resolve_instrument_ids_batch.assert_called_once()


def test_metadata_service_get_securities(service: MetadataService) -> None:
    """测试查询证券数据."""
    # 准备测试数据
    test_df = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "symbol": ["平安银行", "万科A"],
            "name": ["平安银行股份有限公司", "万科企业股份有限公司"],
            "exchange": ["SZ", "SZ"],
            "asset_class": ["stock", "stock"],
        }
    )

    # 设置 mock
    service._instrument_store.find_securities.return_value = test_df

    # 调用方法
    result = service.get_securities(instrument_ids=[1, 2])

    # 验证
    assert len(result) == 2
    assert result["instrument_id"].to_list() == [1, 2]
    service._instrument_store.find_securities.assert_called_once()


def test_metadata_service_get_symbol(service: MetadataService) -> None:
    """测试根据 instrument_id 获取 symbol."""
    # 设置 mock
    service._instrument_store.get_symbol.return_value = "平安银行"

    # 调用方法
    result = service.get_symbol(1)

    # 验证
    assert result == "平安银行"
    service._instrument_store.get_symbol.assert_called_once_with(1)


def test_metadata_service_get_source_ticker(
    service: MetadataService,
) -> None:
    """测试根据 instrument_id 获取 source_ticker."""
    # 设置 mock
    service._identity_store.get_source_ticker.return_value = "000001.SZ"

    # 调用方法（注意：方法名仍然是 get_source_ticker，这是为了向后兼容）
    result = service.get_source_ticker(1, "tushare", None)

    # 验证
    assert result == "000001.SZ"
    service._identity_store.get_source_ticker.assert_called_once_with(
        1, "tushare", None
    )


def test_metadata_service_get_industries(service: MetadataService) -> None:
    """测试查询行业数据."""
    # 准备测试数据
    test_df = pl.DataFrame(
        {
            "industry_id": ["sw_l1_01", "sw_l1_02"],
            "industry_name": ["银行", "非银金融"],
            "industry_level": ["l1", "l1"],
        }
    )

    # 设置 mock
    service._industry_basic_store.get_all.return_value = test_df

    # 调用方法
    result = service.get_industries()

    # 验证
    assert len(result) == 2
    assert result["industry_id"].to_list() == ["sw_l1_01", "sw_l1_02"]
    service._industry_basic_store.get_all.assert_called_once()


def test_metadata_service_get_stock_industry(
    service: MetadataService,
) -> None:
    """测试查询股票所属行业."""
    # 准备测试数据
    test_data = {
        "instrument_id": 1,
        "industry_id": "sw_l1_01",
        "industry_name": "银行",
        "effective_from": "2020-01-01",
    }

    # 设置 mock
    service._industry_mapping_store.get_stock_industry.return_value = test_data

    # 调用方法
    result = service.get_stock_industry(1, None)

    # 验证
    assert result == test_data
    service._industry_mapping_store.get_stock_industry.assert_called_once_with(1, None)


def test_metadata_service_get_industry_stocks(
    service: MetadataService,
) -> None:
    """测试查询行业成分股."""
    # 设置 mock
    service._industry_mapping_store.get_stocks.return_value = [1, 2, 3]

    # 调用方法
    result = service.get_industry_stocks("sw_l1_01", None)

    # 验证
    assert result == [1, 2, 3]
    service._industry_mapping_store.get_stocks.assert_called_once_with("sw_l1_01", None)


def test_metadata_service_get_trading_days(
    service: MetadataService,
) -> None:
    """测试查询交易日."""
    # 设置 mock
    service._calendar_store.get_range.return_value = [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
    ]

    # 调用方法
    result = service.get_trading_days("2024-01-01", "2024-01-05", True)

    # 验证
    assert len(result) == 3
    assert result[0] == "2024-01-02"
    service._calendar_store.get_range.assert_called_once_with(
        "2024-01-01", "2024-01-05"
    )


def test_metadata_service_is_trading_day(service: MetadataService) -> None:
    """测试判断是否为交易日."""
    # 设置 mock
    service._calendar_store.is_trading_day.return_value = True

    # 调用方法
    result = service.is_trading_day("2024-01-02")

    # 验证
    assert result is True
    service._calendar_store.is_trading_day.assert_called_once_with("2024-01-02")


def test_metadata_service_get_universe(service: MetadataService) -> None:
    """测试查询标的池成分股."""
    # 设置 mock
    service._universe_store.get_constituents_sids.return_value = [1, 2, 3, 4, 5]

    # 调用方法
    result = service.get_universe("hs300", None)

    # 验证
    assert result == [1, 2, 3, 4, 5]
    service._universe_store.get_constituents_sids.assert_called_once_with("hs300", None)


def test_metadata_service_register_security(
    service: MetadataService,
) -> None:
    """测试注册新证券."""
    # 准备测试数据
    registration = InstrumentRegistration(
        source_ticker="600000.SH",
        symbol="浦发银行",
        name="上海浦东发展银行股份有限公司",
        exchange="SH",
        asset_class="stock",
        list_date="1999-11-10",
        source="tushare",
        board="主板",
    )

    # 设置 mock
    service._instrument_id_allocator.allocate.return_value = 100
    service._instrument_store.register.return_value = 100

    # 调用方法
    result = service.register_security(registration)

    # 验证
    assert result == 100
    service._instrument_id_allocator.allocate.assert_called_once_with("stock")
    service._instrument_store.register.assert_called_once()
