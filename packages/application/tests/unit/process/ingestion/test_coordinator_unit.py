"""Tests for IngestionCoordinator."""

from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.config import IngestionCoordinatorConfig
from ditto_application.processes.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionServices,
    MarketServices,
    SourceFetchers,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.errors import SourceFetchError
from ditto_data.lineage import InMemoryDataLineage
from ditto_data.models.ingestion import IngestionLog, IngestionResult, IngestionStatus
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    OnDuplicate,
    init,
    reset_for_testing,
)


def mock_market_save_bars(file_path: str, checksum: str) -> int:
    """创建 Mock MarketService.save_bars() 的返回值（行情数据）。"""
    _ = file_path, checksum
    return 2


def mock_market_save_adj_factor() -> int:
    """创建 Mock MarketService.save_adj_factor() 的返回值（复权因子）。"""
    return 1


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性。"""
    reset_for_testing()
    config = ObservabilityConfig(
        environment=Environment.TESTING,
        pytest_running=True,
        assertions_enabled=True,
        verbose_logging=False,
        tracing_enabled=True,
        tracing_sample_rate=1.0,
        metrics_enabled=True,
    )
    init(config, force=True)
    yield
    reset_for_testing()


@pytest.fixture
def mock_metadata_service(mocker):
    """创建 Mock MetadataService。"""
    service = mocker.Mock()
    service.is_trading_day.return_value = True
    service.upsert.return_value = len
    service.list_trading_days.return_value = []
    service.get_securities.return_value = pl.DataFrame()

    # Instrument 相关方法
    service.instrument.register_instruments_batch = mocker.Mock()
    service.instrument.resolve_or_create_instruments_batch = mocker.Mock()
    service.instrument.resolve_instrument_ids_batch = mocker.Mock()

    # 设置默认的 side_effect
    stock_counter = [1_000_000]
    etf_counter = [2_000_000]
    index_counter = [3_000_000]

    def register_side_effect(df, source, asset_class, **kwargs):
        _ = df, source, kwargs
        return (f"instrument_store:{asset_class}_basic", f"checksum_{asset_class}")

    def resolve_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        if asset_class == "stock":
            instrument_id = stock_counter[0]
            stock_counter[0] += 1
        elif asset_class == "etf":
            instrument_id = etf_counter[0]
            etf_counter[0] += 1
        elif asset_class == "index":
            instrument_id = index_counter[0]
            index_counter[0] += 1
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: instrument_id}

    def resolve_ids_side_effect(identifiers, source, asof, **kwargs):
        """为 resolve_instrument_ids_batch 模拟返回值."""
        _ = source, asof, kwargs
        result = {}
        for i, ticker in enumerate(identifiers):
            # 简单映射：每个 ticker 映射到一个 instrument_id
            result[ticker] = 1_000_000 + i
        return result

    service.instrument.register_instruments_batch.side_effect = register_side_effect
    service.instrument.resolve_or_create_instruments_batch.side_effect = (
        resolve_side_effect
    )
    service.instrument.resolve_instrument_ids_batch.side_effect = (
        resolve_ids_side_effect
    )

    return service


@pytest.fixture
def mock_market_write_service(mocker):
    """创建 Mock MarketService。"""
    service = mocker.Mock()

    # save_* 方法现在返回 int (写入的行数)
    service.save_bars.return_value = 1
    service.save_adj_factor.return_value = 1
    service.save_stock_status.return_value = 1
    return service


@pytest.fixture
def mock_fundamental_store(mocker):
    """创建 Mock FundamentalStore。"""
    service = mocker.Mock()
    service.write.return_value = mocker.Mock(records_written=1)
    return service


@pytest.fixture
def mock_capital_store(mocker):
    """创建 Mock CapitalStore。"""
    service = mocker.Mock()
    service.write.return_value = mocker.Mock(records_written=1)
    return service


@pytest.fixture
def mock_macro_service(mocker):
    """创建 Mock MacroService。"""
    service = mocker.Mock()
    service.write.return_value = mocker.Mock(records_written=1)
    return service


@pytest.fixture
def mock_ingestion_log_store(mocker):
    """创建 Mock IngestionLogStore。"""
    service = mocker.Mock()
    service.get_log = mocker.Mock(return_value=None)
    service.save_log = mocker.Mock(return_value=None)
    service.list_ingested_dates = mocker.Mock(return_value=[])
    return service


@pytest.fixture
def mock_quality_checker(mocker):
    """Create a passing write-time L1/L2 gate for production-like ingestion."""
    checker = mocker.Mock()
    checker.handle.side_effect = lambda command: (command.df, False)
    return checker


@pytest.fixture
def in_memory_catalog() -> InMemoryDataCatalog:
    """Share the coordinator's durable catalog with evidence-oriented tests."""
    return InMemoryDataCatalog()


@pytest.fixture
def mock_source(mocker):
    """创建 Mock DataSource。"""
    from ditto_data.sources.tushare.tushare_source import TushareSource

    source = mocker.Mock(spec=TushareSource)
    return source


@pytest.fixture
def coordinator(
    mock_metadata_service,
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_macro_service,
    mock_ingestion_log_store,
    mock_quality_checker,
    mock_source,
    in_memory_catalog,
):
    """创建 IngestionCoordinator 实例。"""
    return IngestionCoordinator(
        services=IngestionServices(
            metadata=mock_metadata_service,
            market=MarketServices(
                query=mock_market_write_service,
                write=mock_market_write_service,
            ),
            fundamental=mock_fundamental_store,
            capital=mock_capital_store,
            macro=mock_macro_service,
        ),
        fetchers=SourceFetchers(
            metadata=mock_source,
            market=mock_source,
            fundamental=mock_source,
            capital=mock_source,
            macro=mock_source,
        ),
        config=IngestionCoordinatorConfig(
            ingestion_log_store=mock_ingestion_log_store,
            quality_checker=mock_quality_checker,
            catalog_reader=in_memory_catalog,
            catalog_writer=in_memory_catalog,
        ),
    )


@pytest.mark.unit
class TestIngestionResult:
    """测试 IngestionResult 类。"""

    def test_create_success_result(self) -> None:
        """创建成功结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="success",
            row_count=1000,
            checksum="abc123",
            message="数据摄取成功",
        )

        assert result.dataset == "stock_daily"
        assert result.trade_date == "2024-12-27"
        assert result.status == "success"
        assert result.row_count == 1000
        assert result.checksum == "abc123"
        assert result.message == "数据摄取成功"
        assert result.error is None

    def test_create_skipped_result(self) -> None:
        """创建跳过结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="skipped",
            message="数据已存在",
        )

        assert result.status == "skipped"
        assert result.row_count is None
        assert result.checksum is None

    def test_create_failed_result(self) -> None:
        """创建失败结果。"""
        result = IngestionResult(
            dataset="stock_daily",
            trade_date="2024-12-27",
            status="failed",
            error="FETCH_ERROR",
            message="获取数据失败",
        )

        assert result.status == "failed"
        assert result.error == "FETCH_ERROR"
        assert result.row_count is None


@pytest.mark.unit
class TestIngestDate:
    """测试 ingest_date 方法。"""

    def test_ingest_date_skipped_when_previous_success(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        in_memory_catalog,
    ) -> None:
        """历史成功时跳过摄取。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="abc123",
            rows=1000,
        )
        in_memory_catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="market.stock_daily.v1",
                    row_count=1000,
                ),
                source="tushare",
                freshness_at=datetime(2024, 12, 27, tzinfo=UTC),
                source_snapshot_id=(
                    "snapshot:tushare:stock_daily:2024-12-27:abc123:quality=l1-l2"
                ),
            )
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "skipped"
        assert (
            "成功" in result.message
            or "SUCCESS" in result.message
            or "已存在" in result.message
        )
        assert result.checksum == "abc123"
        assert result.row_count == 1000
        assert result.quality_evidence is not None
        assert result.quality_evidence.kind == "persisted_ingestion_l1_l2"
        assert result.quality_evidence.checksum == "abc123"
        # 不应该调用 source
        mock_source.fetch_stock_daily.assert_not_called()

    def test_sparse_same_day_skip_returns_cumulative_pit_snapshot(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
    ) -> None:
        catalog = InMemoryDataCatalog()
        for partition_date, checksum, rows in (
            ("2024-12-20", "old", 3),
            ("2024-12-27", "current", 2),
        ):
            catalog.upsert_asset(
                DataCatalogEntry(
                    asset=DataAssetRef(
                        dataset_id="balance_sheet",
                        namespace="fundamental",
                        partition_keys=(f"trade_date={partition_date}",),
                    ),
                    storage_uri=f"balance_sheet/{partition_date}",
                    schema=DataSchemaFingerprint(
                        schema_hash="fundamental.balance_sheet.v1",
                        row_count=rows,
                    ),
                    source="tushare",
                    freshness_at=datetime(2024, 12, 27, tzinfo=UTC),
                    source_snapshot_id=(
                        f"snapshot:tushare:balance_sheet:{partition_date}:"
                        f"{checksum}:quality=l1-l2"
                    ),
                )
            )
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="balance_sheet",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="current",
            rows=2,
        )
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_store=mock_ingestion_log_store,
                catalog_reader=catalog,
            ),
        )

        result = coordinator.ingest_date("balance_sheet", "2024-12-27")

        assert result.status == "skipped"
        assert result.checksum is None
        assert result.snapshot_evidence is not None
        assert result.snapshot_evidence.row_count == 5
        assert result.snapshot_evidence.source_snapshot_ids == (
            "snapshot:tushare:balance_sheet:2024-12-20:old:quality=l1-l2",
            "snapshot:tushare:balance_sheet:2024-12-27:current:quality=l1-l2",
        )
        assert result.quality_evidence is not None
        assert result.quality_evidence.checksum == "current"
        mock_source.fetch_balance_sheet.assert_not_called()

    def test_ingest_date_skipped_when_catalog_has_exact_trade_date_asset(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
    ) -> None:
        """Catalog-only residue must trigger reingestion instead of a dead-loop skip."""
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="stock_daily/2024",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=1000,
                ),
                source="tushare",
                freshness_at=datetime.now(UTC),
            )
        )
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_store=mock_ingestion_log_store,
                catalog_reader=catalog,
            ),
        )
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1_000_000],
                "amount": [10_200_000],
                "pct_change": [2.0],
            }
        )
        mock_market_write_service.save_bars.return_value = 1

        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        assert result.status == "success"
        mock_source.fetch_stock_daily.assert_called_once_with("2024-12-27")

    def test_ingest_date_success_etf_daily(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """成功摄取 etf_daily 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None  # 无历史记录
        source_df = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "510500.SH"],
                "trade_date": [date(2024, 12, 27), date(2024, 12, 27)],
                "open": [4.0, 3.5],
                "high": [4.1, 3.6],
                "low": [3.9, 3.4],
                "close": [4.05, 3.55],
                "pre_close": [4.0, 3.5],
                "volume": [1000000, 800000],
                "amount": [4050000, 2840000],
                "pct_change": [1.25, 1.43],
            }
        )
        mock_source.fetch_etf_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="etf_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("etf_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        # checksum 是实际计算的 MD5 值，只需验证非空即可
        assert result.checksum is not None
        assert len(result.checksum) > 0
        mock_source.fetch_etf_daily.assert_called_once_with("2024-12-27")
        mock_market_write_service.save_bars.assert_called_once()
        mock_ingestion_log_store.save_log.assert_called_once()

    def test_ingest_date_success_stock_daily(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """成功摄取 stock_daily 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum456",
        )
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum456",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_stock_daily.assert_called_once_with("2024-12-27")

    def test_ingest_date_success_records_data_lineage(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
    ) -> None:
        """成功摄取后记录源数据到落库资产的 lineage。"""
        # Arrange
        lineage = InMemoryDataLineage()
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_store=mock_ingestion_log_store,
                lineage_recorder=lineage,
            ),
        )
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_market_write_service.save_bars.return_value = 1

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        source_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="source",
            partition_keys=("source=tushare", "trade_date=2024-12-27"),
        )
        output_asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2024-12-27",),
        )
        events = lineage.list_events_for_asset(output_asset)
        assert len(events) == 1
        event = events[0]
        assert event.operation == "ingest"
        assert event.run_id.startswith("ingest:tushare:stock_daily:2024-12-27:")
        assert tuple(ref.asset for ref in event.inputs) == (source_asset,)
        assert tuple(ref.role for ref in event.inputs) == ("source",)
        assert tuple(ref.asset for ref in event.outputs) == (output_asset,)
        assert tuple(ref.role for ref in event.outputs) == ("dataset",)

    def test_ingest_date_success_upserts_data_catalog_entry(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
    ) -> None:
        """成功摄取后将落库资产写入 DataCatalog runtime。"""
        catalog = InMemoryDataCatalog()
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_store=mock_ingestion_log_store,
                catalog_writer=catalog,
            ),
        )
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_market_write_service.save_bars.return_value = 1

        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        assert result.status == "success"
        asset = DataAssetRef(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2024-12-27",),
        )
        entry = catalog.get_asset(asset)
        assert entry is not None
        assert entry.asset == asset
        assert entry.storage_uri == "stock_daily/2024"
        assert entry.source == "tushare"
        assert entry.schema.row_count == 1
        assert entry.schema.schema_version == "market.stock_daily.v1"
        assert entry.schema.schema_hash.startswith("schema:sha256:")
        assert (
            entry.source_snapshot_id
            == f"snapshot:tushare:stock_daily:2024-12-27:{result.checksum}"
        )

    def test_ingest_date_success_adj_factor(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """成功摄取 adj_factor 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_market_write_service.save_adj_factor.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="adj_factor",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum789",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("adj_factor", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_adj_factor.assert_called_once_with("2024-12-27")
        mock_market_write_service.save_adj_factor.assert_called_once()

    def test_ingest_date_success_stock_status(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """成功摄取 stock_status 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_status.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "is_suspended": [False],
                "suspend_timing": [None],
                "is_st": [False],
                "st_type": [None],
                "list_status": ["L"],
            }
        )

        # save_stock_status 返回写入的行数
        mock_market_write_service.save_stock_status.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_status",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_status",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_status", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_stock_status.assert_called_once_with("2024-12-27")
        mock_market_write_service.save_stock_status.assert_called_once()

    def test_ingest_date_success_balance_sheet(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_fundamental_store,
        mocker,
    ) -> None:
        """成功摄取 balance_sheet 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_balance_sheet.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "report_date": [date(2024, 9, 30)],
                "knowledge_date": [date(2024, 10, 31)],
                "effective_from": [date(2024, 10, 31)],
                "effective_to": [None],
                "total_assets": [100.0],
                "total_liabilities": [60.0],
                "net_assets": [40.0],
                "current_assets": [30.0],
                "current_liabilities": [20.0],
            }
        )
        mock_fundamental_store.save_balance_sheet.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="balance_sheet",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_balance_sheet",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("balance_sheet", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_balance_sheet.assert_called_once_with("2024-12-27")
        mock_fundamental_store.save_balance_sheet.assert_called_once()

    def test_ingest_date_success_valuation_metrics(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_capital_store,
        mocker,
    ) -> None:
        """成功摄取 valuation_metrics 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_valuation_metrics.return_value = pl.DataFrame(
            {
                "instrument_id": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pe_ratio": [12.5],
                "pb_ratio": [1.8],
                "ps_ratio": [2.1],
                "dividend_yield": [0.03],
                "market_cap": [1000000000.0],
            }
        )
        mock_capital_store.save_valuation_metrics.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="valuation_metrics",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_valuation_metrics",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("valuation_metrics", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_valuation_metrics.assert_called_once_with("2024-12-27")
        mock_capital_store.save_valuation_metrics.assert_called_once()

    def test_ingest_date_success_macro_indicators(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_macro_service,
        mocker,
    ) -> None:
        """成功摄取 macro_indicators 数据。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_macro_indicators.return_value = pl.DataFrame(
            {
                "indicator_code": ["SHIBOR_ON"],
                "indicator_name": ["隔夜Shibor"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 12, 27)],
                "value": [1.92],
                "knowledge_date": [date(2024, 12, 28)],
            }
        )
        mock_macro_service.save_indicators.return_value = mocker.Mock(records_written=1)
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="macro_indicators",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_macro_indicators",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("macro_indicators", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_macro_indicators.assert_called_once_with("2024-12-27")
        mock_macro_service.save_indicators.assert_called_once()

    def test_ingest_date_fred_source_uses_fred_macro_fetcher(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
        mocker,
    ) -> None:
        """source=fred 摄取 macro_indicators 时使用 FRED macro fetcher."""
        fred_macro_source = mocker.Mock()
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=fred_macro_source,
            ),
            config=IngestionCoordinatorConfig(
                source_name="fred",
                ingestion_log_store=mock_ingestion_log_store,
            ),
        )
        mock_ingestion_log_store.get_log.return_value = None
        fred_macro_source.fetch_macro_indicators.return_value = pl.DataFrame(
            {
                "indicator_code": ["FEDFUNDS"],
                "indicator_name": ["Federal Funds Effective Rate"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 12, 27)],
                "value": [4.33],
                "knowledge_date": [date(2024, 12, 28)],
            }
        )
        mock_macro_service.save_indicators.return_value = mocker.Mock(records_written=1)
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="macro_indicators",
            source="fred",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_macro_indicators",
            rows=1,
        )

        result = coordinator.ingest_date("macro_indicators", "2024-12-27")

        assert result.status == "success"
        fred_macro_source.fetch_macro_indicators.assert_called_once_with("2024-12-27")
        mock_source.fetch_macro_indicators.assert_not_called()
        mock_macro_service.save_indicators.assert_called_once()

    def test_ingest_date_success_calendar(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_metadata_service,
    ) -> None:
        """成功摄取 calendar 数据（范围数据）。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27), date(2024, 12, 30)],
                "is_open": [True, True],
            }
        )

        mock_metadata_service.reset_mock()
        mock_metadata_service.upsert.return_value = 2
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="calendar",
            source="tushare",
            trade_date="2024-12-27",  # 对于 calendar，这是范围起始日期
            status=IngestionStatus.SUCCESS,
            checksum="checksum000",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("calendar", "2024-12-27")

        # Assert
        assert result.status == "success"
        mock_source.fetch_calendar.assert_called_once()

    def test_ingest_date_fetch_error(
        self, coordinator, mock_ingestion_log_store, mock_source
    ) -> None:
        """获取数据失败时返回失败结果。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None

        mock_source.fetch_stock_daily.side_effect = SourceFetchError(
            "Network error", source="tushare"
        )
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="FETCH_ERROR",
            error_message="Network error",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "FETCH_ERROR"
        assert "Network error" in result.message

    def test_ingest_date_empty_dataframe(
        self, coordinator, mock_ingestion_log_store, mock_source
    ) -> None:
        """获取到空数据时返回失败结果。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.return_value = pl.DataFrame()
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="EMPTY_DATA",
            error_message="获取的数据为空",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "EMPTY_DATA"
        assert "空" in result.message or "empty" in result.message.lower()

    def test_ingest_date_force_overwrites_previous_success(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """force=True 时覆盖历史成功记录。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="old_checksum",
            rows=1000,
        )

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "new_checksum",
        )
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="new_checksum",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27", force=True)

        # Assert
        assert result.status == "success"
        # checksum 是实际计算的 MD5 值，只需验证非空即可
        assert result.checksum is not None
        assert len(result.checksum) > 0
        mock_source.fetch_stock_daily.assert_called_once()

    def test_ingest_date_unknown_error(
        self, coordinator, mock_ingestion_log_store, mock_source
    ) -> None:
        """测试非 SourceFetchError 异常的处理。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_daily.side_effect = RuntimeError("Unexpected error")
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="UNKNOWN_ERROR",
            error_message="RuntimeError: Unexpected error",
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "UNKNOWN_ERROR"
        assert "Unexpected error" in result.message

    def test_ingest_date_dq_blocked(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
        mocker,
    ) -> None:
        """测试 DQ 质量检查阻断时的处理。

        DQ 阻断由 CheckDataQualityHandler.handle() 显式触发，
        而非由 save_bars 返回 0 行推断。
        """
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        # 模拟 DQ 质量检查阻断：CheckDataQualityHandler 返回 has_errors=True
        from ditto_application.commands.quality_check import CheckDataQualityHandler

        mock_quality_checker = mocker.Mock(spec=CheckDataQualityHandler)
        mock_quality_checker.handle.return_value = (
            source_df,
            True,  # has_errors=True
        )

        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.FAIL,
            error_code="DQ_BLOCKED",
            error_message="DQ L1 check failed: 10 errors",
        )

        # 创建带 quality_checker 的 coordinator
        dq_coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                ingestion_log_store=mock_ingestion_log_store,
                quality_checker=mock_quality_checker,
            ),
        )

        # Act
        result = dq_coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "failed"
        assert result.error == "DQ_BLOCKED"
        assert "DQ" in result.message or "check failed" in result.message
        # 验证 DQ 质量检查被调用
        mock_quality_checker.handle.assert_called_once()
        # 验证 write_data 未被调用（DQ 阻断在写入之前）
        mock_market_write_service.save_bars.assert_not_called()

    def test_ingest_date_unsupported_dataset_raises_error(
        self, coordinator, mock_ingestion_log_store, mock_source
    ) -> None:
        """不支持的 dataset 抛出 AppProcessError。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None

        # Act & Assert
        with pytest.raises(AppProcessError, match="不支持的数据集"):
            coordinator.ingest_date("unsupported_dataset", "2024-12-27")

    def test_ingest_date_rejects_source_not_declared_by_catalog_metadata(
        self,
        mock_metadata_service,
        mock_market_write_service,
        mock_fundamental_store,
        mock_capital_store,
        mock_macro_service,
        mock_ingestion_log_store,
        mock_source,
    ) -> None:
        """运行期 source 必须被 data-owned catalog metadata 声明支持。"""
        coordinator = IngestionCoordinator(
            services=IngestionServices(
                metadata=mock_metadata_service,
                market=MarketServices(
                    query=mock_market_write_service,
                    write=mock_market_write_service,
                ),
                fundamental=mock_fundamental_store,
                capital=mock_capital_store,
                macro=mock_macro_service,
            ),
            fetchers=SourceFetchers(
                metadata=mock_source,
                market=mock_source,
                fundamental=mock_source,
                capital=mock_source,
                macro=mock_source,
            ),
            config=IngestionCoordinatorConfig(
                source_name="fred",
                ingestion_log_store=mock_ingestion_log_store,
            ),
        )

        with pytest.raises(AppProcessError, match="does not support dataset"):
            coordinator.ingest_date("stock_daily", "2024-12-27")

        mock_source.fetch_stock_daily.assert_not_called()


@pytest.mark.unit
class TestIngestRange:
    """测试 ingest_range 方法。"""

    def test_ingest_range_multiple_dates(
        self,
        coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """成功摄取日期范围内的多个交易日。"""
        # Arrange
        mock_metadata_service.reset_mock()
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        mock_ingestion_log_store.get_log.return_value = None  # 无历史记录

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 3
        assert all(r.status == "success" for r in results)
        mock_metadata_service.list_trading_days.assert_called_once_with(
            "2024-12-25", "2024-12-27"
        )
        assert mock_source.fetch_stock_daily.call_count == 3

    def test_ingest_chunk_fetches_each_partition_but_writes_one_range_payload(
        self,
        coordinator,
        mock_source,
        mock_market_write_service,
        in_memory_catalog,
    ) -> None:
        frames = [
            pl.DataFrame(
                {
                    "source_ticker": ["000001.SZ"],
                    "trade_date": [date(2024, 12, day)],
                    "open": [10.0],
                    "close": [10.2],
                    "pre_close": [10.0],
                    "volume": [1_000_000],
                    "amount": [10_200_000],
                    "pct_change": [2.0],
                    "high": [10.5],
                    "low": [9.8],
                }
            )
            for day in (25, 26, 27)
        ]
        mock_source.fetch_stock_daily.side_effect = frames
        mock_market_write_service.save_bars.return_value = 3

        result = coordinator.ingest_chunk(
            "stock_daily",
            chunk_id="chunk:tushare:stock_daily:2024-12:2024-12-25:2024-12-27",
            request_start="2024-12-25",
            request_end="2024-12-27",
            partition_dates=("2024-12-25", "2024-12-26", "2024-12-27"),
        )

        assert result.status == "success"
        assert result.trade_date == "2024-12-25"
        assert result.row_count == 3
        assert mock_source.fetch_stock_daily.call_count == 3
        mock_market_write_service.save_bars.assert_called_once()
        entry = in_memory_catalog.get_asset(
            DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=(
                    "start_date=2024-12-25",
                    "end_date=2024-12-27",
                ),
            )
        )
        assert entry is not None
        assert entry.schema.row_count == 3

    def test_source_defined_chunk_uses_one_range_fetch(
        self,
        coordinator,
        mock_source,
    ) -> None:
        expected = pl.DataFrame({"date": [date(2024, 1, 2)], "value": [1.5]})
        mock_source.fetch_macro_indicators_range.return_value = expected

        result = coordinator._fetch_source_defined_range(
            "macro_indicators",
            "2024-01-01",
            "2024-12-31",
        )

        assert result is expected
        mock_source.fetch_macro_indicators_range.assert_called_once_with(
            "2024-01-01",
            "2024-12-31",
        )

    def test_sparse_pit_chunk_uses_one_bounded_range_fetch(
        self,
        coordinator,
        mock_source,
    ) -> None:
        expected = pl.DataFrame(
            {
                "knowledge_date": [date(2024, 1, 31)],
                "total_assets": [100.0],
            }
        )
        mock_source.fetch_balance_sheet_range.return_value = expected

        result = coordinator._fetch_sparse_range(
            "balance_sheet",
            "2024-01-01",
            "2024-01-31",
        )

        assert result is expected
        mock_source.fetch_balance_sheet_range.assert_called_once_with(
            "2024-01-01",
            "2024-01-31",
        )

    def test_ingest_range_with_skipped_dates(
        self,
        coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
        in_memory_catalog,
    ) -> None:
        """日期范围内有跳过的日期。"""
        # Arrange
        mock_metadata_service.reset_mock()
        mock_metadata_service.list_trading_days.return_value = [
            "2024-12-25",
            "2024-12-26",
            "2024-12-27",
        ]

        # 模拟第二天已经成功
        def get_log_side_effect(dataset, source, trade_date):
            if trade_date == "2024-12-26":
                return IngestionLog(
                    dataset="stock_daily",
                    source="tushare",
                    trade_date=trade_date,
                    status=IngestionStatus.SUCCESS,
                    checksum="old_checksum",
                    rows=1000,
                )
            return None

        mock_ingestion_log_store.get_log.side_effect = get_log_side_effect
        in_memory_catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-26",),
                ),
                storage_uri="stock_daily/2024-12-26",
                schema=DataSchemaFingerprint(
                    schema_hash="market.stock_daily.v1",
                    row_count=1000,
                ),
                source="tushare",
                freshness_at=datetime(2024, 12, 26, tzinfo=UTC),
                source_snapshot_id=(
                    "snapshot:tushare:stock_daily:2024-12-26:old_checksum:quality=l1-l2"
                ),
            )
        )

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 3
        # 第二天应该被跳过
        skipped_results = [r for r in results if r.status == "skipped"]
        assert len(skipped_results) == 1
        assert skipped_results[0].trade_date == "2024-12-26"

    def test_ingest_range_empty_range(self, coordinator, mock_metadata_service) -> None:
        """日期范围为空时返回空列表。"""
        # Arrange
        mock_metadata_service.reset_mock()
        mock_metadata_service.list_trading_days.return_value = []

        # Act
        results = coordinator.ingest_range("stock_daily", "2024-12-25", "2024-12-27")

        # Assert
        assert len(results) == 0

    def test_ingest_range_with_force(
        self,
        coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """force=True 时跳过所有历史检查。"""
        # Arrange
        mock_metadata_service.reset_mock()
        mock_metadata_service.list_trading_days.return_value = ["2024-12-27"]

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum123",
        )

        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range(
            "stock_daily", "2024-12-27", "2024-12-27", force=True
        )

        # Assert
        assert len(results) == 1
        assert results[0].status == "success"

    def test_ingest_range_uses_natural_days_for_fx_daily(
        self,
        coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mock_source,
        mock_macro_service,
        mocker,
    ) -> None:
        """fx_daily 使用自然日而非交易日列表。"""
        # Arrange
        mock_metadata_service.reset_mock()
        # 不应调用 list_trading_days，因为是自然日调度
        mock_ingestion_log_store.get_log.return_value = None

        mock_source.fetch_fx_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["USDCNY"],
                "trade_date": [date(2024, 12, 25)],
                "open": [7.1],
                "close": [7.12],
                "high": [7.15],
                "low": [7.09],
            }
        )
        mock_macro_service.write.return_value = mocker.Mock(records_written=1)
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="fx_daily",
            source="tushare",
            trade_date="2024-12-25",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_fx",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range("fx_daily", "2024-12-25", "2024-12-27")

        # Assert — 3 个自然日（25, 26, 27）
        assert len(results) == 3
        mock_metadata_service.list_trading_days.assert_not_called()

    def test_ingest_range_uses_natural_days_for_commodity_daily(
        self,
        coordinator,
        mock_metadata_service,
        mock_ingestion_log_store,
        mock_source,
        mock_macro_service,
        mocker,
    ) -> None:
        """commodity_daily 使用自然日（SOURCE_DEFINED 调度走自然日路径）。"""
        # Arrange
        mock_metadata_service.reset_mock()
        mock_ingestion_log_store.get_log.return_value = None

        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="commodity_daily",
            source="tushare",
            trade_date="2024-12-25",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_commodity",
            rows=1,
        )

        # Act
        results = coordinator.ingest_range(
            "commodity_daily", "2024-12-25", "2024-12-27"
        )

        # Assert — 3 个自然日
        assert len(results) == 3
        mock_metadata_service.list_trading_days.assert_not_called()


@pytest.mark.unit
class TestWriteT0Data:
    """测试 T0 数据（stock_basic, etf_basic）写入。"""

    def test_ingest_date_success_stock_basic(
        self, coordinator, mock_ingestion_log_store, mock_source, mocker
    ) -> None:
        """成功摄取 stock_basic 数据到 instrument_store。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_stock_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "600000.SH"],
                "symbol": ["000001", "600000"],
                "name": ["平安银行", "浦发银行"],
                "exchange": ["SZSE", "SSE"],
                "list_date": [date(1991, 4, 3), date(1999, 11, 10)],
            }
        )

        mock_ingestion_log_store.save_log.return_value = mocker.Mock(
            dataset="stock_basic",
            source="tushare",
            trade_date="2024-01-03",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("stock_basic", "2024-01-03")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        mock_source.fetch_stock_basic.assert_called_once()

    def test_ingest_date_success_etf_basic(
        self, coordinator, mock_ingestion_log_store, mock_source, mocker
    ) -> None:
        """成功摄取 etf_basic 数据到 instrument_store。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_etf_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "159919.SZ"],
                "symbol": ["510300", "159919"],
                "name": ["沪深300ETF", "沪深300ETF"],
                "exchange": ["SSE", "SZSE"],
                "list_date": [date(2012, 7, 6), date(2019, 6, 24)],
            }
        )

        mock_ingestion_log_store.save_log.return_value = mocker.Mock(
            dataset="etf_basic",
            source="tushare",
            trade_date="2024-01-03",
            status=IngestionStatus.SUCCESS,
            checksum="checksum456",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("etf_basic", "2024-01-03")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        mock_source.fetch_etf_basic.assert_called_once()


@pytest.mark.unit
class TestForceParameter:
    """测试 force 参数语义。"""

    def test_force_false_maps_to_error_on_duplicate(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """验证 force=False 映射到 OnDuplicate.ERROR。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        coordinator.ingest_date("stock_daily", "2024-12-27", force=False)

        # Assert
        mock_market_write_service.save_bars.assert_called_once()
        # 验证 on_duplicate 参数传递正确（位置参数：dataset, df, year, on_duplicate）
        call_kwargs = mock_market_write_service.save_bars.call_args.kwargs
        assert (
            call_kwargs.get("on_duplicate") == "error"
            or call_kwargs.get("on_duplicate") == OnDuplicate.ERROR
        )

    def test_force_true_maps_to_keep_last_on_duplicate(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """验证 force=True 映射到 OnDuplicate.KEEP_LAST。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        coordinator.ingest_date("stock_daily", "2024-12-27", force=True)

        # Assert
        mock_market_write_service.save_bars.assert_called_once()
        # 验证 on_duplicate 参数传递正确（force=True 对应 KEEP_LAST）
        call_kwargs = mock_market_write_service.save_bars.call_args.kwargs
        assert (
            call_kwargs.get("on_duplicate") == "keep_last"
            or call_kwargs.get("on_duplicate") == OnDuplicate.KEEP_LAST
        )

    def test_force_true_for_adj_factor_uses_keep_last(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """验证 force=True 对 adj_factor 数据集也传递正确的 on_duplicate。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_adj_factor.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "adj_factor": [1.2345],
            }
        )

        mock_market_write_service.save_adj_factor.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="adj_factor",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum789",
            rows=1,
        )

        # Act
        coordinator.ingest_date("adj_factor", "2024-12-27", force=True)

        # Assert
        mock_market_write_service.save_adj_factor.assert_called_once()
        # 验证 on_duplicate 参数传递正确（force=True 对应 KEEP_LAST）
        call_kwargs = mock_market_write_service.save_adj_factor.call_args.kwargs
        assert (
            call_kwargs.get("on_duplicate") == "keep_last"
            or call_kwargs.get("on_duplicate") == OnDuplicate.KEEP_LAST
        )


@pytest.mark.unit
class TestFetchDataEdgeCases:
    """测试 _fetch_data 方法的边界情况。"""

    def test_fetch_data_raises_app_process_error_for_unsupported_dataset(
        self, coordinator, mock_source
    ) -> None:
        """验证 _fetch_data 对不支持的数据集抛出 AppProcessError。"""
        # Arrange
        # 使用不在 _DATASET_METHODS 中的数据集
        unsupported_dataset = "unsupported_dataset"

        # Act & Assert
        with pytest.raises(AppProcessError, match="不支持的数据集"):
            coordinator._fetch_data(unsupported_dataset, "2024-12-27")

        # 验证没有调用 source 的任何方法
        mock_source.fetch_stock_daily.assert_not_called()
        mock_source.fetch_etf_daily.assert_not_called()


@pytest.mark.unit
class TestTradingDayCheck:
    """测试交易日检查（P0-2）。"""

    def test_stock_daily_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """stock_daily 在非交易日静默跳过。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None  # 无历史记录
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_stock_daily.assert_not_called()
        # 不应该记录 ingestion_log（静默跳过）
        mock_ingestion_log_store.save_log.assert_not_called()

    def test_etf_daily_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """etf_daily 在非交易日静默跳过。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("etf_daily", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        # 不应该调用 source
        mock_source.fetch_etf_daily.assert_not_called()

    def test_stock_status_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """stock_status 在非交易日静默跳过。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("stock_status", "2024-12-28")

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        mock_source.fetch_stock_status.assert_not_called()

    def test_index_weight_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
    ) -> None:
        """index_weight only evaluates provider intervals on trading days."""
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        result = coordinator.ingest_date("index_weight", "2024-12-28")

        assert result.status == "skipped"
        mock_metadata_service.is_trading_day.assert_called_once_with("2024-12-28")

    def test_stock_daily_proceeds_on_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """stock_daily 在交易日继续处理。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = True

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 12, 27)],
                "open": [10.0],
                "close": [10.2],
                "pre_close": [10.0],
                "volume": [1000000],
                "amount": [10200000],
                "pct_change": [2.0],
                "high": [10.5],
                "low": [9.8],
            }
        )
        mock_source.fetch_stock_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = mock_market_save_bars(
            "/path/to/file.parquet",
            "checksum123",
        )
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="stock_daily",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum123",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("stock_daily", "2024-12-27")

        # Assert
        assert result.status == "success"
        # 验证调用了 source
        mock_source.fetch_stock_daily.assert_called_once_with("2024-12-27")

    def test_adj_factor_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """adj_factor 在非交易日静默跳过。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("adj_factor", "2024-12-27")

        # Assert
        assert result.status == "skipped"
        mock_source.fetch_adj_factor.assert_not_called()
        mock_metadata_service.is_trading_day.assert_called_once_with("2024-12-27")

    def test_calendar_does_not_check_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """calendar 不检查交易日（基础类数据集）。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        mock_source.fetch_calendar.return_value = pl.DataFrame(
            {
                "trade_date": [date(2024, 12, 27)],
                "is_open": [True],
            }
        )

        mock_metadata_service.reset_mock()
        mock_metadata_service.upsert.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="calendar",
            source="tushare",
            trade_date="2024-12-27",
            status=IngestionStatus.SUCCESS,
            checksum="checksum000",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("calendar", "2024-12-27")

        # Assert
        assert result.status == "success"
        # 验证调用了 source（没有因为非交易日而跳过）
        mock_source.fetch_calendar.assert_called_once()
        # 验证没有调用 is_trading_day
        mock_metadata_service.is_trading_day.assert_not_called()

    def test_macro_indicators_does_not_check_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
        mock_macro_service,
        mocker,
    ) -> None:
        """macro_indicators 不检查交易日（非交易日也允许摄取）。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        mock_source.fetch_macro_indicators.return_value = pl.DataFrame(
            {
                "indicator_code": ["SHIBOR_ON"],
                "indicator_name": ["隔夜Shibor"],
                "category": ["interest_rate"],
                "frequency": ["daily"],
                "need_pit": [False],
                "date": [date(2024, 12, 28)],
                "value": [1.91],
                "knowledge_date": [date(2024, 12, 29)],
            }
        )

        mock_macro_service.save_indicators.return_value = mocker.Mock(records_written=1)
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="macro_indicators",
            source="tushare",
            trade_date="2024-12-28",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_macro_indicators",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("macro_indicators", "2024-12-28")

        # Assert
        assert result.status == "success"
        mock_source.fetch_macro_indicators.assert_called_once_with("2024-12-28")
        mock_metadata_service.is_trading_day.assert_not_called()


@pytest.mark.unit
class TestIndexDatasetSupport:
    """测试指数数据集支持（INDEX_BASIC, INDEX_DAILY）。"""

    def test_fetch_data_supports_index_basic(self, coordinator, mock_source) -> None:
        """验证 _fetch_data 支持 INDEX_BASIC。"""
        # Arrange
        mock_source.fetch_index_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SH", "399001.SZ"],
                "name": ["上证指数", "深证成指"],
                "market": ["SSE", "SZSE"],
            }
        )

        # Act
        result = coordinator._fetch_data("index_basic", "")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        mock_source.fetch_index_basic.assert_called_once()

    def test_fetch_data_supports_index_daily(self, coordinator, mock_source) -> None:
        """验证 _fetch_data 支持 INDEX_DAILY。"""
        # Arrange
        mock_source.fetch_index_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SH"],
                "trade_date": [date(2024, 1, 2)],
                "open": [2990.0],
                "close": [3000.0],
                "high": [3010.0],
                "low": [2980.0],
                "volume": [1000000.0],
            }
        )

        # Act
        result = coordinator._fetch_data("index_daily", "2024-01-02")

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1
        # 验证调用包含 trade_date 和 ts_codes 参数
        mock_source.fetch_index_daily.assert_called_once()
        call_args = mock_source.fetch_index_daily.call_args
        assert call_args[0][0] == "2024-01-02"  # 第一个位置参数是 trade_date
        assert "ts_codes" in call_args.kwargs  # ts_codes 作为关键字参数传递

    def test_index_daily_skips_on_non_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """index_daily 在非交易日静默跳过。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = False

        # Act
        result = coordinator.ingest_date("index_daily", "2024-01-06")  # 周六

        # Assert
        assert result.status == "skipped"
        assert "非交易日" in result.message or "跳过" in result.message
        mock_source.fetch_index_daily.assert_not_called()

    def test_index_daily_proceeds_on_trading_day(
        self,
        coordinator,
        mock_ingestion_log_store,
        mock_metadata_service,
        mock_source,
        mock_market_write_service,
    ) -> None:
        """index_daily 在交易日继续处理。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_metadata_service.reset_mock()
        mock_metadata_service.is_trading_day.return_value = True

        source_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SH"],
                "trade_date": [date(2024, 1, 2)],
                "open": [2990.0],
                "close": [3000.0],
                "high": [3010.0],
                "low": [2980.0],
                "volume": [1000000.0],
                "amount": [3000000000.0],
                "pct_change": [0.33],
                "pre_close": [2990.0],
            }
        )
        mock_source.fetch_index_daily.return_value = source_df

        mock_market_write_service.save_bars.return_value = 1
        mock_ingestion_log_store.save_log.return_value = IngestionLog(
            dataset="index_daily",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_index",
            rows=1,
        )

        # Act
        result = coordinator.ingest_date("index_daily", "2024-01-02")

        # Assert
        assert result.status == "success"
        # 验证调用包含 trade_date 和 ts_codes 参数
        mock_source.fetch_index_daily.assert_called_once()
        call_args = mock_source.fetch_index_daily.call_args
        assert call_args[0][0] == "2024-01-02"  # 第一个位置参数是 trade_date
        assert "ts_codes" in call_args.kwargs  # ts_codes 作为关键字参数传递
        mock_market_write_service.save_bars.assert_called_once()

    def test_ingest_date_success_index_basic(
        self, coordinator, mock_ingestion_log_store, mock_source, mocker
    ) -> None:
        """成功摄取 index_basic 数据到 instrument_store。"""
        # Arrange
        mock_ingestion_log_store.get_log.return_value = None
        mock_source.fetch_index_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SH", "399001.SZ"],
                "name": ["上证指数", "深证成指"],
                "market": ["SSE", "SZSE"],
            }
        )

        mock_ingestion_log_store.save_log.return_value = mocker.Mock(
            dataset="index_basic",
            source="tushare",
            trade_date="2024-01-02",
            status=IngestionStatus.SUCCESS,
            checksum="checksum_index_basic",
            rows=2,
        )

        # Act
        result = coordinator.ingest_date("index_basic", "2024-01-02")

        # Assert
        assert result.status == "success"
        assert result.row_count == 2
        mock_source.fetch_index_basic.assert_called_once()
