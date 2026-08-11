"""Fail-closed daily lifecycle step for the continuous risk runtime."""

from __future__ import annotations

from ditto_kernel import traced

from ditto_backtest.risk_runtime import BacktestRiskContext, BacktestRiskRuntime
from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["DailyContinuousRiskStep"]


class DailyContinuousRiskStep:
    """Run the continuous daily scan before any new recommendation is built."""

    def __init__(self, runtime: BacktestRiskRuntime | None) -> None:
        self._runtime = runtime

    @traced("backtest.step.daily_continuous_risk")
    def execute(self, ctx: StepContext) -> StepResult:
        """Block the step chain whenever risk readiness is not explicitly ready."""
        if self._runtime is None:
            return StepResult.skipped()
        outcome = self._runtime.daily_scan(
            BacktestRiskContext(
                trade_date=ctx.time_context.trade_date,
                account_view=ctx.require_account_view(),
                bars=ctx.bars,
            )
        )
        ctx.daily_risk_evidence = dict(outcome.evidence)
        if outcome.readiness != "ready":
            reasons = ",".join(outcome.block_reasons) or "unknown"
            return StepResult.fail(f"risk_gate_blocked: {reasons}")
        return StepResult.ok()
