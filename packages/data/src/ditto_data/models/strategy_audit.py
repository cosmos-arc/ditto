"""
Data 本地审计 DTO — 与 Core 记录解耦.

Data 层持久化审计日志所需的本地数据传输对象。
字段与 Core 的 RiskScanRecord / PreTradeDecisionRecord 对齐，
但不反向依赖 Core 包，枚举值用 str 表示。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_kernel.enums import RiskScope


class AuditRecordType(StrEnum):
    """审计记录类型。"""

    RISK_SCAN = "risk_scan"
    PRE_TRADE_DECISION = "pre_trade_decision"
    TRADE_FILL = "trade_fill"


@dataclass(frozen=True)
class RiskScanPayload:
    """
    PostTrade 风控扫描记录 — Data 本地 DTO.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        rule_id: 触发规则标识符
        instrument_id: 标的 ID (None 表示全组合)
        scope: 扫描范围 (instrument / portfolio)
        severity: 严重程度 ("warning" / "critical" / "emergency")
        action_taken: 采取的动作 ("reduce_position" / "liquidate" / "alert")
        detail: 风险描述
        current_value: 当前实际值
        threshold: 触发阈值

    """

    trade_date: str
    rule_id: str
    instrument_id: int | None
    scope: RiskScope
    severity: str
    action_taken: str
    detail: str
    current_value: float
    threshold: float


@dataclass(frozen=True)
class PreTradeDecisionPayload:
    """
    PreTrade 订单校验决策记录 — Data 本地 DTO.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        order_id: 订单 ID
        instrument_id: 标的 ID
        direction: 方向 (buy/sell)
        original_quantity: 原始数量
        final_quantity: 最终数量
        decision: 决策 (accepted/rejected/resized)
        reason: 决策原因 (None = 无原因)
        check_sequence: 触发的检查链路

    """

    trade_date: str
    order_id: str
    instrument_id: int
    direction: str
    original_quantity: int
    final_quantity: int
    decision: str
    reason: str | None
    check_sequence: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeFillPayload:
    """
    Trade Fill 成交审计记录 — Data 本地 DTO.

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        fill_id: 成交 ID
        order_id: 关联订单 ID
        instrument_id: 标的 ID
        direction: 方向 (buy/sell)
        filled_quantity: 成交数量
        fill_price: 成交价格
        fee: 手续费
        slippage: 滑点

    """

    trade_date: str
    fill_id: str
    order_id: str
    instrument_id: int
    direction: str
    filled_quantity: int
    fill_price: float
    fee: float
    slippage: float


__all__ = [
    "AuditRecordType",
    "PreTradeDecisionPayload",
    "RiskScanPayload",
    "RiskScope",
    "TradeFillPayload",
]
