"""
etf_trend_swing 策略模板 -- ETF 趋势追踪的标准 Pipeline.

标准流程:
  Signal -> TrendFilter -> Score -> RiskLockFilter -> Select -> Allocate -> TrailingStop

提供:
- ETFTrendSwingConfig: 策略模板运行时配置
- TrailingStopStage: 追踪止损约束
- build_etf_trend_swing_pipeline: 组装标准 Pipeline
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_engine.portfolio.allocation import (
    AllocationStage,
    EqualWeightAllocator,
    InverseVolAllocator,
    WeightAllocator,
)
from ditto_engine.strategy.builtins.filtering import RiskLockFilter, TrendFilterStage
from ditto_engine.strategy.builtins.scoring import ScoringMethod, ScoringStage
from ditto_engine.strategy.builtins.selection import SelectionStage
from ditto_engine.strategy.builtins.signal import SignalStage
from ditto_engine.strategy.context import StrategyContext
from ditto_engine.strategy.pipeline import StrategyPipeline
from ditto_engine.strategy.protocols import DecisionStage

__all__ = [
    "ETFTrendSwingConfig",
    "TrailingStopStage",
    "build_etf_trend_swing_pipeline",
]


@dataclass(frozen=True)
class TrailingStopStage:
    """
    追踪止损 -- 持仓跌破止损线时权重归零.

    止损线 = 持仓成本 * (1 - trailing_stop_pct)

    Attributes:
        trailing_stop_pct: 追踪止损百分比。
        price_column: 当前价格列名。

    """

    trailing_stop_pct: float
    price_column: str = "close"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """检查持仓是否触发止损，触发则权重归零并标记原因。"""
        if not context.positions or self.price_column not in frame.columns:
            return frame

        # Build stop prices as a lookup frame for vectorized join
        stop_frame = pl.DataFrame(
            {
                "instrument_id": list(context.positions.keys()),
                "stop_price": [
                    cost * (1 - self.trailing_stop_pct)
                    for cost in context.positions.values()
                ],
            },
        )

        # Vectorized: join frame with stop prices, check trigger condition
        triggered = (
            frame.select("instrument_id", self.price_column)
            .join(stop_frame, on="instrument_id", how="inner")
            .filter(pl.col(self.price_column) < pl.col("stop_price"))
        )

        if triggered.is_empty():
            return frame

        triggered_ids = triggered["instrument_id"].to_list()

        # Set weight to 0 for triggered positions
        result = frame.with_columns(
            pl.when(pl.col("instrument_id").is_in(triggered_ids))
            .then(pl.lit(0.0))
            .otherwise(pl.col("weight").fill_null(0.0))
            .alias("weight"),
        )

        # Add / append reason_codes for triggered instruments
        if "reason_codes" not in result.columns:
            result = result.with_columns(
                pl.lit(None).cast(pl.List(pl.Utf8)).alias("reason_codes"),
            )

        result = result.with_columns(
            pl.when(pl.col("instrument_id").is_in(triggered_ids))
            .then(
                pl.coalesce(
                    pl.col("reason_codes"),
                    pl.lit([]).cast(pl.List(pl.Utf8)),
                ).list.concat(pl.lit(["trailing_stop"])),
            )
            .otherwise(pl.col("reason_codes"))
            .alias("reason_codes"),
        )

        return result


@dataclass(frozen=True)
class ETFTrendSwingConfig:
    """
    etf_trend_swing 策略模板的运行时配置.

    Attributes:
        lookback_window: 动量回看窗口（引擎预计算时使用）。
        trend_threshold: 趋势过滤阈值。
        trailing_stop_pct: 追踪止损百分比。
        max_positions: 最大持仓数量。
        scoring_method: 评分方法。
        scoring_ascending: True 表示信号值小的得分高。
        allocation_method: 分配方式 (``"equal_weight"`` / ``"inverse_vol"``)。
        cash_target: 目标现金比例。
        signal_column: 信号源列名。

    """

    lookback_window: int = 20
    trend_threshold: float = 0.0
    trailing_stop_pct: float = 0.08
    max_positions: int = 10
    scoring_method: ScoringMethod = ScoringMethod.RANK
    scoring_ascending: bool = True
    allocation_method: str = "equal_weight"
    cash_target: float = 0.0
    signal_column: str = "signal_value"


def build_etf_trend_swing_pipeline(
    config: ETFTrendSwingConfig,
) -> StrategyPipeline:
    """
    组装 etf_trend_swing 的标准 Pipeline.

    流程:
      Signal -> TrendFilter -> Score -> RiskLockFilter ->
      Select -> Allocate -> TrailingStop

    Args:
        config: 运行时配置。

    Returns:
        配置完成的 StrategyPipeline。

    """
    stages: list[DecisionStage] = [
        SignalStage(source_column=config.signal_column),
        TrendFilterStage(
            threshold=config.trend_threshold,
            direction="long",
            signal_column=config.signal_column,
        ),
        ScoringStage(
            method=config.scoring_method,
            ascending=config.scoring_ascending,
        ),
        RiskLockFilter(),
        SelectionStage(top_k=config.max_positions),
    ]

    # Allocator
    if config.allocation_method == "inverse_vol":
        allocator: WeightAllocator = InverseVolAllocator(
            cash_target=config.cash_target,
        )
    else:
        allocator = EqualWeightAllocator(cash_target=config.cash_target)
    stages.append(AllocationStage(allocator=allocator))

    # Trailing Stop (post-allocation)
    if config.trailing_stop_pct > 0:
        stages.append(
            TrailingStopStage(trailing_stop_pct=config.trailing_stop_pct),
        )

    return StrategyPipeline(stages)
