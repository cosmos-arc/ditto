"""
stock_selection_trend 策略模板 -- 多因子选股趋势追踪的 alpha stages.

标准流程:
  MultiFactorSignal -> TrendFilter -> Scoring -> RiskLockFilter ->
  Select(top_k) -> [Regime]

提供:
- StockSelectionTrendConfig: 策略模板运行时配置
- MultiFactorSignalStage: 多因子加权信号 Stage
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_stock_selection_trend_pipeline: 组装 alpha stages
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_strategy.alpha.builtins.filtering import RiskLockFilter, TrendFilterStage
from ditto_strategy.alpha.builtins.regime import RegimeConfig
from ditto_strategy.alpha.builtins.regime_allocation import (
    RegimeAwareAllocationStage,
)
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import ParamConstraint

__all__ = [
    "MultiFactorSignalStage",
    "StockSelectionTrendConfig",
    "build_stock_selection_trend_pipeline",
    "get_param_constraints",
    "validate_config",
]


# ---------------------------------------------------------------------------
# StockSelectionTrendConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockSelectionTrendConfig:
    """
    stock_selection_trend 策略模板的运行时配置.

    Attributes:
        universe_filter: Universe 过滤条件名（预留）。
        signal_factors: 因子列名列表，从 signal_values DataFrame 中读取。
        signal_weights: 因子权重列表，须与 signal_factors 长度一致。
        top_k: 选取排名前 K 的标的。
        max_weight: 单标的最大权重。
        allocation_method: 分配方式 (``"equal_weight"`` / ``"inverse_vol"``)。
        cash_target: 目标现金比例。
        trend_threshold: 趋势过滤阈值。
        rebalance_freq: 调仓频率 (``"daily"`` / ``"weekly"`` / ``"monthly"``)。
        regime_config: Regime 评分配置（None = 不使用 regime 缩放）。

    """

    universe_filter: str = ""
    signal_factors: tuple[str, ...] = ("signal_value",)
    signal_weights: tuple[float, ...] = (1.0,)
    top_k: int = 10
    max_weight: float = 0.15
    allocation_method: str = "equal_weight"
    cash_target: float = 0.0
    trend_threshold: float = 0.0
    rebalance_freq: str = "daily"
    regime_config: RegimeConfig | None = None


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: StockSelectionTrendConfig) -> None:
    """
    校验 StockSelectionTrendConfig 合法性.

    Raises:
        ValueError: 配置不合法时抛出描述性异常。

    """
    if len(config.signal_factors) != len(config.signal_weights):
        msg = (
            f"signal_factors (len={len(config.signal_factors)}) and "
            f"signal_weights (len={len(config.signal_weights)}) "
            f"must have the same length"
        )
        raise ValueError(msg)

    if config.top_k < 1:
        msg = f"top_k must be >= 1, got {config.top_k}"
        raise ValueError(msg)

    if config.max_weight <= 0 or config.max_weight > 1:
        msg = f"max_weight must be > 0 and <= 1, got {config.max_weight}"
        raise ValueError(msg)

    valid_methods = ("equal_weight", "inverse_vol")
    if config.allocation_method not in valid_methods:
        msg = (
            f"allocation_method must be one of {valid_methods}, "
            f"got '{config.allocation_method}'"
        )
        raise ValueError(msg)

    valid_freqs = ("daily", "weekly", "monthly")
    if config.rebalance_freq not in valid_freqs:
        msg = (
            f"rebalance_freq must be one of {valid_freqs}, "
            f"got '{config.rebalance_freq}'"
        )
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


def get_param_constraints() -> tuple[ParamConstraint, ...]:
    """
    返回 stock_selection_trend 模板的参数扫描元数据.

    Returns:
        ParamConstraint 元组，描述可调参数的范围和可选值。

    """
    return (
        ParamConstraint(
            name="top_k",
            dtype="int",
            min_value=1,
            max_value=100,
            step=1,
        ),
        ParamConstraint(
            name="max_weight",
            dtype="float",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
        ),
        ParamConstraint(
            name="trend_threshold",
            dtype="float",
            min_value=0.0,
            max_value=0.2,
            step=0.01,
        ),
        ParamConstraint(
            name="cash_target",
            dtype="float",
            min_value=0.0,
            max_value=0.5,
            step=0.05,
        ),
        ParamConstraint(
            name="allocation_method",
            dtype="str",
            allowed_values=("equal_weight", "inverse_vol"),
        ),
        ParamConstraint(
            name="rebalance_freq",
            dtype="str",
            allowed_values=("daily", "weekly", "monthly"),
        ),
    )


# ---------------------------------------------------------------------------
# MultiFactorSignalStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MultiFactorSignalStage:
    """
    多因子加权信号 Stage -- 从多个因子列计算加权综合信号.

    使用 rank-based 标准化: 对每个因子列独立做百分位排名 (0-1)，
    然后加权求和: score = sum(w_i * rank_i) / sum(w_i)

    Attributes:
        signal_factors: 因子列名列表。
        signal_weights: 因子权重列表。
        output_column: 输出列名。

    """

    signal_factors: tuple[str, ...] = ("signal_value",)
    signal_weights: tuple[float, ...] = (1.0,)
    output_column: str = "signal_value"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        计算多因子加权信号并写入 output_column.

        边界处理:
        - 空 frame 或无因子 → 填充 0.0
        - 缺失因子列 → rank 视为 0.0
        """
        if frame.is_empty() or not self.signal_factors:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        weight_sum = sum(self.signal_weights)
        if weight_sum == 0.0:
            return frame.with_columns(pl.lit(0.0).alias(self.output_column))

        result = frame
        weighted_sum = pl.lit(0.0)

        for factor_name, weight in zip(
            self.signal_factors,
            self.signal_weights,
            strict=True,
        ):
            if factor_name not in frame.columns:
                # Missing factor: rank = 0.0 for all instruments
                continue

            col = pl.col(factor_name)
            n = frame.height
            rank_expr = col.rank(method="average", descending=False) / n
            weighted_sum = weighted_sum + pl.lit(weight) * rank_expr

        return result.with_columns(
            (weighted_sum / pl.lit(weight_sum)).alias(self.output_column),
        )


# ---------------------------------------------------------------------------
# build_stock_selection_trend_pipeline
# ---------------------------------------------------------------------------


def build_stock_selection_trend_pipeline(
    config: StockSelectionTrendConfig,
) -> list[DecisionStage]:
    """
    组装 stock_selection_trend 的 alpha stages.

    流程:
      MultiFactorSignal -> TrendFilter -> Scoring -> RiskLockFilter ->
      Select(top_k) -> [Regime]

    分配与约束由 application 层根据 config 参数独立配置。

    Args:
        config: 运行时配置。

    Returns:
        alpha DecisionStage 列表。

    """
    stages: list[DecisionStage] = [
        MultiFactorSignalStage(
            signal_factors=config.signal_factors,
            signal_weights=config.signal_weights,
            output_column="signal_value",
        ),
        TrendFilterStage(
            threshold=config.trend_threshold,
            direction="long",
            signal_column="signal_value",
        ),
        ScoringStage(method=ScoringMethod.RANK, ascending=False),
        RiskLockFilter(),
        SelectionStage(top_k=config.top_k),
    ]

    # Regime-aware allocation (optional, strategy-internal)
    if config.regime_config is not None:
        stages.append(RegimeScoringStep(config.regime_config))
        stages.append(RegimeAwareAllocationStage())

    return stages
