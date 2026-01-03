"""Tests for SecurityMapper."""

from unittest.mock import Mock

import polars as pl
import pytest
from ditto_datahub.stores.security_store import SecurityStore
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_server.ingestion.services.security_mapper import SecurityMapper


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_security_store():
    """创建 Mock SecurityStore。"""
    store = Mock(spec=SecurityStore)
    # 默认情况下 resolve_sid 返回 None (不存在)
    store.resolve_sid.return_value = None
    return store


@pytest.fixture
def mapper(mock_security_store):
    """创建 SecurityMapper 实例。"""
    return SecurityMapper(mock_security_store)


class TestMapOrCreate:
    """测试 map_or_create 方法。"""

    def test_maps_existing_single_code(self, mapper, mock_security_store):
        """映射已存在的单个 src_code。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = 1000001

        # Act
        result = mapper.map_or_create(
            src_codes=["000001.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "symbol": ["平安银行"],
                    "name": ["平安银行股份有限公司"],
                    "exchange": ["SZ"],
                    "list_date": ["19910403"],
                }
            ),
        )

        # Assert
        assert result == {"000001.SZ": 1000001}
        mock_security_store.resolve_sid.assert_called_once_with(
            "000001.SZ", "tushare", None
        )
        mock_security_store.register.assert_not_called()

    def test_maps_existing_multiple_codes(self, mapper, mock_security_store):
        """映射已存在的多个 src_codes。"""

        # Arrange
        def resolve_side_effect(code, source, asof):
            return {"000001.SZ": 1000001, "000002.SZ": 1000002}.get(code)

        mock_security_store.resolve_sid.side_effect = resolve_side_effect

        # Act
        result = mapper.map_or_create(
            src_codes=["000001.SZ", "000002.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "symbol": ["平安银行", "万科A"],
                    "name": ["平安银行股份有限公司", "万科企业股份有限公司"],
                    "exchange": ["SZ", "SZ"],
                    "list_date": ["19910403", "19910129"],
                }
            ),
        )

        # Assert
        assert result == {
            "000001.SZ": 1000001,
            "000002.SZ": 1000002,
        }
        assert mock_security_store.resolve_sid.call_count == 2
        mock_security_store.register.assert_not_called()

    def test_creates_new_stock_security(self, mapper, mock_security_store):
        """为不存在的股票创建新 SID。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None  # 不存在

        # Act
        result = mapper.map_or_create(
            src_codes=["000001.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "symbol": ["平安银行"],
                    "name": ["平安银行股份有限公司"],
                    "exchange": ["SZ"],
                    "list_date": ["19910403"],
                }
            ),
        )

        # Assert
        assert result == {"000001.SZ": 1000000}  # 股票 SID 从 1000000 开始
        mock_security_store.register.assert_called_once_with(
            sid=1000000,
            source="tushare",
            src_code="000001.SZ",
            symbol="平安银行",
            name="平安银行股份有限公司",
            exchange="SZ",
            asset_class="stock",
            list_date="19910403",
            board=None,
        )

    def test_creates_new_etf_security(self, mapper, mock_security_store):
        """为不存在的 ETF 创建新 SID。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None

        # Act
        result = mapper.map_or_create(
            src_codes=["510300.SH"],
            source="tushare",
            asset_class="etf",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["510300.SH"],
                    "symbol": ["300ETF"],
                    "name": ["华泰柏瑞沪深300ETF"],
                    "exchange": ["SH"],
                    "list_date": ["20120507"],
                }
            ),
        )

        # Assert
        assert result == {"510300.SH": 2000000}  # ETF SID 从 2000000 开始
        mock_security_store.register.assert_called_once_with(
            sid=2000000,
            source="tushare",
            src_code="510300.SH",
            symbol="300ETF",
            name="华泰柏瑞沪深300ETF",
            exchange="SH",
            asset_class="etf",
            list_date="20120507",
            board=None,
        )

    def test_mixes_existing_and_new_codes(self, mapper, mock_security_store):
        """混合处理已存在和不存在的 src_codes。"""

        # Arrange
        def resolve_side_effect(code, source, asof):
            return {"000001.SZ": 1000001}.get(code)  # 000002.SZ 返回 None

        mock_security_store.resolve_sid.side_effect = resolve_side_effect

        # Act
        result = mapper.map_or_create(
            src_codes=["000001.SZ", "000002.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "symbol": ["平安银行", "万科A"],
                    "name": ["平安银行股份有限公司", "万科企业股份有限公司"],
                    "exchange": ["SZ", "SZ"],
                    "list_date": ["19910403", "19910129"],
                }
            ),
        )

        # Assert
        assert result == {
            "000001.SZ": 1000001,  # 已存在
            "000002.SZ": 1000000,  # 新创建
        }

    def test_allocates_incrementing_sids_for_stocks(self, mapper, mock_security_store):
        """为股票分配递增的 SID。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None  # 都不存在

        # Act
        result = mapper.map_or_create(
            src_codes=["000001.SZ", "000002.SZ", "000003.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
                    "symbol": ["平安银行", "万科A", "国农科技"],
                    "name": [
                        "平安银行股份有限公司",
                        "万科企业股份有限公司",
                        "国农科技股份有限公司",
                    ],
                    "exchange": ["SZ", "SZ", "SZ"],
                    "list_date": ["19910403", "19910129", "19901212"],
                }
            ),
        )

        # Assert
        assert result == {
            "000001.SZ": 1000000,
            "000002.SZ": 1000001,
            "000003.SZ": 1000002,
        }

    def test_allocates_incrementing_sids_for_etfs(self, mapper, mock_security_store):
        """为 ETF 分配递增的 SID。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None

        # Act
        result = mapper.map_or_create(
            src_codes=["510300.SH", "510500.SH"],
            source="tushare",
            asset_class="etf",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["510300.SH", "510500.SH"],
                    "symbol": ["300ETF", "500ETF"],
                    "name": ["华泰柏瑞沪深300ETF", "南方中证500ETF"],
                    "exchange": ["SH", "SH"],
                    "list_date": ["20120507", "20130318"],
                }
            ),
        )

        # Assert
        assert result == {
            "510300.SH": 2000000,
            "510500.SH": 2000001,
        }

    def test_uses_cache_for_subsequent_calls(self, mapper, mock_security_store):
        """后续调用使用缓存。"""

        # Arrange
        def resolve_side_effect(code, source, asof):
            # 000001.SZ 存在,000002.SZ 不存在
            if code == "000001.SZ":
                return 1000001
            return None

        mock_security_store.resolve_sid.side_effect = resolve_side_effect

        # Act - 第一次调用
        result1 = mapper.map_or_create(
            src_codes=["000001.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "symbol": ["平安银行"],
                    "name": ["平安银行股份有限公司"],
                    "exchange": ["SZ"],
                    "list_date": ["19910403"],
                }
            ),
        )

        # Act - 第二次调用相同代码
        result2 = mapper.map_or_create(
            src_codes=["000001.SZ", "000002.SZ"],
            source="tushare",
            asset_class="stock",
            metadata=pl.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "symbol": ["平安银行", "万科A"],
                    "name": ["平安银行股份有限公司", "万科企业股份有限公司"],
                    "exchange": ["SZ", "SZ"],
                    "list_date": ["19910403", "19910129"],
                }
            ),
        )

        # Assert - 000001.SZ 第二次从缓存获取
        # resolve_sid 调用:
        # 1. 第一次调用: 000001.SZ
        # 2. 第二次调用: 000002.SZ (map_or_create 中)
        # 3. 第三次调用: 000002.SZ (_register_security 中并发检查)
        assert (
            mock_security_store.resolve_sid.call_count == 3
        )  # 000001.SZ (第一次) + 000002.SZ (第二次) + 000002.SZ 并发检查
        assert result1 == {"000001.SZ": 1000001}
        assert result2 == {
            "000001.SZ": 1000001,  # 从缓存获取
            "000002.SZ": 1000000,  # 新创建的
        }


class TestEnrichDataFrame:
    """测试 enrich_dataframe 方法。"""

    def test_enriches_stock_dataframe(self, mapper, mock_security_store):
        """为股票 DataFrame 添加 sid 列。"""

        # Arrange
        def resolve_side_effect(code, source, asof):
            return {"000001.SZ": 1000001, "000002.SZ": 1000002}.get(code)

        mock_security_store.resolve_sid.side_effect = resolve_side_effect

        df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "close": [10.5, 15.3],
            }
        )

        # Act
        result = mapper.enrich_dataframe(
            df, src_code_col="ts_code", asset_class="stock"
        )

        # Assert
        expected = pl.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "close": [10.5, 15.3],
                "sid": [1000001, 1000002],
                "source": ["tushare", "tushare"],
            }
        )
        assert_frame_equal(result, expected)

    def test_enriches_etf_dataframe(self, mapper, mock_security_store):
        """为 ETF DataFrame 添加 sid 列。"""

        # Arrange
        def resolve_side_effect(code, source, asof):
            return {"510300.SH": 2000001}.get(code)

        mock_security_store.resolve_sid.side_effect = resolve_side_effect

        df = pl.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "close": [4.5],
            }
        )

        # Act
        result = mapper.enrich_dataframe(df, src_code_col="ts_code", asset_class="etf")

        # Assert
        expected = pl.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "close": [4.5],
                "sid": [2000001],
                "source": ["tushare"],
            }
        )
        assert_frame_equal(result, expected)

    def test_creates_new_sid_when_not_exists(self, mapper, mock_security_store):
        """当 SID 不存在时创建新的。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None

        df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "close": [10.5],
            }
        )

        # Act
        result = mapper.enrich_dataframe(
            df, src_code_col="ts_code", asset_class="stock"
        )

        # Assert
        expected = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "close": [10.5],
                "sid": [1000000],
                "source": ["tushare"],
            }
        )
        assert_frame_equal(result, expected)
        mock_security_store.register.assert_called_once()

    def test_handles_empty_dataframe(self, mapper, mock_security_store):
        """处理空 DataFrame。"""
        # Arrange
        df = pl.DataFrame(
            {
                "ts_code": [],
                "close": [],
            }
        )

        # Act
        result = mapper.enrich_dataframe(
            df, src_code_col="ts_code", asset_class="stock"
        )

        # Assert
        expected = pl.DataFrame(
            {
                "ts_code": [],
                "close": [],
                "sid": [],
                "source": [],
            }
        )
        assert_frame_equal(result, expected)
        mock_security_store.resolve_sid.assert_not_called()

    def test_uses_custom_source(self, mock_security_store):
        """使用自定义 source。"""
        # Arrange
        mapper = SecurityMapper(mock_security_store)
        mock_security_store.resolve_sid.return_value = 1000001

        df = pl.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "close": [10.5],
            }
        )

        # Act
        result = mapper.enrich_dataframe(
            df,
            src_code_col="ts_code",
            asset_class="stock",
            source="custom_source",
        )

        # Assert
        assert result["source"][0] == "custom_source"
        mock_security_store.resolve_sid.assert_called_once_with(
            "000001.SZ", "custom_source", None
        )


def assert_frame_equal(left, right):
    """辅助函数:断言两个 DataFrame 相等。"""
    assert left.shape == right.shape
    assert left.columns == right.columns
    for col in left.columns:
        assert left[col].to_list() == right[col].to_list()
