"""PostTrade RiskGuard 单元测试。"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from unittest.mock import Mock

import pytest
from ditto_engine.accounting.account import AccountView
from ditto_engine.accounting.cash import CashBook
from ditto_engine.accounting.order_book import OrderBook
from ditto_engine.accounting.position import Position
from ditto_engine.alpha.models import TargetPortfolio
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.engine import EngineConfig, EngineLoop, EngineOptions
from ditto_engine.execution.reality.market import MarketSnapshot
from ditto_engine.risk.post_trade import (
    CompositePostTradeGuard,
    ConcentrationLimitRule,
    MarketAnomalyRule,
    MaxDrawdownRule,
    PostTradeRiskGuard,
    RiskAction,
    RiskActionType,
    RiskSeverity,
    SingleLossLimitRule,
)
from ditto_engine.risk.pre_trade import Decision, OrderCheckResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_position(
    instrument_id: int = 1,
    quantity: int = 1000,
    average_cost: float = 4.0,
    market_value: float = 5000.0,
    unrealized_pnl: float = 1000.0,
) -> Position:
    return Position(
        instrument_id=instrument_id,
        quantity=quantity,
        available_quantity=quantity,
        average_cost=average_cost,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=0.0,
        total_fees=0.0,
    )


def _make_account_view(
    nav: float = 100000.0,
    positions: dict[int, Position] | None = None,
) -> AccountView:
    pos = positions or {}
    cash = CashBook(available=50000.0, settled=50000.0, frozen=0.0)
    return AccountView(
        positions=MappingProxyType(pos),
        cash=cash,
        total_value=nav,
        nav=nav,
        exposure=sum(p.market_value for p in pos.values()),
        pending_buy_value=0.0,
        order_book=OrderBook().readonly_view(),
    )


def _make_bar(
    instrument_id: int = 1,
    close: float = 4.5,
    prev_close: float = 4.3,
) -> MarketSnapshot:
    return MarketSnapshot(
        trade_date="2026-01-15",
        instrument_id=instrument_id,
        open=prev_close,
        high=close,
        low=prev_close,
        close=close,
        prev_close=prev_close,
        volume=1000000.0,
        amount=4500000.0,
    )


def _make_slice(bars: dict[int, MarketSnapshot] | None = None) -> Slice:
    return Slice(
        trade_date="2026-01-15",
        step_time=datetime(2026, 1, 15, 15, 0),
        bars=bars or {},
    )


# ---------------------------------------------------------------------------
# RiskAction — Model Tests
# ---------------------------------------------------------------------------


class TestRiskAction:
    def test_frozen_immutability(self) -> None:
        action = RiskAction(
            action_type=RiskActionType.ALERT,
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.WARNING,
            rule_id="test_rule",
            detail="test detail",
            current_value=0.15,
            threshold=0.10,
        )
        with pytest.raises(AttributeError):
            action.instrument_id = 99  # type: ignore[misc]

    def test_default_optional_fields(self) -> None:
        action = RiskAction(
            action_type=RiskActionType.ALERT,
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.WARNING,
            rule_id="test",
            detail="d",
            current_value=0.1,
            threshold=0.1,
        )
        assert action.cooldown_until_date is None
        assert action.target_quantity is None

    def test_portfolio_wide_action_has_none_instrument_id(self) -> None:
        """Portfolio-wide actions use instrument_id=None, scope='portfolio'."""
        action = RiskAction(
            action_type=RiskActionType.LIQUIDATE,
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.EMERGENCY,
            rule_id="max_drawdown",
            detail="drawdown exceeded",
            current_value=0.25,
            threshold=0.20,
        )
        assert action.instrument_id is None
        assert action.scope == "portfolio"

    def test_instrument_action_has_concrete_instrument_id(self) -> None:
        """Instrument-scoped actions use concrete instrument_id, scope='instrument'."""
        action = RiskAction(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.CRITICAL,
            rule_id="single_loss_limit",
            detail="loss exceeded",
            current_value=0.20,
            threshold=0.15,
        )
        assert action.instrument_id == 1
        assert action.scope == "instrument"


class TestRiskActionType:
    def test_enum_values(self) -> None:
        assert RiskActionType.REDUCE_POSITION == "reduce_position"
        assert RiskActionType.LIQUIDATE == "liquidate"
        assert RiskActionType.ALERT == "alert"


class TestRiskSeverity:
    def test_enum_values(self) -> None:
        assert RiskSeverity.WARNING == "warning"
        assert RiskSeverity.CRITICAL == "critical"
        assert RiskSeverity.EMERGENCY == "emergency"


# ---------------------------------------------------------------------------
# MaxDrawdownRule
# ---------------------------------------------------------------------------


class TestMaxDrawdownRule:
    def test_no_drawdown_returns_empty(self) -> None:
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_warning_threshold_triggers_alert(self) -> None:
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        # First scan sets peak at 100k, second scan at 88k -> 12% drawdown
        view_peak = _make_account_view(nav=100000.0)
        sl = _make_slice()
        rule.scan(view_peak, sl)

        view_dd = _make_account_view(nav=88000.0)
        actions = rule.scan(view_dd, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT
        assert actions[0].severity == RiskSeverity.WARNING
        assert actions[0].instrument_id is None
        assert actions[0].scope == "portfolio"
        assert actions[0].rule_id == "max_drawdown"

    def test_emergency_threshold_triggers_liquidate(self) -> None:
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        view_peak = _make_account_view(nav=100000.0)
        sl = _make_slice()
        rule.scan(view_peak, sl)

        view_dd = _make_account_view(nav=75000.0)
        actions = rule.scan(view_dd, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.LIQUIDATE
        assert actions[0].severity == RiskSeverity.EMERGENCY
        assert actions[0].instrument_id is None
        assert actions[0].scope == "portfolio"

    def test_peak_nav_tracks_across_scans(self) -> None:
        rule = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        sl = _make_slice()

        # Scan 1: NAV=100k -> peak=100k
        rule.scan(_make_account_view(nav=100000.0), sl)
        # Scan 2: NAV=110k -> peak=110k
        rule.scan(_make_account_view(nav=110000.0), sl)
        # Scan 3: NAV=99k -> drawdown = (110k-99k)/110k = 10% >= 10%
        actions = rule.scan(_make_account_view(nav=99000.0), sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT

    def test_zero_peak_nav_returns_empty(self) -> None:
        rule = MaxDrawdownRule()
        view = _make_account_view(nav=0.0)
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_negative_peak_nav_impossible(self) -> None:
        """NAV cannot be negative, but even if somehow set, peak stays 0."""
        rule = MaxDrawdownRule()
        # Scan with NAV=0 keeps peak at 0
        sl = _make_slice()
        rule.scan(_make_account_view(nav=0.0), sl)
        # Negative NAV (shouldn't happen in practice)
        actions = rule.scan(_make_account_view(nav=-1000.0), sl)
        assert actions == []

    def test_invalid_thresholds_raise(self) -> None:
        with pytest.raises(ValueError, match="must be non-negative"):
            MaxDrawdownRule(warning_threshold=-0.1, emergency_threshold=0.2)
        with pytest.raises(ValueError, match=r"warning_threshold.*emergency"):
            MaxDrawdownRule(warning_threshold=0.30, emergency_threshold=0.20)


# ---------------------------------------------------------------------------
# SingleLossLimitRule
# ---------------------------------------------------------------------------


class TestSingleLossLimitRule:
    def test_no_positions_returns_empty(self) -> None:
        rule = SingleLossLimitRule(threshold=0.15)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_not_in_loss_returns_empty(self) -> None:
        rule = SingleLossLimitRule(threshold=0.15)
        pos = _make_position(instrument_id=1, average_cost=4.0)
        bar = _make_bar(instrument_id=1, close=4.5, prev_close=4.3)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_loss_exceeds_threshold(self) -> None:
        rule = SingleLossLimitRule(threshold=0.15)
        pos = _make_position(
            instrument_id=1,
            average_cost=4.0,
        )
        # Price at 3.0 -> loss = (3.0-4.0)/4.0 = 25% > 15%
        bar = _make_bar(instrument_id=1, close=3.0, prev_close=3.2)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.REDUCE_POSITION
        assert actions[0].severity == RiskSeverity.CRITICAL
        assert actions[0].instrument_id == 1
        assert actions[0].rule_id == "single_loss_limit"

    def test_position_without_bar_data_skipped(self) -> None:
        rule = SingleLossLimitRule(threshold=0.15)
        pos = _make_position(instrument_id=1, average_cost=4.0)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice(bars={})  # No bar data for position

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_exactly_at_threshold_no_action(self) -> None:
        """Position at exactly the threshold boundary (not exceeded) -> no action."""
        rule = SingleLossLimitRule(threshold=0.15)
        pos = _make_position(
            instrument_id=1,
            average_cost=4.0,
        )
        # Loss limit = 4.0 * (1 - 0.15) = 3.4. Price at 3.4 = exactly threshold.
        bar = _make_bar(instrument_id=1, close=3.4, prev_close=3.5)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_multiple_positions_some_in_loss(self) -> None:
        rule = SingleLossLimitRule(threshold=0.15)
        pos1 = _make_position(instrument_id=1, average_cost=4.0)
        pos2 = _make_position(instrument_id=2, average_cost=1.0)
        bar1 = _make_bar(instrument_id=1, close=3.0, prev_close=3.2)
        bar2 = _make_bar(instrument_id=2, close=1.1, prev_close=1.0)
        view = _make_account_view(
            nav=100000.0,
            positions={1: pos1, 2: pos2},
        )
        sl = _make_slice(bars={1: bar1, 2: bar2})

        actions = rule.scan(view, sl)

        assert len(actions) == 1
        assert actions[0].instrument_id == 1

    def test_invalid_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold must be positive"):
            SingleLossLimitRule(threshold=0.0)
        with pytest.raises(ValueError, match="threshold must be positive"):
            SingleLossLimitRule(threshold=-0.1)


# ---------------------------------------------------------------------------
# ConcentrationLimitRule
# ---------------------------------------------------------------------------


class TestConcentrationLimitRule:
    def test_no_positions_returns_empty(self) -> None:
        rule = ConcentrationLimitRule(max_weight=0.20)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_under_limit_returns_empty(self) -> None:
        rule = ConcentrationLimitRule(max_weight=0.20)
        pos = _make_position(instrument_id=1, market_value=10000.0)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_over_limit_returns_action(self) -> None:
        rule = ConcentrationLimitRule(max_weight=0.20)
        pos = _make_position(instrument_id=1, market_value=30000.0)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.REDUCE_POSITION
        assert actions[0].severity == RiskSeverity.WARNING
        assert actions[0].instrument_id == 1
        assert actions[0].rule_id == "concentration_limit"

    def test_zero_nav_returns_empty(self) -> None:
        rule = ConcentrationLimitRule(max_weight=0.20)
        pos = _make_position(instrument_id=1, market_value=10000.0)
        view = _make_account_view(nav=0.0, positions={1: pos})
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_position_at_exact_limit_returns_empty(self) -> None:
        """Weight exactly at limit (20%) -> no action (must be >, not >=)."""
        rule = ConcentrationLimitRule(max_weight=0.20)
        pos = _make_position(instrument_id=1, market_value=20000.0)
        view = _make_account_view(nav=100000.0, positions={1: pos})
        sl = _make_slice()

        actions = rule.scan(view, sl)

        assert actions == []

    def test_invalid_max_weight_raises(self) -> None:
        with pytest.raises(ValueError, match="max_weight must be in"):
            ConcentrationLimitRule(max_weight=0.0)
        with pytest.raises(ValueError, match="max_weight must be in"):
            ConcentrationLimitRule(max_weight=1.5)


# ---------------------------------------------------------------------------
# MarketAnomalyRule
# ---------------------------------------------------------------------------


class TestMarketAnomalyRule:
    def test_no_bars_returns_empty(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_normal_return_returns_empty(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        bar = _make_bar(instrument_id=1, close=4.35, prev_close=4.30)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_large_positive_return_triggers_alert(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        bar = _make_bar(instrument_id=1, close=4.80, prev_close=4.30)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT
        assert actions[0].instrument_id == 1
        assert actions[0].rule_id == "market_anomaly"

    def test_large_negative_return_triggers_alert(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        bar = _make_bar(instrument_id=1, close=3.80, prev_close=4.30)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert len(actions) == 1
        assert actions[0].action_type == RiskActionType.ALERT
        assert actions[0].instrument_id == 1

    def test_zero_prev_close_skipped(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        bar = _make_bar(instrument_id=1, close=4.50, prev_close=0.0)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_negative_prev_close_skipped(self) -> None:
        """Negative prev_close would cause wrong abs() calc — skip it."""
        rule = MarketAnomalyRule(threshold=0.05)
        bar = MarketSnapshot(
            trade_date="2026-01-15",
            instrument_id=1,
            open=4.5,
            high=4.5,
            low=4.5,
            close=4.5,
            prev_close=-1.0,
            volume=1000000.0,
            amount=4500000.0,
        )
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar})

        actions = rule.scan(view, sl)

        assert actions == []

    def test_multiple_bars_some_anomaly(self) -> None:
        rule = MarketAnomalyRule(threshold=0.05)
        bar1 = _make_bar(instrument_id=1, close=4.35, prev_close=4.30)
        bar2 = _make_bar(instrument_id=2, close=5.50, prev_close=5.00)
        view = _make_account_view(nav=100000.0)
        sl = _make_slice(bars={1: bar1, 2: bar2})

        actions = rule.scan(view, sl)

        # 159915.SZ: abs(5.5/5.0 - 1) = 10% > 5%
        assert len(actions) == 1
        assert actions[0].instrument_id == 2

    def test_invalid_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold must be positive"):
            MarketAnomalyRule(threshold=0.0)
        with pytest.raises(ValueError, match="threshold must be positive"):
            MarketAnomalyRule(threshold=-0.05)


# ---------------------------------------------------------------------------
# CompositePostTradeGuard
# ---------------------------------------------------------------------------


class TestCompositePostTradeGuard:
    def test_empty_rules_returns_empty(self) -> None:
        guard = CompositePostTradeGuard(rules=())
        view = _make_account_view(nav=100000.0)
        sl = _make_slice()

        actions = guard.scan(view, sl)

        assert actions == []

    def test_multiple_rules_collect_all_actions(self) -> None:
        """Multiple rules each return actions, all collected."""
        # Mock rule 1: returns 1 action
        mock_rule1 = Mock(spec=PostTradeRiskGuard)
        action1 = RiskAction(
            action_type=RiskActionType.ALERT,
            instrument_id=1,
            scope="instrument",
            severity=RiskSeverity.WARNING,
            rule_id="rule_1",
            detail="test",
            current_value=0.1,
            threshold=0.1,
        )
        mock_rule1.scan.return_value = [action1]

        # Mock rule 2: returns 2 actions
        mock_rule2 = Mock(spec=PostTradeRiskGuard)
        action2 = RiskAction(
            action_type=RiskActionType.REDUCE_POSITION,
            instrument_id=2,
            scope="instrument",
            severity=RiskSeverity.CRITICAL,
            rule_id="rule_2",
            detail="test",
            current_value=0.2,
            threshold=0.15,
        )
        action3 = RiskAction(
            action_type=RiskActionType.LIQUIDATE,
            instrument_id=None,
            scope="portfolio",
            severity=RiskSeverity.EMERGENCY,
            rule_id="rule_2",
            detail="test",
            current_value=0.3,
            threshold=0.2,
        )
        mock_rule2.scan.return_value = [action2, action3]

        guard = CompositePostTradeGuard(
            rules=(mock_rule1, mock_rule2),
        )
        view = _make_account_view(nav=100000.0)
        sl = _make_slice()

        actions = guard.scan(view, sl)

        assert len(actions) == 3
        assert actions[0].instrument_id == 1
        assert actions[0].scope == "instrument"
        assert actions[1].instrument_id == 2
        assert actions[1].scope == "instrument"
        assert actions[2].instrument_id is None
        assert actions[2].scope == "portfolio"

    def test_real_rules_combined(self) -> None:
        """Real rule instances combined via CompositePostTradeGuard."""
        max_dd = MaxDrawdownRule(warning_threshold=0.10, emergency_threshold=0.20)
        concentration = ConcentrationLimitRule(max_weight=0.20)

        guard = CompositePostTradeGuard(rules=(max_dd, concentration))

        # Set peak, then drop below warning threshold
        view_peak = _make_account_view(nav=100000.0)
        sl = _make_slice()
        guard.scan(view_peak, sl)

        # Now: NAV=85k (15% drawdown) + concentrated position
        pos = _make_position(instrument_id=1, market_value=30000.0)
        view_dd = _make_account_view(
            nav=85000.0,
            positions={1: pos},
        )
        actions = guard.scan(view_dd, sl)

        # MaxDrawdown: 15% > 10% -> ALERT
        # Concentration: 30k/85k = 35.3% > 20% -> REDUCE_POSITION
        assert len(actions) == 2
        action_types = {a.action_type for a in actions}
        assert RiskActionType.ALERT in action_types
        assert RiskActionType.REDUCE_POSITION in action_types


# ---------------------------------------------------------------------------
# EngineLoop Integration Tests
# ---------------------------------------------------------------------------


def _make_engine_config() -> EngineConfig:
    return EngineConfig(
        start_date="2026-01-15",
        end_date="2026-01-17",
        initial_cash=1_000_000.0,
        strategy_id="default",
        strategy_run_id="run-test",
    )


def _make_mock_plan() -> Mock:
    """创建空的 mock ExecutionPlan。"""
    return Mock(
        plan_id="plan-001",
        trade_date="2026-01-15",
        orders=(),
        estimated_turnover=0.0,
        estimated_cost=0.0,
        blocked_orders=(),
    )


def _make_target_portfolio(
    positions: dict[int, float] | None = None,
) -> TargetPortfolio:
    """创建 mock TargetPortfolio。"""
    return TargetPortfolio(
        trade_date="2026-01-15",
        strategy_id="default",
        run_id="run-test",
        positions=positions or {},
        cash_target=1.0 - sum(positions.values()) if positions else 1.0,
    )


class TestEngineLoopPostTradeIntegration:
    """PostTrade guard 集成到 EngineLoop._step 的测试。"""

    def test_post_trade_guard_triggers_locks_passed_to_planner(self) -> None:
        """PostTrade 扫描产生 REDUCE_POSITION → locked_instruments 传给 planner。"""
        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15"],
                target=_make_target_portfolio({1: 0.3}),
                plan=_make_mock_plan(),
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.return_value = [
            RiskAction(
                action_type=RiskActionType.REDUCE_POSITION,
                instrument_id=1,
                scope="instrument",
                severity=RiskSeverity.CRITICAL,
                rule_id="single_loss_limit",
                detail="510300.SH loss exceeds 15%",
                current_value=0.25,
                threshold=0.15,
            ),
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        call_kwargs = planner.plan.call_args[1]
        assert 1 in call_kwargs["locked_instruments"]

    def test_no_post_trade_guard_no_locks(self) -> None:
        """post_trade_guard=None → planner.plan 收到空 locked_instruments。"""
        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15"],
                target=_make_target_portfolio({1: 0.3}),
                plan=_make_mock_plan(),
            )
        )

        self._run_loop(
            post_trade_guard=None,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        call_kwargs = planner.plan.call_args[1]
        assert call_kwargs["locked_instruments"] == set()

    def test_daily_locks_cleared_at_start_of_each_step(self) -> None:
        """每日 _step 开始时 _locked_instruments 被清空。"""
        plan = _make_mock_plan()
        captured_locks: list[set[int]] = []

        def capture_plan(**kwargs: object) -> Mock:
            captured_locks.append(set(kwargs["locked_instruments"]))  # type: ignore[index]
            return plan

        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15", "2026-01-16"],
                target=_make_target_portfolio({1: 0.3}),
                plan=plan,
                planner_side_effect=capture_plan,
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.side_effect = [
            [
                RiskAction(
                    action_type=RiskActionType.REDUCE_POSITION,
                    instrument_id=1,
                    scope="instrument",
                    severity=RiskSeverity.CRITICAL,
                    rule_id="test",
                    detail="test",
                    current_value=0.25,
                    threshold=0.15,
                ),
            ],
            [],
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        assert planner.plan.call_count == 2
        assert 1 in captured_locks[0]
        assert 1 not in captured_locks[1]

    def test_wildcard_instrument_id_not_added_to_locks(self) -> None:
        """LIQUIDATE with scope='portfolio' 不应加入 locked_instruments。"""
        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15"],
                target=_make_target_portfolio(),
                plan=_make_mock_plan(),
                nav=75000.0,
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.return_value = [
            RiskAction(
                action_type=RiskActionType.LIQUIDATE,
                instrument_id=None,
                scope="portfolio",
                severity=RiskSeverity.EMERGENCY,
                rule_id="max_drawdown",
                detail="portfolio drawdown exceeds 20%",
                current_value=0.25,
                threshold=0.20,
            ),
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        call_kwargs = planner.plan.call_args[1]
        assert call_kwargs["locked_instruments"] == set()

    def test_alert_action_type_not_added_to_locks(self) -> None:
        """ALERT action type 不应加入 locked_instruments (只有 REDUCE/LIQUIDATE)。"""
        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15"],
                target=_make_target_portfolio(),
                plan=_make_mock_plan(),
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.return_value = [
            RiskAction(
                action_type=RiskActionType.ALERT,
                instrument_id=1,
                scope="instrument",
                severity=RiskSeverity.WARNING,
                rule_id="market_anomaly",
                detail="510300.SH return exceeds 5%",
                current_value=0.08,
                threshold=0.05,
            ),
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        call_kwargs = planner.plan.call_args[1]
        assert call_kwargs["locked_instruments"] == set()

    def test_cooldown_lock_persists_to_next_day(self) -> None:
        """带 cooldown_until 的锁定在次日仍然生效。"""
        plan = _make_mock_plan()
        captured_locks: list[set[int]] = []

        def capture_plan(**kwargs: object) -> Mock:
            captured_locks.append(set(kwargs["locked_instruments"]))  # type: ignore[index]
            return plan

        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15", "2026-01-16"],
                target=_make_target_portfolio({1: 0.3}),
                plan=plan,
                planner_side_effect=capture_plan,
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.side_effect = [
            [
                RiskAction(
                    action_type=RiskActionType.REDUCE_POSITION,
                    instrument_id=1,
                    scope="instrument",
                    severity=RiskSeverity.CRITICAL,
                    rule_id="single_loss_limit",
                    detail="loss exceeds 15%",
                    current_value=0.25,
                    threshold=0.15,
                    cooldown_until_date="2026-01-16",
                ),
            ],
            [],
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        assert planner.plan.call_count == 2
        assert 1 in captured_locks[0]
        assert 1 in captured_locks[1]

    def test_cooldown_lock_cleared_on_expiry(self) -> None:
        """cooldown_until 到期日的次日锁定被清除。"""
        plan = _make_mock_plan()
        captured_locks: list[set[int]] = []

        def capture_plan(**kwargs: object) -> Mock:
            captured_locks.append(set(kwargs["locked_instruments"]))  # type: ignore[index]
            return plan

        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15", "2026-01-16", "2026-01-17"],
                target=_make_target_portfolio({1: 0.3}),
                plan=plan,
                planner_side_effect=capture_plan,
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.side_effect = [
            [
                RiskAction(
                    action_type=RiskActionType.REDUCE_POSITION,
                    instrument_id=1,
                    scope="instrument",
                    severity=RiskSeverity.CRITICAL,
                    rule_id="single_loss_limit",
                    detail="loss exceeds 15%",
                    current_value=0.25,
                    threshold=0.15,
                    cooldown_until_date="2026-01-16",
                ),
            ],
            [],
            [],
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        assert planner.plan.call_count == 3
        assert 1 in captured_locks[0]
        assert 1 in captured_locks[1]
        assert 1 not in captured_locks[2]

    def test_same_day_lock_and_cooldown_coexist(self) -> None:
        """当日锁定和跨日 cooldown 可以同时存在。"""
        plan = _make_mock_plan()
        captured_locks: list[set[int]] = []

        def capture_plan(**kwargs: object) -> Mock:
            captured_locks.append(set(kwargs["locked_instruments"]))  # type: ignore[index]
            return plan

        data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model = (
            self._setup_common_mocks(
                trading_days=["2026-01-15", "2026-01-16"],
                target=_make_target_portfolio({1: 0.3, 2: 0.2}),
                plan=plan,
                planner_side_effect=capture_plan,
            )
        )

        mock_guard = Mock(spec=PostTradeRiskGuard)
        mock_guard.scan.side_effect = [
            [
                RiskAction(
                    action_type=RiskActionType.REDUCE_POSITION,
                    instrument_id=1,
                    scope="instrument",
                    severity=RiskSeverity.CRITICAL,
                    rule_id="single_loss_limit",
                    detail="loss exceeds 15%",
                    current_value=0.25,
                    threshold=0.15,
                    cooldown_until_date="2026-01-16",
                ),
                RiskAction(
                    action_type=RiskActionType.REDUCE_POSITION,
                    instrument_id=2,
                    scope="instrument",
                    severity=RiskSeverity.CRITICAL,
                    rule_id="concentration_limit",
                    detail="concentration exceeds 20%",
                    current_value=0.25,
                    threshold=0.20,
                ),
            ],
            [],
        ]

        self._run_loop(
            post_trade_guard=mock_guard,
            data_feed=data_feed,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            fee_model=fee_model,
        )

        assert planner.plan.call_count == 2
        assert 1 in captured_locks[0]
        assert 2 in captured_locks[0]
        assert 1 in captured_locks[1]
        assert 2 not in captured_locks[1]

    # -- helpers -------------------------------------------------------------

    @classmethod
    def _setup_common_mocks(
        cls,
        *,
        trading_days: list[str],
        target: TargetPortfolio,
        plan: Mock,
        nav: float = 100000.0,
        planner_side_effect: object = None,
    ) -> tuple[Mock, Mock, Mock, Mock, Mock, Mock]:
        """构建 integration test 共用的 mock 组件。"""
        data_feed = Mock()
        data_feed.trading_days.return_value = trading_days
        if len(trading_days) == 1:
            data_feed.get_slice.return_value = _make_slice()
        else:
            data_feed.get_slice.side_effect = [_make_slice()] * len(trading_days)

        pipeline = Mock()
        pipeline.run.return_value = target

        planner = Mock()
        if planner_side_effect is not None:
            planner.plan.side_effect = planner_side_effect
        else:
            planner.plan.return_value = plan

        brokerage = Mock()
        brokerage.get_account.return_value = _make_account_view(nav=nav)
        brokerage.process_pending.return_value = ()

        pre_trade_check = Mock()
        pre_trade_check.check_order.return_value = OrderCheckResult(
            decision=Decision.ACCEPT,
            order_id="o-1",
        )
        fee_model = Mock()

        return data_feed, pipeline, planner, brokerage, pre_trade_check, fee_model

    @classmethod
    def _run_loop(
        cls,
        *,
        post_trade_guard: PostTradeRiskGuard | None,
        data_feed: Mock,
        pipeline: Mock,
        planner: Mock,
        brokerage: Mock,
        pre_trade_check: Mock,
        fee_model: Mock,
    ) -> None:
        """构建并运行 EngineLoop。"""
        loop = EngineLoop(
            config=_make_engine_config(),
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=EngineOptions(
                fee_model=fee_model,
                post_trade_guard=post_trade_guard,
            ),
        )
        loop.run()
