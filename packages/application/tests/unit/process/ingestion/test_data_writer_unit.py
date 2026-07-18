"""Tests for IngestionDataWriter."""

from datetime import date

import polars as pl
import pytest
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)


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
    service.instrument.register_instruments_batch = mocker.Mock()
    service.instrument.resolve_or_create_instruments_batch = mocker.Mock()
    service.instrument.resolve_instrument_ids_batch = mocker.Mock(return_value={})

    def register_side_effect(df, source, asset_class, **kwargs):
        _ = df, source, kwargs
        return (f"instrument_store:{asset_class}_basic", f"checksum_{asset_class}")

    def resolve_side_effect(df, source, asset_class, **kwargs):
        _ = source, kwargs
        source_tickers = df["source_ticker"].to_list()
        return {source_tickers[0]: 1_000_000}

    service.instrument.register_instruments_batch.side_effect = register_side_effect
    service.instrument.resolve_or_create_instruments_batch.side_effect = (
        resolve_side_effect
    )

    return service


@pytest.fixture
def mock_market_write_service(mocker):
    """创建 Mock MarketWriteService。"""
    service = mocker.Mock()
    service.save_bars.return_value = 1
    service.save_adj_factor.return_value = 1
    service.save_fund_adj.return_value = 1
    service.save_stock_status.return_value = 1
    return service


@pytest.mark.unit
def test_fund_adj_uses_etf_writer_and_logical_catalog_uri(
    data_writer,
    mock_metadata_service,
    mock_market_write_service,
) -> None:
    mock_metadata_service.instrument.resolve_instrument_ids_batch.return_value = {
        "510300.SH": 2_000_001
    }
    df = pl.DataFrame(
        {
            "source_ticker": ["510300.SH"],
            "trade_date": [date(2024, 12, 27)],
            "adj_factor": [1.25],
        }
    )

    result = data_writer.write_data("fund_adj", df, "2024-12-27")

    assert result.file_path == "fund_adj/2024"
    mock_market_write_service.save_fund_adj.assert_called_once()
    mock_market_write_service.save_adj_factor.assert_not_called()


@pytest.fixture
def mock_fundamental_store(mocker):
    """创建 Mock FundamentalStore。"""
    service = mocker.Mock()
    service.save_balance_sheet.return_value = 1
    service.save_income_statement.return_value = 1
    service.save_cash_flow.return_value = 1
    service.save_dividend.return_value = 1
    return service


@pytest.fixture
def mock_capital_store(mocker):
    """创建 Mock CapitalStore。"""
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
    mock_market_write_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_macro_service,
):
    """创建 IngestionDataWriter 实例。"""
    return IngestionDataWriter(
        metadata_service=mock_metadata_service,
        market_write_service=mock_market_write_service,
        fundamental_store=mock_fundamental_store,
        capital_store=mock_capital_store,
        macro_service=mock_macro_service,
        source_name="tushare",
    )


@pytest.mark.unit
class TestWriteCapital:
    """测试 _write_capital 方法。"""

    def test_write_capital_valuation_metrics_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
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
        mock_capital_store.save_valuation_metrics.assert_called_once()

    def test_write_capital_margin_trading_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
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
        mock_capital_store.save_margin_trading.assert_called_once()

    def test_write_capital_pledge_ratio_writes_successfully(
        self,
        data_writer,
        mock_capital_store,
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
        mock_capital_store.save_pledge_ratio.assert_called_once()


@pytest.mark.unit
class TestWriteFundamental:
    """测试基本面写入路径。"""

    def test_write_fundamental_filters_unresolved_tickers_without_schema_error(
        self,
        data_writer,
        mock_fundamental_store,
    ) -> None:
        """空 instrument_id mapping 不应导致 Polars join dtype 错误。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["999999.SZ"],
                "report_date": [date(2024, 12, 31)],
                "announcement_date": [date(2025, 1, 7)],
                "knowledge_date": [date(2025, 1, 8)],
                "effective_from": [date(2025, 1, 8)],
                "effective_to": [None],
                "total_assets": [1_000_000.0],
            }
        )

        result = data_writer.write_data(
            dataset="balance_sheet",
            df=df,
            trade_date="2025-01-07",
        )

        assert result.rows_written == 0
        assert not result.blocked
        mock_fundamental_store.save_balance_sheet.assert_not_called()


@pytest.mark.unit
class TestToWriteResult:
    """Test _to_write_result helper."""

    def test_to_write_result_never_infers_blocked(self):
        """_to_write_result 不应从 rows_written==0 推断 blocked。
        blocked 只应由显式 DQ 检查设置。"""
        from ditto_application.processes.ingestion.data_writer import _to_write_result

        df = pl.DataFrame({"a": [1, 2, 3]})

        # 零行写入 — blocked 应为 False（不是 DQ 阻断）
        result = _to_write_result("test_ds", 2024, df, rows_written=0)
        assert result.blocked is False
        assert result.rows_written == 0

        # 正常写入 — blocked 应为 False
        result = _to_write_result("test_ds", 2024, df, rows_written=3)
        assert result.blocked is False
        assert result.rows_written == 3
