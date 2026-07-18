"""
StrategySpec — 策略定义的核心语义契约.

混合范式：信号用表达式，编排用 Pipeline，风险用约束。
每个阶段通过 Protocol 接受声明式或命令式输入。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn, TypeGuard, cast

from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_kernel.trading import DEFAULT_COMMISSION_RATE

from ditto_strategy.alpha._canonical_values import freeze_json_mapping
from ditto_strategy.alpha.nodes import PipelineSpec
from ditto_strategy.alpha.production_guard import (
    UnsafeProductionFactorExpressionError,
    validate_production_factor_expression,
)
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "STRATEGY_SPEC_V2_SCHEMA_VERSION",
    "ConstraintSpec",
    "CostModelSpec",
    "ExecutionSpec",
    "ParamConstraint",
    "ScorerSpec",
    "SelectorSpec",
    "StrategyKind",
    "StrategySpec",
    "StrategySpecV2",
]

STRATEGY_SPEC_V2_SCHEMA_VERSION = 2
_PARAMETER_DTYPES = frozenset({"int", "float", "str"})


def _validate_v2_schema_version(value: object) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value != STRATEGY_SPEC_V2_SCHEMA_VERSION
    ):
        _raise_spec_error(
            "StrategySpecV2.schema_version must be exactly 2",
            field_name="schema_version",
            reason="unsupported_schema_version",
            actual_value=value,
        )


def _validate_v2_strategy_kind(value: object) -> None:
    if not isinstance(value, StrategyKind):
        _raise_spec_error(
            "StrategySpecV2.strategy_kind must be a StrategyKind",
            field_name="strategy_kind",
            reason="invalid_strategy_kind",
            actual_value=value,
        )


def _validate_v2_pipeline(value: object) -> None:
    if not isinstance(value, PipelineSpec):
        _raise_spec_error(
            "StrategySpecV2.pipeline must be a PipelineSpec",
            field_name="pipeline",
            reason="invalid_pipeline",
        )


def _validate_v2_parameter_schema(value: object) -> tuple[ParamConstraint, ...]:
    if not _is_object_tuple(value) or not all(
        isinstance(parameter, ParamConstraint) for parameter in value
    ):
        _raise_spec_error(
            "StrategySpecV2.parameter_schema must be a tuple of ParamConstraint values",
            field_name="parameter_schema",
            reason="invalid_parameter_schema",
        )
    return tuple(
        parameter for parameter in value if isinstance(parameter, ParamConstraint)
    )


def _validate_v2_tags(value: object) -> tuple[str, ...]:
    if not _is_object_tuple(value) or not all(isinstance(tag, str) for tag in value):
        _raise_spec_error(
            "StrategySpecV2.tags must be tuple[str, ...]",
            field_name="tags",
            reason="invalid_tags",
        )
    return tuple(tag for tag in value if isinstance(tag, str))


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _raise_spec_error(
    message: str,
    *,
    field_name: str,
    reason: str,
    **details: object,
) -> NoReturn:
    """Raise StrategySpecError with a consistent details payload."""
    payload: dict[str, object] = {
        "field_name": field_name,
        "reason": reason,
    }
    payload.update(details)
    raise StrategySpecError(message, details=payload)


def _validated_parameter_allowed_values(
    value: object,
    *,
    allow_list: bool,
) -> tuple[str, ...]:
    if _is_object_tuple(value):
        items = value
    elif allow_list and _is_object_list(value):
        items = tuple(value)
    else:
        _raise_spec_error(
            "ParamConstraint.allowed_values must be a canonical string sequence",
            field_name="allowed_values",
            reason="invalid_parameter_allowed_values",
            actual_type=type(value).__name__,
        )
    if not all(isinstance(item, str) for item in items):
        _raise_spec_error(
            "ParamConstraint.allowed_values must contain only strings",
            field_name="allowed_values",
            reason="invalid_parameter_allowed_values",
        )
    return tuple(item for item in items if isinstance(item, str))


def _canonical_parameter_number(value: object, *, field_name: str) -> float:
    """Return one stable JSON numeric identity or fail closed."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_spec_error(
            f"ParamConstraint.{field_name} must be a finite canonical number",
            field_name=field_name,
            reason="non_finite_parameter_identity",
            actual_value=value,
        )
    try:
        normalized = float(value)
    except OverflowError:
        _raise_spec_error(
            f"ParamConstraint.{field_name} must be a finite canonical number",
            field_name=field_name,
            reason="non_finite_parameter_identity",
            actual_value=value,
        )
    if not math.isfinite(normalized) or (
        isinstance(value, int) and int(normalized) != value
    ):
        _raise_spec_error(
            f"ParamConstraint.{field_name} must be a finite canonical number",
            field_name=field_name,
            reason="non_finite_parameter_identity",
            actual_value=value,
        )
    return normalized


def _is_non_empty_string(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and value != ""


def _is_supported_parameter_dtype(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and value in _PARAMETER_DTYPES


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

    def __post_init__(self) -> None:
        """Normalize mutable inputs, then validate the complete identity."""
        allowed_values = _validated_parameter_allowed_values(
            self.allowed_values,
            allow_list=True,
        )
        object.__setattr__(self, "allowed_values", allowed_values)
        min_value, max_value, step = self.validate_canonical_identity()
        object.__setattr__(self, "min_value", min_value)
        object.__setattr__(self, "max_value", max_value)
        object.__setattr__(self, "step", step)

    def validate_canonical_identity(
        self,
    ) -> tuple[float | None, float | None, float | None]:
        """Return canonical numeric identity without mutating this value object."""
        if not _is_non_empty_string(self.name):
            _raise_spec_error(
                "ParamConstraint.name must be a non-empty canonical string",
                field_name="name",
                reason="invalid_parameter_name",
                actual_type=type(self.name).__name__,
            )
        if not _is_supported_parameter_dtype(self.dtype):
            _raise_spec_error(
                "ParamConstraint.dtype must be one of int, float, or str",
                field_name="dtype",
                reason="invalid_parameter_dtype",
                actual_value=self.dtype,
            )
        _validated_parameter_allowed_values(
            self.allowed_values,
            allow_list=False,
        )
        normalized_values: list[float | None] = []
        for field_name in ("min_value", "max_value", "step"):
            value = getattr(self, field_name)
            normalized_values.append(
                None
                if value is None
                else _canonical_parameter_number(
                    value,
                    field_name=field_name,
                )
            )
        min_value, max_value, step = normalized_values
        return min_value, max_value, step


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
    slippage_bps: float = 1.0
    impact_model: ImpactModel = ImpactModel.NONE


@dataclass(frozen=True)
class ExecutionSpec:
    """
    执行层配置。

    Attributes:
        frequency: 换仓频率 (D / W / M / Q)
        method: 触发方法 (calendar / signal_change_pct / composite)
        cost_model: 成本模型
        default_order_type: 默认订单类型 (MARKET / LIMIT)

    """

    frequency: str = "M"
    method: str = "calendar"
    cost_model: CostModelSpec = field(default_factory=CostModelSpec)
    default_order_type: OrderType = OrderType.MARKET


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


class StrategyKind(StrEnum):
    """R3 两条 canonical 策略黄金路径。"""

    STOCK_SELECTION = "stock_selection"
    ETF_ROTATION = "etf_rotation"


@dataclass(frozen=True)
class StrategySpecV2:
    """R3 类型化策略规格；与 R1 legacy ``StrategySpec`` 显式分离。"""

    schema_version: int
    strategy_family_id: str
    strategy_kind: StrategyKind
    name: str
    pipeline: PipelineSpec
    parameter_schema: tuple[ParamConstraint, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict[str, object])
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验 V2 顶层类型边界，拒绝隐式 legacy/松散 payload。"""
        _validate_v2_schema_version(self.schema_version)
        for field_name in ("strategy_family_id", "name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                _raise_spec_error(
                    f"StrategySpecV2.{field_name} must be non-empty",
                    field_name=field_name,
                    reason="empty_required_field",
                    actual_value=value,
                )
        _validate_v2_strategy_kind(self.strategy_kind)
        _validate_v2_pipeline(self.pipeline)
        _validate_v2_parameter_schema(self.parameter_schema)
        _validate_v2_tags(self.tags)
        object.__setattr__(
            self,
            "metadata",
            freeze_json_mapping(self.metadata, field_name="metadata"),
        )


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
    required_datasets: tuple[str, ...] = ()

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
                _raise_spec_error(
                    f"StrategySpec.{field_name} must be non-empty",
                    field_name=field_name,
                    reason="empty_required_field",
                    actual_value=value,
                )

        # template 枚举
        if self.template not in self._VALID_TEMPLATES:
            valid = sorted(self._VALID_TEMPLATES)
            _raise_spec_error(
                f"StrategySpec.template must be one of {valid}, got '{self.template}'",
                field_name="template",
                reason="invalid_template",
                allowed_values=valid,
                actual_value=self.template,
            )

        # benchmark 格式验证（格式合法即通过，不再限制为已知指数白名单）
        if self.benchmark is not None and not self._BENCHMARK_RE.match(self.benchmark):
            _raise_spec_error(
                "StrategySpec.benchmark must match 'NNNNNN.SH|SZ', "
                + f" got '{self.benchmark}'",
                field_name="benchmark",
                reason="invalid_format",
                pattern=self._BENCHMARK_RE.pattern,
                actual_value=self.benchmark,
            )

        # execution.frequency 枚举
        if self.execution.frequency not in self._VALID_FREQUENCIES:
            valid_freq = sorted(self._VALID_FREQUENCIES)
            _raise_spec_error(
                "StrategySpec.execution.frequency must be one of "
                + f"{valid_freq}, got '{self.execution.frequency}'",
                field_name="execution.frequency",
                reason="invalid_frequency",
                allowed_values=valid_freq,
                actual_value=self.execution.frequency,
            )

        # cost_model 边界
        cm = self.execution.cost_model
        if not (0.0 <= cm.commission_rate <= 1.0):
            _raise_spec_error(
                "StrategySpec.commission_rate must be in [0, 1], "
                + f"got {cm.commission_rate}",
                field_name="execution.cost_model.commission_rate",
                reason="out_of_range",
                min_value=0.0,
                max_value=1.0,
                actual_value=cm.commission_rate,
            )
        if cm.slippage_bps < 0:
            _raise_spec_error(
                "StrategySpec.slippage_bps must be >= 0, " + f"got {cm.slippage_bps}",
                field_name="execution.cost_model.slippage_bps",
                reason="below_min",
                min_value=0.0,
                actual_value=cm.slippage_bps,
            )

        # signal_expressions / signal_weights 长度一致性
        if (
            self.signal_expressions
            and self.signal_weights
            and len(self.signal_expressions) != len(self.signal_weights)
        ):
            _raise_spec_error(
                f"StrategySpec.signal_weights length ({len(self.signal_weights)}) "
                + "must match signal_expressions length "
                + f"({len(self.signal_expressions)})",
                field_name="signal_weights",
                reason="length_mismatch",
                signal_expression_count=len(self.signal_expressions),
                signal_weight_count=len(self.signal_weights),
            )

        _validate_production_signal_expressions(
            tags=self.tags,
            params=self.params,
            signal_expressions=self.signal_expressions,
        )


def _validate_production_signal_expressions(
    *,
    tags: tuple[str, ...],
    params: dict[str, object],
    signal_expressions: tuple[str, ...],
) -> None:
    if "production" not in tags:
        return
    materialized_columns = _materialized_factor_columns(params)
    for expression in signal_expressions:
        try:
            validate_production_factor_expression(
                expression,
                materialized_columns=materialized_columns,
            )
        except UnsafeProductionFactorExpressionError as exc:
            _raise_spec_error(
                f"StrategySpec production factor expression is unsafe: {exc}",
                field_name="signal_expressions",
                reason="unsafe_production_factor_expression",
                expression=expression,
            )


def _materialized_factor_columns(params: dict[str, object]) -> frozenset[str]:
    raw = params.get("materialized_factor_columns", ())
    if isinstance(raw, str):
        return frozenset((raw,))
    if isinstance(raw, tuple):
        return _stringified_columns(cast(tuple[object, ...], raw))
    if isinstance(raw, list):
        return _stringified_columns(cast(list[object], raw))
    if isinstance(raw, set):
        return _stringified_columns(cast(set[object], raw))
    if isinstance(raw, frozenset):
        return _stringified_columns(cast(frozenset[object], raw))
    return frozenset()


def _stringified_columns(
    values: tuple[object, ...] | list[object] | set[object] | frozenset[object],
) -> frozenset[str]:
    return frozenset(str(item) for item in values)
