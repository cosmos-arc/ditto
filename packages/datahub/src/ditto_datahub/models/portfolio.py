"""
Portfolio 域数据模型.

本模块定义 Portfolio 域的逻辑密集型模型，使用 dataclass 表示。

设计原则:
- 逻辑密集型用 dataclass（对象传输）
- 支持状态管理和业务规则
- 类型安全（类型注解）
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Position:
    """
    持仓模型.

    支持聚合计算和业务规则验证。

    Attributes:
        instrument_id: 证券 ID
        quantity: 持仓数量（可正可负）
        avg_price: 平均成本价
        market_price: 当前市价
        market_value: 市值
        unrealized_pnl: 浮动盈亏

    """

    instrument_id: int
    quantity: int
    avg_price: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    def is_long(self) -> bool:
        """是否多头持仓."""
        return self.quantity > 0

    def is_short(self) -> bool:
        """是否空头持仓."""
        return self.quantity < 0


@dataclass(frozen=True)
class Portfolio:
    """
    组合模型.

    Attributes:
        portfolio_id: 组合唯一标识
        positions: 持仓字典（instrument_id → Position）
        cash: 现金
        total_value: 总价值
        created_at: 创建时间

    """

    portfolio_id: str
    positions: dict[int, Position]
    cash: Decimal
    total_value: Decimal
    created_at: datetime


__all__ = [
    "Portfolio",
    "Position",
]
