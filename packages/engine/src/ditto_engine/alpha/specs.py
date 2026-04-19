"""
StrategySpec — 策略定义的核心语义契约.

混合范式：信号用表达式，编排用 Pipeline，风险用约束。
每个阶段通过 Protocol 接受声明式或命令式输入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ditto_kernel.strategy import ImpactModel

from ditto_engine.execution.reality.constants import DEFAULT_COMMISSION_RATE

__all__ = [
    "ConstraintSpec",
    "CostModelSpec",
    "ExecutionSpec",
    "ParamConstraint",
    "ScorerSpec",
    "SelectorSpec",
    "StrategySpec",
]


@dataclass(frozen=True)
class ParamConstraint:
    """
    参数约束 — 为参数扫描 UI 和 Walk-Forward 提供元数据。

    Attributes:
        name: 参数名
        dtype: 数据类型 (int / float / str)
        min_value: 最小值
        max_value: 最大值
        step: 步长
        allowed_values: 枚举型参数的可选值

    """

    name: str
    dtype: str
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class CostModelSpec:
    """
    成本模型配置。

    Attributes:
        commission_rate: 佣金费率。
        slippage_bps: 滑点（基点）。
        impact_model: 冲击成本模型名称。

    """

    commission_rate: float = DEFAULT_COMMISSION_RATE
    slippage_bps: float = 5.0
    impact_model: ImpactModel = ImpactModel.NONE


@dataclass(frozen=True)
class ExecutionSpec:
    """
    执行层配置。

    Attributes:
        frequency: 换仓频率 (D / W / M / Q)
        method: 触发方法 (calendar / signal_change_pct / composite)
        cost_model: 成本模型

    """

    frequency: str = "M"
    method: str = "calendar"
    cost_model: CostModelSpec = field(default_factory=CostModelSpec)


@dataclass(frozen=True)
class ConstraintSpec:
    """
    单条风险约束。

    Attributes:
        type: 约束类型
        params: 约束参数
        priority: 优先级（数字小优先，默认 100）

    """

    type: str
    params: dict[str, object] = field(default_factory=dict)
    priority: int = 100


@dataclass(frozen=True)
class ScorerSpec:
    """
    评分器定义。

    Attributes:
        method: 评分方法名称。
        params: 评分方法参数。

    """

    method: str = "equal_weight"
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectorSpec:
    """
    标的选取器定义。

    Attributes:
        method: 选取方法名称。
        params: 选取方法参数。

    """

    method: str = "top_k"
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategySpec:
    """
    策略完整定义 — 一等语义对象。

    Attributes:
        strategy_id: 策略唯一 ID
        name: 策略名称
        template: 策略模板
            (etf_rotation / etf_trend_swing / stock_selection / stock_sector_rotation)
        universe: Universe ID
        asset_class: 资产类别
        scorer: 评分器配置
        selector: 选取器配置
        execution: 执行配置
        constraints: 风险约束列表
        benchmark: 基准代码
        params: 策略参数（运行时可覆盖）
        param_constraints: 参数约束元数据
        tags: 标签

    """

    strategy_id: str
    name: str
    template: str
    universe: str
    asset_class: str
    scorer: ScorerSpec = field(default_factory=ScorerSpec)
    selector: SelectorSpec = field(default_factory=SelectorSpec)
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
    constraints: tuple[ConstraintSpec, ...] = ()
    benchmark: str | None = None
    params: dict[str, object] = field(default_factory=dict)
    param_constraints: tuple[ParamConstraint, ...] = ()
    tags: tuple[str, ...] = ()
    signal_expressions: tuple[str, ...] = ()
    signal_weights: tuple[float, ...] = ()

    _VALID_TEMPLATES = frozenset(
        {"etf_rotation", "etf_trend_swing", "stock_selection", "stock_sector_rotation"},
    )
    _VALID_FREQUENCIES = frozenset({"D", "W", "M", "Q"})
    _BENCHMARK_RE = re.compile(r"^\d{6}\.(SH|SZ)$")
    _KNOWN_BENCHMARKS = frozenset(
        {
            "000300.SH",  # 沪深300
            "000905.SH",  # 中证500
            "000852.SH",  # 中证1000
            "000016.SH",  # 上证50
            "399006.SZ",  # 创业板指
            "399673.SZ",  # 创业板50
            "000688.SH",  # 科创50
            "000001.SH",  # 上证综指
            "399001.SZ",  # 深证成指
        },
    )

    def __post_init__(self) -> None:
        """验证 StrategySpec 各字段的合法性。"""
        # 必填字段非空
        required = ("strategy_id", "name", "template", "universe", "asset_class")
        for field_name in required:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"StrategySpec.{field_name} must be non-empty")

        # template 枚举
        if self.template not in self._VALID_TEMPLATES:
            valid = sorted(self._VALID_TEMPLATES)
            raise ValueError(
                f"StrategySpec.template must be one of {valid}, got '{self.template}'"
            )

        # benchmark 格式
        if self.benchmark is not None and not self._BENCHMARK_RE.match(self.benchmark):
            raise ValueError(
                "StrategySpec.benchmark must match 'NNNNNN.SH|SZ', "
                + f" got '{self.benchmark}'"
            )

        # benchmark 白名单
        if self.benchmark is not None and self.benchmark not in self._KNOWN_BENCHMARKS:
            known = sorted(self._KNOWN_BENCHMARKS)
            msg = (
                f"StrategySpec.benchmark '{self.benchmark}' "
                f"is not a known index; known: {known}"
            )
            raise ValueError(msg)

        # execution.frequency 枚举
        if self.execution.frequency not in self._VALID_FREQUENCIES:
            valid_freq = sorted(self._VALID_FREQUENCIES)
            raise ValueError(
                "StrategySpec.execution.frequency must be one of "
                + f"{valid_freq}, got '{self.execution.frequency}'"
            )

        # cost_model 边界
        cm = self.execution.cost_model
        if not (0.0 <= cm.commission_rate <= 1.0):
            raise ValueError(
                "StrategySpec.commission_rate must be in [0, 1], "
                + f"got {cm.commission_rate}"
            )
        if cm.slippage_bps < 0:
            raise ValueError(
                "StrategySpec.slippage_bps must be >= 0, " + f"got {cm.slippage_bps}"
            )

        # signal_expressions / signal_weights 长度一致性
        if (
            self.signal_expressions
            and self.signal_weights
            and len(self.signal_expressions) != len(self.signal_weights)
        ):
            raise ValueError(
                f"StrategySpec.signal_weights length ({len(self.signal_weights)}) "
                + "must match signal_expressions length "
                + f"({len(self.signal_expressions)})"
            )
