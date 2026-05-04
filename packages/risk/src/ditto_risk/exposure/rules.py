"""Exposure rules — 暴露度相关风控规则."""

from __future__ import annotations

from ditto_kernel.strategy import RiskScope
from ditto_portfolio.accounting.account import AccountView

from ditto_risk._validation import validate_weight
from ditto_risk.errors import RiskConfigurationError
from ditto_risk.post_trade import (
    RiskAction,
    RiskActionType,
    RiskSeverity,
    SliceView,
)

__all__ = ["ConcentrationLimitRule", "MarketAnomalyRule"]


class ConcentrationLimitRule:
    """
    持仓集中度检测 — stateless.

    Parameters
    ----------
        max_weight: 单标的最大权重（默认 20%）

    """

    def __init__(self, max_weight: float = 0.20) -> None:
        validate_weight(max_weight, "max_weight")
        self._max_weight = max_weight

    def scan(
        self,
        account_view: AccountView,
        slice_: SliceView,
    ) -> list[RiskAction]:
        """检测每个持仓标的的权重是否超过上限。"""
        nav = account_view.nav
        if nav <= 0:
            return []

        actions: list[RiskAction] = []

        for position in account_view.positions.values():
            weight = position.market_value / nav
            if weight > self._max_weight:
                actions.append(
                    RiskAction(
                        action_type=RiskActionType.REDUCE_POSITION,
                        instrument_id=position.instrument_id,
                        scope=RiskScope.INSTRUMENT,
                        severity=RiskSeverity.WARNING,
                        rule_id="concentration_limit",
                        detail=(
                            f"{position.instrument_id} 持仓权重 {weight:.2%} "
                            f"超过上限 {self._max_weight:.2%}"
                        ),
                        current_value=weight,
                        threshold=self._max_weight,
                    ),
                )

        return actions

    def reset(self) -> None:
        """无状态规则，no-op。"""


class MarketAnomalyRule:
    """
    市场异常波动检测 — stateless, 扫描全市场（非仅持仓）.

    Parameters
    ----------
        threshold: 日涨跌幅阈值（默认 5%）

    """

    def __init__(self, threshold: float = 0.05) -> None:
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
        """检测所有标的中是否存在异常波动。"""
        actions: list[RiskAction] = []

        for instrument_id, bar in slice_.bars.items():
            if bar.prev_close <= 0:
                continue

            daily_return = abs(bar.close / bar.prev_close - 1.0)
            if daily_return > self._threshold:
                actions.append(
                    RiskAction(
                        action_type=RiskActionType.ALERT,
                        instrument_id=instrument_id,
                        scope=RiskScope.INSTRUMENT,
                        severity=RiskSeverity.WARNING,
                        rule_id="market_anomaly",
                        detail=(
                            f"{instrument_id} 日涨跌幅 {daily_return:.2%} "
                            f"超过阈值 {self._threshold:.2%}"
                        ),
                        current_value=daily_return,
                        threshold=self._threshold,
                    ),
                )

        return actions

    def reset(self) -> None:
        """无状态规则，no-op。"""
