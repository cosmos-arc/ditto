"""
StrategyRun / StrategyTemplate / StrategyVersion / SignalSnapshot / TargetPortfolio.

策略运行期的核心对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "RebalancePlan",
    "SignalSnapshot",
    "StrategyRun",
    "StrategyTemplate",
    "StrategyVersion",
    "TargetPortfolio",
]


@dataclass(frozen=True)
class StrategyVersion:
    """
    策略版本 — 每次修改 Spec 产生新版本。

    Attributes:
        version: 版本号
        strategy_id: 关联策略 ID
        spec_json: Spec 的 JSON 快照
        created_at: 创建时间 (RFC3339)
        status: 状态 (draft / published)

    """

    version: int
    strategy_id: str
    spec_json: dict[str, object]
    created_at: str
    status: str = "draft"


@dataclass(frozen=True)
class StrategyTemplate:
    """
    策略模板 — 预配置的策略蓝图。

    Attributes:
        template_id: 模板 ID
        name: 模板名称
        description: 描述
        asset_class: 资产类别
        required_signals: 必需的信号列表
        built_in_constraints: 内置约束类型

    """

    template_id: str
    name: str
    description: str = ""
    asset_class: str = "etf"
    required_signals: tuple[str, ...] = ()
    built_in_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyRun:
    """
    一次策略运行。

    Attributes:
        run_id: 运行唯一 ID
        strategy_id: 关联策略 ID
        spec_version: 使用的 Spec 版本
        start: 开始日期
        end: 结束日期
        status: 状态 (pending / running / completed / failed)
        parameters: 参数覆盖
        baseline_run_id: 对比基线运行 ID
        mode: 运行模式 (research / backtest / recommendation)

    """

    run_id: str
    strategy_id: str
    spec_version: int
    start: str
    end: str
    status: str = "pending"
    parameters: dict[str, object] = field(default_factory=dict)
    baseline_run_id: str | None = None
    mode: str = "research"


@dataclass(frozen=True)
class SignalSnapshot:
    """
    某日策略的信号快照。

    Attributes:
        trade_date: 交易日期
        strategy_id: 策略 ID
        run_id: 运行 ID
        signals: instrument_id → signal value
        valid_until: 信号有效期截止日期（含），None 表示仅当日有效

    """

    trade_date: str
    strategy_id: str
    run_id: str
    signals: dict[str, float] = field(default_factory=dict)
    valid_until: str | None = None


@dataclass(frozen=True)
class TargetPortfolio:
    """
    目标持仓 — 策略决策层的最终输出。

    Attributes:
        trade_date: 交易日期
        strategy_id: 策略 ID
        run_id: 运行 ID
        positions: instrument_id → weight
        cash_target: 目标现金比例

    """

    trade_date: str
    strategy_id: str
    run_id: str
    positions: dict[str, float] = field(default_factory=dict)
    cash_target: float = 0.0


@dataclass(frozen=True)
class RebalancePlan:
    """
    调仓计划 — 策略输出的可执行调仓指令。

    Attributes:
        trade_date: 调仓日期
        strategy_id: 策略 ID
        run_id: 运行 ID
        target_weights: instrument_id → 目标权重
        executed: 是否已执行
        execution_date: 实际执行日期

    """

    trade_date: str
    strategy_id: str
    run_id: str
    target_weights: dict[str, float] = field(default_factory=dict)
    executed: bool = False
    execution_date: str | None = None
