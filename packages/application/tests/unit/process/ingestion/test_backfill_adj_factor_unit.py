"""Tests for IngestionCoordinator.backfill_adj_factor — smart gap detection."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.coordinator import (
    IngestionCoordinator,
    IngestionServices,
    MarketServices,
    SourceFetchers,
)
from ditto_platform.foundation import (
    Environment,
    ObservabilityConfig,
    init,
    reset_for_testing,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def mock_metadata_service():
    """创建 Mock MetadataService。"""
    service = MagicMock()
    service.is_trading_day.return_value = True
    service.list_trading_days.return_value = []
    service.resolve_source_ticker.return_value = "000001.SZ"
    # IngestionDataWriter._write_adj_factor 需要 resolve_instrument_ids_batch
    service.resolve_instrument_ids_batch.return_value = {
        "000001.SZ": 1,
    }
    return service


@pytest.fixture
def mock_market_service():
    """创建 Mock MarketService（用于读取）。"""
    service = MagicMock()
    return service


@pytest.fixture
def mock_fundamental_store():
    """创建 Mock FundamentalStore。"""
    return MagicMock()


@pytest.fixture
def mock_capital_store():
    """创建 Mock CapitalStore。"""
    return MagicMock()


@pytest.fixture
def mock_macro_service():
    """创建 Mock MacroService。"""
    return MagicMock()


@pytest.fixture
def mock_source():
    """创建 Mock DataSource。"""
    return MagicMock()


@pytest.fixture
def coordinator(
    mock_metadata_service,
    mock_market_service,
    mock_fundamental_store,
    mock_capital_store,
    mock_macro_service,
    mock_source,
):
    """创建 IngestionCoordinator 实例。"""
    return IngestionCoordinator(
        services=IngestionServices(
            metadata=mock_metadata_service,
            market=MarketServices(
                query=mock_market_service,
                write=MagicMock(),
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
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackfillAdjFactor:
    """测试 backfill_adj_factor 智能回填方法。"""

    def test_no_gaps_returns_empty_summary(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """当数据完整（无空洞）时，不发起任何 fetch 调用。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-05"

        trading_days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        mock_metadata_service.list_trading_days.return_value = trading_days

        # 已有全部交易日的数据
        existing_dates = pl.DataFrame(
            {
                "instrument_id": [instrument_id] * 4,
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ],
                "adj_factor": [1.0, 1.0, 1.0, 1.0],
            }
        )
        mock_market_service.get_adj_factors.return_value = existing_dates

        # Act
        result = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result["status"] == "ok"
        assert result["gap_count"] == 0
        assert result["filled_dates"] == 0
        mock_source.fetch_adj_factor_by_ticker.assert_not_called()

    def test_single_gap_fetches_missing_dates(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """当存在一个空洞时，只 fetch 缺失的日期范围。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-05"

        trading_days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        mock_metadata_service.list_trading_days.return_value = trading_days

        # 缺少 2024-01-03
        existing_dates = pl.DataFrame(
            {
                "instrument_id": [instrument_id, instrument_id, instrument_id],
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        mock_market_service.get_adj_factors.return_value = existing_dates

        gap_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 1, 3)],
                "adj_factor": [1.0],
            }
        )
        mock_source.fetch_adj_factor_by_ticker.return_value = gap_df

        # Act
        result = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result["status"] == "ok"
        assert result["gap_count"] == 1
        assert result["filled_dates"] == 1
        mock_source.fetch_adj_factor_by_ticker.assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240103",
            end_date="20240103",
        )

    def test_multiple_gaps_fetches_all_missing_ranges(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """当存在多个不连续空洞时，按连续区间分组 fetch。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-08"

        trading_days = [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-06",
            "2024-01-07",
            "2024-01-08",
        ]
        mock_metadata_service.list_trading_days.return_value = trading_days

        # 只有 1/2 和 1/5 有数据，空洞为 [1/3-1/4] 和 [1/6-1/8]
        existing_dates = pl.DataFrame(
            {
                "instrument_id": [instrument_id, instrument_id],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 5)],
                "adj_factor": [1.0, 1.0],
            }
        )
        mock_market_service.get_adj_factors.return_value = existing_dates

        gap1_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 2,
                "trade_date": [date(2024, 1, 3), date(2024, 1, 4)],
                "adj_factor": [1.0, 1.0],
            }
        )
        gap2_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 3,
                "trade_date": [date(2024, 1, 6), date(2024, 1, 7), date(2024, 1, 8)],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        mock_source.fetch_adj_factor_by_ticker.side_effect = [gap1_df, gap2_df]

        # Act
        result = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result["status"] == "ok"
        assert result["gap_count"] == 2
        assert result["filled_dates"] == 5
        assert mock_source.fetch_adj_factor_by_ticker.call_count == 2
        mock_source.fetch_adj_factor_by_ticker.assert_any_call(
            ts_code="000001.SZ",
            start_date="20240103",
            end_date="20240104",
        )
        mock_source.fetch_adj_factor_by_ticker.assert_any_call(
            ts_code="000001.SZ",
            start_date="20240106",
            end_date="20240108",
        )

    def test_empty_existing_data_fetches_full_range(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """当已有数据为空时，fetch 整个日期范围。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-04"

        trading_days = ["2024-01-02", "2024-01-03", "2024-01-04"]
        mock_metadata_service.list_trading_days.return_value = trading_days

        # 没有已有数据
        mock_market_service.get_adj_factors.return_value = pl.DataFrame()

        full_df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 3,
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        mock_source.fetch_adj_factor_by_ticker.return_value = full_df

        # Act
        result = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result["status"] == "ok"
        assert result["gap_count"] == 1
        assert result["filled_dates"] == 3
        mock_source.fetch_adj_factor_by_ticker.assert_called_once_with(
            ts_code="000001.SZ",
            start_date="20240102",
            end_date="20240104",
        )

    def test_idempotent_no_duplicate_writes(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """连续调用两次，第二次不应再发起 fetch。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-04"

        trading_days = ["2024-01-02", "2024-01-03", "2024-01-04"]
        mock_metadata_service.list_trading_days.return_value = trading_days

        full_df = pl.DataFrame(
            {
                "instrument_id": [instrument_id] * 3,
                "trade_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "adj_factor": [1.0, 1.0, 1.0],
            }
        )
        mock_market_service.get_adj_factors.return_value = full_df

        # Act — 第一次调用
        result1 = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Act — 第二次调用
        result2 = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result1["gap_count"] == 0
        assert result2["gap_count"] == 0
        mock_source.fetch_adj_factor_by_ticker.assert_not_called()

    def test_fetch_returns_empty_records_as_filled_zero(
        self,
        coordinator: IngestionCoordinator,
        mock_metadata_service: MagicMock,
        mock_market_service: MagicMock,
        mock_source: MagicMock,
    ) -> None:
        """数据源返回空数据时，filled_dates 仍为 0，不报错。"""
        # Arrange
        instrument_id = 1
        start = "2024-01-02"
        end = "2024-01-04"

        trading_days = ["2024-01-02", "2024-01-03", "2024-01-04"]
        mock_metadata_service.list_trading_days.return_value = trading_days

        # 没有已有数据
        mock_market_service.get_adj_factors.return_value = pl.DataFrame()

        # 数据源返回空
        mock_source.fetch_adj_factor_by_ticker.return_value = pl.DataFrame()

        # Act
        result = coordinator.backfill_adj_factor(instrument_id, start, end)

        # Assert
        assert result["status"] == "ok"
        assert result["gap_count"] == 1
        assert result["filled_dates"] == 0
