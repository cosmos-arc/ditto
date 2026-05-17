"""Drawdown rules — 回撤相关风控规则."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting import AccountView

from ditto_risk.errors import RiskConfigurationError
from ditto_risk.post_trade import (
    RiskAction,
    RiskActionType,
    RiskSeverity,
    SliceView,
)

__all__ = ["DrawdownStateSnapshot", "MaxDrawdownRule", "SingleLossLimitRule"]


@dataclass(frozen=True)
class DrawdownStateSnapshot:
    """MaxDrawdownRule 的可恢复状态。"""

    peak_nav: float


class MaxDrawdownRule:
    """
    组合最大回撤检测 — stateful, 内部维护峰值 NAV.

    Parameters
    ----------
        warning_threshold: 警告阈值（默认 10%）
        emergency_threshold: 紧急阈值（默认 20%）

    """

    def __init__(
        self,
        warning_threshold: float = 0.10,
        emergency_threshold: float = 0.20,
    ) -> None:
        if warning_threshold < 0 or emergency_threshold < 0:
            raise RiskConfigurationError(
                "thresholds must be non-negative",
                warning_threshold=warning_threshold,
                emergency_threshold=emergency_threshold,
            )
        if warning_threshold >= emergency_threshold:
            msg = (
                f"warning_threshold ({warning_threshold}) must be "
                f"< emergency_threshold ({emergency_threshold})"
            )
            raise RiskConfigurationError(
                msg,
                warning_threshold=warning_threshold,
                emergency_threshold=emergency_threshold,
            )
        self._warning_threshold = warning_threshold
        self._emergency_threshold = emergency_threshold
        self._peak_nav: float = 0.0

    def reset(self) -> None:
        """重置内部峰值 NAV 状态，确保跨回测隔离。"""
        self._peak_nav = 0.0

    def snapshot(self) -> DrawdownStateSnapshot:
        """捕获当前 peak NAV 状态快照。"""
        return DrawdownStateSnapshot(peak_nav=self._peak_nav)

    def restore(self, state: DrawdownStateSnapshot) -> None:
        """从快照恢复 peak NAV 状态。"""
        self._peak_nav = state.peak_nav

    def scan(
        self,
        account_view: AccountView,
        slice_: SliceView,
    ) -> list[RiskAction]:
        """检测组合回撤是否超过阈值。"""
        nav = account_view.nav
        self._peak_nav = max(self._peak_nav, nav)

        if self._peak_nav <= 0:
            return []

        drawdown = (self._peak_nav - nav) / self._peak_nav

        if drawdown >= self._emergency_threshold:
            return self._make_action(
                drawdown,
                self._emergency_threshold,
                RiskActionType.LIQUIDATE,
                RiskSeverity.EMERGENCY,
            )

        if drawdown >= self._warning_threshold:
            return self._make_action(
                drawdown,
                self._warning_threshold,
                RiskActionType.ALERT,
                RiskSeverity.WARNING,
            )

        return []

    def _make_action(
        self,
        drawdown: float,
        threshold: float,
        action_type: RiskActionType,
        severity: RiskSeverity,
    ) -> list[RiskAction]:
        """构建回撤 RiskAction。"""
        level = "紧急" if severity == RiskSeverity.EMERGENCY else "警告"
        return [
            RiskAction(
                action_type=action_type,
                instrument_id=None,
                scope=RiskScope.PORTFOLIO,
                severity=severity,
                rule_id="max_drawdown",
                detail=f"组合回撤 {drawdown:.2%} 超过{level}阈值 {threshold:.2%}",
                current_value=drawdown,
                threshold=threshold,
            ),
        ]


class SingleLossLimitRule:
    """
    单标的亏损限制检测 — stateless.

    Parameters
    ----------
        threshold: 亏损阈值（默认 15%）

    """

    def __init__(self, threshold: float = 0.15) -> None:
        if threshold <= 0:
            raise RiskConfigurationError(
                f"threshold must be positive, got {threshold}",
                field="threshold",
                value=threshold,
                min_exclusive=0.0,
            )
        self._threshold = threshold

    def scan(
        self,
        account_view: AccountView,
        slice_: SliceView,
    ) -> list[RiskAction]:
        """检测每个持仓标的的亏损是否超过阈值。"""
        actions: list[RiskAction] = []

        for position in account_view.positions.values():
            bar = slice_.bars.get(position.instrument_id)
            if bar is None:
                # 无行情数据的持仓跳过
                continue

            current_price = bar.close
            loss_limit = position.average_cost * (1 - self._threshold)

            if current_price < loss_limit:
                loss_pct = (
                    current_price - position.average_cost
                ) / position.average_cost
                actions.append(
                    RiskAction(
                        action_type=RiskActionType.REDUCE_POSITION,
                        instrument_id=position.instrument_id,
                        scope=RiskScope.INSTRUMENT,
                        severity=RiskSeverity.CRITICAL,
                        rule_id="single_loss_limit",
                        detail=(
                            f"{position.instrument_id} 亏损 {loss_pct:.2%} "
                            f"超过阈值 {self._threshold:.2%}"
                        ),
                        current_value=loss_pct,
                        threshold=-self._threshold,
                    ),
                )

        return actions

    def reset(self) -> None:
        """无状态规则，no-op。"""
