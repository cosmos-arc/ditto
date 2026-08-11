"""
Risk domain contracts — PreTrade 解耦 Protocol + RiskGate lifecycle.

将 Risk 对 Execution (Order / OrderTicket) 的直接依赖
替换为本地 Protocol 抽象，使 Risk 不再 import ditto_execution。

ADR: RiskGate 定义回测与模拟盘共用的风控门控契约。
4 个生命周期钩子覆盖订单全流程：提交前 / 撤单前 / 成交后 / 每日扫描。
具体实现由 backtest / paper-trading runtime 各自提供。
"""

# ruff: noqa: D102 — Protocol stubs don't need docstrings

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide, OrderType

from ditto_risk.post_trade import RiskAction

__all__ = [
    "LegacyRiskGate",
    "PreTradeOrder",
    "PreTradeTicket",
    "RiskGate",
]


@runtime_checkable
class PreTradeOrder(Protocol):
    """订单抽象 — Risk 风控校验所需的只读订单接口。"""

    @property
    def instrument_id(self) -> InstrumentId: ...

    @property
    def quantity(self) -> int: ...

    @property
    def direction(self) -> OrderSide: ...

    @property
    def order_id(self) -> str: ...

    @property
    def order_type(self) -> OrderType: ...

    @property
    def price(self) -> float | None: ...

    def with_quantity(self, qty: int) -> PreTradeOrder: ...


@runtime_checkable
class PreTradeTicket(Protocol):
    """订单票据抽象 — Risk 风控校验所需的只读票据接口。"""

    @property
    def order(self) -> PreTradeOrder: ...

    @property
    def leaves_quantity(self) -> int: ...


# ---------------------------------------------------------------------------
# RiskGate — unified risk gate lifecycle (ADR)
# ---------------------------------------------------------------------------


class LegacyRiskGate(Protocol):
    """
    风控门控统一契约 — backtest / paper-trading 共用。

    ADR: 定义 4 个生命周期钩子，将散布在 backtest 和 paper-trading
    中的风控门控逻辑收拢为单一 Protocol。具体实现由各 runtime 提供。
    """

    def pre_submit(self, order: PreTradeOrder) -> PreTradeOrder | None:
        """订单提交前校验 — 返回修改后订单或 None（拒绝）。"""
        ...

    def pre_cancel(self, order_id: str) -> None:
        """撤单前处理。"""
        ...

    def post_fill(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        qty: int,
        price: float,
    ) -> None:
        """成交后更新风控状态。"""
        ...

    def daily_scan(self) -> list[RiskAction]:
        """每日风控扫描 — 返回风控行为列表。"""
        ...


class RiskGate(Protocol):
    """R4 continuous gate contract; orchestration supplies every state context."""

    def pre_trade(self, order: object, context: object) -> object:
        """Return an auditable ALLOW or REJECT decision."""
        ...

    def post_fill(self, fill: object, context: object, event_id: str) -> object:
        """Idempotently apply the next ordered fill event."""
        ...

    def daily_scan(self, input_: object) -> object:
        """Return one typed daily risk report."""
        ...

    def snapshot_state(self) -> object:
        """Capture risk-owned state for persistence or checkpointing."""
        ...

    def restore_state(self, snapshot: object, **kwargs: object) -> None:
        """Restore only verified state matching authoritative positions."""
        ...
