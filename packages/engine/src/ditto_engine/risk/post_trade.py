"""
PostTradeRiskGuard — 每日组合风控扫描 (V3).

PostTrade 风控在每个交易日开盘前执行，扫描整个组合状态，
发现风险后生成 RiskAction 供上层处理（V1: 记录日志 + RiskLock）。

内置规则:
  - MaxDrawdownRule: 组合回撤检测（stateful — 追踪峰值 NAV）
  - SingleLossLimitRule: 单标的亏损检测（stateless）
  - ConcentrationLimitRule: 持仓集中度检测（stateless）
  - MarketAnomalyRule: 市场异常波动检测（stateless）

CompositePostTradeGuard 组合多条规则，顺序扫描返回所有 RiskAction。

Design Doc: v3 §7.1, §7.3
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from ditto_kernel.enums import RiskScope
from ditto_kernel.identity import InstrumentId

from ditto_engine.accounting.account import AccountView
from ditto_engine.risk._validation import validate_weight


class _SliceView(Protocol):
    """
    Minimal slice protocol for post-trade risk scanning.

    Decouples risk from backtest — avoids circular risk → backtest import.
    """

    @property
    def bars(self) -> dict[InstrumentId, Any]: ...


__all__ = [
    "CompositePostTradeGuard",
    "ConcentrationLimitRule",
    "MarketAnomalyRule",
    "MaxDrawdownRule",
    "PostTradeRiskGuard",
    "RiskAction",
    "RiskActionType",
    "RiskScope",
    "RiskSeverity",
    "SingleLossLimitRule",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskActionType(StrEnum):
    """风控行为类型。"""

    REDUCE_POSITION = "reduce_position"
    LIQUIDATE = "liquidate"
    ALERT = "alert"


class RiskSeverity(StrEnum):
    """风险严重程度。"""

    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskAction:
    """
    风控行为指令 — frozen, 由 PostTrade 规则生成。

    Attributes:
        action_type: 行为类型 (REDUCE_POSITION / LIQUIDATE / ALERT)
        instrument_id: 标的 ID (None 表示全组合)
        scope: 扫描范围 (instrument / portfolio)
        severity: 严重程度
        rule_id: 触发规则的标识符
        detail: 风险描述
        current_value: 当前实际值
        threshold: 触发阈值
        cooldown_until_date: 冷却截止日期 (None = 无冷却)
        target_quantity: 目标数量 (None = 未指定)

    """

    action_type: RiskActionType
    instrument_id: InstrumentId | None
    scope: RiskScope
    severity: RiskSeverity
    rule_id: str
    detail: str
    current_value: float
    threshold: float
    cooldown_until_date: str | None = None
    target_quantity: int | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PostTradeRiskGuard(Protocol):
    """每日组合风控扫描协议。"""

    def scan(
        self,
        account_view: AccountView,
        slice_: _SliceView,
    ) -> list[RiskAction]:
        """扫描当前组合状态，返回所有触发的风控行为。"""
        ...

    def reset(self) -> None:
        """重置内部状态，确保跨回测隔离。"""
        ...
        ...


# ---------------------------------------------------------------------------
# MaxDrawdownRule — stateful, 追踪峰值 NAV
# ---------------------------------------------------------------------------


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
            raise ValueError("thresholds must be non-negative")
        if warning_threshold >= emergency_threshold:
            msg = (
                f"warning_threshold ({warning_threshold}) must be "
                f"< emergency_threshold ({emergency_threshold})"
            )
            raise ValueError(msg)
        self._warning_threshold = warning_threshold
        self._emergency_threshold = emergency_threshold
        self._peak_nav: float = 0.0

    def reset(self) -> None:
        """重置内部峰值 NAV 状态，确保跨回测隔离。"""
        self._peak_nav = 0.0

    def scan(
        self,
        account_view: AccountView,
        slice_: _SliceView,
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


# ---------------------------------------------------------------------------
# SingleLossLimitRule — stateless
# ---------------------------------------------------------------------------


class SingleLossLimitRule:
    """
    单标的亏损限制检测 — stateless.

    Parameters
    ----------
        threshold: 亏损阈值（默认 15%）

    """

    def __init__(self, threshold: float = 0.15) -> None:
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")
        self._threshold = threshold

    def scan(
        self,
        account_view: AccountView,
        slice_: _SliceView,
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


# ---------------------------------------------------------------------------
# ConcentrationLimitRule — stateless
# ---------------------------------------------------------------------------


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
        slice_: _SliceView,
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


# ---------------------------------------------------------------------------
# MarketAnomalyRule — stateless, 全市场扫描
# ---------------------------------------------------------------------------


class MarketAnomalyRule:
    """
    市场异常波动检测 — stateless, 扫描全市场（非仅持仓）.

    Parameters
    ----------
        threshold: 日涨跌幅阈值（默认 5%）

    """

    def __init__(self, threshold: float = 0.05) -> None:
        if threshold <= 0:
            raise ValueError(f"threshold must be positive, got {threshold}")
        self._threshold = threshold

    def scan(
        self,
        account_view: AccountView,
        slice_: _SliceView,
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


# ---------------------------------------------------------------------------
# CompositePostTradeGuard — 组合多条规则
# ---------------------------------------------------------------------------


class CompositePostTradeGuard:
    """
    组合多条 PostTrade 规则，顺序扫描返回所有 RiskAction.

    V1: 只扫描并返回，不做去重或优先级排序。

    Parameters
    ----------
        rules: PostTrade 规则列表

    """

    def __init__(self, rules: tuple[PostTradeRiskGuard, ...]) -> None:
        self._rules = rules

    def scan(
        self,
        account_view: AccountView,
        slice_: _SliceView,
    ) -> list[RiskAction]:
        """依次执行每条规则，收集所有风控行为。"""
        actions: list[RiskAction] = []
        for rule in self._rules:
            actions.extend(rule.scan(account_view, slice_))
        return actions

    def reset(self) -> None:
        """重置所有子规则的状态。"""
        for rule in self._rules:
            rule.reset()
