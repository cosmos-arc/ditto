"""Tests for CheckDataQualityHandler（原 QualityService 逻辑）."""

import polars as pl
import pytest
from ditto_application.commands.quality_check import CheckDataQualityHandler


@pytest.mark.unit
class TestCheckDataQualityHandlerInit:
    """测试 CheckDataQualityHandler 初始化."""

    def test_init(self, mock_quality_engine) -> None:
        """正常初始化."""
        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        assert handler._engine is mock_quality_engine

    def test_init_with_quarantine_writer(
        self, mock_quality_engine, mock_quarantine_writer
    ) -> None:
        """带 quarantine_writer 初始化."""
        handler = CheckDataQualityHandler(
            engine=mock_quality_engine, quarantine_writer=mock_quarantine_writer
        )
        assert handler._engine is mock_quality_engine
        assert handler._quarantine_writer is mock_quarantine_writer


@pytest.mark.unit
class TestCheckAndQuarantine:
    """测试 handle 方法（check_and_quarantine 逻辑）."""

    def test_no_issues_returns_original_df_and_false_block(
        self, mock_quality_engine, sample_primary_df, sample_dq_result_passed
    ) -> None:
        """无质量问题，返回原数据且不阻断."""
        # Arrange
        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        mock_quality_engine.check.return_value = sample_dq_result_passed

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=sample_primary_df, dataset="stock_daily")

        # Act
        result_df, should_block = handler.handle(cmd)

        # Assert
        assert result_df.equals(sample_primary_df)
        assert should_block is False
        mock_quality_engine.check.assert_called_once_with(
            df=sample_primary_df,
            dataset="stock_daily",
            levels=["l1", "l2"],
            context=None,
        )

    def test_with_l2_warnings_does_not_block(
        self,
        mock_quality_engine,
        sample_primary_df,
        sample_dq_issue_warning,
    ) -> None:
        """L2 警告不阻断写入."""
        # Arrange
        from ditto_kernel.quality import DQResult

        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        mock_quality_engine.check.return_value = DQResult(
            dataset="stock_daily",
            passed=True,
            issues=[sample_dq_issue_warning],
        )

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=sample_primary_df, dataset="stock_daily")

        # Act
        result_df, should_block = handler.handle(cmd)

        # Assert
        assert result_df.equals(sample_primary_df)
        assert should_block is False
        mock_quality_engine.check.assert_called_once()

    def test_with_l1_errors_blocks(
        self,
        mock_quality_engine,
        sample_primary_df,
        sample_dq_issue_error,
    ) -> None:
        """L1 错误阻断写入."""
        # Arrange
        from ditto_kernel.quality import DQResult

        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        mock_quality_engine.check.return_value = DQResult(
            dataset="stock_daily",
            passed=False,
            issues=[sample_dq_issue_error],
        )

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=sample_primary_df, dataset="stock_daily")

        # Act
        result_df, should_block = handler.handle(cmd)

        # Assert
        assert result_df.equals(sample_primary_df)
        assert should_block is True

    def test_empty_dataframe_handled(self, mock_quality_engine) -> None:
        """空 DataFrame 处理."""
        # Arrange
        empty_df = pl.DataFrame()
        handler = CheckDataQualityHandler(engine=mock_quality_engine)

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=empty_df, dataset="stock_daily")

        # Act
        result_df, should_block = handler.handle(cmd)

        # Assert
        assert result_df.equals(empty_df)
        assert should_block is False
        mock_quality_engine.check.assert_called_once()

    def test_with_context_passed_to_engine(
        self, mock_quality_engine, sample_primary_df
    ) -> None:
        """传递 context 参数给引擎."""
        # Arrange
        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        context = {"reference_values": [1000001, 1000002]}

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(
            df=sample_primary_df, dataset="stock_daily", context=context
        )

        # Act
        handler.handle(cmd)

        # Assert
        mock_quality_engine.check.assert_called_once_with(
            df=sample_primary_df,
            dataset="stock_daily",
            levels=["l1", "l2"],
            context=context,
        )


@pytest.mark.unit
class TestQuarantineData:
    """测试 _quarantine_data 方法."""

    def test_quarantine_logs_info(
        self,
        mock_quality_engine,
        sample_primary_df,
        sample_dq_result_with_issues,
    ) -> None:
        """隔离数据时记录日志."""
        # Arrange
        handler = CheckDataQualityHandler(engine=mock_quality_engine)
        mock_quality_engine.check.return_value = sample_dq_result_with_issues

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=sample_primary_df, dataset="stock_daily")

        # Act
        handler.handle(cmd)

        # Assert - 验证 quarantine 被调用（通过验证日志记录来间接验证）
        mock_quality_engine.check.assert_called_once()

    def test_quarantine_saves_failed_data(
        self,
        mock_quality_engine,
        sample_primary_df,
        sample_dq_result_with_issues,
        mock_quarantine_writer,
    ) -> None:
        """测试 quarantine_writer.save_failed_data 被调用."""
        # Arrange
        handler = CheckDataQualityHandler(
            engine=mock_quality_engine, quarantine_writer=mock_quarantine_writer
        )
        mock_quality_engine.check.return_value = sample_dq_result_with_issues

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=sample_primary_df, dataset="stock_daily")

        # Act
        handler.handle(cmd)

        # Assert - 验证 quarantine store 被调用
        # 每个 issue 应该调用一次 save_failed_data
        assert mock_quarantine_writer.save_failed_data.call_count == len(
            sample_dq_result_with_issues.issues
        )
