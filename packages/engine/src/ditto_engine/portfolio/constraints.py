"""
约束检查器 -- 按 priority 依次执行约束规则调整权重.

提供三种内置约束：
- MaxWeightConstraint: 单标的权重上限
- MinWeightConstraint: 单标的权重下限（低于则清零）
- MaxPositionsConstraint: 最大持仓数量

ConstraintStage 是 DecisionStage 适配器，将 ConstraintChecker 包装为
Pipeline 可消费的 Stage。
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import polars as pl

__all__ = [
    "Constraint",
    "ConstraintAdjustment",
    "ConstraintChecker",
    "ConstraintStage",
    "MaxPositionsConstraint",
    "MaxWeightConstraint",
    "MinWeightConstraint",
]


@dataclass(frozen=True)
class ConstraintAdjustment:
    """
    单条约束的调整结果.

    Attributes:
        constraint_id: 约束 ID
        adjusted_weights: 调整后的权重 {instrument_id: weight}
        reason_codes: 调整原因说明

    """

    constraint_id: str
    adjusted_weights: dict[str, float]
    reason_codes: tuple[str, ...]


class Constraint(Protocol):
    """单条约束规则。"""

    @property
    def constraint_id(self) -> str:
        """约束 ID。"""
        ...

    @property
    def priority(self) -> int:
        """优先级（数字小优先）。"""
        ...

    def check(
        self,
        weights: dict[str, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """检查权重并返回调整结果。"""
        ...


@dataclass(frozen=True)
class MaxWeightConstraint:
    """
    单标的权重上限.

    Attributes:
        constraint_id: 约束 ID
        priority: 优先级（数字小优先）
        max_weight: 单标的最大权重

    """

    constraint_id: str = "max_weight"
    priority: int = 10
    max_weight: float = 0.2

    def check(
        self,
        weights: dict[str, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """截断超过上限的权重。"""
        adjusted: dict[str, float] = {}
        reasons: list[str] = []
        for iid, w in weights.items():
            if w > self.max_weight:
                adjusted[iid] = self.max_weight
                reasons.append(
                    f"{self.constraint_id}: {iid} weight {w:.4f} > {self.max_weight}"
                )
            else:
                adjusted[iid] = w
        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


@dataclass(frozen=True)
class MinWeightConstraint:
    """
    单标的权重下限 -- 低于则清零.

    Attributes:
        constraint_id: 约束 ID
        priority: 优先级（数字小优先）
        min_weight: 低于此值的权重清零

    """

    constraint_id: str = "min_weight"
    priority: int = 20
    min_weight: float = 0.02

    def check(
        self,
        weights: dict[str, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """将低于下限的正权重清零。"""
        adjusted: dict[str, float] = {}
        reasons: list[str] = []
        for iid, w in weights.items():
            if 0 < w < self.min_weight:
                adjusted[iid] = 0.0
                msg = (
                    f"{self.constraint_id}: {iid} weight {w:.4f}"
                    f" < {self.min_weight}, zeroed"
                )
                reasons.append(msg)
            else:
                adjusted[iid] = w
        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


@dataclass(frozen=True)
class MaxPositionsConstraint:
    """
    最大持仓数量 -- 保留 top K，其余清零.

    Attributes:
        constraint_id: 约束 ID
        priority: 优先级（数字小优先）
        max_positions: 最大持仓标的数量

    """

    constraint_id: str = "max_positions"
    priority: int = 30
    max_positions: int = 10

    def check(
        self,
        weights: dict[str, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """保留权重最大的 K 个标的，其余清零。"""
        sorted_items = sorted(weights.items(), key=operator.itemgetter(1), reverse=True)
        top_ids = {iid for iid, _ in sorted_items[: self.max_positions]}
        adjusted: dict[str, float] = {}
        reasons: list[str] = []
        for iid, w in weights.items():
            if iid in top_ids:
                adjusted[iid] = w
            elif w > 0:
                adjusted[iid] = 0.0
                msg = (
                    f"{self.constraint_id}: {iid} removed"
                    f" (exceeds max_positions={self.max_positions})"
                )
                reasons.append(msg)
            else:
                adjusted[iid] = w
        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


class ConstraintChecker:
    """
    约束检查器 -- 按 priority 升序执行，逐条调整权重.

    Parameters
    ----------
        constraints: 约束序列

    """

    def __init__(self, constraints: Sequence[Constraint]) -> None:
        self._constraints = tuple(constraints)

    def check(self, frame: pl.DataFrame) -> pl.DataFrame:
        """
        依次执行所有约束，调整 frame 中的 weight 列.

        返回的 frame 包含:
        - weight: 调整后的权重
        - reason_codes: 所有调整原因的列表
        """
        weights = dict(
            zip(
                frame["instrument_id"].to_list(),
                frame["weight"].to_list(),
                strict=True,
            )
        )
        all_reasons: list[str] = []

        for constraint in sorted(
            self._constraints, key=operator.attrgetter("priority")
        ):
            result = constraint.check(weights, frame)
            weights = result.adjusted_weights
            all_reasons.extend(result.reason_codes)

        weight_expr = pl.col("instrument_id").replace_strict(
            old=list(weights.keys()),
            new=list(weights.values()),
            default=0.0,
        )
        return frame.with_columns(
            weight_expr.alias("weight"),
        ).with_columns(
            pl.lit(all_reasons).alias("reason_codes"),
        )


@dataclass(frozen=True)
class ConstraintStage:
    """
    Pipeline Stage 适配器 -- 包装 ConstraintChecker.

    Attributes:
        checker: 约束检查器实例

    """

    checker: ConstraintChecker

    def process(self, frame: pl.DataFrame, context: object) -> pl.DataFrame:
        """委托给 checker.check，context 由 Pipeline 传入但不使用。"""
        return self.checker.check(frame)
