"""
etf_trend_swing 策略模板 -- ETF 趋势追踪的 alpha stages.

标准流程:
  Signal -> TrendFilter -> Score -> RiskLockFilter -> Select -> [Regime] -> TrailingStop

提供:
- ETFTrendSwingConfig: 策略模板运行时配置
- TrailingStopStage: 追踪止损约束
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_etf_trend_swing_pipeline: 组装 alpha stages
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
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import ParamConstraint
from ditto_strategy.alpha.templates._common import raise_config_error

__all__ = [
    "ETFTrendSwingConfig",
    "TrailingStopStage",
    "build_etf_trend_swing_pipeline",
    "get_param_constraints",
    "validate_config",
]


def _raise_config_error(
    message: str,
    *,
    field_name: str,
    reason: str,
    actual_value: object,
    **details: object,
) -> None:
    """Raise a template config error with consistent metadata."""
    raise_config_error(
        message,
        template="etf_trend_swing",
        field_name=field_name,
        reason=reason,
        actual_value=actual_value,
        **details,
    )


# ---------------------------------------------------------------------------
# TrailingStopStage
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ETFTrendSwingConfig
# ---------------------------------------------------------------------------


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
        regime_config: Regime 评分配置（None = 不使用 regime 缩放）。

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
    regime_config: RegimeConfig | None = None


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: ETFTrendSwingConfig) -> None:
    """
    校验 ETFTrendSwingConfig 合法性.

    Raises:
        StrategySpecError: 配置不合法时抛出描述性异常。

    """
    if config.lookback_window < 1:
        msg = f"lookback_window must be >= 1, got {config.lookback_window}"
        _raise_config_error(
            msg,
            field_name="lookback_window",
            reason="below_min",
            actual_value=config.lookback_window,
            min_value=1,
        )

    if config.max_positions < 1:
        msg = f"max_positions must be >= 1, got {config.max_positions}"
        _raise_config_error(
            msg,
            field_name="max_positions",
            reason="below_min",
            actual_value=config.max_positions,
            min_value=1,
        )

    if config.trailing_stop_pct < 0 or config.trailing_stop_pct >= 1:
        msg = f"trailing_stop_pct must be >= 0 and < 1, got {config.trailing_stop_pct}"
        _raise_config_error(
            msg,
            field_name="trailing_stop_pct",
            reason="out_of_range",
            actual_value=config.trailing_stop_pct,
            min_value=0,
            max_value=1,
        )

    valid_methods = ("equal_weight", "inverse_vol")
    if config.allocation_method not in valid_methods:
        msg = (
            f"allocation_method must be one of {valid_methods}, "
            f"got '{config.allocation_method}'"
        )
        _raise_config_error(
            msg,
            field_name="allocation_method",
            reason="invalid_enum",
            actual_value=config.allocation_method,
            allowed_values=valid_methods,
        )

    if config.cash_target < 0 or config.cash_target >= 1:
        msg = f"cash_target must be >= 0 and < 1, got {config.cash_target}"
        _raise_config_error(
            msg,
            field_name="cash_target",
            reason="out_of_range",
            actual_value=config.cash_target,
            min_value=0,
            max_value=1,
        )


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


def get_param_constraints() -> tuple[ParamConstraint, ...]:
    """
    返回 etf_trend_swing 模板的参数扫描元数据.

    Returns:
        ParamConstraint 元组，描述可调参数的范围和可选值。

    """
    return (
        ParamConstraint(
            name="lookback_window",
            dtype="int",
            min_value=5,
            max_value=120,
            step=5,
        ),
        ParamConstraint(
            name="trend_threshold",
            dtype="float",
            min_value=0.0,
            max_value=0.2,
            step=0.01,
        ),
        ParamConstraint(
            name="trailing_stop_pct",
            dtype="float",
            min_value=0.01,
            max_value=0.30,
            step=0.01,
        ),
        ParamConstraint(
            name="max_positions",
            dtype="int",
            min_value=1,
            max_value=50,
            step=1,
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
    )


# ---------------------------------------------------------------------------
# build_etf_trend_swing_pipeline
# ---------------------------------------------------------------------------


def build_etf_trend_swing_pipeline(
    config: ETFTrendSwingConfig,
) -> list[DecisionStage]:
    """
    组装 etf_trend_swing 的 alpha stages.

    流程:
      Signal -> TrendFilter -> Score -> RiskLockFilter ->
      Select -> [Regime] -> TrailingStop

    分配由 application 层根据 config 参数独立配置。

    Args:
        config: 运行时配置。

    Returns:
        alpha DecisionStage 列表。

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

    # Regime-aware allocation (optional, strategy-internal)
    if config.regime_config is not None:
        stages.append(RegimeScoringStep(config.regime_config))
        stages.append(RegimeAwareAllocationStage())

    # Trailing Stop (post-selection)
    if config.trailing_stop_pct > 0:
        stages.append(
            TrailingStopStage(trailing_stop_pct=config.trailing_stop_pct),
        )

    return stages
