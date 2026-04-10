"""Tests for exception chain preservation in IngestionCoordinator."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app.process.ingestion.config import IngestionCoordinatorConfig
from ditto_app.process.ingestion.coordinator import (
    IngestionCoordinator,
    MarketServices,
)
from ditto_data.errors import IdentifierNotFoundError
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.observability import init, reset_for_testing
from ditto_infra.foundation.observability.config import ObservabilityConfig
from ditto_kernel.types import InstrumentIngestParams


@pytest.fixture(autouse=True)
def setup_observability():
    """初始化可观测性."""
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
def mock_metadata_service():
    """创建 Mock MetadataService."""
    service = MagicMock()
    service.is_trading_day.return_value = True
    service.upsert.return_value = len
    service.list_trading_days.return_value = []
    service.get_securities.return_value = pl.DataFrame()
    service.resolve_source_ticker.side_effect = IdentifierNotFoundError(
        identifier="000001",
        identifier_type="ticker",
    )
    return service


@pytest.fixture
def mock_market_service():
    """创建 Mock MarketService."""
    service = MagicMock()
    service.save_bars.return_value = 1
    return service


@pytest.fixture
def mock_fundamental_service():
    """创建 Mock FundamentalService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_capital_service():
    """创建 Mock CapitalService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_macro_service():
    """创建 Mock MacroService."""
    service = MagicMock()
    service.write.return_value = MagicMock(records_written=1)
    return service


@pytest.fixture
def mock_ingestion_log_service():
    """创建 Mock IngestionLogService."""
    service = MagicMock()
    service.get_log = MagicMock(return_value=None)
    service.save_log = MagicMock(return_value=None)
    service.list_ingested_dates = MagicMock(return_value=[])
    return service


@pytest.fixture
def mock_source():
    """创建 Mock DataSource."""
    source = MagicMock()
    return source


@pytest.fixture
def coordinator(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
    mock_ingestion_log_service,
    mock_source,
):
    """创建 IngestionCoordinator 实例."""
    return IngestionCoordinator(
        metadata_service=mock_metadata_service,
        market_services=MarketServices(
            query=mock_market_service,
            write=mock_market_service,
        ),
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source=mock_source,
        config=IngestionCoordinatorConfig(
            ingestion_log_service=mock_ingestion_log_service,
        ),
    )


@pytest.mark.unit
class TestExceptionChainPreservation:
    """测试异常因果链保留."""

    def test_exception_chain_preserved_on_fetch_error(
        self,
        coordinator,
        mock_source,
    ) -> None:
        """验证 fetch 失败时异常因果链被保留。"""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        # 模拟 fetch_stock_basic 抛出网络错误
        network_error = ConnectionError("Network timeout")
        mock_source.fetch_stock_basic.side_effect = network_error

        # Act & Assert
        with pytest.raises(IdentifierNotFoundError) as exc_info:
            coordinator.ingest_by_instrument("stock_daily", params)

        # 验证异常因果链被保留
        raised_error = exc_info.value
        assert raised_error.__cause__ is network_error, (
            f"Expected __cause__ to be network_error, got {raised_error.__cause__}"
        )

    def test_exception_chain_preserved_on_empty_data(
        self,
        coordinator,
        mock_source,
    ) -> None:
        """验证数据为空时异常因果链被保留（None cause）。"""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        # 模拟 fetch_stock_basic 返回空 DataFrame
        mock_source.fetch_stock_basic.return_value = pl.DataFrame()

        # Act & Assert
        with pytest.raises(IdentifierNotFoundError) as exc_info:
            coordinator.ingest_by_instrument("stock_daily", params)

        # 当数据为空时，__cause__ 应该是 None（没有底层异常）
        raised_error = exc_info.value
        cause = raised_error.__cause__
        assert cause is None, (
            f"Expected __cause__ to be None for empty data, got {cause}"
        )

    def test_exception_chain_preserved_on_register_error(
        self,
        coordinator,
        mock_source,
        mock_metadata_service,
    ) -> None:
        """验证 register 失败时异常因果链被保留。"""
        # Arrange
        params = InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        )
        # 模拟 fetch_stock_basic 返回有效数据
        mock_source.fetch_stock_basic.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "name": ["平安银行"],
                "list_date": ["19910403"],
            }
        )
        # 模拟 register_instruments_batch 抛出数据库错误
        db_error = RuntimeError("Database connection failed")
        mock_metadata_service.register_instruments_batch.side_effect = db_error

        # Act & Assert
        with pytest.raises(IdentifierNotFoundError) as exc_info:
            coordinator.ingest_by_instrument("stock_daily", params)

        # 验证异常因果链被保留
        raised_error = exc_info.value
        assert raised_error.__cause__ is db_error, (
            f"Expected __cause__ to be db_error, got {raised_error.__cause__}"
        )
