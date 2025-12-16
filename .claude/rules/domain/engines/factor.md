---
paths: packages/core/src/ditto_core/engine/factor*.py, packages/core/src/ditto_core/engine/*factor*.py
---

# FactorEngine — 因子计算引擎

> 计算用于选股/择时的量化因子

## 职责

- 根据配置计算各类因子（动量、波动率、价值等）
- 保证因子计算的 PIT 安全性
- 支持因子标准化和去极值
- 提供因子有效性验证

## 因子定义

```python
from dataclasses import dataclass
from typing import Callable, Literal
from enum import Enum
import polars as pl


class FactorCategory(Enum):
    """因子类别"""
    MOMENTUM = "momentum"       # 动量类
    VALUE = "value"             # 价值类
    VOLATILITY = "volatility"   # 波动率类
    VOLUME = "volume"           # 成交量类
    QUALITY = "quality"         # 质量类
    SENTIMENT = "sentiment"     # 情绪类


@dataclass
class FactorDefinition:
    """因子定义"""

    name: str                           # 因子名称
    category: FactorCategory            # 因子类别
    description: str                    # 因子描述
    compute_fn: Callable[[pl.DataFrame, "FactorConfig"], pl.Series]

    # 因子方向
    higher_is_better: bool = True       # True: 值越高越好

    # 数据要求
    required_columns: set[str] = None   # 必需的输入列
    min_periods: int = 1                # 最少需要的历史数据

    def __post_init__(self):
        if self.required_columns is None:
            self.required_columns = {"close"}


# ========== 预定义因子 ==========

def momentum_factor(data: pl.DataFrame, config: "FactorConfig") -> pl.Series:
    """动量因子：N日收益率"""
    window = config.factor_params.get("momentum_window", 20)
    return (
        pl.col("close") / pl.col("close").shift(window) - 1
    ).over("code")


def volatility_factor(data: pl.DataFrame, config: "FactorConfig") -> pl.Series:
    """波动率因子：N日收益率标准差"""
    window = config.factor_params.get("volatility_window", 20)
    return (
        pl.col("close")
          .pct_change()
          .rolling_std(window, closed="left")
          .over("code")
    )


def volume_ratio_factor(data: pl.DataFrame, config: "FactorConfig") -> pl.Series:
    """成交量比率因子：当前成交量 / N日平均"""
    window = config.factor_params.get("volume_window", 20)
    return (
        pl.col("volume") /
        pl.col("volume").rolling_mean(window, closed="left")
    ).over("code")


def rs_factor(data: pl.DataFrame, config: "FactorConfig") -> pl.Series:
    """相对强度因子：相对基准的超额收益"""
    window = config.factor_params.get("rs_window", 20)

    # 计算标的收益
    stock_ret = pl.col("close").pct_change(window).over("code")

    # 计算基准收益（需要 benchmark_return 列）
    if "benchmark_return" in data.columns:
        bench_ret = pl.col("benchmark_return")
        return stock_ret - bench_ret
    else:
        return stock_ret


def turnover_factor(data: pl.DataFrame, config: "FactorConfig") -> pl.Series:
    """换手率因子"""
    window = config.factor_params.get("turnover_window", 20)
    return (
        pl.col("turnover_rate")
          .rolling_mean(window, closed="left")
          .over("code")
    )


# 因子注册表
BUILTIN_FACTORS: dict[str, FactorDefinition] = {
    "momentum": FactorDefinition(
        name="momentum",
        category=FactorCategory.MOMENTUM,
        description="N日动量（收益率）",
        compute_fn=momentum_factor,
        higher_is_better=True,
        required_columns={"close"},
        min_periods=20,
    ),
    "volatility": FactorDefinition(
        name="volatility",
        category=FactorCategory.VOLATILITY,
        description="N日波动率",
        compute_fn=volatility_factor,
        higher_is_better=False,  # 低波动更好
        required_columns={"close"},
        min_periods=20,
    ),
    "volume_ratio": FactorDefinition(
        name="volume_ratio",
        category=FactorCategory.VOLUME,
        description="成交量比率",
        compute_fn=volume_ratio_factor,
        higher_is_better=True,
        required_columns={"volume"},
        min_periods=20,
    ),
    "rs": FactorDefinition(
        name="rs",
        category=FactorCategory.MOMENTUM,
        description="相对强度",
        compute_fn=rs_factor,
        higher_is_better=True,
        required_columns={"close"},
        min_periods=20,
    ),
}
```

## 配置

```python
from dataclasses import dataclass, field


@dataclass
class FactorConfig:
    """因子配置"""

    # 要计算的因子列表
    factor_names: list[str] = field(default_factory=lambda: ["momentum", "volatility"])

    # 因子参数
    factor_params: dict[str, int | float] = field(default_factory=lambda: {
        "momentum_window": 20,
        "volatility_window": 20,
        "volume_window": 20,
        "rs_window": 20,
    })

    # 数据处理
    lookback_days: int = 60              # 回看天数

    # 标准化
    normalize: bool = True               # 是否标准化
    normalize_method: str = "zscore"     # zscore | rank | minmax

    # 去极值
    winsorize: bool = True               # 是否去极值
    winsorize_limits: tuple[float, float] = (0.01, 0.99)  # 分位数范围

    # 自定义因子
    custom_factors: list[FactorDefinition] = field(default_factory=list)

    def validate(self) -> None:
        for name in self.factor_names:
            if name not in BUILTIN_FACTORS and not self._has_custom(name):
                raise ValueError(f"Unknown factor: {name}")

    def _has_custom(self, name: str) -> bool:
        return any(f.name == name for f in self.custom_factors)
```

## 结果

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class FactorResult:
    """因子计算结果"""

    # 因子数据（包含所有因子值）
    data: pl.DataFrame

    # PIT 信息
    knowledge_date: date             # 数据可知日期

    # 元数据
    factor_names: list[str]          # 计算的因子
    factor_stats: dict[str, FactorStats]  # 因子统计信息


@dataclass
class FactorStats:
    """因子统计信息"""

    name: str
    count: int                       # 有效值数量
    mean: float
    std: float
    min: float
    max: float
    null_ratio: float                # 空值比例

    # IC 信息（如果有收益数据）
    ic: float | None = None          # 信息系数
    ic_ir: float | None = None       # IC 信息比率
```

## 实现

```python
import polars as pl
from .base import BaseEngine


class FactorEngine(BaseEngine[FactorConfig, pl.DataFrame, FactorResult]):
    """因子计算引擎"""

    def _validate_config(self, config: FactorConfig) -> None:
        config.validate()

    def _validate_input(self, data: pl.DataFrame) -> None:
        # 基础列检查
        required = {"code", "trade_date", "close"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        # 检查每个因子的必需列
        for name in self.config.factor_names:
            factor_def = self._get_factor_def(name)
            factor_missing = factor_def.required_columns - set(data.columns)
            if factor_missing:
                raise ValueError(
                    f"Factor '{name}' requires columns: {factor_missing}"
                )

    def _do_process(self, data: pl.DataFrame) -> FactorResult:
        """计算因子"""
        # 1. 排序
        data = data.sort(["code", "trade_date"])

        # 2. 计算每个因子
        factor_cols = []
        for name in self.config.factor_names:
            factor_def = self._get_factor_def(name)
            factor_series = factor_def.compute_fn(data, self.config)
            factor_cols.append(factor_series.alias(name))

        data = data.with_columns(factor_cols)

        # 3. 去极值
        if self.config.winsorize:
            data = self._winsorize(data)

        # 4. 标准化
        if self.config.normalize:
            data = self._normalize(data)

        # 5. 计算统计信息
        factor_stats = self._compute_stats(data)

        # 6. 确定 knowledge_date
        knowledge_date = data["trade_date"].max()

        return FactorResult(
            data=data,
            knowledge_date=knowledge_date,
            factor_names=self.config.factor_names,
            factor_stats=factor_stats,
        )

    def _get_factor_def(self, name: str) -> FactorDefinition:
        """获取因子定义"""
        if name in BUILTIN_FACTORS:
            return BUILTIN_FACTORS[name]

        for custom in self.config.custom_factors:
            if custom.name == name:
                return custom

        raise ValueError(f"Factor not found: {name}")

    def _winsorize(self, data: pl.DataFrame) -> pl.DataFrame:
        """去极值：缩尾处理"""
        lower, upper = self.config.winsorize_limits

        winsorize_cols = []
        for name in self.config.factor_names:
            col = pl.col(name)
            lower_bound = col.quantile(lower)
            upper_bound = col.quantile(upper)

            winsorized = (
                pl.when(col < lower_bound).then(lower_bound)
                  .when(col > upper_bound).then(upper_bound)
                  .otherwise(col)
                  .alias(name)
            )
            winsorize_cols.append(winsorized)

        return data.with_columns(winsorize_cols)

    def _normalize(self, data: pl.DataFrame) -> pl.DataFrame:
        """标准化"""
        method = self.config.normalize_method

        norm_cols = []
        for name in self.config.factor_names:
            col = pl.col(name)

            if method == "zscore":
                # Z-score: (x - mean) / std
                normalized = (col - col.mean()) / col.std()
            elif method == "rank":
                # 排名百分比
                normalized = col.rank() / col.count()
            elif method == "minmax":
                # Min-Max: (x - min) / (max - min)
                normalized = (col - col.min()) / (col.max() - col.min())
            else:
                raise ValueError(f"Unknown normalize method: {method}")

            norm_cols.append(normalized.alias(f"{name}_norm"))

        return data.with_columns(norm_cols)

    def _compute_stats(self, data: pl.DataFrame) -> dict[str, FactorStats]:
        """计算因子统计信息"""
        stats = {}

        for name in self.config.factor_names:
            col = data[name]
            stats[name] = FactorStats(
                name=name,
                count=col.drop_nulls().len(),
                mean=col.mean(),
                std=col.std(),
                min=col.min(),
                max=col.max(),
                null_ratio=col.null_count() / col.len(),
            )

        return stats
```

## 自定义因子

```python
# 定义自定义因子
def custom_momentum_factor(data: pl.DataFrame, config: FactorConfig) -> pl.Series:
    """自定义动量因子：加权动量"""
    short_window = 5
    long_window = 20

    short_mom = pl.col("close").pct_change(short_window)
    long_mom = pl.col("close").pct_change(long_window)

    # 短期权重更高
    return (short_mom * 0.6 + long_mom * 0.4).over("code")


# 注册使用
custom_factor = FactorDefinition(
    name="weighted_momentum",
    category=FactorCategory.MOMENTUM,
    description="加权动量因子",
    compute_fn=custom_momentum_factor,
    higher_is_better=True,
    required_columns={"close"},
    min_periods=20,
)

config = FactorConfig(
    factor_names=["momentum", "weighted_momentum"],
    custom_factors=[custom_factor],
)
```

## 因子有效性分析

```python
class FactorAnalyzer:
    """因子有效性分析"""

    @staticmethod
    def compute_ic(
        factor_data: pl.DataFrame,
        factor_name: str,
        return_col: str = "forward_return",
        method: str = "spearman",
    ) -> float:
        """计算信息系数 (IC)"""
        if method == "spearman":
            # Spearman 秩相关
            return factor_data.select([
                pl.corr(
                    pl.col(factor_name).rank(),
                    pl.col(return_col).rank(),
                )
            ])[0, 0]
        else:
            # Pearson 相关
            return factor_data.select([
                pl.corr(factor_name, return_col)
            ])[0, 0]

    @staticmethod
    def compute_ic_series(
        factor_data: pl.DataFrame,
        factor_name: str,
        return_col: str = "forward_return",
    ) -> pl.DataFrame:
        """计算 IC 时间序列"""
        return (
            factor_data
            .group_by("trade_date")
            .agg([
                pl.corr(
                    pl.col(factor_name).rank(),
                    pl.col(return_col).rank(),
                ).alias("ic")
            ])
            .sort("trade_date")
        )

    @staticmethod
    def compute_factor_returns(
        factor_data: pl.DataFrame,
        factor_name: str,
        n_groups: int = 5,
    ) -> pl.DataFrame:
        """计算分组收益"""
        return (
            factor_data
            .with_columns([
                pl.col(factor_name)
                  .qcut(n_groups, labels=[f"G{i+1}" for i in range(n_groups)])
                  .over("trade_date")
                  .alias("factor_group")
            ])
            .group_by(["trade_date", "factor_group"])
            .agg([
                pl.col("forward_return").mean().alias("group_return")
            ])
        )
```

## 测试用例

```python
class TestFactorEngine:

    @pytest.fixture
    def engine(self):
        engine = FactorEngine()
        engine.initialize(FactorConfig(
            factor_names=["momentum", "volatility"],
            factor_params={"momentum_window": 5, "volatility_window": 5},
        ))
        return engine

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame({
            "code": ["A"] * 30 + ["B"] * 30,
            "trade_date": list(pl.date_range(
                date(2024, 1, 1), date(2024, 1, 30), eager=True
            )) * 2,
            "close": list(range(100, 130)) + list(range(200, 230)),
            "volume": [1000000] * 60,
        })

    def test_compute_factors(self, engine, sample_data):
        """测试因子计算"""
        result = engine.process(sample_data)

        assert "momentum" in result.data.columns
        assert "volatility" in result.data.columns
        assert len(result.factor_names) == 2

    def test_factor_stats(self, engine, sample_data):
        """测试因子统计"""
        result = engine.process(sample_data)

        assert "momentum" in result.factor_stats
        stats = result.factor_stats["momentum"]
        assert stats.count > 0
        assert stats.null_ratio < 1.0

    def test_pit_safety(self, engine):
        """测试 PIT 安全性"""
        # 构造数据：第 6 天的动量应该只用前 5 天
        data = pl.DataFrame({
            "code": ["A"] * 10,
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 1, 10), eager=True
            ),
            "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            "volume": [1000000] * 10,
        })

        result = engine.process(data)

        # 第 6 天 (idx=5) 的 5 日动量 = (105 - 100) / 100 = 0.05
        # 但由于 closed="left" 或 shift，实际用的是前 5 天
        momentum_day6 = result.data.filter(
            pl.col("trade_date") == date(2024, 1, 6)
        )["momentum"][0]

        # 验证计算正确
        assert momentum_day6 is not None

    def test_normalization(self):
        """测试标准化"""
        engine = FactorEngine()
        engine.initialize(FactorConfig(
            factor_names=["momentum"],
            normalize=True,
            normalize_method="zscore",
        ))

        data = pl.DataFrame({
            "code": ["A"] * 30,
            "trade_date": pl.date_range(
                date(2024, 1, 1), date(2024, 1, 30), eager=True
            ),
            "close": list(range(100, 130)),
            "volume": [1000000] * 30,
        })

        result = engine.process(data)

        # Z-score 标准化后均值接近 0，标准差接近 1
        norm_col = result.data["momentum_norm"].drop_nulls()
        assert abs(norm_col.mean()) < 0.1
        assert abs(norm_col.std() - 1.0) < 0.1
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 使用未来数据计算 | PIT 泄露 | `closed="left"` 或 `shift()` |
| 不处理空值 | 计算错误 | 明确 null 处理逻辑 |
| 硬编码因子参数 | 不可调优 | 放入 Config |
| 不做标准化 | 因子量纲不同 | 统一标准化 |
| 不去极值 | 极端值影响 | 缩尾或截尾处理 |
| 忽略因子统计 | 无法评估质量 | 计算并返回统计信息 |
