"""
PaperTradingRuntime — 纸上交易运行时编排器.

纯编排层：委托 BrokerGateway 执行订单，并从 BrokerGateway 读取账户状态。
不包含任何撮合、成交或账户记账逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ditto_execution.broker.contracts import BrokerGateway
from ditto_execution.orders.model import Order
from ditto_execution.orders.ticket import OrderTicket
from ditto_portfolio.accounting import AccountView, FillEvent
from ditto_risk.constraints.context import PreTradeContext

from ditto_application.exceptions import AppProcessError

__all__ = [
    "PaperRiskContext",
    "PaperRiskDecision",
    "PaperRiskRuntime",
    "PaperTradingRuntime",
]


@dataclass(frozen=True)
class PaperRiskContext:
    """Authoritative paper account state at one risk lifecycle boundary."""

    trade_date: str
    account_view: AccountView
    pre_trade_context: PreTradeContext | None = None


@dataclass(frozen=True)
class PaperRiskDecision:
    """Application-level paper pre-trade decision."""

    allow: bool
    adjusted_order: Order | None
    reason_code: str | None = None
    reason: str | None = None


class PaperRiskRuntime(Protocol):
    """Continuous risk lifecycle owned above the broker gateway."""

    def pre_trade(
        self,
        order: Order,
        context: PaperRiskContext,
    ) -> PaperRiskDecision:
        """Allow, resize, or reject before broker submission."""
        ...

    def post_fill(
        self,
        fill: FillEvent,
        context: PaperRiskContext,
        event_id: str,
    ) -> None:
        """Apply one broker fill after authoritative accounting."""
        ...


class PaperTradingRuntime:
    """
    纸上交易运行时 — 最小冒烟测试级别的订单执行编排器.

    职责仅限于：
    1. 提交订单到 BrokerGateway
    2. 返回 gateway 产出的订单状态
    3. 从 gateway 读取账户快照

    不实现任何撮合、定价或风控逻辑。
    """

    def __init__(
        self,
        gateway: BrokerGateway,
        risk_runtime: PaperRiskRuntime | None = None,
    ) -> None:
        self._gateway = gateway
        self._risk_runtime = risk_runtime

    def execute_order(
        self,
        order: Order,
        *,
        trade_date: str | None = None,
        pre_trade_context: PreTradeContext | None = None,
    ) -> OrderTicket:
        """
        执行订单：提交到 gateway，并由 gateway 拥有账户记账状态.

        Args:
            order: 待执行订单
            trade_date: 新连续风控启用时必须显式提供的交易日。
            pre_trade_context: 已配置资金、T+1、集中度等规则所需的权威上下文。

        Returns:
            填充完成的 OrderTicket

        """
        risk_runtime = self._risk_runtime
        if risk_runtime is not None:
            if trade_date is None or not trade_date.strip():
                raise AppProcessError(
                    "paper continuous risk requires an explicit trade_date",
                    code="PAPER_RISK_CONTEXT_MISSING",
                )
            account_view = self._gateway.get_account()
            if (
                pre_trade_context is not None
                and pre_trade_context.account_view != account_view
            ):
                raise AppProcessError(
                    "paper pre-trade context does not match authoritative account",
                    code="PAPER_RISK_CONTEXT_MISMATCH",
                )
            decision = risk_runtime.pre_trade(
                order,
                PaperRiskContext(
                    trade_date=trade_date,
                    account_view=account_view,
                    pre_trade_context=pre_trade_context,
                ),
            )
            if not decision.allow or decision.adjusted_order is None:
                raise AppProcessError(
                    "continuous risk gate rejected paper order",
                    code="PAPER_RISK_REJECTED",
                    reason_code=decision.reason_code,
                    reason=decision.reason,
                )
            order = decision.adjusted_order

        ticket = self._gateway.submit_order(order)
        if risk_runtime is not None:
            account_view = self._gateway.get_account()
            context = PaperRiskContext(
                trade_date=trade_date or "",
                account_view=account_view,
            )
            for fill in self._gateway.query_fills(order.order_id):
                risk_runtime.post_fill(fill, context, fill.fill_id)
        return ticket

    def get_account(self) -> AccountView:
        """返回 gateway 拥有的当前账户快照."""
        return self._gateway.get_account()
