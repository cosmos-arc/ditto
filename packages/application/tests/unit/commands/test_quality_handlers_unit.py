"""质量 Command Handler 单元测试."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_kernel.quality import DQResult

# ---------------------------------------------------------------------------
# CheckDataQualityHandler
# ---------------------------------------------------------------------------


class TestCheckDataQualityHandler:
    """CheckDataQualityHandler — 数据质量检查 Command Handler."""

    def _make_handler(
        self, *, engine: MagicMock | None = None, writer: MagicMock | None = None
    ) -> tuple:
        """构建 CheckDataQualityHandler 及其 mock 依赖."""
        from ditto_application.commands.quality_check import (
            CheckDataQualityHandler,
        )

        mock_engine = engine or MagicMock()
        if not engine:
            # 仅在未提供自定义 engine 时设置默认 return_value
            mock_engine.check.return_value = DQResult(
                dataset="test", passed=True, issues=[]
            )
        mock_writer = writer

        handler = CheckDataQualityHandler(
            engine=mock_engine, quarantine_writer=mock_writer
        )
        return handler, mock_engine, mock_writer

    def test_handle_delegates_to_engine(self) -> None:
        """Handler 将 command 参数委托给 QualityEngine.check."""
        handler, mock_engine, _ = self._make_handler()
        df = pl.DataFrame({"a": [1, 2, 3]})

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=df, dataset="stock_daily")
        result_df, has_errors = handler.handle(cmd)

        assert result_df is df
        assert has_errors is False
        mock_engine.check.assert_called_once_with(
            df=df,
            dataset="stock_daily",
            levels=["l1", "l2"],
            context=None,
        )

    def test_handle_passes_context(self) -> None:
        """Handler 正确传递 context 参数给 engine."""
        handler, mock_engine, _ = self._make_handler()
        df = pl.DataFrame({"a": [1]})
        context = {"reference_values": [100]}

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=df, dataset="etf_daily", context=context)
        handler.handle(cmd)

        mock_engine.check.assert_called_once_with(
            df=df,
            dataset="etf_daily",
            levels=["l1", "l2"],
            context=context,
        )

    def test_handle_returns_has_errors_true(self) -> None:
        """当有 L1 错误时，返回 (df, True)."""
        from ditto_kernel.quality import DQIssue, DQLevel, DQSeverity

        mock_engine = MagicMock()
        mock_engine.check.return_value = DQResult(
            dataset="test",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="not_null",
                    message="null found",
                    affected_rows=1,
                ),
            ],
        )

        handler, _, _ = self._make_handler(engine=mock_engine)
        df = pl.DataFrame({"a": [1]})

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=df, dataset="test")
        result_df, has_errors = handler.handle(cmd)

        assert has_errors is True
        assert result_df is df

    def test_handle_propagates_engine_error(self) -> None:
        """Handler 传播 engine 抛出的异常."""
        mock_engine = MagicMock()
        mock_engine.check.side_effect = ValueError("engine error")

        handler, _, _ = self._make_handler(engine=mock_engine)

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=pl.DataFrame(), dataset="bad")

        with pytest.raises(ValueError, match="engine error"):
            handler.handle(cmd)

    def test_quarantine_writer_called_on_issues(self) -> None:
        """有 issue 时 quarantine_writer.save_failed_data 被调用."""
        from ditto_kernel.quality import DQIssue, DQLevel, DQSeverity

        mock_engine = MagicMock()
        mock_engine.check.return_value = DQResult(
            dataset="stock_daily",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="not_null",
                    message="null found",
                    affected_rows=2,
                    sample_data=[
                        {"ticker": "000001", "field": "close"},
                        {"ticker": "600000", "field": "close"},
                    ],
                ),
            ],
        )
        mock_writer = MagicMock()

        handler, _, _ = self._make_handler(engine=mock_engine, writer=mock_writer)
        df = pl.DataFrame({"a": [1]})

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=df, dataset="stock_daily")
        handler.handle(cmd)

        mock_writer.save_failed_data.assert_called_once()

    def test_no_quarantine_writer_skips_gracefully(self) -> None:
        """无 quarantine_writer 时不报错."""
        from ditto_kernel.quality import DQIssue, DQLevel, DQSeverity

        mock_engine = MagicMock()
        mock_engine.check.return_value = DQResult(
            dataset="test",
            passed=False,
            issues=[
                DQIssue(
                    level=DQLevel.TECHNICAL,
                    severity=DQSeverity.WARNING,
                    rule_name="positive",
                    message="negative value",
                    affected_rows=1,
                    sample_data=[{"ticker": "000001"}],
                ),
            ],
        )

        handler, _, _ = self._make_handler(engine=mock_engine, writer=None)
        df = pl.DataFrame({"a": [1]})

        from ditto_application.contracts import CheckDataQualityCommand

        cmd = CheckDataQualityCommand(df=df, dataset="test")
        result_df, _has_errors = handler.handle(cmd)

        assert result_df is df

    def test_satisfies_command_handler_protocol(self) -> None:
        """CheckDataQualityHandler 满足 CommandHandler Protocol."""
        from ditto_application.commands.protocols import CommandHandler

        handler, _, _ = self._make_handler()
        assert isinstance(handler, CommandHandler)


# ---------------------------------------------------------------------------
# ReconcileSourcesHandler — 直接使用 Protocol mocks
# ---------------------------------------------------------------------------


def _make_handler(
    *,
    engine: MagicMock | None = None,
    tdx_source: MagicMock | None = None,
    comparison_store: MagicMock | None = None,
    instrument_store: MagicMock | None = None,
) -> tuple:
    """构建 ReconcileSourcesHandler 及其 mock 依赖."""
    from ditto_application.commands.quality_reconciliation import (
        ReconcileSourcesHandler,
    )

    mock_engine = engine or MagicMock()
    mock_tdx = tdx_source or MagicMock()
    mock_comparison = comparison_store or MagicMock()
    mock_instrument = instrument_store or MagicMock()

    handler = ReconcileSourcesHandler(
        engine=mock_engine,
        tdx_source=mock_tdx,
        comparison_store=mock_comparison,
        instrument_store=mock_instrument,
    )
    return handler, mock_engine, mock_tdx, mock_comparison, mock_instrument


class TestReconcileSourcesHandler:
    """ReconcileSourcesHandler — 数据源对账 Command Handler."""

    def test_full_reconciliation_pass(self) -> None:
        """完整对账流程成功."""
        from ditto_kernel.quality import DQResult

        handler, mock_engine, mock_tdx, _mock_cmp, mock_instrument = _make_handler()

        primary_df = pl.DataFrame({"instrument_id": [1000001]})
        enriched_df = primary_df.with_columns(pl.Series("ticker", ["000001"]))
        mock_instrument.enrich_with_ticker.return_value = enriched_df
        mock_tdx.fetch_stock_daily_bars.return_value = pl.DataFrame(
            {"ticker": ["000001"], "close": [10.0]},
        )
        mock_engine.check_cross_source.return_value = DQResult(
            dataset="stock_daily",
            passed=True,
            issues=[],
        )

        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=primary_df,
            trade_date="20250115",
            dataset="stock_daily",
        )

        result = handler.handle(cmd)

        assert result.passed is True
        assert result.issue_count == 0
        assert result.trade_date == "20250115"
        assert result.dataset == "stock_daily"

        mock_instrument.enrich_with_ticker.assert_called_once_with(primary_df)
        mock_tdx.fetch_stock_daily_bars.assert_called_once()
        mock_engine.check_cross_source.assert_called_once()

    def test_no_secondary_data_skips(self) -> None:
        """无辅助数据时跳过."""
        handler, mock_engine, mock_tdx, _, mock_instrument = _make_handler()

        primary_df = pl.DataFrame({"instrument_id": [1000001]})
        enriched_df = primary_df.with_columns(pl.Series("ticker", ["000001"]))
        mock_instrument.enrich_with_ticker.return_value = enriched_df
        mock_tdx.fetch_stock_daily_bars.return_value = pl.DataFrame()

        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=primary_df,
            trade_date="20250115",
            dataset="stock_daily",
        )

        result = handler.handle(cmd)

        assert result.passed is True
        assert result.issue_count == 0
        assert result.skip_reason == "no_secondary_data"
        mock_engine.check_cross_source.assert_not_called()

    def test_missing_instrument_id_returns_error(self) -> None:
        """缺少 instrument_id 列时返回错误结果."""
        handler, *_ = _make_handler()

        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=pl.DataFrame({"a": [1]}),
            trade_date="20250115",
        )

        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "ValueError" in result.error

    def test_handle_returns_reconciliation_with_issues(self) -> None:
        """当对账发现问题时返回 passed=False."""
        from ditto_kernel.quality import DQIssue, DQLevel, DQResult, DQSeverity

        handler, mock_engine, mock_tdx, mock_comparison, mock_instrument = (
            _make_handler()
        )

        primary_df = pl.DataFrame({"instrument_id": [1000001]})
        enriched_df = primary_df.with_columns(pl.Series("ticker", ["000001"]))
        mock_instrument.enrich_with_ticker.return_value = enriched_df
        mock_tdx.fetch_stock_daily_bars.return_value = pl.DataFrame(
            {"ticker": ["000001"], "close": [10.0]},
        )

        issues = [
            DQIssue(
                level=DQLevel.TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message="close is null",
                affected_rows=1,
                sample_data=[{"ticker": "000001", "trade_date": "20250115"}],
            ),
        ]
        mock_engine.check_cross_source.return_value = DQResult(
            dataset="stock_daily",
            passed=False,
            issues=issues,
        )

        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=primary_df,
            trade_date="20250115",
            dataset="stock_daily",
        )

        result = handler.handle(cmd)

        assert result.passed is False
        assert result.issue_count == 1
        mock_comparison.write_comparison.assert_called_once()

    def test_handle_unexpected_error_returns_error_result(self) -> None:
        """未知异常返回错误结果."""
        handler, mock_engine, mock_tdx, _, mock_instrument = _make_handler()

        primary_df = pl.DataFrame({"instrument_id": [1000001]})
        enriched_df = primary_df.with_columns(pl.Series("ticker", ["000001"]))
        mock_instrument.enrich_with_ticker.return_value = enriched_df
        mock_tdx.fetch_stock_daily_bars.return_value = pl.DataFrame(
            {"ticker": ["000001"], "close": [10.0]},
        )
        mock_engine.check_cross_source.side_effect = RuntimeError("Unexpected error")

        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesCommand,
        )

        cmd = ReconcileSourcesCommand(
            primary_df=primary_df,
            trade_date="20250115",
        )

        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "RuntimeError" in result.error

    def test_satisfies_command_handler_protocol(self) -> None:
        """ReconcileSourcesHandler 满足 CommandHandler Protocol."""
        from ditto_application.commands.protocols import CommandHandler
        from ditto_application.commands.quality_reconciliation import (
            ReconcileSourcesHandler,
        )

        handler = ReconcileSourcesHandler(
            engine=MagicMock(),
            tdx_source=MagicMock(),
            comparison_store=MagicMock(),
            instrument_store=MagicMock(),
        )
        assert isinstance(handler, CommandHandler)
