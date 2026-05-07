"""
PostTradeRiskGuard — 每日组合风控扫描 (V3).

PostTrade 风控在每个交易日开盘前执行，扫描整个组合状态，
发现风险后生成 RiskAction 供上层处理（V1: 记录日志 + RiskLock）。

类型定义（enums, RiskAction, protocols）保留在本模块，
规则实现已迁移到 drawdown/ 和 exposure/ 子模块。

Design Doc: v3 §7.1, §7.3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RiskScope as _RiskScope
from ditto_portfolio.accounting.account import AccountView

__all__ = [
    "CompositePostTradeGuard",
    "PostTradeRiskGuard",
    "RiskAction",
    "RiskActionType",
    "RiskSeverity",
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
    scope: _RiskScope
    severity: RiskSeverity
    rule_id: str
    detail: str
    current_value: float
    threshold: float
    cooldown_until_date: str | None = None
    target_quantity: int | None = None


# ---------------------------------------------------------------------------
# Internal Protocol
# ---------------------------------------------------------------------------


class SliceView(Protocol):
    """
    Minimal slice protocol for post-trade risk scanning.

    Decouples risk from backtest — avoids circular risk -> backtest import.
    """

    @property
    def bars(self) -> dict[InstrumentId, Any]: ...


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PostTradeRiskGuard(Protocol):
    """每日组合风控扫描协议。"""

    def scan(
        self,
        account_view: AccountView,
        slice_: SliceView,
    ) -> list[RiskAction]:
        """扫描当前组合状态，返回所有触发的风控行为。"""
        ...

    def reset(self) -> None:
        """重置内部状态，确保跨回测隔离。"""
        ...


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
        callbacks: 扫描完成后回调列表（用于通知/告警）

    """

    def __init__(
        self,
        rules: tuple[PostTradeRiskGuard, ...],
        callbacks: tuple[Callable[[list[RiskAction]], None], ...] = (),
    ) -> None:
        self._rules = rules
        self._callbacks = callbacks

    def scan(
        self,
        account_view: AccountView,
        slice_: SliceView,
    ) -> list[RiskAction]:
        """依次执行每条规则，收集所有风控行为，触发回调。"""
        actions: list[RiskAction] = []
        for rule in self._rules:
            actions.extend(rule.scan(account_view, slice_))
        for cb in self._callbacks:
            cb(actions)
        return actions

    def reset(self) -> None:
        """重置所有子规则的状态。"""
        for rule in self._rules:
            rule.reset()
