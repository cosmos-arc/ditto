"""
审计记录 — frozen dataclass 定义.

RiskScanRecord: PostTrade 风控扫描记录.
PreTradeDecisionRecord: PreTrade 订单校验决策记录.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_core.backtest.risk.post_trade import RiskActionType, RiskSeverity

__all__ = [
    "PreTradeDecisionRecord",
    "RiskScanRecord",
]


@dataclass(frozen=True)
class RiskScanRecord:
    """
    PostTrade 风控扫描记录 — frozen.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        rule_id: 触发规则标识符
        instrument_id: 标的 ID ("*" 表示全组合)
        severity: 严重程度 (RiskSeverity 枚举)
        action_taken: 采取的动作 (RiskActionType 枚举)
        detail: 风险描述
        current_value: 当前实际值
        threshold: 触发阈值

    """

    trade_date: str
    rule_id: str
    instrument_id: str
    severity: RiskSeverity
    action_taken: RiskActionType
    detail: str
    current_value: float
    threshold: float


@dataclass(frozen=True)
class PreTradeDecisionRecord:
    """
    PreTrade 订单校验决策记录 — frozen.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        order_id: 订单 ID
        instrument_id: 标的 ID
        direction: 方向 (buy/sell)
        original_quantity: 原始数量
        final_quantity: 最终数量 (accepted/resized 时有值, rejected 时为 0)
        decision: 决策 (accepted/rejected/resized)
        reason: 决策原因 (None = 无原因)
        check_sequence: 触发的检查链路 (e.g. ("lot_size", "buying_power"))

    """

    trade_date: str
    order_id: str
    instrument_id: str
    direction: str
    original_quantity: int
    final_quantity: int
    decision: str
    reason: str | None
    check_sequence: tuple[str, ...] = ()
