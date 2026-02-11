"""
Strategy 域数据模型.

本模块定义 Strategy 域的逻辑密集型模型，使用 dataclass 表示。

设计原则:
- 逻辑密集型用 dataclass（对象传输）
- 支持状态管理和业务规则
- 类型安全（类型注解）
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SignalType(str, Enum):
    """信号类型."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Signal:
    """
    信号模型.

    Attributes:
        signal_id: 信号唯一标识
        instrument_id: 证券 ID
        signal_type: 信号类型
        strength: 信号强度（0-1）
        confidence: 信号置信度（0-1）
        generated_at: 生成时间

    """

    signal_id: str
    instrument_id: int
    signal_type: SignalType
    strength: float
    confidence: float
    generated_at: datetime


@dataclass(frozen=True)
class MarketState:
    """
    市场状态模型.

    Attributes:
        state_id: 状态唯一标识
        timestamp: 时间戳
        is_trading_day: 是否交易日
        market_open: 是否开盘
        volatility: 波动率
        trend: 趋势方向（up/down/neutral）

    """

    state_id: str
    timestamp: datetime
    is_trading_day: bool
    market_open: bool
    volatility: float
    trend: str


__all__ = [
    "MarketState",
    "Signal",
    "SignalType",
]
