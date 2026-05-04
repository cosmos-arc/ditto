"""
AuditStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.steps import AuditStep, StepContext, TradingStep
from packages.backtest.tests.unit._helpers import (
    _make_account_view,
    _make_fill,
    _make_slice,
)


class TestAuditStep:
    """AuditStep: 记录账户快照 + 成交 + 平仓交易审计。"""

    def _make_ctx_with_fills(self) -> StepContext:
        """构建包含 slice_, fills 的 StepContext。"""
        ctx = StepContext(date="2026-03-01", is_rebalance_day=True)
        ctx.slice_ = _make_slice()
        fill = _make_fill()
        ctx.step_fills.append(fill)
        return ctx

    def test_records_account_view(self) -> None:
        """记录每日账户快照到 audit_collector。"""
        account_view = _make_account_view()
        brokerage = Mock(get_account=Mock(return_value=account_view))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)

        assert result.success is True
        collector.record_account_view.assert_called_once_with(
            "2026-03-01",
            account_view,
        )

    def test_records_fills(self) -> None:
        """记录每个 fill 到 audit_collector。"""
        fill = _make_fill()
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        collector.record_fill.assert_called_once_with(fill)

    def test_records_closed_trades(self) -> None:
        """通过 trade_builder 匹配成交 -> 记录已平仓交易。"""
        trade = Mock(trade_id="trade-1")
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[trade]),
        )
        recorded_ids: set[str] = set()

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=recorded_ids,
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        collector.record_closed_trade.assert_called_once_with(trade)
        assert "trade-1" in recorded_ids

    def test_deduplicates_closed_trades(self) -> None:
        """已记录的 trade_id 不重复记录。"""
        trade = Mock(trade_id="trade-1")
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[trade]),
        )
        recorded_ids: set[str] = {"trade-1"}  # 已存在

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=recorded_ids,
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        # 已记录的不重复
        collector.record_closed_trade.assert_not_called()

    def test_passes_fills_to_trade_builder(self) -> None:
        """每个 fill 传给 trade_builder.on_fill。"""
        fill = _make_fill()
        account_view = _make_account_view()
        brokerage = Mock(get_account=Mock(return_value=account_view))
        collector = Mock(spec=ExecutionAuditCollector)
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=collector,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        step.execute(ctx)

        trade_builder.on_fill.assert_called_once_with(fill, account_view)

    def test_skips_when_no_audit_collector(self) -> None:
        """audit_collector 为 None 时跳过审计。"""
        brokerage = Mock(get_account=Mock(return_value=_make_account_view()))
        trade_builder = Mock(
            on_fill=Mock(),
            get_closed_trades=Mock(return_value=[]),
        )

        step = AuditStep(
            audit_collector=None,
            brokerage=brokerage,
            trade_builder=trade_builder,
            recorded_trade_ids=set(),
        )

        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)

        assert result.success is True

    def test_satisfies_trading_step_protocol(self) -> None:
        """AuditStep 满足 TradingStep Protocol。"""
        step: TradingStep = AuditStep(  # type: ignore[assignment]
            audit_collector=None,
            brokerage=Mock(get_account=Mock(return_value=_make_account_view())),
            trade_builder=Mock(
                on_fill=Mock(),
                get_closed_trades=Mock(return_value=[]),
            ),
            recorded_trade_ids=set(),
        )
        ctx = self._make_ctx_with_fills()
        result = step.execute(ctx)
        assert result.success is True
