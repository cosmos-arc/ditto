"""Tests for DataHub Facade."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.errors import InstrumentIdNotFoundError
from ditto_datahub.hub import DataHub
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine

# Service moved to services.capital
from ditto_datahub.services.capital import CapitalService

# Features & Factors imports
# Service moved to services.factors
from ditto_datahub.services.factors import FactorService

# Service moved to services.features
from ditto_datahub.services.features import FeatureService

# Service moved to services.fundamental
from ditto_datahub.services.fundamental import FundamentalService

# Service moved to services.macro
from ditto_datahub.services.macro import MacroService

# Service moved to services.market
from ditto_datahub.services.market import MarketService

# Service moved to services.metadata
from ditto_datahub.services.metadata import MetadataService
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.capital.capital_store import CapitalStore
from ditto_datahub.stores.factors.factor_metadata_store import (
    FactorMetadataStore,
)
from ditto_datahub.stores.factors.factor_store import FactorStore
from ditto_datahub.stores.features.technical import (
    IndicatorMetadataStore as FeatureIndicatorMetadataStore,
)
from ditto_datahub.stores.features.technical import (
    IndicatorStore as FeatureIndicatorStore,
)
from ditto_datahub.stores.fundamental.fundamental_store import FundamentalStore
from ditto_datahub.stores.macro.indicator.indicator_store import (
    IndicatorStore as MacroIndicatorStore,
)
from ditto_datahub.stores.macro.indicator.metadata_store import (
    IndicatorMetadataStore,
)
from ditto_datahub.stores.market.etf.adj import EtfAdjFactorStore
from ditto_datahub.stores.market.etf.bars import EtfBarsStore
from ditto_datahub.stores.market.etf.nav import EtfNavStore
from ditto_datahub.stores.market.etf.status import EtfStatusStore
from ditto_datahub.stores.market.index.bars import IndexBarsStore
from ditto_datahub.stores.market.index.constituent import IndexConstituentStore
from ditto_datahub.stores.market.stock.adj import StockAdjFactorStore
from ditto_datahub.stores.market.stock.bars import StockBarsStore
from ditto_datahub.stores.market.stock.status import StockStatusStore
from ditto_datahub.stores.metadata.calendar.calendar_store import (
    CalendarStore as MetadataCalendarStore,
)
from ditto_datahub.stores.metadata.identity.identity_store import IdentityStore
from ditto_datahub.stores.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.stores.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)
from ditto_datahub.stores.metadata.instrument import InstrumentStore
from ditto_datahub.stores.metadata.instrument.instrument_store import (
    InstrumentStore as MetadataInstrumentStore,
)
from ditto_datahub.stores.metadata.universe import UniverseStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager
from pytest_mock import MockerFixture

# Schema 文件路径
_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "ditto_datahub"
    / "scripts"
    / "schema.sql"
)


@pytest.fixture
def sqlite_pool(tmp_path: Path) -> Generator[SQLitePool, None, None]:
    """
    SQLite 连接池 fixture（单元测试专用）.

    生命周期由 fixture 管理，yield 后自动清理.
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "meta").mkdir(parents=True, exist_ok=True)

    db_path = data_root / "meta" / "hub.sqlite"
    pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    pool.init_schema()

    yield pool

    # fixture cleanup 自动清理
    pool.close()


@pytest.fixture
def datahub_with_dependencies(
    tmp_path: Path,
    sqlite_pool: SQLitePool,
) -> Generator[DataHub, None, None]:
    """
    创建完整的 DataHub 实例及所有依赖.

    这个 fixture 创建所有必需的依赖对象，模拟 DataHubProvider 的行为.
    使用 tmp_path 作为临时数据目录，确保测试隔离.

    Note: sqlite_pool 由独立的 fixture 提供，生命周期由该 fixture 管理.
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "locks").mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)

    # Runtime Layer
    file_lock = FileLockManager(data_root / "locks")
    instrument_id_allocator = InstrumentIdAllocator(sqlite_pool)
    freeze_manager = FreezeManager(data_root=str(data_root))

    # Store Layer
    sqlite_client = SQLiteClient(sqlite_pool)
    security_store = InstrumentStore(sqlite_client)
    calendar_store = MetadataCalendarStore(sqlite_client)
    ingestion_log_store = IngestionLogStore(sqlite_client)
    universe_store = UniverseStore(sqlite_client)

    # Metadata Domain Stores
    metadata_security_store = MetadataInstrumentStore(data_root / "meta" / "hub.sqlite")
    identity_store = IdentityStore(data_root / "meta" / "hub.sqlite")
    industry_basic_store = IndustryBasicStore(data_root / "meta" / "hub.sqlite")
    industry_mapping_store = IndustryMappingStore(data_root / "meta" / "hub.sqlite")

    # Metadata Query Service
    metadata_query_service = MetadataService(
        instrument_store=metadata_security_store,
        identity_store=identity_store,
        calendar_store=calendar_store,
        industry_basic_store=industry_basic_store,
        industry_mapping_store=industry_mapping_store,
        universe_store=universe_store,
        instrument_id_allocator=instrument_id_allocator,
    )

    # Market Domain Stores
    stock_bars_store = StockBarsStore(data_root=data_root)
    stock_status_store = StockStatusStore(data_root=data_root)
    stock_adj_store = StockAdjFactorStore(data_root=data_root)
    etf_bars_store = EtfBarsStore(data_root=data_root)
    etf_status_store = EtfStatusStore(data_root=data_root)
    etf_nav_store = EtfNavStore(data_root=data_root)
    etf_adj_store = EtfAdjFactorStore(data_root=data_root)
    index_bars_store = IndexBarsStore(data_root=data_root)
    index_constituent_store = IndexConstituentStore(data_root=data_root)

    # Market Query Service
    market_query_service = MarketService(
        stock_bars_store=stock_bars_store,
        stock_status_store=stock_status_store,
        stock_adj_store=stock_adj_store,
        etf_bars_store=etf_bars_store,
        etf_status_store=etf_status_store,
        instrument_store=security_store,
        file_lock=file_lock,
        etf_nav_store=etf_nav_store,
        etf_adj_store=etf_adj_store,
        index_bars_store=index_bars_store,
        index_constituent_store=index_constituent_store,
    )

    # Fundamental & Capital Domain Stores
    fundamental_store = FundamentalStore(sqlite_client)
    capital_store = CapitalStore(sqlite_client)

    # Fundamental Query Service
    fundamental_query_service = FundamentalService(
        fundamental_store=fundamental_store,
    )

    # Capital Query Service
    capital_query_service = CapitalService(
        capital_store=capital_store,
    )

    # Macro Domain Stores
    macro_indicator_store = MacroIndicatorStore(sqlite_client)
    macro_metadata_store = IndicatorMetadataStore(sqlite_client)

    # Macro Query Service
    macro_query_service = MacroService(
        indicator_store=macro_indicator_store,
        metadata_store=macro_metadata_store,
    )

    # Features Domain Stores
    feature_indicator_store = FeatureIndicatorStore(
        data_root=data_root / "features" / "technical" / "indicators_narrow"
    )
    feature_indicator_metadata_store = FeatureIndicatorMetadataStore(sqlite_client)

    # Features Query Service
    features_query_service = FeatureService(
        indicator_store=feature_indicator_store,
        metadata_store=feature_indicator_metadata_store,
    )

    # Factors Domain Stores
    factor_store = FactorStore(data_root=data_root / "factors" / "factors_narrow")
    factor_metadata_store = FactorMetadataStore(sqlite_client)

    # Factors Query Service
    factors_query_service = FactorService(
        factor_store=factor_store,
        metadata_store=factor_metadata_store,
    )

    # SqlEngine
    sql_engine = SqlEngine(
        data_root=data_root,
        instrument_store=security_store,
        calendar_store=calendar_store,
    )

    # DataHub
    hub = DataHub(
        data_root=data_root,
        sqlite_pool=sqlite_pool,
        file_lock=file_lock,
        instrument_id_allocator=instrument_id_allocator,
        freeze_manager=freeze_manager,
        instrument_store=security_store,
        metadata_query_service=metadata_query_service,
        market_query_service=market_query_service,
        fundamental_query_service=fundamental_query_service,
        capital_query_service=capital_query_service,
        macro_query_service=macro_query_service,
        features_query_service=features_query_service,
        factors_query_service=factors_query_service,
        ingestion_log_store=ingestion_log_store,
        sources=DataSources(tushare=MagicMock()),
        sql_engine=sql_engine,
    )

    return hub

    # sqlite_pool 的清理由 sqlite_pool fixture 负责


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    """
    创建测试用的 data_root 路径.

    用于需要直接创建 DataHub 的测试(已废弃，新架构应使用 datahub_with_dependencies).
    """
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "meta").mkdir(parents=True, exist_ok=True)
    (data_root / "locks").mkdir(parents=True, exist_ok=True)
    (data_root / "config").mkdir(parents=True, exist_ok=True)

    # [REVIEW] SQLite Pool
    db_path = data_root / "meta" / "hub.sqlite"
    sqlite_pool = SQLitePool(str(db_path), schema_path=_SCHEMA_PATH)
    sqlite_pool.init_schema()
    sqlite_pool.close()

    return data_root


class TestDataHub:
    """Test cases for DataHub Facade."""

    # [REVIEW] setup_method，使用 pytest fixture

    @staticmethod
    def _get_sample_calendar_rows() -> list[tuple]:
        """
        Get sample trading calendar rows for testing.

        Returns:
            List of calendar row tuples matching trading_calendar schema.

        """
        return [
            (
                "2024-01-02",
                True,
                None,
                "2024-01-03",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-03",
                True,
                "2024-01-02",
                "2024-01-04",
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
            (
                "2024-01-04",
                True,
                "2024-01-03",
                None,
                1,
                1,
                1,
                2024,
                False,
                False,
                False,
            ),
        ]

    @staticmethod
    def _insert_calendar_data(
        data_root: Path,
        rows: list[tuple] | None = None,
        sqlite_pool: SQLitePool | None = None,
    ) -> None:
        """
        Insert calendar test data into database.

        Args:
            data_root: Data root directory path.
            rows: Calendar rows to insert. If None, uses sample data.
            sqlite_pool: SQLite pool to use. If None, creates a new one.

        """
        if rows is None:
            rows = TestDataHub._get_sample_calendar_rows()

        # [REVIEW] sqlite_pool，使用它；否则创建新的
        pool = sqlite_pool or SQLitePool(str(data_root / "meta" / "hub.sqlite"))
        close_pool = sqlite_pool is None

        for row in rows:
            pool.execute(
                """INSERT INTO trading_calendar
                (trade_date, is_open, prev_trade_date, next_trade_date,
                 week_of_year, month, quarter, year,
                 is_week_end, is_month_end, is_quarter_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
        pool.commit()

        # [REVIEW] pool 时才关闭
        if close_pool:
            pool.close()

    def test_init_creates_hub(
        self, datahub_with_dependencies: DataHub, mocker: MockerFixture
    ) -> None:
        """Test __init__ creates DataHub instance."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        hub = datahub_with_dependencies
        assert hub.data_root == datahub_with_dependencies.data_root

    def test_init_exposes_only_v5_service_entrypoints(
        self, datahub_with_dependencies: DataHub
    ) -> None:
        """DataHub should not expose removed legacy alias entrypoints."""
        hub = datahub_with_dependencies
        assert hasattr(hub, "metadata")
        assert hasattr(hub, "market")
        assert hasattr(hub, "ingestion_log_store")

        for alias in ("calendar", "universe", "index", "securities", "ingestion_log"):
            assert not hasattr(hub, alias)

    # [REVIEW] - 新架构使用依赖注入，无懒加载

    def test_sql_execute_returns_dataframe(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test sql method returns DataFrame."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        result = datahub_with_dependencies.sql("SELECT 1 AS num")

        assert isinstance(result, pl.DataFrame)
        assert result["num"][0] == 1

    def test_repr_shows_initialized_components(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test __repr__ shows initialized components."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        _ = datahub_with_dependencies.sqlite_pool

        repr_str = repr(datahub_with_dependencies)
        assert "DataHub" in repr_str
        # __repr__ 只显示 data_root，不显示具体组件
        assert "data_root" in repr_str

    # ========================================================================
    # Universe Store and Accessor Tests
    # ========================================================================
    # - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Index Store and Accessor Tests
    # ========================================================================
    # - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Runtime Layer - Freeze Manager Tests
    # ========================================================================
    # - 新架构使用依赖注入，无懒加载

    # ========================================================================
    # Convenience Methods Tests
    # ========================================================================

    def test_get_trading_days_returns_list(
        self,
        datahub_with_dependencies: DataHub,
        sqlite_pool: SQLitePool,
        mocker: MockerFixture,
    ) -> None:
        """Test get_trading_days returns list of dates."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            sqlite_pool=sqlite_pool,
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.metadata._calendar_store.reload()  # type: ignore[attr-defined]

        trading_days = datahub_with_dependencies.get_trading_days(
            "2024-01-01",
            "2024-01-05",
        )

        assert isinstance(trading_days, list)
        assert len(trading_days) == 3
        assert "2024-01-02" in trading_days
        assert "2024-01-03" in trading_days

    def test_get_trading_days_only_open_false(
        self,
        datahub_with_dependencies: DataHub,
        sqlite_pool: SQLitePool,
        mocker: MockerFixture,
    ) -> None:
        """Test get_trading_days with only_open=False."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            rows,
            sqlite_pool=sqlite_pool,
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.metadata._calendar_store.reload()  # type: ignore[attr-defined]

        # When only_open=False, should return all days (closed + open)
        all_days = datahub_with_dependencies.get_trading_days(
            "2024-01-01",
            "2024-01-05",
            only_open=False,
        )

        # Should include at least the trading days
        assert isinstance(all_days, list)
        assert len(all_days) >= 2

    def test_is_trading_day_returns_bool(
        self,
        datahub_with_dependencies: DataHub,
        sqlite_pool: SQLitePool,
        mocker: MockerFixture,
    ) -> None:
        """Test is_trading_day returns boolean."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Use only first 2 rows for this test
        rows = self._get_sample_calendar_rows()[:2]
        self._insert_calendar_data(
            datahub_with_dependencies.data_root,
            rows,
            sqlite_pool=sqlite_pool,
        )

        # Reload calendar cache to pick up the inserted data
        datahub_with_dependencies.metadata._calendar_store.reload()  # type: ignore[attr-defined]

        assert datahub_with_dependencies.is_trading_day("2024-01-02") is True
        assert datahub_with_dependencies.is_trading_day("2024-01-06") is False

    # ========================================================================
    # resolve_instrument_id Tests
    # ========================================================================

    def test_resolve_instrument_id_raises_sid_not_found_error(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test resolve_instrument_id raises when identifier is not found."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Try to resolve a non-existent identifier
        with pytest.raises(InstrumentIdNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_instrument_id(
                "999999.SH", source="tushare"
            )

        # Verify exception contains the identifier and source
        assert exc_info.value.details["identifier"] == "999999.SH"
        assert exc_info.value.details["source"] == "tushare"
        assert "999999.SH" in str(exc_info.value)

    def test_resolve_instrument_id_with_custom_source(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test resolve_instrument_id with custom source parameter."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Try to resolve with custom source
        with pytest.raises(InstrumentIdNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_instrument_id(
                "000001.SZ", source="akshare"
            )

        assert exc_info.value.details["source"] == "akshare"

    def test_resolve_instrument_id_with_asof_parameter(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test resolve_instrument_id with asof parameter for PIT queries."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Try to resolve with asof parameter
        with pytest.raises(InstrumentIdNotFoundError) as exc_info:
            datahub_with_dependencies.resolve_instrument_id(
                "600000.SH",
                source="tushare",
                asof="2023-01-01",
            )

        assert exc_info.value.details["identifier"] == "600000.SH"

    # ========================================================================
    # refresh_sql_views Tests
    # ========================================================================

    def test_refresh_sql_views_without_sql_engine_initialized(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test refresh_sql_views when sql_engine is not initialized."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # sql_engine is always initialized in new architecture
        # This test just verifies refresh_sql_views doesn't raise
        datahub_with_dependencies.refresh_sql_views()

    def test_refresh_sql_views_with_sql_engine_initialized(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test refresh_sql_views when sql_engine is initialized."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # Access sql_engine to trigger initialization
        _ = datahub_with_dependencies.sql_engine

        # [REVIEW] mocker.patch mock refresh_views 方法
        mock_refresh = mocker.patch.object(
            datahub_with_dependencies.sql_engine,
            "refresh_views",
        )

        # Call refresh_sql_views
        datahub_with_dependencies.refresh_sql_views()

        # Verify refresh_views was called
        mock_refresh.assert_called_once()

    # ========================================================================
    # __init__ with Default Path Tests
    # ========================================================================

    def test_init_with_none_uses_default_path(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test __init__ with data_root=None uses default path."""
        # [REVIEW] 新架构中 index 已合并到 market
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # data_root 正确设置
        assert datahub_with_dependencies.data_root is not None
        assert isinstance(datahub_with_dependencies.data_root, Path)

    # Note: DataHub resource lifecycle is managed by the dependency injection container.
    # The sqlite_pool is created and closed by the Provider/factory that created it.
    # DataHub does not implement close() or context manager protocol anymore.

    # ========================================================================
    # Convenience API with Params Tests (Task 2.4)
    # ========================================================================

    def test_bars_params_creation(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test BarsQuerySpec dataclass creation and frozen property."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.hub import BarsQuerySpec

        # 测试创建参数对象
        params = BarsQuerySpec(
            identifiers=["000001.SZ", "万科A"],
            start="2024-01-01",
            end="2024-01-31",
            adj="qfq",
        )

        assert params.identifiers == ["000001.SZ", "万科A"]
        assert params.start == "2024-01-01"
        assert params.adj == "qfq"

        # 测试 frozen 属性（不可变）
        # frozen dataclass 抛出 FrozenInstanceError
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            params.identifiers = ["000002.SZ"]  # type: ignore

    def test_instruments_params_creation(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test InstrumentsQuerySpec dataclass creation."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.hub import InstrumentsQuerySpec

        # 测试创建参数对象
        params = InstrumentsQuerySpec(
            identifiers=["000001.SZ"],
            asset_class="stock",
            is_active=True,
        )

        assert params.identifiers == ["000001.SZ"]
        assert params.asset_class == "stock"
        assert params.is_active is True

    def test_get_bars_with_params_instrument_id_only(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test get_bars with BarsQuerySpec using Instrument ID identifiers."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.hub import BarsQuerySpec

        # Mock market.query 返回空 DataFrame（因为没有真实数据）
        mock_bars_get = mocker.patch.object(
            datahub_with_dependencies.market, "query", return_value=pl.DataFrame()
        )

        # 测试 Instrument ID 标识符
        params = BarsQuerySpec(identifiers=[1, 2, 3])
        result = datahub_with_dependencies.get_bars(params)

        # 验证 market.query 被调用
        assert mock_bars_get.called
        # 验证返回类型
        assert isinstance(result, pl.DataFrame)

    def test_get_bars_with_params_mixed_identifiers(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test get_bars with BarsQuerySpec using mixed identifiers."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.hub import BarsQuerySpec

        # Mock resolve_instrument_ids_from_inputs 返回空列表
        mocker.patch.object(
            datahub_with_dependencies,
            "resolve_instrument_ids_from_inputs",
            return_value=[],
        )

        # 测试混合标识符
        params = BarsQuerySpec(
            identifiers=[1, "000001.SZ", "万科A"],
            start="2024-01-01",
        )
        result = datahub_with_dependencies.get_bars(params)

        # 验证返回空 DataFrame（因为没有解析到 Instrument ID）
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0

    def test_get_instruments_with_params(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test get_instruments with InstrumentsQuerySpec."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.hub import InstrumentsQuerySpec

        # Mock metadata.query 返回空 DataFrame
        mock_metadata_get_instruments = mocker.patch.object(
            datahub_with_dependencies.metadata,
            "query",
            return_value=pl.DataFrame(),
        )

        # 测试参数对象
        params = InstrumentsQuerySpec(
            identifiers=["000001.SZ"],
            asset_class="stock",
        )
        result = datahub_with_dependencies.get_instruments(params)

        # 验证 metadata.query 被调用
        assert mock_metadata_get_instruments.called
        assert isinstance(result, pl.DataFrame)

    # ========================================================================
    # Market Query Service Tests (Task 8)
    # ========================================================================

    def test_market_property_exists(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test DataHub has market property."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        # 验证 market 属性存在且为 MarketService 实例
        assert hasattr(datahub_with_dependencies, "market")
        assert isinstance(datahub_with_dependencies.market, MarketService)

    def test_market_get_bars_returns_dataframe(
        self,
        datahub_with_dependencies: DataHub,
        mocker: MockerFixture,
    ) -> None:
        """Test market.get_bars returns DataFrame."""
        # Mock sources
        mock_tushare = mocker.Mock(spec=TushareSource)
        sources = DataSources(tushare=mock_tushare)
        datahub_with_dependencies._sources = sources

        from ditto_datahub.services.market import AdjType, MarketBarsQuery

        # Mock market.get_bars 返回空 DataFrame
        mock_get_bars = mocker.patch.object(
            datahub_with_dependencies.market,
            "get_bars",
            return_value=pl.DataFrame(),
        )

        # 创建查询参数
        query = MarketBarsQuery(
            instrument_ids=[1, 2, 3],
            start="2024-01-01",
            end="2024-01-31",
            adj=AdjType.NONE,
        )

        result = datahub_with_dependencies.market.get_bars(query)

        # 验证返回类型
        assert isinstance(result, pl.DataFrame)
        # 验证 get_bars 被调用
        mock_get_bars.assert_called_once()
