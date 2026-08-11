"""Continuous RiskGate lifecycle integration tests for backtest steps."""

from __future__ import annotations

from unittest.mock import Mock

from ditto_backtest.risk_runtime import BacktestRiskDecision, DailyRiskOutcome
from ditto_backtest.steps.continuous_risk import DailyContinuousRiskStep
from ditto_backtest.steps.execution import ExecutionStep
from ditto_backtest.steps.pre_trade import PreTradeStep
from ditto_risk.pre_trade import Decision
from packages.backtest.tests.unit._helpers import (
    _make_account_view,
    _make_clock,
    _make_ctx,
    _make_execution_plan,
    _make_fill,
    _make_order,
    _make_slice,
)


def test_daily_scan_blocks_the_step_chain() -> None:
    runtime = Mock(
        daily_scan=Mock(
            return_value=DailyRiskOutcome(
                readiness="blocked",
                block_reasons=("reconciliation_mismatch",),
                evidence={"event_sequence": 4},
            )
        )
    )
    ctx = _make_ctx()
    ctx.account_view = _make_account_view()

    result = DailyContinuousRiskStep(runtime).execute(ctx)

    assert result.success is False
    assert result.errors == ("risk_gate_blocked: reconciliation_mismatch",)
    assert ctx.daily_risk_evidence == {"event_sequence": 4}


def test_pre_trade_runtime_rejects_before_brokerage_submission() -> None:
    order = _make_order()
    legacy = Mock(
        check_order=Mock(
            return_value=Mock(
                decision=Decision.ACCEPT,
                resized_quantity=None,
                reason=None,
                triggered_checks=(),
            )
        )
    )
    runtime = Mock(
        pre_trade=Mock(
            return_value=BacktestRiskDecision(
                allow=False,
                adjusted_order=None,
                reason_code="kill_switch",
                reason="gate locked",
            )
        )
    )
    brokerage = Mock()
    ctx = _make_ctx()
    ctx.slice_ = _make_slice()
    ctx.account_view = _make_account_view()
    ctx.execution_plan = _make_execution_plan(orders=(order,))
    ctx.rules = {}

    PreTradeStep(
        pre_trade_check=legacy,
        brokerage=brokerage,
        fee_model=None,
        event_bus=None,
        clock=_make_clock(),
        risk_runtime=runtime,
    ).execute(ctx)

    brokerage.place_order.assert_not_called()
    assert ctx.pre_trade_decisions[0].reason == "kill_switch: gate locked"


def test_each_fill_is_applied_to_continuous_runtime() -> None:
    fill = _make_fill()
    account = _make_account_view()
    brokerage = Mock(
        process_pending=Mock(return_value=(fill,)),
        get_account=Mock(return_value=account),
    )
    runtime = Mock()
    ctx = _make_ctx()
    ctx.slice_ = _make_slice()

    ExecutionStep(
        brokerage=brokerage,
        event_bus=None,
        clock=_make_clock(),
        risk_runtime=runtime,
    ).execute(ctx)

    runtime.post_fill.assert_called_once()
    call = runtime.post_fill.call_args
    assert call.args[0] is fill
    assert call.args[1].account_view is account
    assert call.args[2] == "fill-1"
