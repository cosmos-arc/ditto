"""
RiskScanStep 单元测试.
"""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.steps import RiskScanStep, StepContext, TradingStep
from ditto_kernel.strategy import RiskScope
from ditto_risk.post_trade import RiskActionType
from ditto_strategy.alpha.context import StrategyContext
from packages.backtest.tests.unit._helpers import (
    IID_1,
    _make_account_view,
    _make_clock,
    _make_ctx,
    _make_risk_action,
    _make_slice,
)


class TestRiskScanStep:
    """RiskScanStep: PostTrade 风控扫描 + 锁管理。"""

    def _make_ctx_with_data(self) -> StepContext:
        """构建包含 slice_ 和 account_view 的 StepContext。"""
        ctx = _make_ctx()
        ctx.slice_ = _make_slice()
        ctx.account_view = _make_account_view()
        return ctx

    def test_skips_when_no_post_trade_guard(self) -> None:
        """post_trade_guard 为 None 时跳过风控扫描。"""
        step = RiskScanStep(
            post_trade_guard=None,
            audit_collector=None,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True

    def test_scans_and_locks_instruments(self) -> None:
        """REDUCE_POSITION + INSTRUMENT scope -> 锁定标的。"""
        action = _make_risk_action(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
            cooldown_until_date="2026-03-05",
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)

        assert result.success is True
        assert strategy_context.is_locked(IID_1)

    def test_liquidate_locks_instrument(self) -> None:
        """LIQUIDATE + INSTRUMENT scope -> 锁定标的。"""
        action = _make_risk_action(
            action_type=RiskActionType.LIQUIDATE,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        assert strategy_context.is_locked(IID_1)

    def test_alert_does_not_lock_instrument(self) -> None:
        """ALERT action 不锁定标的（action_type 不在锁定范围）。"""
        action = _make_risk_action(
            action_type=RiskActionType.ALERT,
            instrument_id=IID_1,
            scope=RiskScope.INSTRUMENT,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        assert not strategy_context.is_locked(IID_1)

    def test_portfolio_scope_does_not_lock(self) -> None:
        """PORTFOLIO scope 不锁定（只有 INSTRUMENT scope 才锁定）。"""
        action = _make_risk_action(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=None,
            scope=RiskScope.PORTFOLIO,
        )
        strategy_context = StrategyContext()
        guard = Mock(scan=Mock(return_value=[action]))

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=None,
            strategy_context=strategy_context,
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        # PORTFOLIO scope -> 不锁定任何标的
        assert len(strategy_context.get_locked_instruments()) == 0

    def test_records_risk_scan_audit(self) -> None:
        """有 audit_collector 时记录风控扫描审计。"""
        action = _make_risk_action()
        guard = Mock(scan=Mock(return_value=[action]))
        collector = Mock(spec=ExecutionAuditCollector)

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=collector,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        collector.record_risk_scan.assert_called_once()
        call_args = collector.record_risk_scan.call_args
        assert call_args[0][0] == "2026-03-01"  # date

    def test_publishes_risk_guard_triggered_event(self) -> None:
        """有 event_bus 时发布 RiskGuardTriggered 事件。"""
        action = _make_risk_action()
        guard = Mock(scan=Mock(return_value=[action]))
        event_bus = Mock()

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=None,
            event_bus=event_bus,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.rule_name == "single_loss_limit"

    def test_no_audit_when_no_risk_actions(self) -> None:
        """guard 扫描无结果时不记录审计。"""
        guard = Mock(scan=Mock(return_value=[]))
        collector = Mock(spec=ExecutionAuditCollector)

        step = RiskScanStep(
            post_trade_guard=guard,
            audit_collector=collector,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )

        ctx = self._make_ctx_with_data()
        step.execute(ctx)

        collector.record_risk_scan.assert_not_called()

    def test_satisfies_trading_step_protocol(self) -> None:
        """RiskScanStep 满足 TradingStep Protocol。"""
        step: TradingStep = RiskScanStep(  # type: ignore[assignment]
            post_trade_guard=None,
            audit_collector=None,
            event_bus=None,
            strategy_context=StrategyContext(),
            clock=_make_clock(),
        )
        ctx = self._make_ctx_with_data()
        result = step.execute(ctx)
        assert result.success is True
