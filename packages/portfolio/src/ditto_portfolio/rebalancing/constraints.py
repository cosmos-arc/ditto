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
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import polars as pl

__all__ = [
    "Constraint",
    "ConstraintAdjustment",
    "ConstraintChecker",
    "ConstraintStage",
    "IndustryMaxWeightConstraint",
    "LiquidityConstraint",
    "MaxPositionsConstraint",
    "MaxTurnoverConstraint",
    "MaxWeightConstraint",
    "MinWeightConstraint",
    "TradabilityConstraint",
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
    adjusted_weights: dict[Hashable, float]
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
        weights: dict[Hashable, float],
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
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """截断超过上限的权重。"""
        adjusted: dict[Hashable, float] = {}
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
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """将低于下限的正权重清零。"""
        adjusted: dict[Hashable, float] = {}
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
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """保留权重最大的 K 个标的，其余清零。"""
        sorted_items = sorted(weights.items(), key=operator.itemgetter(1), reverse=True)
        top_ids = {iid for iid, _ in sorted_items[: self.max_positions]}
        adjusted: dict[Hashable, float] = {}
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


@dataclass(frozen=True)
class IndustryMaxWeightConstraint:
    """
    行业权重上限 -- 当行业列可用时，按组内权重比例压低超限行业.

    缺失行业列或单行行业为空时保持原权重不变。行业内正权重之和超过
    ``max_industry_weight`` 时，仅缩放该行业内正权重，其他行业不受影响。
    """

    constraint_id: str = "max_industry_weight"
    priority: int = 15
    max_industry_weight: float = 0.30
    industry_column: str = "industry"

    def check(
        self,
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """Cap positive exposure for each available industry group."""
        industry_by_id = _column_by_instrument(frame, self.industry_column)
        if not industry_by_id:
            return ConstraintAdjustment(self.constraint_id, dict(weights), ())

        adjusted: dict[Hashable, float] = dict(weights)
        totals: dict[Hashable, float] = {}
        for iid, weight in weights.items():
            industry = industry_by_id.get(iid)
            if industry is None or weight <= 0.0:
                continue
            totals[industry] = totals.get(industry, 0.0) + weight

        reasons: list[str] = []
        for industry, total_weight in totals.items():
            if total_weight <= self.max_industry_weight:
                continue
            scale = self.max_industry_weight / total_weight
            for iid, weight in weights.items():
                if industry_by_id.get(iid) == industry and weight > 0.0:
                    adjusted[iid] = weight * scale
            reason = (
                f"{self.constraint_id}: {industry} weight {total_weight:.4f} "
                f"> {self.max_industry_weight:.4f}"
            )
            reasons.append(reason)

        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


@dataclass(frozen=True)
class LiquidityConstraint:
    """
    最小流动性过滤 -- 流动性低于阈值或缺值的正权重标的清零.

    缺失流动性列时不做调整；列存在但单个标的缺值时按不满足阈值处理。
    """

    constraint_id: str = "min_liquidity"
    priority: int = 25
    min_liquidity: float = 0.0
    liquidity_column: str = "avg_daily_turnover"

    def check(
        self,
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """Zero positive weights whose liquidity is below the launch threshold."""
        liquidity_by_id = _column_by_instrument(frame, self.liquidity_column)
        if not liquidity_by_id:
            return ConstraintAdjustment(self.constraint_id, dict(weights), ())

        adjusted: dict[Hashable, float] = {}
        reasons: list[str] = []
        for iid, weight in weights.items():
            liquidity = _as_float(liquidity_by_id.get(iid))
            if weight > 0.0 and (liquidity is None or liquidity < self.min_liquidity):
                adjusted[iid] = 0.0
                reason = (
                    f"{self.constraint_id}: {iid} liquidity {liquidity} "
                    f"< {self.min_liquidity:.4f}"
                )
                reasons.append(reason)
            else:
                adjusted[iid] = weight

        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


@dataclass(frozen=True)
class TradabilityConstraint:
    """
    ST/停牌过滤 -- 状态列标记为不可交易时清零正权重.

    任一状态列缺失时跳过该状态检查；两列都缺失时整体不做调整。
    """

    constraint_id: str = "tradability"
    priority: int = 5
    st_column: str = "is_st"
    suspended_column: str = "is_suspended"

    def check(
        self,
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """Exclude instruments marked ST or suspended by available status columns."""
        st_by_id = _column_by_instrument(frame, self.st_column)
        suspended_by_id = _column_by_instrument(frame, self.suspended_column)
        if not st_by_id and not suspended_by_id:
            return ConstraintAdjustment(self.constraint_id, dict(weights), ())

        adjusted: dict[Hashable, float] = {}
        reasons: list[str] = []
        for iid, weight in weights.items():
            is_st = _truthy(st_by_id.get(iid))
            is_suspended = _truthy(suspended_by_id.get(iid))
            if weight > 0.0 and (is_st or is_suspended):
                adjusted[iid] = 0.0
                if is_st:
                    reasons.append(f"st_exclusion: {iid} marked ST")
                if is_suspended:
                    reasons.append(f"suspended_exclusion: {iid} suspended")
            else:
                adjusted[iid] = weight

        return ConstraintAdjustment(self.constraint_id, adjusted, tuple(reasons))


@dataclass(frozen=True)
class MaxTurnoverConstraint:
    """
    最大换手约束 -- 从旧仓位到目标仓位的调整路径按比例截断.

    换手定义为当前 frame 标的 ``abs(target - previous)`` 之和。若 previous
    holdings 未通过 ``previous_weights`` 或 frame 的 ``previous_weight_column``
    提供，则不做调整。
    """

    constraint_id: str = "max_turnover"
    priority: int = 40
    max_turnover: float = 0.30
    previous_weights: Mapping[Hashable, float] | None = None
    previous_weight_column: str = "previous_weight"

    def check(
        self,
        weights: dict[Hashable, float],
        frame: pl.DataFrame,
    ) -> ConstraintAdjustment:
        """Limit total target-weight movement from supplied previous holdings."""
        previous = _previous_weights_by_instrument(
            frame,
            previous_weights=self.previous_weights,
            previous_weight_column=self.previous_weight_column,
        )
        if not previous:
            return ConstraintAdjustment(self.constraint_id, dict(weights), ())

        turnover = sum(
            abs(weight - _lookup_previous_weight(previous, iid))
            for iid, weight in weights.items()
        )
        max_turnover = max(self.max_turnover, 0.0)
        if turnover <= max_turnover or turnover == 0.0:
            return ConstraintAdjustment(self.constraint_id, dict(weights), ())

        scale = max_turnover / turnover
        adjusted = {
            iid: _lookup_previous_weight(previous, iid)
            + (weight - _lookup_previous_weight(previous, iid)) * scale
            for iid, weight in weights.items()
        }
        reason = (
            f"{self.constraint_id}: turnover {turnover:.4f} "
            f"> {max_turnover:.4f}, scaled by {scale:.4f}"
        )
        return ConstraintAdjustment(self.constraint_id, adjusted, (reason,))


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
        """
        委托给 checker.check.

        context: 接收 DecisionStage Protocol 的 StrategyContext，
        但本 stage 不使用。类型为 object 因 portfolio 禁止依赖 strategy。
        """
        return self.checker.check(frame)


def _column_by_instrument(
    frame: pl.DataFrame,
    column: str,
) -> dict[Hashable, object]:
    if column not in frame.columns or frame.is_empty():
        return {}
    return dict(
        zip(
            frame["instrument_id"].to_list(),
            frame[column].to_list(),
            strict=True,
        )
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _previous_weights_by_instrument(
    frame: pl.DataFrame,
    *,
    previous_weights: Mapping[Hashable, float] | None,
    previous_weight_column: str,
) -> dict[Hashable, float]:
    if previous_weights is not None:
        return {key: float(value) for key, value in previous_weights.items()}
    column_values = _column_by_instrument(frame, previous_weight_column)
    result: dict[Hashable, float] = {}
    for iid, value in column_values.items():
        parsed = _as_float(value)
        if parsed is not None:
            result[iid] = parsed
    return result


def _lookup_previous_weight(
    previous: Mapping[Hashable, float],
    instrument_id: Hashable,
) -> float:
    if instrument_id in previous:
        return float(previous[instrument_id])
    instrument_id_text = str(instrument_id)
    if instrument_id_text in previous:
        return float(previous[instrument_id_text])
    return 0.0
