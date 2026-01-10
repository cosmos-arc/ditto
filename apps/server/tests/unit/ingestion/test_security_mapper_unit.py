"""Tests for SecurityMapper."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Lock

import polars as pl
import pytest
from ditto_datahub.stores.security_store import SecurityStore
from ditto_foundation.observability import Mode, init, reset_for_testing
from ditto_server.ingestion.services.security_mapper import (
    SecurityMapper,
    SecurityRegistrationParams,
    _format_date_for_sqlite,
)


@pytest.fixture
def mock_sid_allocator(mocker):
    """创建 Mock SidAllocator。"""
    allocator = mocker.Mock()

    # 使用计数器模拟递增的 SID 分配
    stock_counter = [1_000_000]
    etf_counter = [2_000_000]

    def allocate_side_effect(asset_class: str) -> int:
        if asset_class == "stock":
            sid = stock_counter[0]
            stock_counter[0] += 1
            return sid
        elif asset_class == "etf":
            sid = etf_counter[0]
            etf_counter[0] += 1
            return sid
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")

    allocator.allocate.side_effect = allocate_side_effect
    return allocator


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    init(mode=Mode.TESTING_WITH_ASSERTIONS, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_security_store(mocker):
    """创建 Mock SecurityStore。"""
    store = mocker.Mock(spec=SecurityStore)
    # 默认情况下 resolve_sid 返回 None (不存在)
    store.resolve_sid.return_value = None
    return store


@pytest.fixture
def mapper(mock_security_store, mock_sid_allocator):
    """创建 SecurityMapper 实例。"""
    return SecurityMapper(mock_security_store, mock_sid_allocator)


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

    def test_uses_custom_source(self, mock_security_store, mock_sid_allocator):
        """使用自定义 source。"""
        # Arrange
        mapper = SecurityMapper(mock_security_store, mock_sid_allocator)
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


def assert_frame_equal(left: pl.DataFrame, right: pl.DataFrame) -> None:
    """辅助函数:断言两个 DataFrame 相等。"""
    assert left.shape == right.shape
    assert left.columns == right.columns
    for col in left.columns:
        assert left[col].to_list() == right[col].to_list()


class TestConcurrency:
    """测试并发场景下的 SID 分配。"""

    def test_concurrent_allocation_with_multiple_mapper_instances(
        self, mock_security_store, mock_sid_allocator
    ):
        """测试多个 SecurityMapper 实例并发分配 SID（模拟多进程场景）。

        这个测试模拟真实的生产环境场景：
        - 多个进程/协程同时运行摄取任务
        - 每个进程创建自己的 SecurityMapper 实例
        - 所有实例共享同一个 SidAllocator（线程安全）
        - 验证 SID 分配是唯一的且没有冲突
        """
        # Arrange
        mock_security_store.resolve_sid.return_value = None  # 都不存在

        # 创建线程安全的 sid 集合来跟踪分配的 SID
        allocated_sids: set[int] = set()
        sid_lock = Lock()

        def allocate_with_new_mapper(idx: int) -> int:
            """使用新的 SecurityMapper 实例分配 SID。"""
            # 每个线程创建自己的 mapper 实例（模拟多进程场景）
            # 但所有实例共享同一个 SidAllocator（线程安全）
            local_mapper = SecurityMapper(mock_security_store, mock_sid_allocator)

            metadata = pl.DataFrame(
                {
                    "ts_code": [f"00000{idx}.SZ"],
                    "symbol": [f"Stock{idx}"],
                    "name": [f"Test Stock {idx}"],
                    "exchange": ["SZ"],
                    "list_date": ["19900101"],
                }
            )
            result = local_mapper.map_or_create(
                src_codes=[f"00000{idx}.SZ"],
                source="tushare",
                asset_class="stock",
                metadata=metadata,
            )
            sid = result[f"00000{idx}.SZ"]

            # 线程安全地添加到集合
            with sid_lock:
                if sid in allocated_sids:
                    raise AssertionError(f"SID {sid} 被重复分配!")
                allocated_sids.add(sid)

            return sid

        # Act: 10 个线程并发分配 SID，每个线程使用独立的 mapper 实例
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(allocate_with_new_mapper, i) for i in range(10)]
            results = [f.result() for f in futures]

        # Assert: 所有 SID 应该唯一
        assert len(set(results)) == 10, f"所有 SID 应该唯一, 但得到: {results}"
        assert len(results) == 10, "应该分配 10 个 SID"


class TestFormatDateForSqlite:
    """测试 _format_date_for_sqlite 辅助函数。"""

    def test_formats_date_object(self):
        """测试转换 date 对象为 SQLite 格式。"""
        # Arrange
        input_date = date(2024, 1, 2)

        # Act
        result = _format_date_for_sqlite(input_date)

        # Assert
        assert result == "20240102"

    def test_formats_string_with_dashes(self):
        """测试转换带连字符的日期字符串。"""
        # Arrange
        input_date = "2024-01-02"

        # Act
        result = _format_date_for_sqlite(input_date)

        # Assert
        assert result == "20240102"

    def test_returns_default_for_none(self):
        """测试 None 返回默认日期。"""
        # Act
        result = _format_date_for_sqlite(None)

        # Assert
        assert result == "19900101"

    def test_passes_through_formatted_string(self):
        """测试已格式化的字符串直接返回。"""
        # Arrange
        input_date = "19900101"

        # Act
        result = _format_date_for_sqlite(input_date)

        # Assert
        assert result == "19900101"


class TestRegisterSecurity:
    """测试 _register_security 方法。"""

    def test_handles_missing_metadata(self, mapper, mock_security_store):
        """测试元数据缺失时使用默认值。"""
        # Arrange
        mock_security_store.resolve_sid.return_value = None
        empty_metadata = pl.DataFrame(
            schema={
                "ts_code": pl.String,
                "symbol": pl.String,
                "name": pl.String,
                "exchange": pl.String,
                "list_date": pl.String,
            }
        )

        params = SecurityRegistrationParams(
            src_code="000001.SZ",
            sid=1000000,
            source="tushare",
            asset_class="stock",
            metadata=empty_metadata,
            src_code_col="ts_code",
        )

        # Act
        mapper._register_security(params)

        # Assert
        mock_security_store.register.assert_called_once_with(
            sid=1000000,
            source="tushare",
            src_code="000001.SZ",
            symbol="000001.SZ",  # 默认使用 src_code
            name="000001.SZ",  # 默认使用 src_code
            exchange="UNKNOWN",  # 默认值
            asset_class="stock",
            list_date="19900101",  # 默认值
            board=None,
        )

    def test_skips_when_already_registered_concurrently(
        self, mapper, mock_security_store
    ):
        """测试并发竞态时跳过注册。"""
        # Arrange
        # _register_security 开始时会检查是否已注册
        # 如果已存在（并发竞态），直接返回不注册
        mock_security_store.resolve_sid.return_value = 1000001

        params = SecurityRegistrationParams(
            src_code="000001.SZ",
            sid=1000000,
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
            src_code_col="ts_code",
        )

        # Act
        mapper._register_security(params)

        # Assert
        # 不应该调用 register，因为检测到已注册
        mock_security_store.register.assert_not_called()
        mock_security_store.resolve_sid.assert_called_once_with(
            "000001.SZ", "tushare", None
        )
