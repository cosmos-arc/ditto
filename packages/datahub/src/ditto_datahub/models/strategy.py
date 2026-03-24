"""
Strategy 域数据模型.

本模块定义 Strategy 域的逻辑密集型模型，使用 dataclass 表示。

设计原则:
- 逻辑密集型用 dataclass（对象传输）
- 支持状态管理和业务规则
- 类型安全（类型注解）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ArtifactKind(StrEnum):
    """策略产物类型."""

    # Pipeline 输出
    DECISION_FRAME = "decision_frame"
    SIGNAL_SNAPSHOT = "signal_snapshot"
    TARGET_PORTFOLIO = "target_portfolio"
    REBALANCE_PLAN = "rebalance_plan"
    # 执行层输出
    ORDER_LOG = "order_log"
    FILL_LOG = "fill_log"
    # 统计层输出
    NAV = "nav"
    TRADE_LOG = "trade_log"
    BACKTEST_REPORT = "backtest_report"
    # 审计日志
    RISK_LOG = "risk_log"
    PRE_TRADE_LOG = "pre_trade_log"
    # 诊断
    DIAGNOSTICS = "diagnostics"


class SignalType(StrEnum):
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


@dataclass(frozen=True)
class StrategySpecRecord:
    """
    策略 Spec 存储记录.

    Attributes:
        strategy_id: 策略唯一标识.
        name: 策略名称.
        spec_json: 策略定义 JSON.
        version: 版本号（默认 1）.
        status: 状态（draft / published）.
        created_at: 创建时间.
        updated_at: 更新时间.
        tags: 标签.

    """

    strategy_id: str
    name: str
    spec_json: dict[str, object]
    version: int = 1
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyArtifactRecord:
    """
    策略产物记录.

    Attributes:
        artifact_id: 产物唯一标识.
        strategy_id: 所属策略 ID.
        run_id: 关联运行 ID.
        artifact_type: 产物类型（backtest_report / signal_snapshot 等）.
        file_path: 文件存储路径.
        metadata: 产物元数据.
        status: 状态（active / archived）.
        created_at: 创建时间.

    """

    artifact_id: str
    strategy_id: str
    run_id: str
    artifact_type: ArtifactKind
    file_path: str
    metadata: dict[str, object] = field(default_factory=dict)
    status: str = "active"
    created_at: str = ""


__all__ = [
    "ArtifactKind",
    "MarketState",
    "Signal",
    "SignalType",
    "StrategyArtifactRecord",
    "StrategySpecRecord",
]
