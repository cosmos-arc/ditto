"""Tests for Golden Dataset functionality."""

import polars as pl
import pytest
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler
from ditto_data.quality.golden import GoldenDatasetOptions, GoldenDatasetSpec


@pytest.mark.unit
class TestGoldenDatasetSpec:
    """测试 GoldenDatasetSpec 模型."""

    def test_default_spec(self) -> None:
        """默认配置."""
        spec = GoldenDatasetSpec()

        assert spec.description == ""
        assert spec.tickers == []
        assert spec.options.enabled is True
        assert spec.is_enabled is False  # 空 tickers 所以禁用

    def test_spec_with_tickers(self) -> None:
        """带 tickers 配置."""
        spec = GoldenDatasetSpec(
            description="Test dataset",
            tickers=["600519", "000001", "510300"],
        )

        assert spec.description == "Test dataset"
        assert len(spec.tickers) == 3
        assert "600519" in spec.tickers
        assert spec.is_enabled is True
        assert len(spec.get_tickers()) == 3

    def test_spec_deduplicates_tickers(self) -> None:
        """ticker 去重."""
        spec = GoldenDatasetSpec(
            tickers=["600519", "000001", "600519", "000001", "510300"],
        )

        # 去重后排序
        assert spec.tickers == ["000001", "510300", "600519"]
        assert len(spec.tickers) == 3

    def test_spec_sorts_tickers(self) -> None:
        """ticker 排序."""
        spec = GoldenDatasetSpec(
            tickers=["510300", "600519", "000001"],
        )

        # 排序后
        assert spec.tickers == ["000001", "510300", "600519"]

    def test_spec_disabled_via_options(self) -> None:
        """通过选项禁用."""
        spec = GoldenDatasetSpec(
            tickers=["600519"],
            options=GoldenDatasetOptions(enabled=False),
        )

        assert spec.options.enabled is False
        assert spec.is_enabled is False
        assert spec.get_tickers() == []

    def test_spec_strips_whitespace(self) -> None:
        """去除空格."""
        spec = GoldenDatasetSpec(
            tickers=[" 600519 ", "  000001", "510300  "],
        )

        assert spec.tickers == ["000001", "510300", "600519"]


@pytest.mark.unit
class TestGoldenDatasetFilter:
    """测试黄金数据集过滤功能."""

    @pytest.fixture
    def golden_spec(self) -> GoldenDatasetSpec:
        """黄金数据集配置（仅包含 000001 和 510300）."""
        return GoldenDatasetSpec(
            tickers=["000001", "510300"],
            options=GoldenDatasetOptions(enabled=True),
        )

    @pytest.fixture
    def handler_with_golden(
        self,
        mock_quality_engine: pytest.fixture,
        mock_tdx_source: pytest.fixture,
        mock_comparison_writer: pytest.fixture,
        mock_instrument_store: pytest.fixture,
        golden_spec: pytest.fixture,
    ) -> ReconcileSourcesHandler:
        """带黄金数据集的对账 handler."""
        return ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            golden_dataset=golden_spec,
        )

    @pytest.fixture
    def handler_without_golden(
        self,
        mock_quality_engine: pytest.fixture,
        mock_tdx_source: pytest.fixture,
        mock_comparison_writer: pytest.fixture,
        mock_instrument_store: pytest.fixture,
    ) -> ReconcileSourcesHandler:
        """不带黄金数据集的对账 handler."""
        return ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            golden_dataset=None,
        )

    def test_filter_applies_golden_dataset(
        self,
        handler_with_golden: ReconcileSourcesHandler,
    ) -> None:
        """黄金数据集过滤生效."""
        df = pl.DataFrame(
            {
                "ticker": ["000001", "600000", "510300", "688981"],
                "trade_date": ["20240101"] * 4,
                "close": [10.0, 20.0, 4.0, 50.0],
            },
        )

        result = handler_with_golden._apply_golden_dataset_filter(df)

        # 只保留 000001 和 510300
        assert result.height == 2
        assert set(result["ticker"].to_list()) == {"000001", "510300"}

    def test_filter_disabled_when_no_config(
        self,
        handler_without_golden: ReconcileSourcesHandler,
    ) -> None:
        """未配置不过滤."""
        df = pl.DataFrame(
            {
                "ticker": ["000001", "600000", "510300", "688981"],
                "trade_date": ["20240101"] * 4,
                "close": [10.0, 20.0, 4.0, 50.0],
            },
        )

        result = handler_without_golden._apply_golden_dataset_filter(df)

        # 不过滤，保留所有
        assert result.height == 4

    def test_filter_returns_empty_when_no_match(
        self,
        handler_with_golden: ReconcileSourcesHandler,
    ) -> None:
        """无匹配返回空."""
        df = pl.DataFrame(
            {
                "ticker": ["688981", "300750"],  # 不在黄金数据集中
                "trade_date": ["20240101"] * 2,
                "close": [50.0, 200.0],
            },
        )

        result = handler_with_golden._apply_golden_dataset_filter(df)

        assert result.is_empty()

    @pytest.mark.asyncio
    async def test_reconciliation_with_golden_filter(
        self,
        mock_quality_engine: pytest.fixture,
        mock_tdx_source: pytest.fixture,
        mock_comparison_writer: pytest.fixture,
        mock_instrument_store: pytest.fixture,
        golden_spec: pytest.fixture,
        sample_primary_df: pytest.fixture,
        sample_secondary_df: pytest.fixture,
        sample_dq_result_passed: pytest.fixture,
    ) -> None:
        """对账服务集成黄金数据集过滤."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            golden_dataset=golden_spec,
        )

        # Mock enrich_with_ticker 返回包含 ticker 的 DataFrame
        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df

        # Mock TDX 数据源返回数据
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df

        # Mock 质量引擎返回通过
        mock_quality_engine.check_cross_source.return_value = sample_dq_result_passed

        # Act
        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        # Assert
        assert result.passed is True

        # 验证 TDX 数据源只收到过滤后的 tickers
        call_args = mock_tdx_source.fetch_stock_daily_bars.call_args
        requested_tickers = call_args[0][0]
        # 只应该包含 000001 和 510300
        assert set(requested_tickers) == {"000001", "510300"}

    @pytest.mark.asyncio
    async def test_reconciliation_empty_after_golden_filter(
        self,
        mock_quality_engine: pytest.fixture,
        mock_tdx_source: pytest.fixture,
        mock_comparison_writer: pytest.fixture,
        mock_instrument_store: pytest.fixture,
        sample_dq_result_passed: pytest.fixture,
    ) -> None:
        """黄金数据集过滤后为空，跳过对账."""
        # Arrange - 黄金数据集只有 000001
        golden_spec = GoldenDatasetSpec(
            tickers=["000001"],
            options=GoldenDatasetOptions(enabled=True),
        )

        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            golden_dataset=golden_spec,
        )

        # 创建数据，ticker 都不在黄金数据集中
        primary_df = pl.DataFrame(
            {
                "instrument_id": [1000002, 1000003],  # 对应 600000 和 510300
                "source_ticker": ["600000.SH", "510300.SH"],
                "trade_date": ["20240101", "20240101"],
                "close": [20.0, 4.0],
            },
        )

        # Mock enrich_with_ticker 返回 ticker
        enriched_df = primary_df.with_columns(pl.Series("ticker", ["600000", "510300"]))
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df

        # Act
        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        # Assert - 跳过对账
        assert result.passed is True
        assert result.skipped is True
        assert result.skip_reason == "golden_dataset_filter_empty"

        # 验证不会调用 TDX 数据源
        mock_tdx_source.fetch_stock_daily_bars.assert_not_called()
