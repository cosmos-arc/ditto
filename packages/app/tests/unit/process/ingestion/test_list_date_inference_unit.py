"""Tests for ListDateInferenceService."""

from datetime import date

import polars as pl
import pytest
from ditto_app.process.ingestion.list_date_inference import (
    API_LIMITS,
    EARLIEST_LIST_DATE_INFERENCE,
    ListDateInferenceService,
)
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability import init, reset_for_testing
from ditto_platform.foundation.observability.config import ObservabilityConfig


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
    empty_df = pl.DataFrame()
    service.find_instruments_without_list_date = mocker.Mock(return_value=empty_df)
    service.update_list_date = mocker.Mock()
    return service


@pytest.fixture
def mock_source(mocker):
    """创建 Mock DataSource。"""
    source = mocker.Mock()
    source.fetch_stock_daily = mocker.Mock(return_value=pl.DataFrame())
    source.fetch_etf_daily = mocker.Mock(return_value=pl.DataFrame())
    source.fetch_index_daily = mocker.Mock(return_value=pl.DataFrame())
    return source


@pytest.fixture
def inference_service(mock_metadata_service, mock_source):
    """创建 ListDateInferenceService 实例。"""
    return ListDateInferenceService(
        metadata_service=mock_metadata_service,
        source=mock_source,
        source_name="tushare",
    )


@pytest.mark.unit
class TestListDateInferenceService:
    """测试 ListDateInferenceService。"""

    def test_constants_are_correct(self) -> None:
        """验证常量配置正确。"""
        assert date(2010, 1, 1) == EARLIEST_LIST_DATE_INFERENCE
        assert API_LIMITS["stock"] == 6000
        assert API_LIMITS["etf"] == 2000
        assert API_LIMITS["index"] == 8000
        assert API_LIMITS["sw_index"] == 4000

    def test_infer_for_asset_class_no_instruments_without_list_date(
        self,
        inference_service,
        mock_metadata_service,
    ) -> None:
        """当没有 list_date 为 NULL 的证券时，返回 0。"""
        # Arrange
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            pl.DataFrame()
        )

        # Act
        result = inference_service.infer_for_asset_class("stock")

        # Assert
        assert result == 0
        mock_metadata_service.find_instruments_without_list_date.assert_called_once_with(
            asset_class="stock"
        )

    def test_infer_for_asset_class_infers_list_date(
        self,
        inference_service,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """成功推断 list_date。"""
        # Arrange
        instruments_without_list_date = pl.DataFrame(
            {
                "instrument_id": [1],
                "source_ticker": ["000001.SZ"],
            }
        )
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            instruments_without_list_date
        )

        # Mock 历史数据返回
        mock_source.fetch_stock_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 3,
                "trade_date": [
                    date(2020, 1, 15),
                    date(2020, 1, 16),
                    date(2020, 1, 17),
                ],
            }
        )

        # Act
        result = inference_service.infer_for_asset_class("stock")

        # Assert
        assert result == 1
        mock_metadata_service.update_list_date.assert_called_once_with(
            1, date(2020, 1, 15)
        )

    def test_infer_for_asset_class_ignores_dates_before_2010(
        self,
        inference_service,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """早于 2010 年的日期不被用于推断。"""
        # Arrange
        instruments_without_list_date = pl.DataFrame(
            {
                "instrument_id": [1],
                "source_ticker": ["000001.SZ"],
            }
        )
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            instruments_without_list_date
        )

        # Mock 历史数据返回（包含 2010 年前后的数据）
        mock_source.fetch_stock_daily.return_value = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"] * 2,
                "trade_date": [date(2009, 12, 31), date(2010, 1, 4)],
            }
        )

        # Act
        result = inference_service.infer_for_asset_class("stock")

        # Assert
        assert result == 1
        mock_metadata_service.update_list_date.assert_called_once_with(
            1, date(2010, 1, 4)
        )

    def test_infer_for_asset_class_handles_fetch_error(
        self,
        inference_service,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """处理数据获取错误，不影响主流程。"""
        # Arrange
        instruments_without_list_date = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "source_ticker": ["000001.SZ", "000002.SZ"],
            }
        )
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            instruments_without_list_date
        )

        # 第一个证券获取失败，第二个成功
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error")
            return pl.DataFrame(
                {
                    "source_ticker": ["000002.SZ"],
                    "trade_date": [date(2021, 3, 10)],
                }
            )

        mock_source.fetch_stock_daily.side_effect = side_effect

        # Act
        result = inference_service.infer_for_asset_class("stock")

        # Assert
        assert result == 1  # 只有第二个成功
        # 只更新了第二个证券
        mock_metadata_service.update_list_date.assert_called_once_with(
            2, date(2021, 3, 10)
        )

    def test_infer_for_asset_class_handles_empty_data(
        self,
        inference_service,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """处理空数据，不更新 list_date。"""
        # Arrange
        instruments_without_list_date = pl.DataFrame(
            {
                "instrument_id": [1],
                "source_ticker": ["000001.SZ"],
            }
        )
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            instruments_without_list_date
        )

        # Mock 返回空数据
        mock_source.fetch_stock_daily.return_value = pl.DataFrame()

        # Act
        result = inference_service.infer_for_asset_class("stock")

        # Assert
        assert result == 0
        mock_metadata_service.update_list_date.assert_not_called()

    def test_infer_for_asset_class_uses_correct_fetch_method(
        self,
        inference_service,
        mock_metadata_service,
        mock_source,
    ) -> None:
        """不同资产类型使用正确的 fetch 方法。"""
        # Arrange
        instruments_without_list_date = pl.DataFrame(
            {
                "instrument_id": [1],
                "source_ticker": ["000001.SZ"],
            }
        )
        mock_metadata_service.find_instruments_without_list_date.return_value = (
            instruments_without_list_date
        )

        # Mock 所有 fetch 方法返回有效数据
        for mock_method in [
            mock_source.fetch_stock_daily,
            mock_source.fetch_etf_daily,
            mock_source.fetch_index_daily,
        ]:
            mock_method.return_value = pl.DataFrame(
                {
                    "source_ticker": ["000001.SZ"],
                    "trade_date": [date(2020, 1, 15)],
                }
            )

        # Act & Assert - stock
        inference_service.infer_for_asset_class("stock")
        mock_source.fetch_stock_daily.assert_called()

        # Act & Assert - etf
        inference_service.infer_for_asset_class("etf")
        mock_source.fetch_etf_daily.assert_called()

        # Act & Assert - index
        inference_service.infer_for_asset_class("index")
        mock_source.fetch_index_daily.assert_called()
