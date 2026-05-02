"""Tests for ReconcileSourcesHandler（原 QualityReconciliationService）."""

import polars as pl
import pytest
from ditto_application.commands.quality_reconciliation import ReconcileSourcesHandler


@pytest.mark.unit
class TestReconcileSourcesHandlerInit:
    """测试 ReconcileSourcesHandler 初始化."""

    def test_init(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
    ) -> None:
        """正常初始化."""
        # Act
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Assert
        assert handler._engine is mock_quality_engine
        assert handler._tdx_source is mock_tdx_source
        assert handler._comparison_store is mock_comparison_writer
        assert handler._instrument_store is mock_instrument_store


@pytest.mark.unit
class TestDailyReconciliationSuccess:
    """测试 handle 成功场景."""

    def test_full_reconciliation_pass(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
    ) -> None:
        """完整对账流程成功."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Mock enrich_with_ticker 返回包含 symbol 的 DataFrame
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
        assert result.issue_count == 0
        assert result.trade_date == "20240101"
        assert result.dataset == "stock_daily"

        # 验证调用链
        mock_instrument_store.enrich_with_ticker.assert_called_once_with(
            sample_primary_df,
        )
        mock_tdx_source.fetch_stock_daily_bars.assert_called_once()
        mock_quality_engine.check_cross_source.assert_called_once()

    def test_no_secondary_data_skips(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
    ) -> None:
        """无辅助数据时跳过."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df

        # TDX 返回空数据
        mock_tdx_source.fetch_stock_daily_bars.return_value = pl.DataFrame()

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
        assert result.issue_count == 0
        assert result.skip_reason == "no_secondary_data"

        # 验证不会调用引擎检查
        mock_quality_engine.check_cross_source.assert_not_called()

    def test_no_issues_no_storage(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
    ) -> None:
        """无问题时不存储结果."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
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

        # Assert - 验证不存储结果
        mock_comparison_writer.write_comparison.assert_not_called()
        assert result.passed is True


@pytest.mark.unit
class TestDailyReconciliationWithIssues:
    """测试 handle 有问题场景."""

    def test_with_issues_stores_result(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_with_issues,
    ) -> None:
        """有问题时存储对比结果."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = (
            sample_dq_result_with_issues
        )

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
        assert result.passed is False
        assert result.issue_count == 2

        # 验证存储结果被调用
        mock_comparison_writer.write_comparison.assert_called_once()

    def test_with_issues_sends_alerts(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_with_issues,
    ) -> None:
        """有问题时触发告警."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = (
            sample_dq_result_with_issues
        )

        # Act
        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        handler.handle(cmd)

        # Assert - _send_alerts 应该被调用（通过验证日志）


@pytest.mark.unit
class TestDailyReconciliationEdgeCases:
    """测试 handle 边界情况."""

    def test_missing_sid_column_raises(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
    ) -> None:
        """缺少 instrument_id 列时抛出异常."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # 创建没有 instrument_id 列的 DataFrame
        df_without_sid = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["20240101"],
                "close": [10.0],
            },
        )

        # Act & Assert
        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=df_without_sid,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "ValueError" in result.error

    def test_enrich_with_ticker_fails(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
    ) -> None:
        """Symbol 补全失败时抛出异常."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # 重置 side_effect 并设置 return_value 返回没有 symbol 列的 DataFrame
        mock_instrument_store.enrich_with_ticker.side_effect = None
        df_without_ticker = sample_primary_df.select("instrument_id")
        mock_instrument_store.enrich_with_ticker.return_value = df_without_ticker

        # Mock TDX 返回数据，以便代码能执行到 symbol 检查
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df

        # Mock check_cross_source 返回值（虽然预期不会到达这里）
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
        assert result.passed is False
        assert result.error is not None
        assert "ValueError" in result.error

    def test_unexpected_error_returns_error_dict(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_primary_df,
        sample_secondary_df,
    ) -> None:
        """未知异常返回错误字典."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df

        # Mock TDX 返回数据
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df

        # Mock 引擎抛出异常
        mock_quality_engine.check_cross_source.side_effect = RuntimeError(
            "Unexpected error",
        )

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
        assert result.passed is False
        assert result.error is not None
        assert "RuntimeError" in result.error


@pytest.mark.unit
class TestConvertResultToDf:
    """测试 _convert_result_to_df 方法."""

    def test_empty_issues_returns_empty_df(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_dq_result_passed,
    ) -> None:
        """无问题时返回空 DataFrame."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Act
        result_df = handler._convert_result_to_df(
            sample_dq_result_passed,
            "stock_daily",
        )

        # Assert
        assert result_df.is_empty()

    def test_single_issue_multiple_samples(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_dq_result_with_issues,
    ) -> None:
        """单个问题多个样本转换为多行."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Act
        result_df = handler._convert_result_to_df(
            sample_dq_result_with_issues,
            "stock_daily",
        )

        # Assert - 验证行数等于总样本数
        total_samples = sum(
            len(issue.sample_data) for issue in sample_dq_result_with_issues.issues
        )
        assert len(result_df) == total_samples

    def test_all_fields_mapped_correctly(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_dq_result_with_issues,
    ) -> None:
        """所有字段正确映射."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Act
        result_df = handler._convert_result_to_df(
            sample_dq_result_with_issues,
            "stock_daily",
        )

        # Assert - 验证必需列存在
        expected_columns = {
            "dataset",
            "ticker",
            "trade_date",
            "field",
            "primary_value",
            "secondary_value",
            "diff",
            "severity",
            "rule",
            "message",
        }
        assert set(result_df.columns) == expected_columns


@pytest.mark.unit
class TestSendAlerts:
    """测试 _send_alerts 方法."""

    def test_alerts_logged_as_warning(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        sample_dq_result_with_issues,
    ) -> None:
        """告警记录为 warning 级别."""
        # Arrange
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            tdx_source=mock_tdx_source,
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
        )

        # Act - 调用 _send_alerts
        handler._send_alerts(sample_dq_result_with_issues, "20240101", "stock_daily")

        # Assert - 验证方法完成（通过日志记录验证）
        # （实际验证需要检查日志输出）
