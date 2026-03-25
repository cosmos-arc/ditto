"""策略模板 -- 预配置的 Pipeline 组装方案."""

from ditto_core.strategy.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)
from ditto_core.strategy.templates.etf_trend_swing import (
    ETFTrendSwingConfig,
    TrailingStopStage,
    build_etf_trend_swing_pipeline,
)
from ditto_core.strategy.templates.stock_sector_rotation import (
    FinalStockFilterStage,
    IntraSectorSelectStage,
    SectorScoreAndSelectStage,
    SectorSignalStage,
    SectorWeightStage,
    StockSectorRotationConfig,
    build_stock_sector_rotation_pipeline,
)
from ditto_core.strategy.templates.stock_sector_rotation import (
    get_param_constraints as get_sector_rotation_param_constraints,
)
from ditto_core.strategy.templates.stock_sector_rotation import (
    validate_config as validate_sector_rotation_config,
)
from ditto_core.strategy.templates.stock_selection_trend import (
    MultiFactorSignalStage,
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
    get_param_constraints,
    validate_config,
)

__all__ = [
    "ETFRotationConfig",
    "ETFTrendSwingConfig",
    "FinalStockFilterStage",
    "IntraSectorSelectStage",
    "MultiFactorSignalStage",
    "SectorScoreAndSelectStage",
    "SectorSignalStage",
    "SectorWeightStage",
    "StockSectorRotationConfig",
    "StockSelectionTrendConfig",
    "TrailingStopStage",
    "build_etf_rotation_pipeline",
    "build_etf_trend_swing_pipeline",
    "build_stock_sector_rotation_pipeline",
    "build_stock_selection_trend_pipeline",
    "get_param_constraints",
    "get_sector_rotation_param_constraints",
    "validate_config",
    "validate_sector_rotation_config",
]
