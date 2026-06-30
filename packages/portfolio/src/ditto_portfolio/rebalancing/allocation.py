"""
权重分配器 — 将 score/selection/volatility 转换为权重.

提供三种内置分配策略：
- EqualWeightAllocator: 等权分配
- InverseVolAllocator: 波动率倒数加权分配
- ScoreWeightAllocator: 按 score 加权分配

AllocationStage 是 DecisionStage 适配器，将 WeightAllocator 包装为
Pipeline 可消费的 Stage。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import polars as pl

__all__ = [
    "AllocationStage",
    "EqualWeightAllocator",
    "InverseVolAllocator",
    "ScoreWeightAllocator",
    "WeightAllocator",
]


class WeightAllocator(Protocol):
    """权重分配器 — 将 score/selection 转换为权重。"""

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        """在 frame 上添加 weight 列。"""
        ...


@dataclass(frozen=True)
class EqualWeightAllocator:
    """
    等权分配 — 所有标的无差别分配.

    Attributes:
        cash_target: 目标现金比例（0.0 = 全仓）

    """

    cash_target: float = 0.0

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        """在 frame 上添加等权 weight 列。"""
        n = frame.height
        if n == 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))
        weight_per = (1.0 - self.cash_target) / n
        return frame.with_columns(pl.lit(weight_per).alias("weight"))


@dataclass(frozen=True)
class InverseVolAllocator:
    """
    波动率倒数加权分配 — 低波动率标的获得更高权重.

    分配逻辑:
      weight_i = (1/vol_i) / sum(1/vol_j) * (1 - cash_target)

    边界处理:
      - 空 frame → 返回空 frame + weight 列（全 0）
      - 全零波动率 → 等权分配
      - 部分零波动率 → 零波动率标的权重为 0
      - 单标的 → 权重 = (1 - cash_target)

    Attributes:
        vol_column: 波动率列名
        cash_target: 目标现金比例（0.0 = 全仓）

    """

    vol_column: str = "volatility"
    cash_target: float = 0.0

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        """在 frame 上添加波动率倒数加权的 weight 列。"""
        if frame.height == 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        vol_col = pl.col(self.vol_column)
        total_investable = 1.0 - self.cash_target

        # All-zero volatility → equal weight
        if frame.select((vol_col == 0).all()).item():
            weight_per = total_investable / frame.height
            return frame.with_columns(pl.lit(weight_per).alias("weight"))

        # Compute inverse vol: zero vol → 0.0, else 1/vol
        result = frame.with_columns(
            pl.when(vol_col == 0)
            .then(pl.lit(0.0))
            .otherwise(1.0 / vol_col)
            .alias("_inv_vol"),
        )

        # Normalize: inv_vol / sum(inv_vol) * total_investable
        inv_vol_sum = result.select(pl.col("_inv_vol").sum()).item()
        result = result.with_columns(
            (pl.col("_inv_vol") / inv_vol_sum * total_investable).alias("weight"),
        ).drop("_inv_vol")

        return result


@dataclass(frozen=True)
class ScoreWeightAllocator:
    """
    按 score 加权分配 — score 高的权重大.

    分配逻辑:
      1. null score -> weight = 0.0
      2. 若所有有效 score 相同 -> 等权分配
      3. 归一化 score 到 [0, 1]，然后按比例分配权重
      4. 应用 min_weight 下限

    Attributes:
        score_column: score 列名
        cash_target: 目标现金比例
        min_weight: 单标的最低权重（0 = 不限制）

    """

    score_column: str = "score"
    cash_target: float = 0.0
    min_weight: float = 0.0

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        """在 frame 上添加按 score 加权的 weight 列。"""
        if frame.height == 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        score_col = pl.col(self.score_column)

        # 1. All-null scores -> weight = 0.0
        if frame.select(score_col.is_null().all()).item():
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        # 2. Compute normalized weight: null -> 0.0, else proportional
        # Shift scores so min becomes 0 (making all positive before normalizing)
        non_null = frame.filter(score_col.is_not_null())
        score_min = non_null.select(score_col.min()).item()
        score_max = non_null.select(score_col.max()).item()

        # If all scores are the same -> equal weight for non-null rows
        if score_max == score_min:
            n_valid = non_null.height
            weight_per = (1.0 - self.cash_target) / n_valid
            return frame.with_columns(
                pl.when(score_col.is_null())
                .then(pl.lit(0.0))
                .otherwise(pl.lit(weight_per))
                .alias("weight"),
            )

        # Shift so min score maps to 0 (all scores become >= 0)
        shift = score_min
        score_range = score_max - shift  # always > 0 since max != min
        total_investable = 1.0 - self.cash_target

        # Compute proportional weights (null -> 0.0)
        shifted_col = (score_col - shift) / score_range
        result = frame.with_columns(
            pl.when(score_col.is_null())
            .then(pl.lit(0.0))
            .otherwise(shifted_col)
            .alias("_proportional"),
        )

        # Normalize: proportional / sum(proportional) * total_investable
        weight_sum = result.select(pl.col("_proportional").sum()).item()
        result = result.with_columns(
            (pl.col("_proportional") / weight_sum * total_investable).alias(
                "weight",
            ),
        ).drop("_proportional")

        # 3. Apply min_weight floor
        if self.min_weight > 0:
            result = result.with_columns(
                pl.when(
                    (pl.col("weight") > 0) & (pl.col("weight") < self.min_weight),
                )
                .then(pl.lit(self.min_weight))
                .otherwise(pl.col("weight"))
                .alias("weight"),
            )

        return result


@dataclass(frozen=True)
class AllocationStage:
    """
    Pipeline Stage 适配器 — 包装 WeightAllocator.

    将任意 WeightAllocator 适配为 DecisionStage Protocol，
    使其可被 StrategyPipeline 消费。

    Attributes:
        allocator: 权重分配器实例

    """

    allocator: WeightAllocator

    def process(self, frame: pl.DataFrame, context: object) -> pl.DataFrame:
        """
        委托给 allocator.allocate.

        context: 接收 DecisionStage Protocol 的 StrategyContext，
        但本 stage 不使用。类型为 object 因 portfolio 禁止依赖 strategy。
        """
        return self.allocator.allocate(frame)
