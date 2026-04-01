"""
stock_sector_rotation 策略模板 -- 行业轮动 + 行业内选股的两层 Pipeline.

标准流程:
  SectorSignal -> SectorScoreAndSelect -> IntraSectorSelect -> RiskLockFilter ->
  SectorWeight -> Constraint(max_weight) -> FinalFilter(non-sector)

提供:
- StockSectorRotationConfig: 策略模板运行时配置
- SectorSignalStage: 计算行业动量信号
- SectorScoreAndSelectStage: 评分并选取 Top K 行业，标记关联股票
- IntraSectorSelectStage: 行业内按信号选 Top K 股票
- SectorWeightStage: 行业等权 + 行业内等权分配
- FinalStockFilterStage: 过滤行业 ETF 行，仅保留个股
- validate_config: 配置校验
- get_param_constraints: 参数扫描元数据
- build_stock_sector_rotation_pipeline: 组装标准 Pipeline

DecisionFrame 额外约定列:
  sector_id: str      -- 个股所属行业 ID（行业 ETF 行 = 自身 ID）
  is_sector: bool     -- True = 行业 ETF，False = 个股
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ditto_engine.portfolio.constraints import (
    Constraint,
    ConstraintChecker,
    ConstraintStage,
    MaxWeightConstraint,
)
from ditto_engine.strategy.builtins.filtering import RiskLockFilter
from ditto_engine.strategy.context import StrategyContext
from ditto_engine.strategy.pipeline import StrategyPipeline
from ditto_engine.strategy.protocols import DecisionStage
from ditto_engine.strategy.specs import ParamConstraint

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
# StockSectorRotationConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockSectorRotationConfig:
    """
    stock_sector_rotation 策略模板的运行时配置.

    Attributes:
        sector_signal: 行业信号列名（从 signal_values DataFrame 中读取）。
        stock_signal: 个股信号列名（行业内选股排序用）。
        top_sectors: 选取排名前 K 的行业。
        stocks_per_sector: 每个行业内选取排名前 K 的个股。
        sector_weight_method: 行业间权重分配方式 (``"equal_weight"``)。
        stock_weight_method: 行业内权重分配方式 (``"equal_weight"``)。
        max_weight: 单标的最大权重。
        cash_target: 目标现金比例。
        rebalance_freq: 调仓频率 (``"daily"`` / ``"weekly"`` / ``"monthly"``)。

    """

    sector_signal: str = "signal_value"
    stock_signal: str = "signal_value"
    top_sectors: int = 3
    stocks_per_sector: int = 3
    sector_weight_method: str = "equal_weight"
    stock_weight_method: str = "equal_weight"
    max_weight: float = 0.15
    cash_target: float = 0.0
    rebalance_freq: str = "daily"


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def validate_config(config: StockSectorRotationConfig) -> None:
    """
    校验 StockSectorRotationConfig 合法性.

    Raises:
        ValueError: 配置不合法时抛出描述性异常。

    """
    if config.top_sectors < 1:
        msg = f"top_sectors must be >= 1, got {config.top_sectors}"
        raise ValueError(msg)

    if config.stocks_per_sector < 1:
        msg = f"stocks_per_sector must be >= 1, got {config.stocks_per_sector}"
        raise ValueError(msg)

    if config.max_weight <= 0 or config.max_weight > 1:
        msg = f"max_weight must be > 0 and <= 1, got {config.max_weight}"
        raise ValueError(msg)

    if config.cash_target < 0 or config.cash_target >= 1:
        msg = f"cash_target must be >= 0 and < 1, got {config.cash_target}"
        raise ValueError(msg)

    valid_weight_methods = ("equal_weight",)
    if config.sector_weight_method not in valid_weight_methods:
        msg = (
            f"sector_weight_method must be one of {valid_weight_methods}, "
            f"got '{config.sector_weight_method}'"
        )
        raise ValueError(msg)

    if config.stock_weight_method not in valid_weight_methods:
        msg = (
            f"stock_weight_method must be one of {valid_weight_methods}, "
            f"got '{config.stock_weight_method}'"
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
    返回 stock_sector_rotation 模板的参数扫描元数据.

    Returns:
        ParamConstraint 元组，描述可调参数的范围和可选值。

    """
    return (
        ParamConstraint(
            name="top_sectors",
            dtype="int",
            min_value=1,
            max_value=20,
            step=1,
        ),
        ParamConstraint(
            name="stocks_per_sector",
            dtype="int",
            min_value=1,
            max_value=20,
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
            name="cash_target",
            dtype="float",
            min_value=0.0,
            max_value=0.5,
            step=0.05,
        ),
        ParamConstraint(
            name="rebalance_freq",
            dtype="str",
            allowed_values=("daily", "weekly", "monthly"),
        ),
    )


# ---------------------------------------------------------------------------
# SectorSignalStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorSignalStage:
    """
    计算行业动量信号 — 对行业 ETF 行提取信号值.

    将行业 ETF 的 sector_signal_column 值复制到 sector_signal 列，
    个股行的 sector_signal 设为 null。

    Attributes:
        signal_column: 行业信号源列名。
        is_sector_column: 区分行业 ETF / 个股的布尔列名。
        output_column: 输出的行业信号列名。

    """

    signal_column: str = "signal_value"
    is_sector_column: str = "is_sector"
    output_column: str = "sector_signal"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        提取行业信号。

        边界处理:
        - 空 frame → 返回空 frame + sector_signal 列
        - signal_column 不存在 → sector_signal 全 null
        """
        if frame.is_empty():
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(self.output_column),
            )

        if self.signal_column not in frame.columns:
            return frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(self.output_column),
            )

        return frame.with_columns(
            pl.when(pl.col(self.is_sector_column))
            .then(pl.col(self.signal_column))
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias(self.output_column),
        )


# ---------------------------------------------------------------------------
# SectorScoreAndSelectStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorScoreAndSelectStage:
    """
    对行业 ETF 按信号评分并选取 Top K 行业，标记关联个股.

    流程:
      1. 提取行业 ETF 行，按 sector_signal 降序排名
      2. 选取 Top K 行业
      3. 在 frame 上添加 ``selected_sector`` 布尔列:
         - 行业 ETF 行: 若被选中则为 True
         - 个股行: 若其所属行业被选中则为 True

    Attributes:
        top_k: 选取 Top K 行业。
        signal_column: 行业信号列名（由 SectorSignalStage 输出）。
        is_sector_column: 区分行业 ETF / 个股的布尔列名。
        sector_column: 个股所属行业 ID 列名。

    """

    top_k: int = 3
    signal_column: str = "sector_signal"
    is_sector_column: str = "is_sector"
    sector_column: str = "sector_id"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        评分、选取 Top K 行业，标记关联个股。

        边界处理:
        - 空 frame / 无行业 ETF 行 → selected_sector 全 False
        - top_k >= 行业数量 → 全部选中
        """
        if frame.is_empty():
            return frame.with_columns(
                pl.lit(False).alias("selected_sector"),
            )

        # Extract sector ETF rows and select top K
        sector_rows = frame.filter(pl.col(self.is_sector_column))

        if sector_rows.is_empty():
            return frame.with_columns(
                pl.lit(False).alias("selected_sector"),
            )

        if self.signal_column not in frame.columns:
            return frame.with_columns(
                pl.lit(False).alias("selected_sector"),
            )

        top_sectors = (
            sector_rows.sort(self.signal_column, descending=True, nulls_last=True)
            .head(self.top_k)
            .select(self.sector_column)
        )

        top_sector_ids = set(top_sectors[self.sector_column].to_list())

        # Mark selected sectors and their child stocks
        return frame.with_columns(
            pl.when(pl.col(self.sector_column).is_in(top_sector_ids))
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias("selected_sector"),
        )


# ---------------------------------------------------------------------------
# IntraSectorSelectStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntraSectorSelectStage:
    """
    行业内选股 -- 在每个选中行业内按信号评分选取 Top K 个股.

    流程:
      1. 筛选非行业 ETF 且 selected_sector=True 的行
      2. 在每个 sector_id 分组内，按 stock_signal 降序排名
      3. 选取每组 Top K
      4. 添加 ``intra_selected`` 布尔列

    Attributes:
        stocks_per_sector: 每个行业内选取 Top K 个股。
        signal_column: 个股信号列名。
        is_sector_column: 区分行业 ETF / 个股的布尔列名。
        sector_column: 个股所属行业 ID 列名。

    """

    stocks_per_sector: int = 3
    signal_column: str = "signal_value"
    is_sector_column: str = "is_sector"
    sector_column: str = "sector_id"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        行业内选股，添加 intra_selected 列。

        边界处理:
        - 空 frame → intra_selected 全 False
        - signal_column 不存在 → intra_selected 全 False
        """
        if frame.is_empty() or self.signal_column not in frame.columns:
            result = frame.with_columns(pl.lit(False).alias("intra_selected"))
            return result

        # Collect selected stock IDs per sector
        selected_stocks = (
            frame.filter(
                (~pl.col(self.is_sector_column)) & pl.col("selected_sector"),
            )
            .with_columns(
                pl.col(self.signal_column)
                .rank(method="average", descending=True)
                .over(self.sector_column)
                .alias("_sector_rank"),
            )
            .filter(pl.col("_sector_rank") <= self.stocks_per_sector)
            .select("instrument_id")
        )

        if selected_stocks.is_empty():
            return frame.with_columns(pl.lit(False).alias("intra_selected"))

        selected_ids = set(selected_stocks["instrument_id"].to_list())

        return frame.with_columns(
            pl.when(pl.col("instrument_id").is_in(selected_ids))
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias("intra_selected"),
        )


# ---------------------------------------------------------------------------
# SectorWeightStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorWeightStage:
    """
    两层权重分配 -- 行业等权 + 行业内等权.

    流程:
      1. 统计被选中行业数量和每个行业内被选中个股数量
      2. 行业权重 = (1 - cash_target) / 选中行业数
      3. 个股权重 = 行业权重 / 该行业内选中个股数
      4. 未被选中的行权重 = 0.0
      5. 添加 ``weight`` 列

    Attributes:
        is_sector_column: 区分行业 ETF / 个股的布尔列名。
        sector_column: 个股所属行业 ID 列名。
        cash_target: 目标现金比例。

    """

    is_sector_column: str = "is_sector"
    sector_column: str = "sector_id"
    cash_target: float = 0.0

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """
        计算两层权重，添加 weight 列。

        边界处理:
        - 空 frame → weight 全 0.0
        - 无选中个股 → weight 全 0.0
        - cash_target >= 1.0 → weight 全 0.0
        """
        if frame.is_empty():
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        total_investable = 1.0 - self.cash_target
        if total_investable <= 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        # Collect selected non-sector instruments
        selected = frame.filter(
            (~pl.col(self.is_sector_column)) & pl.col("intra_selected"),
        )

        if selected.is_empty():
            return frame.with_columns(pl.lit(0.0).alias("weight"))

        # Count selected stocks per sector
        sector_counts = (
            selected.group_by(self.sector_column).len().rename({"len": "count"})
        )

        # Number of selected sectors
        num_sectors = selected.select(self.sector_column).n_unique()
        sector_weight = total_investable / num_sectors

        # Start with all weights = 0
        result = frame.with_columns(pl.lit(0.0).alias("weight"))

        # Assign weight to each selected stock per sector
        for row in sector_counts.iter_rows(named=True):
            sid = row[self.sector_column]
            count = row["count"]
            stock_weight = sector_weight / count

            result = result.with_columns(
                pl.when(
                    (pl.col(self.sector_column) == sid)
                    & (~pl.col(self.is_sector_column))
                    & pl.col("intra_selected"),
                )
                .then(pl.lit(stock_weight))
                .otherwise(pl.col("weight"))
                .alias("weight"),
            )

        return result


# ---------------------------------------------------------------------------
# FinalStockFilterStage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinalStockFilterStage:
    """
    过滤行业 ETF 行 + 权重为零的行，仅保留实际持仓个股.

    在两层 Pipeline 的末尾调用，确保 TargetPortfolio 中只包含
    有权重的个股（不包含行业 ETF 和未选中的零权重行）。

    Attributes:
        is_sector_column: 区分行业 ETF / 个股的布尔列名。

    """

    is_sector_column: str = "is_sector"

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        """过滤掉行业 ETF 行和零权重行。"""
        if frame.is_empty():
            return frame

        # Filter out sector ETF rows (if column exists)
        if self.is_sector_column in frame.columns:
            result = frame.filter(~pl.col(self.is_sector_column))
        else:
            result = frame

        # Filter out zero-weight rows
        if "weight" in result.columns:
            result = result.filter(pl.col("weight") > 0.0)

        return result


# ---------------------------------------------------------------------------
# build_stock_sector_rotation_pipeline
# ---------------------------------------------------------------------------


def build_stock_sector_rotation_pipeline(
    config: StockSectorRotationConfig,
) -> StrategyPipeline:
    """
    组装 stock_sector_rotation 的标准 Pipeline.

    流程:
      SectorSignal -> SectorScoreAndSelect -> IntraSectorSelect ->
      RiskLockFilter -> SectorWeight -> Constraint(max_weight) ->
      FinalStockFilter

    Args:
        config: 运行时配置。

    Returns:
        配置完成的 StrategyPipeline。

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

    # Constraint: MaxWeightConstraint (always present)
    constraint_list: list[Constraint] = [
        MaxWeightConstraint(max_weight=config.max_weight),
    ]
    stages.append(ConstraintStage(checker=ConstraintChecker(constraint_list)))

    # Filter out sector ETF rows before building TargetPortfolio
    stages.append(FinalStockFilterStage())

    return StrategyPipeline(stages)
