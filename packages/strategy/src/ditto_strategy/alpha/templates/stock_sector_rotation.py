"""
stock_sector_rotation 策略模板 -- 行业轮动 + 行业内选股的两层 alpha stages.

标准流程:
  SectorSignal -> SectorScoreAndSelect -> IntraSectorSelect -> RiskLockFilter ->
  SectorWeight -> [Regime] -> FinalFilter(non-sector)

提供:
- StockSectorRotationConfig: 策略模板运行时配置
- SectorSignalStage: 计算行业动量信号
- SectorScoreAndSelectStage: 评分并选取 Top K 行业，标记关联股票
- IntraSectorSelectStage: 行业内按信号选 Top K 股票
- SectorWeightStage: 行业等权 + 行业内等权分配
- FinalStockFilterStage: 过滤行业 ETF 行，仅保留个股
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_stock_sector_rotation_pipeline: 组装 alpha stages

DecisionFrame 额外约定列:
  sector_id: str      -- 个股所属行业 ID（行业 ETF 行 = 自身 ID）
  is_sector: bool     -- True = 行业 ETF，False = 个股
"""

from __future__ import annotations

from ditto_strategy.alpha.builtins.filtering import RiskLockFilter
from ditto_strategy.alpha.builtins.regime_allocation import (
    RegimeAwareAllocationStage,
)
from ditto_strategy.alpha.builtins.regime_scoring import RegimeScoringStep
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.templates.stock_sector_rotation_config import (
    StockSectorRotationConfig,
    get_param_constraints,
    validate_config,
)
from ditto_strategy.alpha.templates.stock_sector_rotation_stages import (
    FinalStockFilterStage,
    IntraSectorSelectStage,
    SectorScoreAndSelectStage,
    SectorSignalStage,
    SectorWeightStage,
)

__all__ = [
    "FinalStockFilterStage",
    "IntraSectorSelectStage",
    "SectorScoreAndSelectStage",
    "SectorSignalStage",
    "SectorWeightStage",
    "StockSectorRotationConfig",
    "build_stock_sector_rotation_pipeline",
    "get_param_constraints",
    "validate_config",
]


# ---------------------------------------------------------------------------
# build_stock_sector_rotation_pipeline
# ---------------------------------------------------------------------------


def build_stock_sector_rotation_pipeline(
    config: StockSectorRotationConfig,
) -> list[DecisionStage]:
    """
    组装 stock_sector_rotation 的 alpha stages.

    流程:
      SectorSignal -> SectorScoreAndSelect -> IntraSectorSelect ->
      RiskLockFilter -> SectorWeight -> [Regime] -> FinalStockFilter

    约束由 application 层根据 config.max_weight 独立配置。

    Args:
        config: 运行时配置。

    Returns:
        alpha DecisionStage 列表。

    """
    stages: list[DecisionStage] = [
        SectorSignalStage(
            signal_column=config.sector_signal,
        ),
        SectorScoreAndSelectStage(
            top_k=config.top_sectors,
        ),
        IntraSectorSelectStage(
            stocks_per_sector=config.stocks_per_sector,
            signal_column=config.stock_signal,
        ),
        RiskLockFilter(),
        SectorWeightStage(
            cash_target=config.cash_target,
        ),
    ]

    # Regime-aware allocation (optional, strategy-internal)
    if config.regime_config is not None:
        stages.append(RegimeScoringStep(config.regime_config))
        stages.append(RegimeAwareAllocationStage())

    # Filter out sector ETF rows before building TargetPortfolio
    stages.append(FinalStockFilterStage())

    return stages
