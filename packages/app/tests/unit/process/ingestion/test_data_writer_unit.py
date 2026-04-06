"""Tests for IngestionDataWriter."""

from datetime import date

import polars as pl
import pytest
from ditto_app.process.data_writer import IngestionDataWriter
from ditto_infra.foundation.config.environment import Environment
from ditto_infra.foundation.observability import init, reset_for_testing
from ditto_infra.foundation.observability.config import ObservabilityConfig


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

    # Instrument 相关方法
    service.register_instruments_batch = mocker.Mock()
    service.resolve_or_create_instruments_batch = mocker.Mock()
    service.resolve_instrument_ids_batch = mocker.Mock(return_value={})

    def register_side_effect(df, source, asset_class, **kwargs):
        _ = df, source, kwargs
        return (f"instrument_store:{asset_class}_basic", f"checksum_{asset_class}")

    def resolve_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: 1_000_000}

    service.register_instruments_batch.side_effect = register_side_effect
    service.resolve_or_create_instruments_batch.side_effect = resolve_side_effect

    return service


@pytest.fixture
def mock_market_service(mocker):
    """创建 Mock MarketService。"""
    service = mocker.Mock()
    service.save_bars.return_value = 1
    service.save_adj_factor.return_value = 1
    service.save_stock_status.return_value = 1
    return service


@pytest.fixture
def mock_fundamental_service(mocker):
    """创建 Mock FundamentalService。"""
    service = mocker.Mock()
    service.save_balance_sheet.return_value = 1
    service.save_income_statement.return_value = 1
    service.save_cash_flow.return_value = 1
    service.save_dividend.return_value = 1
    return service


@pytest.fixture
def mock_capital_service(mocker):
    """创建 Mock CapitalService。"""
    service = mocker.Mock()
    service.save_valuation_metrics.return_value = 1
    service.save_margin_trading.return_value = 1
    service.save_pledge_ratio.return_value = 1
    return service


@pytest.fixture
def mock_macro_service(mocker):
    """创建 Mock MacroService。"""
    service = mocker.Mock()
    save_result = mocker.Mock()
    save_result.records_written = 1
    service.save_indicators.return_value = save_result
    return service


@pytest.fixture
def data_writer(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_service,
    mock_capital_service,
    mock_macro_service,
):
    """创建 IngestionDataWriter 实例。"""
    return IngestionDataWriter(
        metadata_service=mock_metadata_service,
        market_service=mock_market_service,
        fundamental_service=mock_fundamental_service,
        capital_service=mock_capital_service,
        macro_service=mock_macro_service,
        source_name="tushare",
    )


@pytest.mark.unit
class TestWriteCapital:
    """测试 _write_capital 方法。"""

    def test_write_capital_valuation_metrics_writes_successfully(
        self,
        data_writer,
        mock_capital_service,
    ) -> None:
        """验证 valuation_metrics 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pe_ratio": [12.5],
                "pb_ratio": [1.8],
                "market_cap": [1000000000.0],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="valuation_metrics",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_service.save_valuation_metrics.assert_called_once()

    def test_write_capital_margin_trading_writes_successfully(
        self,
        data_writer,
        mock_capital_service,
    ) -> None:
        """验证 margin_trading 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "fin_buy_amount": [1000000.0],
                "fin_refund_amount": [500000.0],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="margin_trading",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_service.save_margin_trading.assert_called_once()

    def test_write_capital_pledge_ratio_writes_successfully(
        self,
        data_writer,
        mock_capital_service,
    ) -> None:
        """验证 pledge_ratio 数据写入成功。"""
        # Arrange
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 12, 27)],
                "knowledge_date": [date(2024, 12, 28)],
                "effective_from": [date(2024, 12, 28)],
                "effective_to": [None],
                "pledge_ratio": [0.15],
            }
        )

        # Act
        result = data_writer.write_data(
            dataset="pledge_ratio",
            df=df,
            trade_date="2024-12-27",
        )

        # Assert
        assert result.rows_written == 1
        assert not result.blocked
        mock_capital_service.save_pledge_ratio.assert_called_once()
