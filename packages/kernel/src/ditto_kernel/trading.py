"""A 股交易领域常量、值对象与规则 Protocol。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from ditto_kernel.identity import InstrumentId

__all__ = [
    "DEFAULT_COMMISSION_RATE",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MIN_COMMISSION",
    "DEFAULT_SLIPPAGE_BPS",
    "FeeModel",
    "FeeSchedule",
    "InstrumentDefinition",
    "InstrumentRuleProvider",
    "InstrumentRules",
    "MarketSnapshot",
    "RulesGetter",
    "TradingRuleSet",
    "default_price_limit_pct",
]

# ── 常量 ──────────────────────────────────────────────────────

DEFAULT_COMMISSION_RATE: float = 0.0003
"""默认佣金费率(万分之三)。"""

DEFAULT_MIN_COMMISSION: float = 5.0
"""最低佣金(元)。"""

DEFAULT_LOT_SIZE: int = 100
"""默认最小交易单位(A股一手 = 100 股)。"""

DEFAULT_SLIPPAGE_BPS: float = 1.0
"""默认滑点成本(基点)。"""

# ── 市场快照 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class MarketSnapshot:
    """单个标的在某日的完整市场快照。"""

    trade_date: str
    instrument_id: InstrumentId
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: float
    amount: float
    is_suspended: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    avg_volume_20d: float | None = None


# ── 标的规则 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class InstrumentDefinition:
    """资产的静态定义 — 很少变化，不按日期生效。"""

    instrument_id: InstrumentId
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    lot_size: int
    multiplier: float
    board_segment: str
    lifecycle_state: str
    ipo_date: str | None = None
    delisting_date: str | None = None


@dataclass(frozen=True)
class TradingRuleSet:
    """某个标的在某个时间点的交易规则 — 按日期生效，可回放。"""

    instrument_id: InstrumentId
    as_of_date: str
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: tuple[str, ...]
    call_auction_sessions: tuple[str, ...]


@dataclass(frozen=True)
class FeeSchedule:
    """某个标的在某个时间点的费用结构 — 按日期生效。"""

    instrument_id: InstrumentId
    as_of_date: str
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float


class FeeModel(Protocol):
    """
    交易费用计算协议 — 盘前估算与盘后结算共享。

    order 参数类型为 Any：Protocol 仅定义行为契约，不访问 order 属性。
    具体实现（SimpleFeeModel / AShareFeeModel）使用 ditto_portfolio 的 Order 类型。
    """

    def calculate(
        self,
        order: Any,  # noqa: ANN401
        fill_price: float,
        fill_quantity: int,
        fee_schedule: FeeSchedule,
    ) -> float:
        """计算实际成交手续费。"""
        ...

    def estimate(
        self,
        order: Any,  # noqa: ANN401
        estimated_price: float,
        fee_schedule: FeeSchedule,
    ) -> float:
        """估算手续费（预交易）。"""
        ...


type InstrumentRules = tuple[InstrumentDefinition, TradingRuleSet, FeeSchedule]
"""三层规则元组 — (定义, 交易规则, 费用结构)。"""

type RulesGetter = Callable[[InstrumentId, str], InstrumentRules]
"""规则获取函数 — (instrument_id, trade_date) -> InstrumentRules。"""


# ── 工具函数 ──────────────────────────────────────────────────


def default_price_limit_pct(lifecycle_state: str, board_segment: str) -> float | None:
    """根据 lifecycle_state 和 board_segment 计算默认涨跌停幅度。"""
    if lifecycle_state in ("st", "st_star"):
        return 0.05
    if lifecycle_state == "delisting":
        return 0.10
    if lifecycle_state == "ipo":
        return None
    if board_segment in ("gem", "star"):
        return 0.20
    return 0.10


# ── Protocol ──────────────────────────────────────────────────


class InstrumentRuleProvider(Protocol):
    """三层规则查询 Protocol — 无 I/O。"""

    def get_definition(
        self,
        instrument_id: InstrumentId,
    ) -> InstrumentDefinition | None:
        """获取标的静态定义，不存在返回 None。"""
        ...

    def get_trading_rule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> TradingRuleSet | None:
        """PIT 查询交易规则，不存在返回 None。"""
        ...

    def get_fee_schedule(
        self,
        instrument_id: InstrumentId,
        as_of_date: str,
    ) -> FeeSchedule | None:
        """PIT 查询费率，不存在返回 None。"""
        ...

    def get_rules(
        self,
        as_of_date: str,
        instrument_ids: list[InstrumentId],
    ) -> dict[InstrumentId, InstrumentRules]:
        """批量获取三层规则。"""
        ...
