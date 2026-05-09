"""质量服务层测试共享 Fixtures."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.quality.kernel_types import DQIssue, DQLevel, DQResult, DQSeverity
from pytest_mock import MockerFixture


@pytest.fixture
def mock_quality_engine(mocker: MockerFixture) -> MagicMock:
    """Mock QualityEngine.

    默认配置为返回通过（无问题），可在测试中覆盖。
    """
    engine = mocker.MagicMock()
    engine.check.return_value = DQResult(
        dataset="test_dataset",
        passed=True,
        issues=[],
    )
    return engine


@pytest.fixture
def mock_quarantine_writer(mocker: MockerFixture) -> MagicMock:
    """Mock QuarantineWriter.

    提供 save_failed_data 方法。
    """
    writer = mocker.MagicMock()

    def save_failed_data_impl(
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        """模拟 save_failed_data 实现."""
        return 1

    writer.save_failed_data.side_effect = save_failed_data_impl
    return writer


@pytest.fixture
def mock_instrument_store(mocker: MockerFixture) -> MagicMock:
    """Mock InstrumentStore.

    提供 enrich_with_ticker 方法，将 instrument_id 转换为 ticker。
    """
    store = mocker.MagicMock()

    def enrich_with_ticker_impl(df: pl.DataFrame) -> pl.DataFrame:
        """模拟 enrich_with_ticker 实现."""
        if df.is_empty():
            return df
        # 为每个 instrument_id 分配一个 ticker
        ticker_map = {
            1000001: "000001",
            1000002: "600000",
            1000003: "510300",
        }
        tickers = [
            ticker_map.get(instrument_id, "")
            for instrument_id in df["instrument_id"].to_list()
        ]
        return df.with_columns(pl.Series("ticker", tickers))

    store.enrich_with_ticker.side_effect = enrich_with_ticker_impl
    return store


@pytest.fixture
def mock_tdx_source(mocker: MockerFixture) -> MagicMock:
    """Mock TdxSource.

    默认返回空 DataFrame，可在测试中覆盖。
    """
    source = mocker.MagicMock()
    source.fetch_stock_daily_bars.return_value = pl.DataFrame()
    return source


@pytest.fixture
def mock_comparison_writer(mocker: MockerFixture) -> MagicMock:
    """Mock ComparisonWriter.

    提供 write_comparison 同步方法。
    """
    writer = mocker.MagicMock()

    def write_comparison_impl(trade_date: str, df: pl.DataFrame, dataset: str) -> None:
        """模拟 write_comparison 实现."""
        pass

    writer.write_comparison.side_effect = write_comparison_impl
    return writer


@pytest.fixture
def mock_statistical_engine() -> MagicMock:
    """Mock QualityEngine configured for statistical checks.

    使用 check_statistical 方法（区别于 mock_quality_engine 的 check 方法）。
    """
    engine = MagicMock()
    result = DQResult(
        dataset="stock_daily",
        passed=True,
        issues=[],
    )
    engine.check_statistical.return_value = result
    return engine


@pytest.fixture
def mock_market_service() -> MagicMock:
    """Mock MarketService."""
    service = MagicMock()
    service.find_bars.return_value = pl.DataFrame()
    return service


@pytest.fixture
def mock_metadata_service() -> MagicMock:
    """Mock MetadataService."""
    service = MagicMock()
    service.list_calendar_range.return_value = pl.DataFrame()
    return service


@pytest.fixture
def sample_primary_df() -> pl.DataFrame:
    """示例主数据源 DataFrame.

    包含 instrument_id 列，需要通过 InstrumentStore 补全 ticker。
    """
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000002, 1000003],
            "source_ticker": ["000001.SZ", "600000.SH", "510300.SH"],
            "trade_date": ["20240101", "20240101", "20240101"],
            "open": [10.0, 20.0, 4.0],
            "high": [10.5, 20.5, 4.1],
            "low": [9.8, 19.8, 3.9],
            "close": [10.2, 20.2, 4.05],
            "volume": [1000000, 2000000, 500000],
            "amount": [10200000, 20200000, 2025000],
        }
    )


@pytest.fixture
def sample_secondary_df() -> pl.DataFrame:
    """示例辅助数据源 DataFrame (TDX).

    包含 ticker 列（已转换格式）。
    """
    return pl.DataFrame(
        {
            "ticker": ["000001", "600000", "510300"],
            "trade_date": ["20240101", "20240101", "20240101"],
            "open": [10.0, 20.0, 4.0],
            "high": [10.5, 20.5, 4.1],
            "low": [9.8, 19.8, 3.9],
            "close": [10.2, 20.2, 4.05],
            "volume": [1000000, 2000000, 500000],
            "amount": [10200000, 20200000, 2025000],
        }
    )


@pytest.fixture
def sample_dq_issue_error() -> DQIssue:
    """示例 DQ Issue - ERROR 级别."""
    return DQIssue(
        level=DQLevel.TECHNICAL,
        severity=DQSeverity.ERROR,
        rule_name="not_null",
        message="Column 'close' contains null values",
        affected_rows=2,
        sample_data=[
            {"ticker": "000001", "trade_date": "20240101", "field": "close"},
            {"ticker": "600000", "trade_date": "20240101", "field": "close"},
        ],
    )


@pytest.fixture
def sample_dq_issue_warning() -> DQIssue:
    """示例 DQ Issue - WARNING 级别."""
    return DQIssue(
        level=DQLevel.BUSINESS,
        severity=DQSeverity.WARNING,
        rule_name="positive",
        message="Column 'volume' contains non-positive values",
        affected_rows=1,
        sample_data=[
            {
                "ticker": "510300",
                "trade_date": "20240101",
                "field": "volume",
                "value": 0,
            },
        ],
    )


@pytest.fixture
def sample_dq_result_passed() -> DQResult:
    """示例 DQ Result - 通过."""
    return DQResult(
        dataset="stock_daily",
        passed=True,
        issues=[],
    )


@pytest.fixture
def sample_dq_result_with_issues(
    sample_dq_issue_error: DQIssue,
    sample_dq_issue_warning: DQIssue,
) -> DQResult:
    """示例 DQ Result - 包含问题."""
    return DQResult(
        dataset="stock_daily",
        passed=False,
        issues=[sample_dq_issue_error, sample_dq_issue_warning],
    )
