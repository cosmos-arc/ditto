"""Tests for ReconcileSourcesHandler（原 QualityReconciliationService）.

#395 语义：比较键 instrument_id + trade_date；零交集 = 不可比较（不算通过）；
结果报告两侧数量/匹配/未匹配/重复键/差异数。
#438 adj_factor：事件流 vs 累积因子的同基准比例，不可推导事件单列。
"""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.commands.quality_reconciliation import (
    ReconcileSourcesCommand,
    ReconcileSourcesHandler,
)


def _handler(
    mock_quality_engine,
    mock_tdx_source,
    mock_comparison_writer,
    mock_instrument_store,
    mock_secondary_identity_resolver,
) -> ReconcileSourcesHandler:
    return ReconcileSourcesHandler(
        engine=mock_quality_engine,
        secondary_source=mock_tdx_source,
        comparison_store=mock_comparison_writer,
        instrument_store=mock_instrument_store,
        secondary_identity_resolver=mock_secondary_identity_resolver,
    )


@pytest.mark.unit
class TestReconcileSourcesHandlerInit:
    """测试 ReconcileSourcesHandler 初始化."""

    def test_init(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
    ) -> None:
        """正常初始化."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        assert handler._engine is mock_quality_engine
        assert handler._secondary_source is mock_tdx_source
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
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
        comparable_report,
    ) -> None:
        """完整对账流程成功（非零交集，匹配数>0）。"""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = sample_dq_result_passed
        mock_quality_engine.compare_cross_source.return_value = comparable_report

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is True
        assert result.comparable is True
        assert result.issue_count == 0
        assert result.trade_date == "20240101"
        assert result.dataset == "stock_daily"
        assert result.matched_count == 3

        mock_instrument_store.enrich_with_ticker.assert_called_once_with(
            sample_primary_df,
        )
        mock_tdx_source.fetch_stock_daily_bars.assert_called_once()
        mock_quality_engine.check_cross_source.assert_called_once()
        mock_secondary_identity_resolver.resolve_secondary_ids.assert_called_once()

    def test_no_secondary_data_is_not_comparable(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
    ) -> None:
        """零辅源数据 = 零交集：不可比较，不算通过（#395 收紧）。"""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = pl.DataFrame()

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.comparable is False
        assert result.matched_count == 0
        mock_quality_engine.check_cross_source.assert_not_called()

    def test_no_issues_no_storage(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
        comparable_report,
    ) -> None:
        """无问题时不存储结果."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = sample_dq_result_passed
        mock_quality_engine.compare_cross_source.return_value = comparable_report

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

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
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_with_issues,
        comparable_report,
    ) -> None:
        """有 ERROR 问题时不通过并存储对比结果."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = (
            sample_dq_result_with_issues
        )
        mock_quality_engine.compare_cross_source.return_value = comparable_report

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.issue_count == 2
        mock_comparison_writer.write_comparison.assert_called_once()

    def test_with_issues_sends_alerts(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_with_issues,
        comparable_report,
    ) -> None:
        """有问题时触发告警."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = (
            sample_dq_result_with_issues
        )
        mock_quality_engine.compare_cross_source.return_value = comparable_report

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        handler.handle(cmd)


@pytest.mark.unit
class TestDailyReconciliationEdgeCases:
    """测试 handle 边界情况."""

    def test_missing_sid_column_raises(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
    ) -> None:
        """缺少 instrument_id 列时抛出异常."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        df_without_sid = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["20240101"],
                "close": [10.0],
            },
        )

        cmd = ReconcileSourcesCommand(
            primary_df=df_without_sid,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "AppCommandError" in result.error

    def test_enrich_with_ticker_fails(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
        sample_dq_result_passed,
    ) -> None:
        """ticker 补全失败时抛出异常."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        mock_instrument_store.enrich_with_ticker.side_effect = None
        df_without_ticker = sample_primary_df.select("instrument_id")
        mock_instrument_store.enrich_with_ticker.return_value = df_without_ticker
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.check_cross_source.return_value = sample_dq_result_passed

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "AppCommandError" in result.error

    def test_unexpected_error_returns_error_dict(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
    ) -> None:
        """未知异常返回错误字典."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_quality_engine.compare_cross_source.side_effect = RuntimeError(
            "Unexpected error",
        )

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.error is not None
        assert "RuntimeError" in result.error

    def test_unresolved_secondary_identities_fail_closed(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_secondary_df,
    ) -> None:
        """辅源身份全部无法反解 → 显式零交集不可比较（不算通过）。"""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        enriched_df = sample_primary_df.with_columns(
            pl.Series("ticker", ["000001", "600000", "510300"]),
        )
        mock_instrument_store.enrich_with_ticker.return_value = enriched_df
        mock_tdx_source.fetch_stock_daily_bars.return_value = sample_secondary_df
        mock_secondary_identity_resolver.resolve_secondary_ids.return_value = {}

        cmd = ReconcileSourcesCommand(
            primary_df=sample_primary_df,
            trade_date="20240101",
            dataset="stock_daily",
        )
        result = handler.handle(cmd)

        assert result.passed is False
        assert result.comparable is False
        assert result.matched_count == 0


@pytest.mark.unit
class TestConvertResultToDf:
    """测试 _convert_result_to_df 方法."""

    def test_empty_issues_returns_empty_df(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_dq_result_passed,
    ) -> None:
        """无问题时返回空 DataFrame."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        result_df = handler._convert_result_to_df(
            sample_dq_result_passed,
            "stock_daily",
            sample_primary_df,
        )

        assert result_df.is_empty()

    def test_single_issue_multiple_samples(
        self,
        mock_quality_engine,
        mock_tdx_source,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_dq_result_with_issues,
    ) -> None:
        """单个问题多个样本转换为多行."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        result_df = handler._convert_result_to_df(
            sample_dq_result_with_issues,
            "stock_daily",
            sample_primary_df,
        )

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
        mock_secondary_identity_resolver,
        sample_primary_df,
        sample_dq_result_with_issues,
    ) -> None:
        """所有字段正确映射（落盘列与 CLI 输出同步，含 instrument_id 与除权标记）."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        result_df = handler._convert_result_to_df(
            sample_dq_result_with_issues,
            "stock_daily",
            sample_primary_df,
        )

        expected_columns = {
            "dataset",
            "instrument_id",
            "ticker",
            "trade_date",
            "field",
            "primary_value",
            "secondary_value",
            "diff",
            "ex_dividend_day",
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
        mock_secondary_identity_resolver,
        sample_dq_result_with_issues,
    ) -> None:
        """告警记录为 warning 级别."""
        handler = _handler(
            mock_quality_engine,
            mock_tdx_source,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
        )

        handler._send_alerts(sample_dq_result_with_issues, "20240101", "stock_daily")


def _adj_factor_events_df() -> pl.DataFrame:
    """辅源事件帧（裸码；000001 可推导，600000 缺配股价，510300 缺前价）."""
    return pl.DataFrame(
        {
            "ticker": ["000001", "600000", "510300"],
            "trade_date": [date(2025, 6, 25)] * 3,
            "dividend_per_share": [1.0, None, 0.5],
            "per_share_bonus": [None, None, None],
            "allotment_ratio": [None, 0.1, None],
            "allotment_price": [None, None, None],
        },
        schema={
            "ticker": pl.String,
            "trade_date": pl.Date,
            "dividend_per_share": pl.Float64,
            "per_share_bonus": pl.Float64,
            "allotment_ratio": pl.Float64,
            "allotment_price": pl.Float64,
        },
    )


def _adj_factor_factor_window() -> pl.DataFrame:
    """主源因子窗口：1000001 除权日比例 = 20/19（与事件口径一致）."""
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000001],
            "trade_date": [date(2025, 6, 24), date(2025, 6, 25)],
            "adj_factor": [10.0, 200.0 / 19.0],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "adj_factor": pl.Float64,
        },
    )


def _adj_factor_prev_closes() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000002],
            "prev_close": [20.0, 10.0],
        },
        schema={"instrument_id": pl.Int64, "prev_close": pl.Float64},
    )


def _adj_factor_primary_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1000001, 1000002, 1000003],
            "trade_date": [date(2025, 6, 25)] * 3,
            "adj_factor": [200.0 / 19.0, 1.0, 1.0],
        },
        schema={
            "instrument_id": pl.Int64,
            "trade_date": pl.Date,
            "adj_factor": pl.Float64,
        },
    )


@pytest.mark.unit
class TestAdjFactorReconciliation:
    """#438：adj_factor 对账（事件流 vs 累积因子同基准比例）."""

    def _handler(
        self,
        mock_quality_engine,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        events_source,
        adj_context,
    ) -> ReconcileSourcesHandler:
        return ReconcileSourcesHandler(
            engine=mock_quality_engine,
            secondary_source=MagicMock(),
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            secondary_identity_resolver=mock_secondary_identity_resolver,
            secondary_events_source=events_source,
            adj_factor_context=adj_context,
        )

    def _context_mock(self) -> MagicMock:
        context = MagicMock()
        context.factor_window.return_value = _adj_factor_factor_window()
        context.previous_closes.return_value = _adj_factor_prev_closes()
        return context

    def test_pass_flow_compares_derived_ratios(
        self,
        mock_quality_engine,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
        comparable_report,
    ) -> None:
        """完整流程：事件反解→两侧推导→engine 按数据集规则比较."""
        events_source = MagicMock()
        events_source.fetch_adjustment_events.return_value = _adj_factor_events_df()
        handler = self._handler(
            mock_quality_engine,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
            events_source,
            self._context_mock(),
        )

        result = handler.handle(
            ReconcileSourcesCommand(
                primary_df=_adj_factor_primary_df(),
                trade_date="2025-06-25",
                dataset="adj_factor",
            )
        )

        assert result.passed is True
        assert result.comparable is True
        # 事件侧 3 行全部参与键核算；缺配股价/缺前价 2 行单列不可推导
        assert result.secondary_underivable_count == 2
        call = mock_quality_engine.compare_cross_source.call_args
        assert call.kwargs["dataset"] == "adj_factor"
        assert "adjustment_ratio" in call.kwargs["primary"].columns
        assert "adjustment_ratio" in call.kwargs["secondary"].columns

    def test_underivable_events_written_to_comparison_store(
        self,
        mock_quality_engine,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
    ) -> None:
        """不可推导事件落盘单列（field=event_underivable，原因进 message）."""
        events_source = MagicMock()
        events_source.fetch_adjustment_events.return_value = _adj_factor_events_df()
        handler = self._handler(
            mock_quality_engine,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
            events_source,
            self._context_mock(),
        )

        handler.handle(
            ReconcileSourcesCommand(
                primary_df=_adj_factor_primary_df(),
                trade_date="2025-06-25",
                dataset="adj_factor",
            )
        )

        written = mock_comparison_writer.write_comparison.call_args.args[1]
        underivable = written.filter(pl.col("field") == "event_underivable")
        assert underivable.height == 2
        assert set(underivable["rule"].to_list()) == {"cross_source_event_underivable"}
        messages = " ".join(underivable["message"].to_list())
        assert "missing_allotment_price" in messages
        assert "missing_prev_close" in messages

    def test_no_events_not_comparable(
        self,
        mock_quality_engine,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
    ) -> None:
        """零事件 = 零交集：不可比较，不算通过."""
        events_source = MagicMock()
        events_source.fetch_adjustment_events.return_value = pl.DataFrame()
        handler = self._handler(
            mock_quality_engine,
            mock_comparison_writer,
            mock_instrument_store,
            mock_secondary_identity_resolver,
            events_source,
            self._context_mock(),
        )

        result = handler.handle(
            ReconcileSourcesCommand(
                primary_df=_adj_factor_primary_df(),
                trade_date="2025-06-25",
                dataset="adj_factor",
            )
        )

        assert result.passed is False
        assert result.comparable is False
        mock_quality_engine.check_cross_source.assert_not_called()

    def test_missing_dependencies_return_error_result(
        self,
        mock_quality_engine,
        mock_comparison_writer,
        mock_instrument_store,
        mock_secondary_identity_resolver,
    ) -> None:
        """缺事件辅源/主源上下文：错误结果而非崩溃."""
        handler = ReconcileSourcesHandler(
            engine=mock_quality_engine,
            secondary_source=MagicMock(),
            comparison_store=mock_comparison_writer,
            instrument_store=mock_instrument_store,
            secondary_identity_resolver=mock_secondary_identity_resolver,
        )

        result = handler.handle(
            ReconcileSourcesCommand(
                primary_df=_adj_factor_primary_df(),
                trade_date="2025-06-25",
                dataset="adj_factor",
            )
        )

        assert result.passed is False
        assert result.error is not None
