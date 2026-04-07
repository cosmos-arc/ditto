# Ditto 引擎设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-08**

---

## 1. 设计目标与范围

本引擎设计文档用于回答：

> "Regime / 因子 / 行业轮动 / 回测 / 风控这些核心逻辑是如何被抽象、实现、调度的？"

### 1.1 核心设计原则

1. **引擎与数据分离**：所有引擎依赖 DataService，不直接访问数据库
2. **PIT 安全**：所有计算只使用 `knowledge_date <= trade_date` 的数据
3. **涨跌停感知**：回测引擎必须过滤涨跌停无法成交的情况
4. **向量化优先**：研究阶段使用 Polars 向量化计算，提高效率
5. **对齐严格**：Fast 与 Production 引擎对齐误差 ≤ 0.1%

### 1.2 本版本覆盖引擎

- **RegimeEngine**：市场状态识别 + **自适应阈值** + **确认期机制**
- **FactorEngine**：RS / Value / Vol / Crowding 因子 + **健康度监控**
- **RotationEngine**：多因子加权打分与 TopN 选择
- **Backtest Engines**：Fast（向量化）+ Production（事件驱动）+ **涨跌停过滤**
- **RiskEngine & KillSwitch**：回撤驱动的三层限控 + **回撤速度检测**

---

## 2. Regime 识别引擎设计

### 2.1 目标

- 将市场状态分为三类：`'bull'` / `'osc'` / `'bear'`
- 使用**自适应阈值**（基于历史分位数），而非硬编码
- 引入**确认期机制**，避免频繁切换

### 2.2 核心接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
import polars as pl

@dataclass
class RegimeResult:
    """Regime 计算结果"""
    trade_date: date
    regime_type: str          # 'bull' / 'osc' / 'bear'
    regime_score: float       # 0-1 综合得分
    trend_score: float
    momentum_score: float
    volatility_score: float
    width_score: float
    bull_threshold: float     # 自适应牛市阈值
    bear_threshold: float     # 自适应熊市阈值
    is_confirmed: bool        # 是否经过确认期

class RegimeEngine:
    """Regime 识别引擎"""

    # 维度权重
    TREND_WEIGHT = 0.4
    MOMENTUM_WEIGHT = 0.3
    VOLATILITY_WEIGHT = 0.2
    WIDTH_WEIGHT = 0.1

    # 自适应阈值参数
    LOOKBACK_DAYS = 500       # 历史回看窗口
    BULL_QUANTILE = 0.7       # 牛市阈值分位数
    BEAR_QUANTILE = 0.3       # 熊市阈值分位数

    # 确认期参数
    CONFIRM_DAYS = 3          # 连续 N 天才确认切换

    def __init__(self, data_service: "DataService"):
        self.data = data_service

    def calc_regime_for_range(
        self,
        start_date: date,
        end_date: date,
        index_code: str = "000300.SH"
    ) -> pl.DataFrame:
        """计算一段时间内的 Regime"""
        # 1. 获取指数数据
        df = self.data.get_index_kline(index_code, start_date, end_date)

        # 2. 计算各维度得分
        df = self._calc_trend_score(df)
        df = self._calc_momentum_score(df)
        df = self._calc_volatility_score(df)
        df = self._calc_width_score(df)

        # 3. 综合得分
        df = self._calc_regime_score(df)

        # 4. 自适应阈值分类
        df = self._classify_with_adaptive_threshold(df)

        # 5. 应用确认期
        df = self._apply_confirmation(df)

        return df

    def _calc_trend_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """趋势得分：基于 MA 排列 + 斜率 + 相对位置"""
        df = df.with_columns([
            pl.col("close").rolling_mean(20).alias("ma20"),
            pl.col("close").rolling_mean(60).alias("ma60"),
            pl.col("close").rolling_mean(120).alias("ma120"),
            pl.col("close").rolling_max(252).alias("high_52w"),
            pl.col("close").rolling_min(252).alias("low_52w"),
        ])

        # MA 排列得分（0-1）
        df = df.with_columns([
            pl.when(pl.col("ma20") > pl.col("ma60")).then(1).otherwise(0).alias("ma_align_1"),
            pl.when(pl.col("ma60") > pl.col("ma120")).then(1).otherwise(0).alias("ma_align_2"),
            pl.when(pl.col("close") > pl.col("ma20")).then(1).otherwise(0).alias("ma_align_3"),
        ])
        df = df.with_columns(
            ((pl.col("ma_align_1") + pl.col("ma_align_2") + pl.col("ma_align_3")) / 3)
            .alias("ma_score")
        )

        # MA20 斜率
        df = df.with_columns(
            ((pl.col("ma20") / pl.col("ma20").shift(5) - 1) * 4)
            .clip(-1, 1)
            .alias("slope_score")
        )

        # 相对位置
        df = df.with_columns(
            ((pl.col("close") - pl.col("low_52w")) /
             (pl.col("high_52w") - pl.col("low_52w") + 1e-10))
            .alias("position_score")
        )

        # 综合趋势得分
        df = df.with_columns(
            (0.4 * pl.col("ma_score") +
             0.3 * (pl.col("slope_score") + 1) / 2 +  # 归一化到 0-1
             0.3 * pl.col("position_score"))
            .alias("trend_score")
        )

        return df

    def _calc_momentum_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """动量得分：基于 20/60 日收益率"""
        df = df.with_columns([
            (pl.col("close") / pl.col("close").shift(20) - 1).alias("ret_20d"),
            (pl.col("close") / pl.col("close").shift(60) - 1).alias("ret_60d"),
        ])

        # 归一化到 [0, 1]
        df = df.with_columns([
            ((pl.col("ret_20d").clip(-0.2, 0.2) + 0.2) / 0.4).alias("ret_20d_norm"),
            ((pl.col("ret_60d").clip(-0.3, 0.3) + 0.3) / 0.6).alias("ret_60d_norm"),
        ])

        df = df.with_columns(
            (0.6 * pl.col("ret_20d_norm") + 0.4 * pl.col("ret_60d_norm"))
            .alias("momentum_score")
        )

        return df

    def _calc_volatility_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """波动得分：波动率越低得分越高"""
        df = df.with_columns(
            pl.col("close").pct_change().rolling_std(20).alias("vol_20d")
        )

        # 年化波动率
        df = df.with_columns(
            (pl.col("vol_20d") * (252 ** 0.5)).alias("annual_vol")
        )

        # 归一化：10% → 1.0，30% → 0.0
        df = df.with_columns(
            (1 - (pl.col("annual_vol") - 0.1).clip(0, 0.2) / 0.2)
            .alias("volatility_score")
        )

        return df

    def _calc_width_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """宽度得分：Phase 0-1 简化为常数"""
        # TODO: Phase 2 引入成分股涨跌统计
        df = df.with_columns(pl.lit(0.5).alias("width_score"))
        return df

    def _calc_regime_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """计算综合 Regime Score"""
        df = df.with_columns(
            (self.TREND_WEIGHT * pl.col("trend_score") +
             self.MOMENTUM_WEIGHT * pl.col("momentum_score") +
             self.VOLATILITY_WEIGHT * pl.col("volatility_score") +
             self.WIDTH_WEIGHT * pl.col("width_score"))
            .alias("regime_score")
        )
        return df

    def _classify_with_adaptive_threshold(self, df: pl.DataFrame) -> pl.DataFrame:
        """使用自适应阈值分类（基于历史分位数）"""
        df = df.with_columns([
            pl.col("regime_score")
              .rolling_quantile(self.BULL_QUANTILE, window_size=self.LOOKBACK_DAYS)
              .alias("bull_threshold"),
            pl.col("regime_score")
              .rolling_quantile(self.BEAR_QUANTILE, window_size=self.LOOKBACK_DAYS)
              .alias("bear_threshold"),
        ])

        df = df.with_columns(
            pl.when(pl.col("regime_score") >= pl.col("bull_threshold"))
              .then(pl.lit("bull"))
            .when(pl.col("regime_score") <= pl.col("bear_threshold"))
              .then(pl.lit("bear"))
            .otherwise(pl.lit("osc"))
            .alias("raw_regime")
        )

        return df

    def _apply_confirmation(self, df: pl.DataFrame) -> pl.DataFrame:
        """应用确认期：连续 N 天相同 Regime 才确认切换"""
        # 计算连续相同 Regime 的天数
        df = df.with_columns([
            (pl.col("raw_regime") != pl.col("raw_regime").shift(1))
            .cum_sum()
            .alias("regime_group")
        ])

        df = df.with_columns([
            pl.col("raw_regime")
              .over("regime_group")
              .count()
              .alias("regime_duration")
        ])

        # 只有连续 N 天才确认
        df = df.with_columns([
            pl.when(pl.col("regime_duration") >= self.CONFIRM_DAYS)
              .then(pl.col("raw_regime"))
              .otherwise(pl.col("raw_regime").shift(self.CONFIRM_DAYS).fill_null("osc"))
              .alias("regime_type"),
            (pl.col("regime_duration") >= self.CONFIRM_DAYS).alias("is_confirmed")
        ])

        return df
```

### 2.3 极端行情检测层

```python
class ExtremeMarketDetector:
    """极端行情检测器 - 优先于 Regime 判断"""

    @staticmethod
    def detect(df: pl.DataFrame) -> str | None:
        """检测极端行情

        Returns:
            'CRASH_MODE' / 'CRISIS_MODE' / 'VOL_SPIKE_MODE' / None
        """
        daily_return = df["close"].pct_change().tail(1).item()
        ret_3d = df["close"].pct_change(3).tail(1).item()

        # 单日跌幅超过 5%
        if daily_return < -0.05:
            return "CRASH_MODE"

        # 3日累计跌幅超过 10%
        if ret_3d < -0.10:
            return "CRISIS_MODE"

        # 波动率突然放大 3 倍
        recent_vol = df["close"].pct_change().tail(5).std() * (252 ** 0.5)
        historical_vol = df["close"].pct_change().tail(60).std() * (252 ** 0.5)
        if recent_vol > historical_vol * 3:
            return "VOL_SPIKE_MODE"

        return None
```

### 2.4 Regime 驱动的仓位约束

```python
@dataclass
class PositionLimits:
    """Regime 驱动的仓位约束"""
    regime: str
    total_equity_min: float
    total_equity_max: float
    single_etf_max: float
    target_volatility: float

    @classmethod
    def from_regime(cls, regime: str) -> "PositionLimits":
        limits = {
            "bull": cls(
                regime="bull",
                total_equity_min=0.70,
                total_equity_max=0.90,
                single_etf_max=0.15,
                target_volatility=0.15
            ),
            "osc": cls(
                regime="osc",
                total_equity_min=0.50,
                total_equity_max=0.70,
                single_etf_max=0.12,
                target_volatility=0.12
            ),
            "bear": cls(
                regime="bear",
                total_equity_min=0.10,
                total_equity_max=0.40,
                single_etf_max=0.10,
                target_volatility=0.10
            )
        }
        return limits[regime]

    @classmethod
    def from_extreme_mode(cls, mode: str) -> "PositionLimits":
        """极端行情的仓位约束"""
        return cls(
            regime=mode,
            total_equity_min=0.0,
            total_equity_max=0.20,
            single_etf_max=0.05,
            target_volatility=0.05
        )
```

---

## 3. 因子引擎设计

Polars原生实现核心TA指标

``` python
class TechnicalIndicators:
    """技术指标库（Polars原生）

    实现指标：
    - SMA, EMA: 移动平均
    - RSI: 相对强弱
    - MACD: 平滑异同
    - Bollinger Bands: 布林带
    - ATR: 真实波幅

    性能：比Pandas-TA快18倍
    """

    @staticmethod
    def sma(df: pl.DataFrame, column: str = 'close', period: int = 20):
        return df.with_columns([
            pl.col(column).rolling_mean(window_size=period).over('symbol').alias(f'sma_{period}')
        ])

    @staticmethod
    def ema(df: pl.DataFrame, column: str = 'close', period: int = 20):
        return df.with_columns([
            pl.col(column).ewm_mean(span=period).over('symbol').alias(f'ema_{period}')
        ])

    @staticmethod
    def rsi(df: pl.DataFrame, column: str = 'close', period: int = 14):
        # Polars原生实现，详见技术栈文档
        pass

    @staticmethod
    def macd(df: pl.DataFrame, column: str = 'close', fast: int = 12, slow: int = 26, signal: int = 9):
        # Polars原生实现
        pass

    @staticmethod
    def bollinger_bands(df: pl.DataFrame, column: str = 'close', period: int = 20, std_dev: float = 2.0):
        # Polars原生实现
        pass
```
### 3.1 因子接口抽象

```python
from abc import ABC, abstractmethod

@dataclass
class ExecutionContext:
    """执行上下文"""
    current_date: date
    as_of_date: date         # PIT: 数据可知日期
    data: "DataService"
    universe: list[str]

class Factor(ABC):
    """因子抽象基类"""

    name: str
    category: str            # 'momentum' / 'value' / 'volatility' / 'crowding'

    @abstractmethod
    def to_polars_expr(self) -> pl.Expr:
        """返回 Polars 表达式（用于向量化计算）"""
        pass

    @abstractmethod
    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        """计算因子值"""
        pass

    def calc_z_score(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """计算横截面 Z-Score"""
        return df.with_columns([
            ((pl.col(col) - pl.col(col).mean()) / pl.col(col).std())
            .alias(f"{col}_zscore")
        ])
```

### 3.2 核心因子实现

#### 3.2.1 相对强弱动量因子（RS）

```python
class RSFactor(Factor):
    """相对强弱动量因子"""

    name = "rs"
    category = "momentum"

    def __init__(self, window: int = 20, benchmark: str = "000300.SH"):
        self.window = window
        self.benchmark = benchmark

    def to_polars_expr(self) -> pl.Expr:
        return (
            pl.col("close") / pl.col("close").shift(self.window) - 1
        ).alias(f"rs_{self.window}d")

    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        """计算相对强弱：ETF 收益 - 基准收益"""
        # 获取 ETF 数据
        etf_df = ctx.data.get_kline_batch(
            ctx.universe,
            ctx.current_date - timedelta(days=self.window * 2),
            ctx.current_date
        )

        # 计算 ETF 收益率
        etf_returns = etf_df.group_by("symbol").agg([
            (pl.col("close").last() / pl.col("close").first() - 1).alias("etf_return")
        ])

        # 获取基准收益率
        benchmark_df = ctx.data.get_index_kline(
            self.benchmark,
            ctx.current_date - timedelta(days=self.window * 2),
            ctx.current_date
        )
        benchmark_return = (
            benchmark_df["close"].last() / benchmark_df["close"].first() - 1
        )

        # 相对强弱 = ETF 收益 - 基准收益
        result = etf_returns.with_columns([
            (pl.col("etf_return") - benchmark_return).alias(f"rs_{self.window}d"),
            pl.lit(ctx.current_date).alias("trade_date"),
            pl.lit(ctx.as_of_date).alias("knowledge_date"),
        ])

        # Z-Score
        result = self.calc_z_score(result, f"rs_{self.window}d")

        return result
```

#### 3.2.2 波动率因子（Vol）

```python
class VolatilityFactor(Factor):
    """波动率因子（低波动得分高）"""

    name = "vol"
    category = "volatility"

    def __init__(self, window: int = 20):
        self.window = window

    def to_polars_expr(self) -> pl.Expr:
        return (
            pl.col("close").pct_change().rolling_std(self.window) * (252 ** 0.5)
        ).alias(f"vol_{self.window}d")

    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        etf_df = ctx.data.get_kline_batch(
            ctx.universe,
            ctx.current_date - timedelta(days=self.window * 2),
            ctx.current_date
        )

        result = etf_df.group_by("symbol").agg([
            (pl.col("close").pct_change().std() * (252 ** 0.5)).alias(f"vol_{self.window}d")
        ]).with_columns([
            pl.lit(ctx.current_date).alias("trade_date"),
            pl.lit(ctx.as_of_date).alias("knowledge_date"),
        ])

        # 波动率取负（低波动得分高）
        result = result.with_columns([
            (-pl.col(f"vol_{self.window}d")).alias(f"vol_{self.window}d_neg")
        ])
        result = self.calc_z_score(result, f"vol_{self.window}d_neg")

        return result
```

#### 3.2.3 估值因子（Value）

```python
class ValueFactor(Factor):
    """估值因子"""

    name = "value"
    category = "value"

    def __init__(self, metric: str = "pe", lookback: int = 252):
        self.metric = metric
        self.lookback = lookback

    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        """计算估值分位数"""
        # 获取当前估值
        current_valuation = ctx.data.get_etf_valuation(
            ctx.universe,
            ctx.current_date,
            as_of_date=ctx.as_of_date  # PIT 安全
        )

        # 获取历史估值分布
        historical = ctx.data.get_etf_valuation_history(
            ctx.universe,
            ctx.current_date - timedelta(days=self.lookback),
            ctx.current_date
        )

        # 计算分位数（低估值得分高）
        result = current_valuation.join(
            historical.group_by("symbol").agg([
                pl.col(self.metric).quantile(0.25).alias("q25"),
                pl.col(self.metric).quantile(0.75).alias("q75"),
            ]),
            on="symbol"
        ).with_columns([
            # 分位数得分：越低越好
            ((pl.col("q75") - pl.col(self.metric)) /
             (pl.col("q75") - pl.col("q25") + 1e-10))
            .alias(f"value_{self.metric}"),
            pl.lit(ctx.current_date).alias("trade_date"),
            pl.lit(ctx.as_of_date).alias("knowledge_date"),
        ])

        result = self.calc_z_score(result, f"value_{self.metric}")

        return result
```

#### 3.2.4 拥挤度因子（Crowding）

```python
class CrowdingFactor(Factor):
    """拥挤度因子（低拥挤得分高）"""

    name = "crowding"
    category = "crowding"

    def __init__(self, volume_lookback: int = 60):
        self.volume_lookback = volume_lookback

    def calc(self, ctx: ExecutionContext) -> pl.DataFrame:
        etf_df = ctx.data.get_kline_batch(
            ctx.universe,
            ctx.current_date - timedelta(days=self.volume_lookback * 2),
            ctx.current_date
        )

        # 成交额放大倍数
        result = etf_df.group_by("symbol").agg([
            (pl.col("amount").last() / pl.col("amount").mean()).alias("volume_ratio")
        ]).with_columns([
            # 拥挤度取负（低拥挤得分高）
            (-pl.col("volume_ratio")).alias("crowding_neg"),
            pl.lit(ctx.current_date).alias("trade_date"),
            pl.lit(ctx.as_of_date).alias("knowledge_date"),
        ])

        result = self.calc_z_score(result, "crowding_neg")

        return result
```

### 3.3 因子分析

```python
from dataclasses import dataclass
import polars as pl

@dataclass
class FactorAnalysisResult:
    """因子分析结果"""
    factor_name: str
    mean_ic: float              # 平均IC
    ic_ir: float                # IC信息比率
    ic_decay: Dict[int, float]  # IC衰减 {1: 1.0, 5: 0.8, 10: 0.6, 20: 0.5}
    quantile_returns: Dict[int, float]  # 分位数收益 {1: -0.002, ..., 5: 0.008}
    long_short_return: float    # Q5 - Q1收益
    avg_turnover: float         # 平均换手率
    health_score: float         # 健康度评分 [0, 1]

class FactorAnalyzer:
    """因子分析器（Polars原生实现）

    核心功能：
    1. IC分析（信息系数）
    2. IC衰减分析
    3. 分位数收益分析
    4. 换手率分析
    5. 因子健康度评分
    """

    def analyze(
        self,
        factor_data: pl.DataFrame,
        price_data: pl.DataFrame,
        periods: List[int] = [1, 5, 10, 20]
    ) -> FactorAnalysisResult:
        """分析因子

        Args:
            factor_data: 因子值 [date, symbol, factor_value]
            price_data: 价格数据 [date, symbol, close]
            periods: 前瞻收益周期
        """

        # 1. 计算前瞻收益（Polars向量化）
        forward_returns = self._calc_forward_returns(price_data, periods)

        # 2. 合并因子与收益
        merged = factor_data.join(forward_returns, on=['date', 'symbol'])

        # 3. 计算IC（Polars group_by + corr）
        ic_by_period = self._calc_ic(merged, periods)
        mean_ic = ic_by_period[1]
        ic_ir = self._calc_ic_ir(merged, periods[0])

        # 4. IC衰减
        ic_decay = {p: ic_by_period[p] / ic_by_period[1]
                    for p in periods if ic_by_period[1] != 0}

        # 5. 分位数收益（Polars qcut + group_by）
        quantile_returns, long_short = self._calc_quantile_returns(merged, periods[0])

        # 6. 换手率（Polars rank + shift + corr）
        avg_turnover = self._calc_turnover(merged)

        # 7. 健康度评分
        health_score = self._calc_health_score(
            mean_ic, ic_decay, avg_turnover, long_short
        )

        return FactorAnalysisResult(
            factor_name=factor_data.columns[2],
            mean_ic=mean_ic,
            ic_ir=ic_ir,
            ic_decay=ic_decay,
            quantile_returns=quantile_returns,
            long_short_return=long_short,
            avg_turnover=avg_turnover,
            health_score=health_score
        )
```

**健康度评分规则**：
- IC > 0.05: +0.3分
- IC衰减慢（20日/1日 > 0.5）: +0.2分
- 换手率适中（0.2-0.4）: +0.2分
- 多空收益 > 0.05: +0.3分

---

## 4. 策略引擎设计

### 4.1 层次架构

```
┌─────────────────────────────────────────────────────────┐
│                    Portfolio Layer                      │
│  - 管理多个策略实例                                     │
│  - 资金分配（风险预算）                                 │
│  - 信号聚合与冲突处理                                   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                    Strategy Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Rotation    │  │  Defensive   │  │  Momentum    │  │
│  │  Strategy    │  │  Strategy    │  │  Strategy    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Signal Generation                      │
│  - StrategyContext (提供数据访问)                       │
│  - SignalSet (标准信号格式)                             │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Engine Layer (复用现有)                    │
│  - RegimeEngine / FactorEngine / RotationEngine          │
└─────────────────────────────────────────────────────────┘
```

---

### 4.2 详细接口设计

#### 4.2.1 核心抽象

```python
"""
新增文件：packages/engine/src/ditto_engine/alpha/base.py
替换：原有的简单策略抽象
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List
from enum import Enum
import polars as pl


class SignalType(Enum):
    """信号类型"""
    LONG = "long"           # 做多
    SHORT = "short"         # 做空（期货/期权用）
    CLOSE = "close"         # 平仓
    ADJUST = "adjust"       # 调整


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    target_weight: float        # 目标权重（占策略资金）
    confidence: float           # 信号置信度 [0, 1]
    reason: str                 # 信号原因（可解释性）
    metadata: dict              # 附加信息（因子值、得分等）

    def __post_init__(self):
        assert 0 <= self.target_weight <= 1, "Weight must be in [0, 1]"
        assert 0 <= self.confidence <= 1, "Confidence must be in [0, 1]"


@dataclass
class SignalSet:
    """信号集合"""
    trade_date: date
    strategy_id: str
    signals: List[Signal]
    total_weight: float         # 总权重（可以<1，表示部分持仓）

    def validate(self) -> bool:
        """验证信号集合的有效性"""
        total = sum(s.target_weight for s in self.signals)
        return abs(total - self.total_weight) < 1e-6

    def filter_by_confidence(self, min_confidence: float) -> 'SignalSet':
        """按置信度过滤"""
        filtered = [s for s in self.signals if s.confidence >= min_confidence]
        return SignalSet(
            trade_date=self.trade_date,
            strategy_id=self.strategy_id,
            signals=filtered,
            total_weight=sum(s.target_weight for s in filtered)
        )


@dataclass
class StrategyContext:
    """策略执行上下文

    提供策略运行所需的所有数据访问接口，隔离策略与数据层
    """
    trade_date: date
    universe: List[str]
    data_service: 'DataService'

    # 缓存的公共数据（避免重复查询）
    _regime_cache: Optional['RegimeResult'] = None
    _factors_cache: Optional[pl.DataFrame] = None

    def get_regime(self, index_code: str = "000300.SH") -> 'RegimeResult':
        """获取Regime（带缓存）"""
        if self._regime_cache is None:
            from ditto.engine.regime_engine import RegimeEngine
            engine = RegimeEngine(self.data_service)
            self._regime_cache = engine.calc_regime(self.trade_date, index_code)
        return self._regime_cache

    def get_factors(self, symbols: Optional[List[str]] = None) -> pl.DataFrame:
        """获取因子数据（带缓存）"""
        if symbols is None:
            symbols = self.universe

        if self._factors_cache is None:
            self._factors_cache = self.data_service.get_factors_pit(
                symbols=symbols,
                trade_date=self.trade_date,
                as_of_date=self.trade_date
            )
        return self._factors_cache.filter(pl.col("symbol").is_in(symbols))

    def get_prices(
        self,
        symbols: Optional[List[str]] = None,
        lookback_days: int = 60
    ) -> pl.DataFrame:
        """获取价格数据"""
        if symbols is None:
            symbols = self.universe

        start_date = self.trade_date - timedelta(days=lookback_days)
        return self.data_service.get_kline(
            symbols=symbols,
            start_date=start_date,
            end_date=self.trade_date
        )


class Strategy(ABC):
    """策略基类

    这是核心抽象，所有策略必须实现这个接口
    """

    def __init__(
        self,
        strategy_id: str,
        name: str,
        config: Dict
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.config = config

        # 策略元数据
        self.requires_regime = False    # 是否依赖Regime
        self.requires_factors = False   # 是否依赖因子
        self.min_universe_size = 5      # 最小Universe大小
        self.max_positions = 10         # 最大持仓数

    @abstractmethod
    def generate_signals(self, ctx: StrategyContext) -> SignalSet:
        """生成交易信号

        这是策略的核心逻辑，必须实现

        Args:
            ctx: 策略执行上下文，提供数据访问

        Returns:
            SignalSet: 包含所有交易信号的集合
        """
        pass

    @abstractmethod
    def validate_prerequisites(self, ctx: StrategyContext) -> bool:
        """验证策略运行的前置条件

        例如：
        - Universe大小是否足够
        - 必要数据是否可用
        - Regime是否符合运行条件
        """
        pass

    def get_default_config(self) -> Dict:
        """获取默认配置"""
        return {}

    def get_position_limits(self, regime: Optional[str] = None) -> Dict[str, float]:
        """获取仓位限制

        Returns:
            {'total_weight': 0.8, 'single_position': 0.15}
        """
        return {
            'total_weight': 1.0,
            'single_position': 0.2
        }


class RegimeAwareStrategy(Strategy):
    """感知Regime的策略基类

    为依赖Regime的策略提供便捷方法
    """

    def __init__(self, strategy_id: str, name: str, config: Dict):
        super().__init__(strategy_id, name, config)
        self.requires_regime = True

        # Regime相关配置
        self.regime_position_limits = {
            'bull': {'total': 0.9, 'single': 0.15},
            'osc':  {'total': 0.7, 'single': 0.12},
            'bear': {'total': 0.4, 'single': 0.10}
        }

    def get_position_limits(self, regime: Optional[str] = None) -> Dict[str, float]:
        """根据Regime调整仓位限制"""
        if regime and regime in self.regime_position_limits:
            limits = self.regime_position_limits[regime]
            return {'total_weight': limits['total'], 'single_position': limits['single']}
        return super().get_position_limits(regime)

    def should_run(self, regime: str) -> bool:
        """是否应该在当前Regime下运行"""
        return True  # 默认在所有Regime下运行


class FactorBasedStrategy(Strategy):
    """基于因子的策略基类"""

    def __init__(self, strategy_id: str, name: str, config: Dict):
        super().__init__(strategy_id, name, config)
        self.requires_factors = True

        # 因子权重（可动态调整）
        self.factor_weights = config.get('factor_weights', {})

    def calc_composite_score(
        self,
        factors: pl.DataFrame,
        weights: Optional[Dict[str, float]] = None
    ) -> pl.DataFrame:
        """计算综合得分

        Args:
            factors: 因子数据，每列是一个因子
            weights: 因子权重，如不提供则使用默认权重
        """
        if weights is None:
            weights = self.factor_weights

        # Z-Score标准化
        for col in weights.keys():
            if col in factors.columns:
                factors = factors.with_columns(
                    ((pl.col(col) - pl.col(col).mean()) / pl.col(col).std())
                    .alias(f"{col}_z")
                )

        # 加权求和
        score_expr = sum(
            pl.col(f"{factor}_z") * weight
            for factor, weight in weights.items()
        )

        return factors.with_columns(score_expr.alias("composite_score"))
```

### 4.3 具体策略实现

#### 4.3.1 增强的行业轮动策略

```python
"""
文件：packages/engine/src/ditto_engine/alpha/rotation_strategy.py
修改：增强现有的轮动策略，使其继承新的基类
"""

from ditto.strategy.base import (
    RegimeAwareStrategy, FactorBasedStrategy, SignalSet, Signal, SignalType
)
from typing import Dict
import polars as pl


class ETFRotationStrategy(RegimeAwareStrategy, FactorBasedStrategy):
    """增强版ETF行业轮动策略

    特点：
    1. 支持动态因子权重（基于Regime）
    2. 支持因子健康度衰减
    3. 可配置TopN选择
    """

    def __init__(self, strategy_id: str = "rotation_v2", config: Dict = None):
        config = config or {}
        super().__init__(strategy_id, "ETF Rotation Enhanced", config)

        # 策略参数
        self.top_n = config.get('top_n', 10)
        self.rebalance_threshold = config.get('rebalance_threshold', 0.05)

        # 动态因子权重（基于Regime）
        self.regime_factor_weights = {
            'bull': {
                'rs_20d': 0.45,
                'momentum_60d': 0.30,
                'volatility': 0.15,
                'crowding': 0.10
            },
            'osc': {
                'rs_20d': 0.35,
                'value': 0.25,
                'volatility': 0.25,
                'crowding': 0.15
            },
            'bear': {
                'value': 0.40,
                'volatility': 0.35,
                'defensive': 0.25
            }
        }

        # 因子健康度阈值
        self.factor_health_threshold = config.get('factor_health_threshold', 0.5)

    def validate_prerequisites(self, ctx: StrategyContext) -> bool:
        """验证前置条件"""
        if len(ctx.universe) < self.min_universe_size:
            return False

        # 检查因子数据是否可用
        factors = ctx.get_factors()
        required_factors = set(self.get_required_factors(ctx))
        available_factors = set(factors.columns)

        return required_factors.issubset(available_factors)

    def get_required_factors(self, ctx: StrategyContext) -> list[str]:
        """获取当前Regime下需要的因子"""
        regime = ctx.get_regime()
        weights = self.regime_factor_weights.get(regime.regime_type, {})
        return list(weights.keys())

    def generate_signals(self, ctx: StrategyContext) -> SignalSet:
        """生成信号"""

        # 1. 获取Regime
        regime = ctx.get_regime()

        # 2. 获取因子权重（动态）
        factor_weights = self.get_adjusted_factor_weights(ctx, regime.regime_type)

        # 3. 获取因子数据
        factors = ctx.get_factors()

        # 4. 计算综合得分
        scored = self.calc_composite_score(factors, factor_weights)

        # 5. 过滤涨跌停
        scored = self._filter_limit_locked(scored, ctx)

        # 6. 选择TopN
        top_n = scored.sort("composite_score", descending=True).head(self.top_n)

        # 7. 计算权重（等权或优化权重）
        signals = self._generate_signals_from_scores(top_n, regime.regime_type)

        return SignalSet(
            trade_date=ctx.trade_date,
            strategy_id=self.strategy_id,
            signals=signals,
            total_weight=sum(s.target_weight for s in signals)
        )

    def get_adjusted_factor_weights(
        self,
        ctx: StrategyContext,
        regime: str
    ) -> Dict[str, float]:
        """获取调整后的因子权重

        考虑：
        1. Regime
        2. 因子健康度
        """
        base_weights = self.regime_factor_weights.get(regime, {})

        # 获取因子健康度
        factor_health = self._get_factor_health(ctx)

        # 根据健康度调整权重
        adjusted = {}
        for factor, weight in base_weights.items():
            health = factor_health.get(factor, 1.0)
            if health < self.factor_health_threshold:
                # 健康度低，降低权重
                adjusted[factor] = weight * health
            else:
                adjusted[factor] = weight

        # 重新归一化
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}

        return adjusted

    def _get_factor_health(self, ctx: StrategyContext) -> Dict[str, float]:
        """获取因子健康度

        TODO: 从FactorHealthService获取
        现在返回默认值
        """
        return {factor: 1.0 for factor in self.get_required_factors(ctx)}

    def _filter_limit_locked(
        self,
        scored: pl.DataFrame,
        ctx: StrategyContext
    ) -> pl.DataFrame:
        """过滤涨跌停标的"""
        # 获取当日涨跌停状态
        status = ctx.data_service.get_limit_status(ctx.trade_date)

        # 过滤涨停（不能买入）
        valid_symbols = status.filter(
            pl.col("status") != "LIMIT_UP"
        )["symbol"].to_list()

        return scored.filter(pl.col("symbol").is_in(valid_symbols))

    def _generate_signals_from_scores(
        self,
        top_n: pl.DataFrame,
        regime: str
    ) -> List[Signal]:
        """从得分生成信号"""
        # 获取仓位限制
        limits = self.get_position_limits(regime)
        total_weight = limits['total_weight']
        single_limit = limits['single_position']

        # 计算权重（可以改为优化权重）
        n = len(top_n)
        equal_weight = min(total_weight / n, single_limit)

        signals = []
        for row in top_n.iter_rows(named=True):
            signals.append(Signal(
                symbol=row['symbol'],
                signal_type=SignalType.LONG,
                target_weight=equal_weight,
                confidence=self._calc_confidence(row['composite_score']),
                reason=f"Top{n} by composite score ({row['composite_score']:.3f})",
                metadata={
                    'score': row['composite_score'],
                    'regime': regime
                }
            ))

        return signals

    def _calc_confidence(self, score: float) -> float:
        """计算信号置信度

        基于得分的归一化：score越高，置信度越高
        """
        # 简单映射：假设得分在[-3, 3]之间
        normalized = (score + 3) / 6
        return max(0.0, min(1.0, normalized))
```

#### 4.3.2 防御策略

```python
"""
新文件：packages/engine/src/ditto_engine/alpha/defensive_strategy.py
这是解决"策略单一"问题的关键
"""

from ditto.strategy.base import Strategy, SignalSet, Signal, SignalType
from typing import Dict, List


class DefensiveStrategy(Strategy):
    """防御策略

    目标：
    1. 在熊市或高波动期保护资金
    2. 提供稳定的底仓收益
    3. 与轮动策略互补

    特点：
    - 不依赖Regime（独立决策）
    - 配置固定的防御资产池
    - 基于波动率和回撤触发
    """

    def __init__(self, strategy_id: str = "defensive_v1", config: Dict = None):
        config = config or {}
        super().__init__(strategy_id, "Defensive Strategy", config)

        # 防御资产池
        self.defensive_assets = config.get('defensive_assets', {
            '510880.SH': 0.4,  # 红利ETF
            '511010.SH': 0.4,  # 国债ETF
            '518880.SH': 0.2   # 黄金ETF
        })

        # 触发条件
        self.activation_conditions = {
            'regime_bear': True,              # Regime为熊市
            'drawdown_threshold': 0.08,       # 回撤>8%
            'vol_spike_threshold': 2.0,       # 波动率>2倍正常水平
        }

        self.requires_regime = False  # 可选使用Regime

    def validate_prerequisites(self, ctx: StrategyContext) -> bool:
        """验证前置条件"""
        # 检查防御资产是否在Universe中
        available = set(ctx.universe)
        required = set(self.defensive_assets.keys())
        return required.issubset(available)

    def generate_signals(self, ctx: StrategyContext) -> SignalSet:
        """生成信号"""

        # 1. 判断是否应该激活防御
        should_activate = self._should_activate(ctx)

        if not should_activate:
            # 不激活，返回空信号
            return SignalSet(
                trade_date=ctx.trade_date,
                strategy_id=self.strategy_id,
                signals=[],
                total_weight=0.0
            )

        # 2. 生成防御信号
        signals = []
        for symbol, weight in self.defensive_assets.items():
            signals.append(Signal(
                symbol=symbol,
                signal_type=SignalType.LONG,
                target_weight=weight,
                confidence=0.9,  # 防御策略高置信度
                reason="Defensive allocation activated",
                metadata={'defensive': True}
            ))

        return SignalSet(
            trade_date=ctx.trade_date,
            strategy_id=self.strategy_id,
            signals=signals,
            total_weight=sum(s.target_weight for s in signals)
        )

    def _should_activate(self, ctx: StrategyContext) -> bool:
        """判断是否应激活防御"""

        # 条件1：Regime为熊市
        if self.activation_conditions['regime_bear']:
            regime = ctx.get_regime()
            if regime.regime_type == 'bear':
                return True

        # 条件2：回撤超过阈值
        current_drawdown = self._get_current_drawdown(ctx)
        if current_drawdown > self.activation_conditions['drawdown_threshold']:
            return True

        # 条件3：波动率飙升
        vol_ratio = self._get_volatility_ratio(ctx)
        if vol_ratio > self.activation_conditions['vol_spike_threshold']:
            return True

        return False

    def _get_current_drawdown(self, ctx: StrategyContext) -> float:
        """获取当前回撤

        TODO: 从RiskEngine或PortfolioService获取
        """
        # 临时实现
        return 0.0

    def _get_volatility_ratio(self, ctx: StrategyContext) -> float:
        """获取波动率比率（当前/正常）

        TODO: 计算当前波动率相对历史的比率
        """
        # 临时实现
        return 1.0


class MinimumDefensiveStrategy(DefensiveStrategy):
    """最小防御策略

    这是Phase 1可以快速实现的版本，逻辑极简
    """

    def __init__(self, config: Dict = None):
        config = config or {
            'defensive_assets': {
                '510880.SH': 0.5,  # 红利ETF 50%
                '511010.SH': 0.5   # 国债ETF 50%
            }
        }
        super().__init__("min_defensive", config)

    def _should_activate(self, ctx: StrategyContext) -> bool:
        """简化判断：只看Regime"""
        regime = ctx.get_regime()
        return regime.regime_type == 'bear'
```

#### 4.3.3 纯动量策略（示例）

```python
"""
新文件：packages/engine/src/ditto_engine/alpha/momentum_strategy.py
展示如何实现不依赖Regime的策略
"""

from ditto.strategy.base import Strategy, SignalSet, Signal, SignalType
import polars as pl


class MomentumStrategy(Strategy):
    """纯动量策略

    特点：
    - 完全不依赖Regime
    - 基于价格动量选股
    - 作为轮动策略的补充
    """

    def __init__(self, strategy_id: str = "momentum_v1", config: Dict = None):
        config = config or {}
        super().__init__(strategy_id, "Momentum Strategy", config)

        self.lookback_days = config.get('lookback_days', 60)
        self.top_n = config.get('top_n', 5)
        self.requires_regime = False
        self.requires_factors = False

    def validate_prerequisites(self, ctx: StrategyContext) -> bool:
        return len(ctx.universe) >= self.top_n

    def generate_signals(self, ctx: StrategyContext) -> SignalSet:
        """生成信号"""

        # 1. 获取价格数据
        prices = ctx.get_prices(lookback_days=self.lookback_days)

        # 2. 计算动量
        momentum = self._calc_momentum(prices)

        # 3. 选择TopN
        top_n = momentum.sort("momentum", descending=True).head(self.top_n)

        # 4. 生成信号
        signals = []
        equal_weight = 1.0 / self.top_n

        for row in top_n.iter_rows(named=True):
            signals.append(Signal(
                symbol=row['symbol'],
                signal_type=SignalType.LONG,
                target_weight=equal_weight,
                confidence=min(1.0, row['momentum'] / 0.5),  # 归一化
                reason=f"Momentum: {row['momentum']:.2%}",
                metadata={'momentum': row['momentum']}
            ))

        return SignalSet(
            trade_date=ctx.trade_date,
            strategy_id=self.strategy_id,
            signals=signals,
            total_weight=sum(s.target_weight for s in signals)
        )

    def _calc_momentum(self, prices: pl.DataFrame) -> pl.DataFrame:
        """计算动量

        动量 = (最新价 - N日前价) / N日前价
        """
        return (
            prices
            .group_by("symbol")
            .agg([
                pl.col("close").last().alias("latest_price"),
                pl.col("close").first().alias("start_price")
            ])
            .with_columns(
                ((pl.col("latest_price") / pl.col("start_price") - 1))
                .alias("momentum")
            )
            .select(["symbol", "momentum"])
        )
```

### 4.4 Portfolio管理层

```python
"""
文件：packages/engine/src/ditto_engine/portfolio/portfolio_manager.py
增强：原有的Portfolio概念，增加多策略协调
"""

from dataclasses import dataclass
from typing import Dict, List
from ditto.strategy.base import Strategy, SignalSet, Signal
import polars as pl


@dataclass
class StrategyAllocation:
    """策略资金分配"""
    strategy_id: str
    capital: float              # 分配资金
    weight: float               # 占组合权重
    risk_budget: float          # 风险预算（波动率）
    is_active: bool = True


class PortfolioManager:
    """组合管理器

    职责：
    1. 管理多个策略实例
    2. 协调资金分配
    3. 聚合和去冲突信号
    4. 风险预算控制
    """

    def __init__(
        self,
        portfolio_id: str,
        total_capital: float,
        strategies: List[Strategy],
        allocations: List[StrategyAllocation]
    ):
        self.portfolio_id = portfolio_id
        self.total_capital = total_capital
        self.strategies = {s.strategy_id: s for s in strategies}
        self.allocations = {a.strategy_id: a for a in allocations}

        # 验证
        assert set(self.strategies.keys()) == set(self.allocations.keys())

    def generate_portfolio_signals(
        self,
        ctx: 'StrategyContext'
    ) -> SignalSet:
        """生成组合级信号

        流程：
        1. 各策略独立生成信号
        2. 按资金分配调整权重
        3. 信号去冲突/聚合
        4. 风险预算检查
        """

        # 1. 收集各策略信号
        strategy_signals = {}
        for strategy_id, strategy in self.strategies.items():
            allocation = self.allocations[strategy_id]

            if not allocation.is_active:
                continue

            # 检查前置条件
            if not strategy.validate_prerequisites(ctx):
                continue

            # 生成信号
            signals = strategy.generate_signals(ctx)
            strategy_signals[strategy_id] = signals

        # 2. 按资金分配调整权重
        adjusted_signals = self._adjust_signal_weights(strategy_signals)

        # 3. 信号聚合（去冲突）
        aggregated = self._aggregate_signals(adjusted_signals)

        # 4. 风险预算检查
        final = self._apply_risk_budget(aggregated, ctx)

        return final

    def _adjust_signal_weights(
        self,
        strategy_signals: Dict[str, SignalSet]
    ) -> Dict[str, SignalSet]:
        """调整信号权重

        每个策略的信号权重 × 该策略的资金权重
        """
        adjusted = {}

        for strategy_id, signal_set in strategy_signals.items():
            allocation = self.allocations[strategy_id]
            strategy_weight = allocation.weight

            # 调整每个信号的权重
            adjusted_signals = []
            for signal in signal_set.signals:
                adjusted_signal = Signal(
                    symbol=signal.symbol,
                    signal_type=signal.signal_type,
                    target_weight=signal.target_weight * strategy_weight,
                    confidence=signal.confidence,
                    reason=f"[{strategy_id}] {signal.reason}",
                    metadata={**signal.metadata, 'strategy_id': strategy_id}
                )
                adjusted_signals.append(adjusted_signal)

            adjusted[strategy_id] = SignalSet(
                trade_date=signal_set.trade_date,
                strategy_id=strategy_id,
                signals=adjusted_signals,
                total_weight=signal_set.total_weight * strategy_weight
            )

        return adjusted

    def _aggregate_signals(
        self,
        strategy_signals: Dict[str, SignalSet]
    ) -> SignalSet:
        """聚合信号

        处理：
        1. 同一标的多个策略都推荐 → 合并权重
        2. 信号冲突（极少见）→ 按置信度权衡
        """
        if not strategy_signals:
            return SignalSet(
                trade_date=None,
                strategy_id=self.portfolio_id,
                signals=[],
                total_weight=0.0
            )

        # 所有信号flat化
        all_signals = []
        trade_date = None
        for signal_set in strategy_signals.values():
            if trade_date is None:
                trade_date = signal_set.trade_date
            all_signals.extend(signal_set.signals)

        # 按symbol聚合
        symbol_signals = {}
        for signal in all_signals:
            if signal.symbol not in symbol_signals:
                symbol_signals[signal.symbol] = []
            symbol_signals[signal.symbol].append(signal)

        # 合并同symbol的信号
        merged = []
        for symbol, signals in symbol_signals.items():
            if len(signals) == 1:
                merged.append(signals[0])
            else:
                # 多个策略推荐同一标的 → 合并
                merged.append(self._merge_signals(signals))

        return SignalSet(
            trade_date=trade_date,
            strategy_id=self.portfolio_id,
            signals=merged,
            total_weight=sum(s.target_weight for s in merged)
        )

    def _merge_signals(self, signals: List[Signal]) -> Signal:
        """合并多个信号

        规则：
        1. 权重相加
        2. 置信度取加权平均
        3. reason合并
        """
        total_weight = sum(s.target_weight for s in signals)

        # 加权平均置信度
        weighted_confidence = sum(
            s.confidence * s.target_weight for s in signals
        ) / total_weight

        # 合并原因
        reasons = [s.reason for s in signals]
        merged_reason = " | ".join(reasons)

        return Signal(
            symbol=signals[0].symbol,
            signal_type=signals[0].signal_type,
            target_weight=total_weight,
            confidence=weighted_confidence,
            reason=merged_reason,
            metadata={'merged_from': [s.metadata for s in signals]}
        )

    def _apply_risk_budget(
        self,
        signal_set: SignalSet,
        ctx: 'StrategyContext'
    ) -> SignalSet:
        """应用风险预算约束

        检查：
        1. 总仓位不超限
        2. 单票不超限
        3. 集中度不超限
        """
        # TODO: 实现风险预算检查
        # 当前简化：直接返回
        return signal_set

    def rebalance_allocations(
        self,
        performance: Dict[str, float],
        target_volatility: float = 0.15
    ) -> List[StrategyAllocation]:
        """再平衡策略分配

        基于：
        1. 各策略历史表现
        2. 目标波动率
        3. 风险平价

        TODO: Phase 2-3实现
        """
        pass
```

---

### 4.5 配置驱动

#### 4.5.1 策略配置文件

```yaml
# config/strategies.yaml
# 替换：硬编码的策略参数

portfolio:
  portfolio_id: "main_portfolio"
  total_capital: 1000000  # 100万

  strategies:
    - strategy_id: "rotation_v2"
      class: "ETFRotationStrategy"
      weight: 0.6  # 60%资金
      risk_budget: 0.12  # 12%年化波动
      active: true
      config:
        top_n: 10
        rebalance_threshold: 0.05
        factor_health_threshold: 0.5

    - strategy_id: "defensive_v1"
      class: "DefensiveStrategy"
      weight: 0.3  # 30%资金
      risk_budget: 0.06  # 6%年化波动
      active: true
      config:
        defensive_assets:
          "510880.SH": 0.5
          "511010.SH": 0.5

    - strategy_id: "momentum_v1"
      class: "MomentumStrategy"
      weight: 0.1  # 10%资金
      risk_budget: 0.08
      active: false  # Phase 1暂不启用
      config:
        lookback_days: 60
        top_n: 5

  # 全局风险约束
  risk_constraints:
    max_total_position: 0.95
    max_single_position: 0.15
    max_sector_concentration: 0.40
```

#### 4.5.2 配置加载器

```python
"""
文件：packages/engine/src/ditto_engine/config/strategy_config.py
"""

import yaml
from typing import Dict, List
from ditto.strategy.base import Strategy
from ditto.portfolio.portfolio_manager import StrategyAllocation, PortfolioManager


class StrategyConfigLoader:
    """策略配置加载器"""

    # 策略类注册表
    STRATEGY_REGISTRY = {
        'ETFRotationStrategy': 'ditto.strategy.rotation_strategy.ETFRotationStrategy',
        'DefensiveStrategy': 'ditto.strategy.defensive_strategy.DefensiveStrategy',
        'MomentumStrategy': 'ditto.strategy.momentum_strategy.MomentumStrategy',
    }

    @classmethod
    def load_from_yaml(cls, config_path: str) -> PortfolioManager:
        """从YAML加载配置"""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        portfolio_config = config['portfolio']

        # 1. 实例化策略
        strategies = []
        allocations = []

        for strat_config in portfolio_config['strategies']:
            # 动态导入策略类
            strategy_class = cls._get_strategy_class(strat_config['class'])

            # 实例化
            strategy = strategy_class(
                strategy_id=strat_config['strategy_id'],
                config=strat_config.get('config', {})
            )
            strategies.append(strategy)

            # 资金分配
            allocation = StrategyAllocation(
                strategy_id=strat_config['strategy_id'],
                capital=portfolio_config['total_capital'] * strat_config['weight'],
                weight=strat_config['weight'],
                risk_budget=strat_config['risk_budget'],
                is_active=strat_config.get('active', True)
            )
            allocations.append(allocation)

        # 2. 创建PortfolioManager
        portfolio = PortfolioManager(
            portfolio_id=portfolio_config['portfolio_id'],
            total_capital=portfolio_config['total_capital'],
            strategies=strategies,
            allocations=allocations
        )

        return portfolio

    @classmethod
    def _get_strategy_class(cls, class_name: str):
        """获取策略类"""
        module_path = cls.STRATEGY_REGISTRY[class_name]
        module_name, class_name = module_path.rsplit('.', 1)

        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
```

---

## 5. 回测引擎设计
### 5.1 模块概览

```
┌─────────────────────────────────────────────────────────┐
│              Backtest Orchestrator                      │
│  - 协调各类回测任务                                       |
│  - 统一结果格式                                           │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  FastBacktester  │ │ Production   │ │ StressTester     │
│                  │ │ Backtester   │ │                  │
│                  │ │              │ │                  │
└──────────────────┘ └──────────────┘ └──────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Walk-Forward    │ │ Cost         │ │ Parameter        │
│  Validator       │ │ Sensitivity  │ │ Sensitivity      │
│                  │ │ Analyzer     │ │ Analyzer         │
│                  │ │              │ │                  │
└──────────────────┘ └──────────────┘ └──────────────────┘
```

### 5.2 数据流

```
Strategy Config
     │
     ▼
BacktestOrchestrator ─────┐
     │                     │
     ├─> 标准回测          │
     ├─> Walk-Forward      │──> BacktestResult
     ├─> 成本敏感性        │       │
     ├─> 压力测试          │       ▼
     └─> 参数敏感性        │   PerformanceAnalyzer
                           │       │
                           └───────▼
                              Report (JSON/PDF)
```

### 5.3 配置与结果定义

```python
@dataclass
class BacktestConfig:
    """回测配置"""
    start_date: date
    end_date: date
    initial_capital: float
    universe: list[str]
    top_n: int = 5
    rebalance_freq: str = "monthly"  # 'weekly' / 'monthly'

    # 成本模型
    commission_rate: float = 0.0005
    stamp_tax_rate: float = 0.001
    min_commission: float = 5.0
    slippage_model: str = "enhanced"  # 'simple' / 'enhanced'
    market_impact_coef: float = 0.1

    # 风控
    enable_limit_filter: bool = True  # 涨跌停过滤
    enable_risk_check: bool = True

@dataclass
class BacktestResult:
    """回测结果"""
    backtest_id: str
    config: BacktestConfig
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    calmar_ratio: float
    win_rate: float
    total_trades: int
    turnover_annual: float
    cost_ratio: float
    equity_curve: pl.DataFrame
    daily_holdings: dict[date, dict[str, float]]  # 每日持仓明细
    rebalance_count: int
```

### 5.4 增强版成本模型

```python
@dataclass
class EnhancedCostModel:
    """增强版成本模型"""
    commission_rate: float = 0.0005
    stamp_tax_rate: float = 0.001
    min_commission: float = 5.0
    flow_fee: float = 0.1

    # 滑点模型参数
    base_slippage: float = 0.0005
    market_impact_coef: float = 0.1

    def calc_total_cost(
        self,
        order_amount: float,
        direction: str,
        daily_volume: float,
        volatility: float,
        spread: float
    ) -> float:
        """计算总交易成本"""
        # 佣金
        commission = max(order_amount * self.commission_rate, self.min_commission)

        # 印花税（仅卖出）
        stamp_tax = order_amount * self.stamp_tax_rate if direction == "SELL" else 0

        # 流量费
        flow_fee = self.flow_fee

        # 滑点
        slippage = self.calc_slippage(order_amount, daily_volume, volatility, spread)
        slippage_cost = order_amount * slippage

        return commission + stamp_tax + flow_fee + slippage_cost

    def calc_slippage(
        self,
        order_amount: float,
        daily_volume: float,
        volatility: float,
        spread: float
    ) -> float:
        """计算滑点（考虑订单规模和市场状况）"""
        # 参与率
        participation_rate = order_amount / (daily_volume + 1e-10)

        # 市场冲击 = 系数 * 波动率 * sqrt(参与率)
        market_impact = self.market_impact_coef * volatility * (participation_rate ** 0.5)

        # 总滑点 = 基础滑点 + 价差/2 + 市场冲击
        total_slippage = self.base_slippage + spread / 2 + market_impact

        return min(total_slippage, 0.02)  # 滑点上限 2%
```

### 5.5 FastBacktester（向量化）

```python
class FastBacktester:
    """快速回测引擎（向量化）"""

    def __init__(
        self,
        config: BacktestConfig,
        data_service: "DataService"
    ):
        self.config = config
        self.data = data_service
        self.cost_model = EnhancedCostModel(
            commission_rate=config.commission_rate,
            stamp_tax_rate=config.stamp_tax_rate,
            market_impact_coef=config.market_impact_coef
        )
        self.scoring_engine = RotationScoringEngine(data_service)

    def run(self) -> BacktestResult:
        """运行回测"""
        # 1. 加载数据
        kline_df = self._load_kline_data()
        regime_df = self._load_regime_data()

        # 2. 获取调仓日期
        rebalance_dates = self._get_rebalance_dates()

        # 3. 初始化
        equity = self.config.initial_capital
        positions: dict[str, int] = {}
        equity_curve = []
        daily_holdings = {}
        total_cost = 0
        trade_count = 0

        # 4. 遍历每个交易日
        trading_days = self._get_trading_days()
        for trade_date in trading_days:
            # 4.1 更新持仓市值
            market_values = self._calc_market_values(positions, trade_date, kline_df)
            equity = sum(market_values.values())

            # 4.2 记录每日持仓
            daily_holdings[trade_date] = {
                symbol: mv / equity if equity > 0 else 0
                for symbol, mv in market_values.items()
            }

            # 4.3 调仓日处理
            if trade_date in rebalance_dates:
                # 获取信号
                scores = self.scoring_engine.calc_scores(
                    trade_date,
                    self.config.universe,
                    self.config.top_n
                )
                top_symbols = [s.symbol for s in scores if s.is_top_n]

                # 获取涨跌停状态
                limit_status = self._get_limit_status(trade_date, kline_df)

                # 过滤涨跌停
                if self.config.enable_limit_filter:
                    top_symbols = self._filter_limit_locked(
                        top_symbols, limit_status, "BUY"
                    )

                # 获取 Regime 约束
                regime = regime_df.filter(pl.col("trade_date") == trade_date)
                limits = PositionLimits.from_regime(regime["regime_type"].item())

                # 计算目标权重
                target_weights = self._calc_target_weights(
                    top_symbols, limits, equity
                )

                # 执行调仓（考虑成本）
                cost, trades = self._execute_rebalance(
                    positions, target_weights, trade_date, kline_df, limit_status
                )
                total_cost += cost
                trade_count += trades

            # 4.4 记录权益
            equity_curve.append({
                "trade_date": trade_date,
                "equity": equity,
            })

        # 5. 计算绩效指标
        return self._calc_performance(
            equity_curve, daily_holdings, total_cost, trade_count
        )

    def _filter_limit_locked(
        self,
        symbols: list[str],
        limit_status: dict[str, str],
        direction: str
    ) -> list[str]:
        """过滤涨跌停无法成交的标的"""
        filtered = []
        for symbol in symbols:
            status = limit_status.get(symbol, "NORMAL")

            if direction == "BUY":
                # 涨停/停牌无法买入
                if status not in ("LIMIT_UP", "SUSPENDED"):
                    filtered.append(symbol)
            else:  # SELL
                # 跌停/停牌无法卖出
                if status not in ("LIMIT_DOWN", "SUSPENDED"):
                    filtered.append(symbol)

        return filtered

    def _get_limit_status(
        self,
        trade_date: date,
        kline_df: pl.DataFrame
    ) -> dict[str, str]:
        """获取指定日期的涨跌停状态"""
        day_df = kline_df.filter(pl.col("trade_date") == trade_date)
        return {
            row["symbol"]: row["status"]
            for row in day_df.iter_rows(named=True)
        }
```

### 5.4 ProductionBacktester（事件驱动）

```python
class ProductionBacktester:
    """生产级事件驱动回测引擎"""

    def __init__(
        self,
        config: BacktestConfig,
        data_service: "DataService"
    ):
        self.config = config
        self.data = data_service
        self.portfolio = Portfolio(initial_capital=config.initial_capital)
        self.risk_engine = RiskEngine()
        self.cost_model = EnhancedCostModel()

    def run(self) -> BacktestResult:
        """运行回测"""
        strategy = RotationStrategy(
            scoring_engine=RotationScoringEngine(self.data),
            top_n=self.config.top_n
        )

        equity_curve = []
        daily_holdings = {}

        for trade_date in self._get_trading_calendar():
            ctx = self._create_context(trade_date)

            # 1. 获取市场数据
            market_data = self.data.get_daily_snapshot(trade_date)

            # 2. 更新持仓市值
            self.portfolio.mark_to_market(market_data)

            # 3. 记录每日持仓
            daily_holdings[trade_date] = self.portfolio.get_weights()

            # 4. 调仓日处理
            if self._is_rebalance_date(trade_date):
                # 生成信号
                signals = strategy.generate_signals(ctx)

                # 生成订单
                orders = self._generate_orders(signals, market_data)

                # 涨跌停过滤
                if self.config.enable_limit_filter:
                    orders = self._filter_limit_locked_orders(orders, market_data)

                # 执行订单
                for order in orders:
                    self._execute_order(order, market_data)

            # 5. 风控检查
            if self.config.enable_risk_check:
                risk_decision = self.risk_engine.check_daily(ctx, self.portfolio)
                if risk_decision.action != "ALLOW":
                    self._handle_risk_decision(risk_decision)

            # 6. 记录权益
            equity_curve.append({
                "trade_date": trade_date,
                "equity": self.portfolio.equity,
                "drawdown": self.portfolio.current_drawdown,
            })

        return self._calc_performance(equity_curve, daily_holdings)

    def _filter_limit_locked_orders(
        self,
        orders: list[Order],
        market_data: dict
    ) -> list[Order]:
        """过滤涨跌停订单"""
        filtered = []
        for order in orders:
            status = market_data[order.symbol].get("status", "NORMAL")

            if order.direction == "BUY":
                if status not in ("LIMIT_UP", "SUSPENDED"):
                    filtered.append(order)
                else:
                    logger.info(
                        "order_blocked_by_limit",
                        symbol=order.symbol,
                        direction=order.direction,
                        status=status
                    )
            else:
                if status not in ("LIMIT_DOWN", "SUSPENDED"):
                    filtered.append(order)
                else:
                    logger.info(
                        "order_blocked_by_limit",
                        symbol=order.symbol,
                        direction=order.direction,
                        status=status
                    )

        return filtered
```

### 5.5 对齐测试

```python
class AlignmentTester:
    """Fast vs Production 对齐测试"""

    # 严格标准
    RETURN_TOLERANCE = 0.001      # 0.1%
    DRAWDOWN_TOLERANCE = 0.005    # 0.5%

    def run_alignment_test(self, config: BacktestConfig) -> AlignmentReport:
        """运行对齐测试"""
        # 运行两个引擎
        fast_result = FastBacktester(config, self.data).run()
        prod_result = ProductionBacktestEngine(config, self.data).run()

        # 检查对齐
        return_diff = abs(fast_result.total_return - prod_result.total_return)
        drawdown_diff = abs(fast_result.max_drawdown - prod_result.max_drawdown)
        rebalance_match = fast_result.rebalance_count == prod_result.rebalance_count
        holdings_match = self._compare_daily_holdings(
            fast_result.daily_holdings,
            prod_result.daily_holdings
        )

        passed = (
            return_diff <= self.RETURN_TOLERANCE and
            drawdown_diff <= self.DRAWDOWN_TOLERANCE and
            rebalance_match and
            holdings_match
        )

        return AlignmentReport(
            return_diff=return_diff,
            drawdown_diff=drawdown_diff,
            rebalance_count_match=rebalance_match,
            daily_holdings_match=holdings_match,
            passed=passed,
            details={
                "fast_return": fast_result.total_return,
                "prod_return": prod_result.total_return,
                "fast_drawdown": fast_result.max_drawdown,
                "prod_drawdown": prod_result.max_drawdown,
            }
        )

    def _compare_daily_holdings(
        self,
        fast_holdings: dict,
        prod_holdings: dict
    ) -> bool:
        """比较每日持仓是否一致"""
        for date in fast_holdings.keys():
            if date not in prod_holdings:
                return False

            fast_symbols = set(fast_holdings[date].keys())
            prod_symbols = set(prod_holdings[date].keys())

            if fast_symbols != prod_symbols:
                logger.warning(
                    "holdings_mismatch",
                    date=date,
                    fast_only=fast_symbols - prod_symbols,
                    prod_only=prod_symbols - fast_symbols
                )
                return False

        return True
```

### 5.6 Walk-Forward验证器

```python
"""
新文件：packages/engine/src/ditto_engine/backtest/walk_forward.py
这是解决"过拟合"问题的关键
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict, Callable, Optional
import polars as pl


@dataclass
class WalkForwardConfig:
    """Walk-Forward配置"""
    train_window: int = 252      # 训练窗口（天）
    test_window: int = 63        # 测试窗口（天）
    step: int = 21               # 滚动步长（天）
    anchor: bool = False         # 是否锚定（expanding window）

    # 优化相关
    optimize_params: bool = True
    optimization_metric: str = "sharpe"  # sharpe/calmar/sortino
    param_grid: Dict = None


@dataclass
class WalkForwardPeriod:
    """单个Walk-Forward周期"""
    period_id: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    # 结果
    optimal_params: Optional[Dict] = None
    train_metrics: Optional[Dict] = None
    test_metrics: Optional[Dict] = None


class WalkForwardValidator:
    """Walk-Forward验证器

    核心思想：
    1. 在训练期优化参数（可选）
    2. 在测试期验证
    3. 滚动前进，重复1-2
    4. 汇总所有测试期结果

    优势：
    - 避免过拟合
    - 更接近实盘（无未来信息）
    - 评估策略在不同市场环境的稳健性
    """

    def __init__(
        self,
        backtester: 'BacktesterBase',
        config: WalkForwardConfig
    ):
        self.backtester = backtester
        self.config = config

    def run(
        self,
        start_date: date,
        end_date: date,
        strategy_config: Dict,
        universe: List[str]
    ) -> 'WalkForwardResult':
        """运行Walk-Forward验证

        Args:
            start_date: 起始日期
            end_date: 结束日期
            strategy_config: 策略基础配置
            universe: 股票池

        Returns:
            WalkForwardResult: 包含所有周期的结果
        """

        # 1. 划分周期
        periods = self._split_periods(start_date, end_date)

        # 2. 对每个周期进行训练+测试
        results = []
        for period in periods:
            result = self._run_period(period, strategy_config, universe)
            results.append(result)

        # 3. 汇总结果
        return self._aggregate_results(results)

    def _split_periods(
        self,
        start_date: date,
        end_date: date
    ) -> List[WalkForwardPeriod]:
        """划分训练/测试周期"""
        periods = []
        period_id = 0

        current_date = start_date
        while current_date < end_date:
            # 训练期
            train_start = current_date
            train_end = train_start + timedelta(days=self.config.train_window)

            # 测试期
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.config.test_window)

            if test_end > end_date:
                break

            periods.append(WalkForwardPeriod(
                period_id=period_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end
            ))

            # 移动窗口
            if self.config.anchor:
                # Anchored: train_start不变
                current_date = test_start
            else:
                # Rolling: 整个窗口滚动
                current_date = current_date + timedelta(days=self.config.step)

            period_id += 1

        return periods

    def _run_period(
        self,
        period: WalkForwardPeriod,
        strategy_config: Dict,
        universe: List[str]
    ) -> WalkForwardPeriod:
        """运行单个周期"""

        # 1. 训练期：优化参数（可选）
        if self.config.optimize_params:
            optimal_params = self._optimize_params(
                period.train_start,
                period.train_end,
                strategy_config,
                universe
            )
            period.optimal_params = optimal_params

            # 训练期绩效（样本内）
            train_result = self.backtester.run(
                start_date=period.train_start,
                end_date=period.train_end,
                strategy_config={**strategy_config, **optimal_params},
                universe=universe
            )
            period.train_metrics = train_result.to_dict()
        else:
            period.optimal_params = {}
            period.train_metrics = {}

        # 2. 测试期：使用最优参数（样本外）
        test_result = self.backtester.run(
            start_date=period.test_start,
            end_date=period.test_end,
            strategy_config={**strategy_config, **period.optimal_params},
            universe=universe
        )
        period.test_metrics = test_result.to_dict()

        return period

    def _optimize_params(
        self,
        start_date: date,
        end_date: date,
        strategy_config: Dict,
        universe: List[str]
    ) -> Dict:
        """优化参数

        在训练期找到最优参数组合
        """
        param_grid = self.config.param_grid
        if not param_grid:
            return {}

        # 网格搜索
        best_params = {}
        best_score = -float('inf')

        for params in self._generate_param_combinations(param_grid):
            result = self.backtester.run(
                start_date=start_date,
                end_date=end_date,
                strategy_config={**strategy_config, **params},
                universe=universe
            )

            # 评估
            score = self._get_metric(result, self.config.optimization_metric)

            if score > best_score:
                best_score = score
                best_params = params

        return best_params

    def _generate_param_combinations(self, param_grid: Dict) -> List[Dict]:
        """生成参数组合"""
        import itertools

        keys = param_grid.keys()
        values = param_grid.values()

        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _get_metric(self, result: 'BacktestResult', metric: str) -> float:
        """获取评估指标"""
        if metric == "sharpe":
            return result.sharpe_ratio
        elif metric == "calmar":
            return result.calmar_ratio
        elif metric == "sortino":
            return result.sortino_ratio
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def _aggregate_results(
        self,
        periods: List[WalkForwardPeriod]
    ) -> 'WalkForwardResult':
        """汇总所有周期结果"""

        # 提取所有测试期的指标
        test_sharpes = [p.test_metrics['sharpe_ratio'] for p in periods]
        test_returns = [p.test_metrics['total_return'] for p in periods]
        test_drawdowns = [p.test_metrics['max_drawdown'] for p in periods]

        # 计算统计量
        return WalkForwardResult(
            periods=periods,
            num_periods=len(periods),
            avg_test_sharpe=sum(test_sharpes) / len(test_sharpes),
            std_test_sharpe=self._calc_std(test_sharpes),
            avg_test_return=sum(test_returns) / len(test_returns),
            avg_test_drawdown=sum(test_drawdowns) / len(test_drawdowns),
            positive_periods=sum(1 for r in test_returns if r > 0),
            stability_score=self._calc_stability(test_sharpes)
        )

    def _calc_std(self, values: List[float]) -> float:
        """计算标准差"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    def _calc_stability(self, sharpes: List[float]) -> float:
        """计算稳定性得分

        稳定性 = (正Sharpe的周期数) / 总周期数
        """
        return sum(1 for s in sharpes if s > 0) / len(sharpes)


@dataclass
class WalkForwardResult:
    """Walk-Forward结果"""
    periods: List[WalkForwardPeriod]
    num_periods: int

    # 测试期汇总指标
    avg_test_sharpe: float
    std_test_sharpe: float
    avg_test_return: float
    avg_test_drawdown: float
    positive_periods: int
    stability_score: float  # [0, 1]

    def is_robust(self) -> bool:
        """判断策略是否稳健

        标准：
        1. 平均测试Sharpe > 0.5
        2. 稳定性 > 0.6 (60%周期为正)
        3. 平均回撤 < 0.25
        """
        return (
            self.avg_test_sharpe > 0.5 and
            self.stability_score > 0.6 and
            self.avg_test_drawdown < 0.25
        )

    def to_report(self) -> Dict:
        """生成报告"""
        return {
            'summary': {
                'num_periods': self.num_periods,
                'avg_test_sharpe': self.avg_test_sharpe,
                'std_test_sharpe': self.std_test_sharpe,
                'stability_score': self.stability_score,
                'is_robust': self.is_robust()
            },
            'periods': [
                {
                    'period_id': p.period_id,
                    'test_sharpe': p.test_metrics['sharpe_ratio'],
                    'test_return': p.test_metrics['total_return'],
                    'test_drawdown': p.test_metrics['max_drawdown']
                }
                for p in self.periods
            ]
        }
```

### 5.7 成本敏感性分析器

```python
"""
新文件：packages/engine/src/ditto_engine/backtest/cost_sensitivity.py
"""

from dataclasses import dataclass
from typing import List, Dict
import polars as pl
import matplotlib.pyplot as plt


@dataclass
class CostScenario:
    """成本场景"""
    scenario_name: str
    cost_multiplier: float      # 成本倍数（相对基准）

    # 细分成本
    commission: float           # 佣金
    slippage: float            # 滑点
    impact: float              # 市场冲击

    @classmethod
    def from_multiplier(cls, name: str, multiplier: float, base_cost: float = 0.001):
        """从倍数创建场景"""
        total_cost = base_cost * multiplier
        return cls(
            scenario_name=name,
            cost_multiplier=multiplier,
            commission=total_cost * 0.3,
            slippage=total_cost * 0.5,
            impact=total_cost * 0.2
        )


class CostSensitivityAnalyzer:
    """成本敏感性分析器

    目的：
    1. 评估不同成本水平下的策略表现
    2. 找出策略的成本承受能力
    3. 为实盘执行提供成本预算

    典型用法：
    >>> analyzer = CostSensitivityAnalyzer(backtester)
    >>> result = analyzer.run(
    ...     scenarios=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
    ...     base_config=strategy_config
    ... )
    >>> result.plot()
    >>> assert result.is_profitable_at(3.0), "3x成本下必须盈利"
    """

    def __init__(self, backtester: 'BacktesterBase'):
        self.backtester = backtester

    def run(
        self,
        scenarios: List[float],
        start_date: date,
        end_date: date,
        strategy_config: Dict,
        universe: List[str],
        base_cost: float = 0.001
    ) -> 'CostSensitivityResult':
        """运行成本敏感性分析

        Args:
            scenarios: 成本倍数列表，如 [0.5, 1.0, 2.0, 3.0]
            base_cost: 基准成本（0.1%）
        """

        results = []

        for multiplier in scenarios:
            # 创建成本场景
            scenario = CostScenario.from_multiplier(
                name=f"{multiplier}x",
                multiplier=multiplier,
                base_cost=base_cost
            )

            # 运行回测
            config = {
                **strategy_config,
                'cost_model': {
                    'commission': scenario.commission,
                    'slippage': scenario.slippage,
                    'impact': scenario.impact
                }
            }

            result = self.backtester.run(
                start_date=start_date,
                end_date=end_date,
                strategy_config=config,
                universe=universe
            )

            results.append({
                'scenario': scenario,
                'result': result
            })

        return CostSensitivityResult(results)


@dataclass
class CostSensitivityResult:
    """成本敏感性结果"""
    results: List[Dict]

    def get_metric(self, multiplier: float, metric: str) -> float:
        """获取指定成本倍数下的指标"""
        for r in self.results:
            if r['scenario'].cost_multiplier == multiplier:
                return getattr(r['result'], metric)
        raise ValueError(f"Multiplier {multiplier} not found")

    def is_profitable_at(self, multiplier: float) -> bool:
        """在指定成本倍数下是否盈利"""
        return self.get_metric(multiplier, 'total_return') > 0

    def get_sharpe_at(self, multiplier: float) -> float:
        """获取指定成本下的Sharpe"""
        return self.get_metric(multiplier, 'sharpe_ratio')

    def find_breakeven_cost(self) -> float:
        """找到盈亏平衡点（成本倍数）"""
        for r in sorted(self.results, key=lambda x: x['scenario'].cost_multiplier):
            if r['result'].total_return <= 0:
                return r['scenario'].cost_multiplier
        return float('inf')  # 所有场景都盈利

    def plot(self, save_path: Optional[str] = None):
        """绘制成本敏感性曲线"""
        multipliers = [r['scenario'].cost_multiplier for r in self.results]
        sharpes = [r['result'].sharpe_ratio for r in self.results]
        returns = [r['result'].total_return for r in self.results]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        # Sharpe vs Cost
        ax1.plot(multipliers, sharpes, marker='o')
        ax1.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax1.set_xlabel('Cost Multiplier')
        ax1.set_ylabel('Sharpe Ratio')
        ax1.set_title('Sharpe Ratio vs Trading Cost')
        ax1.grid(True, alpha=0.3)

        # Return vs Cost
        ax2.plot(multipliers, returns, marker='o', color='green')
        ax2.axhline(y=0, color='r', linestyle='--', alpha=0.5)
        ax2.set_xlabel('Cost Multiplier')
        ax2.set_ylabel('Total Return')
        ax2.set_title('Return vs Trading Cost')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150)
        else:
            plt.show()

    def to_report(self) -> Dict:
        """生成报告"""
        return {
            'breakeven_cost': self.find_breakeven_cost(),
            'scenarios': [
                {
                    'multiplier': r['scenario'].cost_multiplier,
                    'sharpe': r['result'].sharpe_ratio,
                    'return': r['result'].total_return,
                    'drawdown': r['result'].max_drawdown,
                    'turnover': r['result'].turnover
                }
                for r in self.results
            ],
            'recommendation': self._get_recommendation()
        }

    def _get_recommendation(self) -> str:
        """给出成本建议"""
        sharpe_3x = self.get_sharpe_at(3.0)

        if sharpe_3x > 0.5:
            return "策略对成本不敏感，可以放心实盘"
        elif sharpe_3x > 0.3:
            return "策略在3倍成本下表现一般，需要优化执行"
        elif sharpe_3x > 0:
            return "策略在3倍成本下勉强盈利，实盘需谨慎"
        else:
            return "策略在3倍成本下亏损，不建议实盘"
```

### 5.8 压力测试

```python
"""
新文件：packages/engine/src/ditto_engine/backtest/stress_test.py
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Dict, Optional, Callable
import polars as pl
import numpy as np


@dataclass
class StressScenario:
    """压力测试场景"""
    scenario_id: str
    scenario_name: str
    scenario_type: str  # 'historical' / 'synthetic'

    # 历史场景
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # 合成场景
    shock_generator: Optional[Callable] = None

    # 预期结果
    expected_max_drawdown: Optional[float] = None


class StressTester:
    """压力测试引擎

    支持两类场景：
    1. 历史场景：重现历史危机（2015股灾、2020新冠）
    2. 合成场景：人工构造极端情况（闪崩、流动性危机）
    """

    # 预定义历史场景
    HISTORICAL_SCENARIOS = {
        '2015_crash': StressScenario(
            scenario_id='2015_crash',
            scenario_name='2015年股灾',
            scenario_type='historical',
            start_date=date(2015, 6, 15),
            end_date=date(2015, 7, 8),
            expected_max_drawdown=0.25
        ),
        '2020_covid': StressScenario(
            scenario_id='2020_covid',
            scenario_name='2020年新冠暴跌',
            scenario_type='historical',
            start_date=date(2020, 2, 3),
            end_date=date(2020, 3, 23),
            expected_max_drawdown=0.15
        ),
        '2022_bear': StressScenario(
            scenario_id='2022_bear',
            scenario_name='2022年熊市',
            scenario_type='historical',
            start_date=date(2022, 4, 1),
            end_date=date(2022, 4, 30),
            expected_max_drawdown=0.20
        ),
    }

    def __init__(self, backtester: 'BacktesterBase'):
        self.backtester = backtester

    def run_historical_scenario(
        self,
        scenario_id: str,
        strategy_config: Dict,
        universe: List[str]
    ) -> 'StressTestResult':
        """运行历史场景"""

        scenario = self.HISTORICAL_SCENARIOS[scenario_id]

        # 运行回测
        result = self.backtester.run(
            start_date=scenario.start_date,
            end_date=scenario.end_date,
            strategy_config=strategy_config,
            universe=universe
        )

        # 检查是否通过
        passed = (
            result.max_drawdown < scenario.expected_max_drawdown
        )

        return StressTestResult(
            scenario=scenario,
            result=result,
            passed=passed
        )

    def run_synthetic_scenario(
        self,
        scenario: StressScenario,
        strategy_config: Dict,
        universe: List[str]
    ) -> 'StressTestResult':
        """运行合成场景

        合成场景通过shock_generator生成模拟数据
        """

        # TODO: 实现合成数据生成
        # 1. 加载基准数据
        # 2. 应用shock_generator
        # 3. 运行回测

        raise NotImplementedError("Synthetic scenarios in Phase 2")

    def run_all_scenarios(
        self,
        strategy_config: Dict,
        universe: List[str]
    ) -> Dict[str, 'StressTestResult']:
        """运行所有历史场景"""

        results = {}
        for scenario_id in self.HISTORICAL_SCENARIOS:
            results[scenario_id] = self.run_historical_scenario(
                scenario_id, strategy_config, universe
            )

        return results


@dataclass
class StressTestResult:
    """压力测试结果"""
    scenario: StressScenario
    result: 'BacktestResult'
    passed: bool

    def to_report(self) -> Dict:
        return {
            'scenario': self.scenario.scenario_name,
            'period': f"{self.scenario.start_date} ~ {self.scenario.end_date}",
            'max_drawdown': self.result.max_drawdown,
            'expected_drawdown': self.scenario.expected_max_drawdown,
            'passed': self.passed,
            'sharpe': self.result.sharpe_ratio,
            'return': self.result.total_return
        }


# 合成场景生成器（示例）
class SyntheticScenarioGenerator:
    """合成场景生成器"""

    @staticmethod
    def flash_crash(
        base_data: pl.DataFrame,
        drop_pct: float = -0.10,
        duration_minutes: int = 5
    ) -> pl.DataFrame:
        """生成闪崩场景

        模拟：5分钟内暴跌10%，然后反弹
        """
        # TODO: 实现
        pass

    @staticmethod
    def liquidity_crisis(
        base_data: pl.DataFrame,
        spread_multiplier: float = 5.0,
        duration_days: int = 5
    ) -> pl.DataFrame:
        """生成流动性危机场景

        模拟：买卖价差扩大5倍，持续5天
        """
        # TODO: 实现
        pass

    @staticmethod
    def regime_whipsaw(
        base_data: pl.DataFrame,
        switches_per_month: int = 4,
        duration_months: int = 3
    ) -> pl.DataFrame:
        """生成Regime频繁切换场景

        模拟：Regime每周切换1次，持续3个月
        """
        # TODO: 实现
        pass
```

### 5.9 回测编排器

```python
"""
新文件：packages/engine/src/ditto_engine/backtest/orchestrator.py
统一协调各类回测任务
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import date


@dataclass
class BacktestTask:
    """回测任务"""
    task_type: str  # 'standard' / 'walk_forward' / 'cost_sensitivity' / 'stress'
    config: Dict


class BacktestOrchestrator:
    """回测编排器

    统一入口，协调各类回测
    """

    def __init__(
        self,
        fast_backtester: 'FastBacktester',
        prod_backtester: 'ProductionBacktester'
    ):
        self.fast = fast_backtester
        self.prod = prod_backtester

        # 初始化各分析器
        self.wf_validator = WalkForwardValidator(self.fast, WalkForwardConfig())
        self.cost_analyzer = CostSensitivityAnalyzer(self.fast)
        self.stress_tester = StressTestEngine(self.fast)

    def run_comprehensive_validation(
        self,
        start_date: date,
        end_date: date,
        strategy_config: Dict,
        universe: List[str]
    ) -> 'ComprehensiveReport':
        """运行全面验证

        包括：
        1. 标准回测
        2. 对齐测试
        3. Walk-Forward
        4. 成本敏感性
        5. 压力测试
        """

        report = ComprehensiveReport()

        # 1. 标准回测
        report.standard_result = self.fast.run(
            start_date, end_date, strategy_config, universe
        )

        # 2. 对齐测试
        report.alignment_result = self._run_alignment_test(
            start_date, end_date, strategy_config, universe
        )

        # 3. Walk-Forward
        report.walk_forward_result = self.wf_validator.run(
            start_date, end_date, strategy_config, universe
        )

        # 4. 成本敏感性
        report.cost_sensitivity_result = self.cost_analyzer.run(
            scenarios=[0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
            start_date=start_date,
            end_date=end_date,
            strategy_config=strategy_config,
            universe=universe
        )

        # 5. 压力测试
        report.stress_test_results = self.stress_tester.run_all_scenarios(
            strategy_config, universe
        )

        return report

    def _run_alignment_test(
        self,
        start_date: date,
        end_date: date,
        strategy_config: Dict,
        universe: List[str]
    ) -> 'AlignmentResult':
        """运行对齐测试"""

        fast_result = self.fast.run(
            start_date, end_date, strategy_config, universe
        )

        prod_result = self.prod.run(
            start_date, end_date, strategy_config, universe
        )

        return AlignmentResult(
            fast_result=fast_result,
            prod_result=prod_result,
            return_diff=abs(fast_result.total_return - prod_result.total_return),
            sharpe_diff=abs(fast_result.sharpe_ratio - prod_result.sharpe_ratio),
            drawdown_diff=abs(fast_result.max_drawdown - prod_result.max_drawdown),
            passed=self._check_alignment(fast_result, prod_result)
        )

    def _check_alignment(self, fast, prod) -> bool:
        """检查对齐"""
        return (
            abs(fast.total_return - prod.total_return) < 0.001 and
            abs(fast.max_drawdown - prod.max_drawdown) < 0.005
        )


@dataclass
class ComprehensiveReport:
    """全面验证报告"""
    standard_result: Optional['BacktestResult'] = None
    alignment_result: Optional['AlignmentResult'] = None
    walk_forward_result: Optional['WalkForwardResult'] = None
    cost_sensitivity_result: Optional['CostSensitivityResult'] = None
    stress_test_results: Optional[Dict] = None

    def is_production_ready(self) -> bool:
        """判断是否可以进入生产

        标准：
        1. 对齐测试通过
        2. Walk-Forward稳健
        3. 3x成本下Sharpe > 0.3
        4. 所有压力测试通过
        """
        if not self.alignment_result or not self.alignment_result.passed:
            return False

        if not self.walk_forward_result or not self.walk_forward_result.is_robust():
            return False

        if not self.cost_sensitivity_result:
            return False
        sharpe_3x = self.cost_sensitivity_result.get_sharpe_at(3.0)
        if sharpe_3x < 0.3:
            return False

        if not self.stress_test_results:
            return False
        all_passed = all(r.passed for r in self.stress_test_results.values())
        if not all_passed:
            return False

        return True

    def to_json(self) -> Dict:
        """生成JSON报告"""
        return {
            'production_ready': self.is_production_ready(),
            'standard': self.standard_result.to_dict() if self.standard_result else None,
            'alignment': self.alignment_result.to_dict() if self.alignment_result else None,
            'walk_forward': self.walk_forward_result.to_report() if self.walk_forward_result else None,
            'cost_sensitivity': self.cost_sensitivity_result.to_report() if self.cost_sensitivity_result else None,
            'stress_tests': {
                k: v.to_report() for k, v in self.stress_test_results.items()
            } if self.stress_test_results else None
        }


@dataclass
class AlignmentResult:
    """对齐测试结果"""
    fast_result: 'BacktestResult'
    prod_result: 'BacktestResult'
    return_diff: float
    sharpe_diff: float
    drawdown_diff: float
    passed: bool

    def to_dict(self) -> Dict:
        return {
            'passed': self.passed,
            'return_diff': self.return_diff,
            'sharpe_diff': self.sharpe_diff,
            'drawdown_diff': self.drawdown_diff
        }

import quantstats as qs

class PerformanceAnalyzer:
    """绩效分析器（基于QuantStats）"""

    def analyze_backtest(
        self,
        returns: pl.Series,
        benchmark_returns: pl.Series,
        output_path: str
    ) -> Dict:
        """生成完整绩效报告

        Returns:
            核心指标字典 + HTML报告
        """

        # 转换为Pandas Series（QuantStats需要）
        returns_pd = returns.to_pandas()
        benchmark_pd = benchmark_returns.to_pandas()

        # 生成HTML报告
        qs.reports.html(
            returns_pd,
            benchmark=benchmark_pd,
            output=output_path,
            title="Backtest Report"
        )

        # 返回核心指标
        return {
            'sharpe': qs.stats.sharpe(returns_pd),
            'sortino': qs.stats.sortino(returns_pd),
            'calmar': qs.stats.calmar(returns_pd),
            'max_drawdown': qs.stats.max_drawdown(returns_pd),
            'var_95': qs.stats.var(returns_pd, confidence=0.95),
            'cvar_95': qs.stats.cvar(returns_pd, confidence=0.95),
            'tail_ratio': qs.stats.tail_ratio(returns_pd),
        }
```

### 5.10. 使用示例

#### 5.10.1 快速验证

```python
# Phase 1A: 快速验证
from ditto.backtest import CostSensitivityAnalyzer, StressTestEngine

# 成本测试
analyzer = CostSensitivityAnalyzer(fast_backtester)
cost_result = analyzer.run(
    scenarios=[1.0, 2.0, 3.0],
    start_date=date(2020, 1, 1),
    end_date=date(2024, 12, 1),
    strategy_config=config,
    universe=universe
)

# 验收
assert cost_result.get_sharpe_at(3.0) > 0.3, "3x成本不达标"
cost_result.plot(save_path="cost_sensitivity.png")

# 压力测试
stress = StressTestEngine(fast_backtester)
results = stress.run_all_scenarios(config, universe)

# 验收
assert all(r.passed for r in results.values()), "压力测试失败"
```

#### 5.10.2 全面验证（完成后）

```python
# Phase 1B: 全面验证
orchestrator = BacktestOrchestrator(fast, prod)

report = orchestrator.run_comprehensive_validation(
    start_date=date(2020, 1, 1),
    end_date=date(2024, 12, 1),
    strategy_config=config,
    universe=universe
)

# 检查
if report.is_production_ready():
    print("✅ 策略通过全面验证，可以进入实盘")
    report.to_json("validation_report.json")
else:
    print("❌ 策略未通过验证")
    print(report.to_json())
```

---


## 6. 风控引擎与 Kill Switch 设计

### 6.1 RiskMetrics & RiskDecision

```python
@dataclass
class RiskMetrics:
    """风险指标"""
    current_drawdown: float
    drawdown_3d: float        # 3日回撤（速度检测）
    drawdown_velocity: float  # 回撤加速度
    peak_equity: float
    total_position: float
    single_max_position: float
    daily_return: float
    cost_ratio: float

@dataclass
class RiskDecision:
    """风控决策"""
    action: str               # 'ALLOW' / 'WARN' / 'BLOCK'
    reason: str | None = None
    required_action: str | None = None
    kill_switch_level: int = 0
```

### 6.2 RiskEngine（含回撤速度检测）

```python
class RiskEngine:
    """风控引擎"""

    # 回撤阈值
    DRAWDOWN_LEVEL1 = 0.10    # 10%
    DRAWDOWN_LEVEL2 = 0.18    # 18%
    DRAWDOWN_LEVEL3 = 0.20    # 20%

    # 速度阈值
    FAST_DRAWDOWN_3D = 0.05   # 3日 5% 提前触发
    DRAWDOWN_ACCELERATION_THRESHOLD = 0.01  # 日加速度 1%

    def __init__(self, db_path: str = "ledger/trading.db"):
        self.kill_switch = KillSwitchService(db_path)
        self.metrics_history: list[RiskMetrics] = []

    def check_daily(
        self,
        ctx: ExecutionContext,
        portfolio: Portfolio
    ) -> RiskDecision:
        """每日风控检查"""
        metrics = self._calc_metrics(portfolio)
        self.metrics_history.append(metrics)

        # 1. 检查回撤速度（优先）
        velocity_decision = self._check_drawdown_velocity(metrics)
        if velocity_decision.action != "ALLOW":
            return velocity_decision

        # 2. 检查绝对回撤
        drawdown_decision = self._check_drawdown(metrics)
        if drawdown_decision.action != "ALLOW":
            return drawdown_decision

        # 3. 检查仓位限制
        position_decision = self._check_position_limits(portfolio, ctx)
        if position_decision.action != "ALLOW":
            return position_decision

        return RiskDecision(action="ALLOW")

    def _check_drawdown_velocity(self, metrics: RiskMetrics) -> RiskDecision:
        """检查回撤速度"""
        # 3日快速回撤
        if metrics.drawdown_3d > self.FAST_DRAWDOWN_3D:
            self.kill_switch.trigger(
                reason="fast_drawdown_3d",
                level=1,
                current_value=metrics.drawdown_3d
            )
            return RiskDecision(
                action="WARN",
                reason=f"Fast drawdown: {metrics.drawdown_3d:.2%} in 3 days",
                required_action="REDUCE_30PCT",
                kill_switch_level=1
            )

        # 回撤加速
        if metrics.drawdown_velocity > self.DRAWDOWN_ACCELERATION_THRESHOLD:
            return RiskDecision(
                action="WARN",
                reason=f"Drawdown accelerating: {metrics.drawdown_velocity:.2%}/day",
                required_action="HALT_NEW_POSITIONS"
            )

        return RiskDecision(action="ALLOW")

    def _check_drawdown(self, metrics: RiskMetrics) -> RiskDecision:
        """检查绝对回撤"""
        dd = metrics.current_drawdown

        if dd >= self.DRAWDOWN_LEVEL3:
            self.kill_switch.trigger("drawdown_critical", level=3, current_value=dd)
            return RiskDecision(
                action="BLOCK",
                reason=f"Drawdown {dd:.2%} >= 20%, force liquidation",
                required_action="LIQUIDATE_ALL",
                kill_switch_level=3
            )

        elif dd >= self.DRAWDOWN_LEVEL2:
            self.kill_switch.trigger("drawdown_severe", level=2, current_value=dd)
            return RiskDecision(
                action="BLOCK",
                reason=f"Drawdown {dd:.2%} >= 18%, force reduce 50%",
                required_action="REDUCE_50PCT",
                kill_switch_level=2
            )

        elif dd >= self.DRAWDOWN_LEVEL1:
            self.kill_switch.trigger("drawdown_warning", level=1, current_value=dd)
            return RiskDecision(
                action="WARN",
                reason=f"Drawdown {dd:.2%} >= 10%, stop new positions",
                required_action="STOP_NEW_POSITIONS",
                kill_switch_level=1
            )

        return RiskDecision(action="ALLOW")

    def _calc_metrics(self, portfolio: Portfolio) -> RiskMetrics:
        """计算风险指标"""
        # 当前回撤
        current_equity = portfolio.equity
        peak_equity = portfolio.peak_equity
        current_drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0

        # 3日回撤
        if len(self.metrics_history) >= 3:
            equity_3d_ago = self.metrics_history[-3].peak_equity
            drawdown_3d = (equity_3d_ago - current_equity) / equity_3d_ago if equity_3d_ago > 0 else 0
        else:
            drawdown_3d = 0

        # 回撤加速度
        if len(self.metrics_history) >= 2:
            dd_today = current_drawdown
            dd_yesterday = self.metrics_history[-1].current_drawdown
            dd_2d_ago = self.metrics_history[-2].current_drawdown if len(self.metrics_history) >= 2 else dd_yesterday

            velocity_today = dd_today - dd_yesterday
            velocity_yesterday = dd_yesterday - dd_2d_ago
            drawdown_velocity = velocity_today - velocity_yesterday
        else:
            drawdown_velocity = 0

        return RiskMetrics(
            current_drawdown=current_drawdown,
            drawdown_3d=drawdown_3d,
            drawdown_velocity=drawdown_velocity,
            peak_equity=peak_equity,
            total_position=portfolio.total_position_ratio,
            single_max_position=portfolio.max_single_position_ratio,
            daily_return=portfolio.daily_return,
            cost_ratio=portfolio.cost_ratio
        )
```

### 6.3 Pre-Trade Risk Check

```python
class PreTradeRiskChecker:
    """下单前风控检查"""

    def check_order(
        self,
        order: Order,
        portfolio: Portfolio,
        regime: str,
        market_data: dict
    ) -> RiskDecision:
        """订单风控检查"""
        limits = PositionLimits.from_regime(regime)

        # 1. 涨跌停检查
        status = market_data.get(order.symbol, {}).get("status", "NORMAL")
        if order.direction == "BUY" and status in ("LIMIT_UP", "SUSPENDED"):
            return RiskDecision(
                action="BLOCK",
                reason=f"Cannot buy {order.symbol}: status is {status}"
            )
        if order.direction == "SELL" and status in ("LIMIT_DOWN", "SUSPENDED"):
            return RiskDecision(
                action="BLOCK",
                reason=f"Cannot sell {order.symbol}: status is {status}"
            )

        # 2. 单票仓位检查
        post_trade_weight = self._calc_post_trade_weight(order, portfolio)
        if post_trade_weight > limits.single_etf_max:
            return RiskDecision(
                action="BLOCK",
                reason=f"Post-trade weight {post_trade_weight:.2%} exceeds limit {limits.single_etf_max:.2%}"
            )

        # 3. 总仓位检查
        post_trade_equity = self._calc_post_trade_equity_ratio(order, portfolio)
        if post_trade_equity > limits.total_equity_max:
            return RiskDecision(
                action="BLOCK",
                reason=f"Post-trade equity {post_trade_equity:.2%} exceeds limit {limits.total_equity_max:.2%}"
            )

        # 4. 流动性检查
        daily_volume = market_data.get(order.symbol, {}).get("amount", 1e10)
        if order.amount > daily_volume * 0.05:
            return RiskDecision(
                action="WARN",
                reason=f"Order size exceeds 5% of daily volume, consider splitting"
            )

        return RiskDecision(action="ALLOW")
```

### 6.4 KillSwitchService

```python
class KillSwitchService:
    """Kill Switch 服务"""

    def __init__(self, db_path: str = "ledger/trading.db"):
        self.db_path = db_path

    def trigger(self, reason: str, level: int, current_value: float) -> None:
        """触发 Kill Switch"""
        now = datetime.now().isoformat()
        today = date.today().isoformat()

        thresholds = {1: 0.10, 2: 0.18, 3: 0.20}

        with sqlite3.connect(self.db_path) as conn:
            # 更新状态
            conn.execute(
                "UPDATE runtime_state SET value = ?, updated_at = ? WHERE key = ?",
                ("true", now, "kill_switch_active")
            )
            conn.execute(
                "UPDATE runtime_state SET value = ?, updated_at = ? WHERE key = ?",
                (str(level), now, "kill_switch_level")
            )
            conn.execute(
                "UPDATE runtime_state SET value = ?, updated_at = ? WHERE key = ?",
                (reason, now, "kill_switch_reason")
            )

            # 记录事件
            conn.execute("""
                INSERT INTO risk_events (
                    event_type, severity, trade_date,
                    current_value, threshold_value, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "kill_switch",
                "CRITICAL",
                today,
                current_value,
                thresholds.get(level, 0),
                f"Kill Switch Level {level} triggered: {reason}",
                now
            ))

        logger.critical(
            "kill_switch_triggered",
            reason=reason,
            level=level,
            value=current_value
        )

    def is_active(self) -> tuple[bool, int, str]:
        """检查 Kill Switch 状态"""
        with sqlite3.connect(self.db_path) as conn:
            active = conn.execute(
                "SELECT value FROM runtime_state WHERE key = 'kill_switch_active'"
            ).fetchone()
            level = conn.execute(
                "SELECT value FROM runtime_state WHERE key = 'kill_switch_level'"
            ).fetchone()
            reason = conn.execute(
                "SELECT value FROM runtime_state WHERE key = 'kill_switch_reason'"
            ).fetchone()

        return (
            active and active[0] == "true",
            int(level[0]) if level else 0,
            reason[0] if reason else ""
        )

    def deactivate(self, operator: str, reason: str) -> None:
        """解除 Kill Switch（需人工确认）"""
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE runtime_state SET value = 'false', updated_at = ? WHERE key = 'kill_switch_active'",
                (now,)
            )
            conn.execute(
                "UPDATE runtime_state SET value = '0', updated_at = ? WHERE key = 'kill_switch_level'",
                (now,)
            )
            conn.execute("""
                INSERT INTO risk_events (event_type, severity, message, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                "kill_switch_deactivated",
                "HIGH",
                f"Kill Switch deactivated by {operator}: {reason}",
                now
            ))

        logger.warning("kill_switch_deactivated", operator=operator, reason=reason)
```

---

## 7.组合优化
使用PyPortfolioOpt

**推荐理由**：
- 成熟的Markowitz均值-方差优化实现
- 支持Black-Litterman模型（结合市场均衡与主观观点）
- 风险预算、CVaR优化等高级功能
- 文档完善，易于使用

**使用场景**：
- Phase 1B：基础Markowitz优化（PortfolioManager中）
- Phase 2：Black-Litterman模型（结合Regime观点）
- Phase 3：高级优化（风险平价、CVaR优化）

**核心用法**：
**场景1：组合权重优化**
``` python
from pypfopt import expected_returns, risk_models
from pypfopt.efficient_frontier import EfficientFrontier

class PortfolioOptimizer:
    """组合优化器"""

    def optimize_weights(
        self,
        prices: pl.DataFrame,
        objective: str = 'max_sharpe'
    ) -> Dict[str, float]:
        """优化组合权重

        Args:
            prices: 价格数据（Polars）
            objective: 'max_sharpe' | 'min_volatility' | 'max_quadratic_utility'

        Returns:
            {symbol: weight}
        """

        # 转换为Pandas（PyPortfolioOpt需要）
        prices_pd = prices.to_pandas().pivot(
            index='date',
            columns='symbol',
            values='close'
        )

        # 计算期望收益和协方差
        mu = expected_returns.mean_historical_return(prices_pd)
        S = risk_models.sample_cov(prices_pd)

        # 优化
        ef = EfficientFrontier(mu, S)

        if objective == 'max_sharpe':
            weights = ef.max_sharpe()
        elif objective == 'min_volatility':
            weights = ef.min_volatility()
        else:
            weights = ef.max_quadratic_utility()

        cleaned_weights = ef.clean_weights()

        return cleaned_weights
```

**场景2：Black-Litterman模型**
``` python
from pypfopt import black_litterman

def optimize_with_views(
    prices: pl.DataFrame,
    views: Dict[str, float],  # 主观观点
    view_confidences: List[float]
) -> Dict[str, float]:
    """Black-Litterman优化

    结合市场均衡 + 主观观点
    """

    # 详细实现...
    pass
```

使用时机：
- Phase 1：基础Markowitz优化（PortfolioManager）
- Phase 2：Black-Litterman模型（结合Regime观点）
- Phase 3：风险预算、最小CVaR等高级优化





## 8. 交易执行引擎

### 8.1 总体架构

```
┌─────────────────────────────────────────────────────────┐
│              Execution Manager (新增)                   │
│  - 接收调仓计划                                         │
│  - 协调各执行器                                         │
│  - 执行质量评估                                         │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Smart Order     │ │ Cost Model   │ │ Market Data      │
│  Router (新增)   │ │ (增强)       │ │ Service          │
│                  │ │              │ │                  │
│ - TWAP           │ │ - 动态滑点   │ │ - 实时深度       │
│ - VWAP           │ │ - 市场冲击   │ │ - 成交量         │
│ - 智能拆单       │ │ - 时间因子   │ │                  │
└──────────────────┘ └──────────────┘ └──────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Order Execution Log (新增)                 │
│  - 记录所有订单                                         │
│  - 成交反馈                                             │
│  - 执行分析                                             │
└─────────────────────────────────────────────────────────┘
```

### 8.2 数据流

```
RebalancePlan
     │
     ▼
ExecutionManager
     │
     ├─> 分析市场状态
     ├─> 计算预期成本
     ├─> 选择执行策略
     │
     ▼
SmartOrderRouter
     │
     ├─> 大单拆分
     ├─> 时间分配
     ├─> 订单生成
     │
     ▼
BrokerAdapter (Phase 2)
     │
     ▼
ExecutionLog
```

---

### 8.3 核心模块设计

#### 8.3.1 动态成本模型

```python
"""
文件：packages/engine/src/ditto_engine/execution/cost_model.py
替换：原有的固定滑点模型
"""

from dataclasses import dataclass
from datetime import time
from typing import Dict, Optional
import polars as pl


@dataclass
class MarketState:
    """市场状态"""
    symbol: str
    bid_price: float
    ask_price: float
    spread: float
    volume_today: float       # 当日累计成交量
    avg_daily_volume: float   # 平均日成交量
    realized_vol: float       # 已实现波动率
    time_of_day: time         # 当前时间


@dataclass
class OrderCost:
    """订单成本"""
    commission: float      # 佣金
    slippage: float       # 滑点
    market_impact: float  # 市场冲击
    timing_cost: float    # 时机成本
    total_cost: float     # 总成本

    def to_bps(self) -> float:
        """转为基点（万分之一）"""
        return self.total_cost * 10000


class DynamicCostModel:
    """动态成本模型

    考虑因素：
    1. 订单大小（相对ADV）
    2. 市场波动率
    3. 买卖价差
    4. 时间因子（开盘/收盘）
    5. 流动性状态

    参考：
    - Almgren-Chriss模型（市场冲击）
    - Implementation Shortfall分解
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}

        # 基础成本（万分之几）
        self.base_commission = self.config.get('base_commission', 0.0003)  # 3个基点
        self.base_slippage = self.config.get('base_slippage', 0.0005)      # 5个基点

        # 市场冲击参数（Almgren-Chriss）
        self.alpha = self.config.get('alpha', 0.1)  # 临时冲击系数
        self.beta = self.config.get('beta', 0.01)   # 永久冲击系数
        self.gamma = self.config.get('gamma', 0.5)  # 参与率指数

    def estimate_cost(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> OrderCost:
        """估算订单成本

        Args:
            order: 订单（包含symbol, quantity, direction）
            market_state: 市场状态

        Returns:
            OrderCost: 分解后的成本
        """

        # 1. 佣金（固定）
        commission = self.base_commission

        # 2. 滑点（动态）
        slippage = self._calc_dynamic_slippage(order, market_state)

        # 3. 市场冲击（基于订单大小）
        market_impact = self._calc_market_impact(order, market_state)

        # 4. 时机成本（基于时间）
        timing_cost = self._calc_timing_cost(order, market_state)

        # 5. 总成本
        total = commission + slippage + market_impact + timing_cost

        return OrderCost(
            commission=commission,
            slippage=slippage,
            market_impact=market_impact,
            timing_cost=timing_cost,
            total_cost=total
        )

    def _calc_dynamic_slippage(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> float:
        """计算动态滑点

        滑点 = 基础滑点 × 价差因子 × 波动因子
        """
        # 价差因子：价差越大，滑点越大
        spread_factor = market_state.spread / market_state.bid_price
        spread_multiplier = 1 + (spread_factor / 0.001)  # 归一化到0.1%

        # 波动因子：波动率越高，滑点越大
        vol_multiplier = market_state.realized_vol / 0.15  # 归一化到15%

        # 综合
        slippage = self.base_slippage * spread_multiplier * vol_multiplier

        return slippage

    def _calc_market_impact(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> float:
        """计算市场冲击

        使用Almgren-Chriss模型的简化版：
        Impact = α × (V / ADV)^γ

        其中：
        - V: 订单量
        - ADV: 平均日成交量
        - γ: 参与率指数（通常0.5-0.7）
        """

        # 参与率 = 订单量 / ADV
        participation_rate = order.quantity / market_state.avg_daily_volume

        # 临时冲击
        temporary_impact = self.alpha * (participation_rate ** self.gamma)

        # 永久冲击（通常很小）
        permanent_impact = self.beta * participation_rate

        return temporary_impact + permanent_impact

    def _calc_timing_cost(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> float:
        """计算时机成本

        不同时段成本不同：
        - 开盘前30分钟：波动大，成本高 × 1.5
        - 收盘前30分钟：波动大，成本高 × 1.5
        - 午市：流动性差 × 1.2
        - 其他时段：正常 × 1.0
        """
        current_time = market_state.time_of_day

        # 开盘期间（9:30-10:00）
        if time(9, 30) <= current_time < time(10, 0):
            return 0.0005  # 5个基点

        # 收盘期间（14:30-15:00）
        elif time(14, 30) <= current_time < time(15, 0):
            return 0.0005

        # 午市（11:30-13:00）
        elif time(11, 30) <= current_time < time(13, 0):
            return 0.0002

        # 其他时段
        else:
            return 0.0

    def get_optimal_execution_window(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> tuple[time, time]:
        """获取最优执行时间窗口

        Returns:
            (start_time, end_time): 建议执行的时间窗口
        """

        # 规则：
        # 1. 避开开盘前30分钟
        # 2. 避开收盘前30分钟
        # 3. 优先10:00-11:30, 13:30-14:30

        # 小单：可以任意时段
        if order.quantity < market_state.avg_daily_volume * 0.01:
            return (time(9, 30), time(15, 0))

        # 大单：避开高波动时段
        return (time(10, 0), time(14, 30))


class SimplifiedCostModel(DynamicCostModel):
    """简化成本模型（Phase 1可用）

    保留核心逻辑，简化计算
    """

    def estimate_cost(
        self,
        order: 'Order',
        market_state: MarketState
    ) -> OrderCost:
        """简化估算

        成本 = 基础成本 × (1 + 订单大小因子)
        """

        # 基础成本
        base = self.base_commission + self.base_slippage

        # 订单大小因子
        participation = order.quantity / market_state.avg_daily_volume
        size_multiplier = 1 + participation  # 简化：线性关系

        total = base * size_multiplier

        return OrderCost(
            commission=self.base_commission,
            slippage=self.base_slippage * size_multiplier,
            market_impact=0,  # 简化：合并到滑点
            timing_cost=0,
            total_cost=total
        )
```

#### 8.3.2 智能订单路由器

```python
"""
文件：packages/engine/src/ditto_engine/execution/smart_router.py
新增：智能订单执行
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum


class ExecutionStrategy(Enum):
    """执行策略"""
    MARKET = "market"          # 市价单（小单）
    TWAP = "twap"              # 时间加权平均价格（大单）
    VWAP = "vwap"              # 成交量加权平均价格
    ARRIVAL_PRICE = "arrival"  # 到达价格（追求最小化Implementation Shortfall）


@dataclass
class SubOrder:
    """子订单"""
    parent_order_id: str
    sub_order_id: str
    symbol: str
    direction: str
    quantity: int
    execute_time: datetime     # 预定执行时间
    urgency: float             # 紧急程度 [0, 1]


class SmartOrderRouter:
    """智能订单路由器

    职责：
    1. 判断订单大小，选择执行策略
    2. 大单拆分（TWAP/VWAP）
    3. 时间分配
    4. 成本优化
    """

    def __init__(self, cost_model: DynamicCostModel):
        self.cost_model = cost_model

        # 阈值配置
        self.small_order_threshold = 0.01   # 小单：< 1% ADV
        self.large_order_threshold = 0.05   # 大单：> 5% ADV

    def route_order(
        self,
        order: 'Order',
        market_state: MarketState,
        time_budget: int = 600  # 秒，默认10分钟
    ) -> List[SubOrder]:
        """路由订单

        Args:
            order: 原始订单
            market_state: 市场状态
            time_budget: 执行时间预算（秒）

        Returns:
            List[SubOrder]: 子订单列表
        """

        # 1. 计算参与率
        participation = order.quantity / market_state.avg_daily_volume

        # 2. 选择执行策略
        if participation < self.small_order_threshold:
            # 小单：直接市价
            strategy = ExecutionStrategy.MARKET
        elif participation < self.large_order_threshold:
            # 中单：TWAP
            strategy = ExecutionStrategy.TWAP
        else:
            # 大单：VWAP或分多日执行
            strategy = ExecutionStrategy.VWAP

        # 3. 生成子订单
        if strategy == ExecutionStrategy.MARKET:
            return self._market_execution(order)
        elif strategy == ExecutionStrategy.TWAP:
            return self._twap_execution(order, time_budget)
        elif strategy == ExecutionStrategy.VWAP:
            return self._vwap_execution(order, time_budget, market_state)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _market_execution(self, order: 'Order') -> List[SubOrder]:
        """市价执行（不拆单）"""
        return [SubOrder(
            parent_order_id=order.order_id,
            sub_order_id=f"{order.order_id}_0",
            symbol=order.symbol,
            direction=order.direction,
            quantity=order.quantity,
            execute_time=datetime.now(),
            urgency=1.0
        )]

    def _twap_execution(
        self,
        order: 'Order',
        time_budget: int
    ) -> List[SubOrder]:
        """TWAP执行（时间均分）

        将订单均匀分布在时间窗口内
        """
        # 决定拆分数量（通常5-10笔）
        num_slices = min(10, max(5, time_budget // 60))

        # 每笔数量
        slice_quantity = order.quantity // num_slices
        remainder = order.quantity % num_slices

        # 时间间隔
        interval = time_budget / num_slices

        # 生成子订单
        sub_orders = []
        current_time = datetime.now()

        for i in range(num_slices):
            qty = slice_quantity + (1 if i < remainder else 0)

            sub_orders.append(SubOrder(
                parent_order_id=order.order_id,
                sub_order_id=f"{order.order_id}_{i}",
                symbol=order.symbol,
                direction=order.direction,
                quantity=qty,
                execute_time=current_time + timedelta(seconds=i * interval),
                urgency=0.5
            ))

        return sub_orders

    def _vwap_execution(
        self,
        order: 'Order',
        time_budget: int,
        market_state: MarketState
    ) -> List[SubOrder]:
        """VWAP执行（成交量加权）

        根据历史成交量分布，分配子订单

        简化版：假设成交量分布
        - 10:00-10:30: 20%
        - 10:30-11:00: 15%
        - 11:00-11:30: 10%
        - 13:30-14:00: 15%
        - 14:00-14:30: 20%
        - 其他: 20%
        """

        # TODO: 从历史数据获取真实的成交量分布
        # 现在使用简化的分布
        volume_profile = {
            time(10, 0): 0.20,
            time(10, 30): 0.15,
            time(11, 0): 0.10,
            time(13, 30): 0.15,
            time(14, 0): 0.20,
            time(14, 30): 0.20
        }

        # 按成交量分布生成子订单
        sub_orders = []
        for i, (exec_time, weight) in enumerate(volume_profile.items()):
            qty = int(order.quantity * weight)

            if qty > 0:
                sub_orders.append(SubOrder(
                    parent_order_id=order.order_id,
                    sub_order_id=f"{order.order_id}_{i}",
                    symbol=order.symbol,
                    direction=order.direction,
                    quantity=qty,
                    execute_time=datetime.combine(datetime.today(), exec_time),
                    urgency=0.6
                ))

        return sub_orders


class SimplifiedRouter(SmartOrderRouter):
    """简化路由器（Phase 1可用）

    只实现TWAP，不实现VWAP
    """

    def route_order(
        self,
        order: 'Order',
        market_state: MarketState,
        time_budget: int = 600
    ) -> List[SubOrder]:
        """简化路由：只区分小单和大单"""

        participation = order.quantity / market_state.avg_daily_volume

        if participation < 0.02:  # 2% ADV
            # 小单：直接执行
            return self._market_execution(order)
        else:
            # 大单：TWAP拆分
            return self._twap_execution(order, time_budget)
```

#### 8.3.3 执行管理器

```python
"""
文件：packages/engine/src/ditto_engine/execution/execution_manager.py
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import polars as pl


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    created_at: datetime
    rebalance_plan_id: str

    # 执行明细
    sub_orders: List[SubOrder]

    # 预期成本
    estimated_cost: OrderCost
    estimated_impact: float

    # 状态
    status: str = "pending"  # pending / executing / completed / failed


@dataclass
class ExecutionResult:
    """执行结果"""
    plan_id: str
    executed_at: datetime

    # 实际成交
    actual_fills: List[Dict]  # 成交记录
    actual_cost: OrderCost
    actual_impact: float

    # 执行质量
    implementation_shortfall: float  # IS = (执行价 - 决策价) / 决策价
    slippage_vs_estimated: float     # 实际滑点 vs 预估滑点


class ExecutionManager:
    """执行管理器

    职责：
    1. 接收调仓计划
    2. 生成执行计划
    3. 协调订单执行
    4. 评估执行质量
    """

    def __init__(
        self,
        cost_model: DynamicCostModel,
        router: SmartOrderRouter,
        market_data_service: 'MarketDataService'
    ):
        self.cost_model = cost_model
        self.router = router
        self.market_data = market_data_service

    def create_execution_plan(
        self,
        rebalance_plan: 'RebalancePlan'
    ) -> ExecutionPlan:
        """创建执行计划

        Args:
            rebalance_plan: 调仓计划

        Returns:
            ExecutionPlan: 包含所有子订单的执行计划
        """

        all_sub_orders = []
        total_cost = 0
        total_impact = 0

        # 对每个目标持仓生成执行计划
        for target in rebalance_plan.targets:
            # 1. 获取市场状态
            market_state = self.market_data.get_market_state(target.symbol)

            # 2. 创建订单
            order = self._create_order_from_target(target)

            # 3. 路由订单（拆分）
            sub_orders = self.router.route_order(order, market_state)
            all_sub_orders.extend(sub_orders)

            # 4. 估算成本
            cost = self.cost_model.estimate_cost(order, market_state)
            total_cost += cost.total_cost * target.notional_value
            total_impact += cost.market_impact * target.notional_value

        # 5. 创建执行计划
        plan = ExecutionPlan(
            plan_id=f"exec_{rebalance_plan.plan_id}",
            created_at=datetime.now(),
            rebalance_plan_id=rebalance_plan.plan_id,
            sub_orders=all_sub_orders,
            estimated_cost=OrderCost(
                commission=0, slippage=0, market_impact=0, timing_cost=0,
                total_cost=total_cost
            ),
            estimated_impact=total_impact
        )

        return plan

    def execute_plan(
        self,
        plan: ExecutionPlan,
        broker: 'BrokerAdapter'
    ) -> ExecutionResult:
        """执行计划

        Phase 1: 只生成计划，不实际执行（纸面交易）
        Phase 2: 对接券商API，实际执行
        """

        # Phase 1: 模拟执行
        plan.status = "executing"

        # TODO: Phase 2实现实际执行
        # for sub_order in plan.sub_orders:
        #     broker.send_order(sub_order)

        plan.status = "completed"

        # 生成执行结果（Phase 1是模拟的）
        result = ExecutionResult(
            plan_id=plan.plan_id,
            executed_at=datetime.now(),
            actual_fills=[],
            actual_cost=plan.estimated_cost,
            actual_impact=plan.estimated_impact,
            implementation_shortfall=0.0,
            slippage_vs_estimated=0.0
        )

        return result

    def _create_order_from_target(self, target: 'TargetPosition') -> 'Order':
        """从目标持仓创建订单"""
        # 简化实现
        return Order(
            order_id=f"order_{target.symbol}_{datetime.now().timestamp()}",
            symbol=target.symbol,
            direction='BUY' if target.action == 'INCREASE' else 'SELL',
            quantity=abs(target.quantity_change),
            order_type='MARKET'
        )

    def analyze_execution_quality(
        self,
        result: ExecutionResult,
        plan: ExecutionPlan
    ) -> Dict:
        """分析执行质量

        Returns:
            包含各项执行指标的字典
        """

        return {
            'implementation_shortfall': result.implementation_shortfall,
            'cost_accuracy': 1 - result.slippage_vs_estimated,
            'fill_rate': len(result.actual_fills) / len(plan.sub_orders),
            'avg_fill_time': self._calc_avg_fill_time(result.actual_fills),
            'total_cost_bps': result.actual_cost.to_bps()
        }

    def _calc_avg_fill_time(self, fills: List[Dict]) -> float:
        """计算平均成交时间"""
        if not fills:
            return 0.0

        times = [f['fill_time'] for f in fills]
        return sum(times) / len(times)
```

#### 8.3.4 市场数据服务

```python
"""
文件：packages/engine/src/ditto_engine/execution/market_data_service.py
Phase 1: 使用历史数据模拟
Phase 2: 接入实时行情
"""

class MarketDataService:
    """市场数据服务

    Phase 1: 从数据库读取历史数据模拟
    Phase 2: 接入实时行情API
    """

    def __init__(self, data_service: 'DataService'):
        self.data = data_service

    def get_market_state(self, symbol: str) -> MarketState:
        """获取市场状态

        Phase 1: 使用历史数据
        Phase 2: 使用实时数据
        """

        # Phase 1实现：从数据库读取最近数据
        latest = self.data.get_latest_kline(symbol)

        # 模拟买卖价差（假设0.1%）
        mid_price = latest['close']
        spread = mid_price * 0.001

        return MarketState(
            symbol=symbol,
            bid_price=mid_price - spread / 2,
            ask_price=mid_price + spread / 2,
            spread=spread,
            volume_today=latest['volume'],
            avg_daily_volume=self._get_avg_volume(symbol),
            realized_vol=self._get_realized_vol(symbol),
            time_of_day=datetime.now().time()
        )

    def _get_avg_volume(self, symbol: str) -> float:
        """获取平均日成交量（60日）"""
        df = self.data.get_kline(symbol, lookback_days=60)
        return df['volume'].mean()

    def _get_realized_vol(self, symbol: str) -> float:
        """获取已实现波动率（20日）"""
        df = self.data.get_kline(symbol, lookback_days=20)
        returns = df['close'].pct_change()
        return returns.std() * (252 ** 0.5)
```

---

### 8.4 执行日志与分析

#### 8.4.1 执行分析器

```python
"""
文件：packages/engine/src/ditto_engine/execution/execution_analyzer.py
"""

import polars as pl
from typing import Dict


class ExecutionAnalyzer:
    """执行分析器

    分析执行质量，生成报告
    """

    def __init__(self, db_path: str):
        self.db = pl.read_database(f"sqlite:///{db_path}")

    def analyze_period(
        self,
        start_date: date,
        end_date: date
    ) -> Dict:
        """分析一段时间的执行质量

        Returns:
            包含各项指标的字典
        """

        # 读取执行日志
        logs = self.db.query(f"""
            SELECT * FROM execution_log
            WHERE execute_time BETWEEN '{start_date}' AND '{end_date}'
        """)

        if len(logs) == 0:
            return {'no_data': True}

        # 计算指标
        return {
            'total_orders': len(logs),
            'fill_rate': (logs['fill_status'] == 'FILLED').mean(),
            'avg_slippage_bps': logs['slippage'].mean() * 10000,
            'avg_commission_bps': logs['commission'].mean() * 10000,
            'avg_total_cost_bps': (
                logs['commission'] + logs['slippage'] + logs['market_impact']
            ).mean() * 10000,
            'avg_implementation_shortfall': logs['implementation_shortfall'].mean(),
            'cost_by_strategy': self._cost_by_strategy(logs),
            'cost_by_symbol': self._cost_by_symbol(logs)
        }

    def _cost_by_strategy(self, logs: pl.DataFrame) -> Dict:
        """按策略类型分组统计成本"""
        return logs.group_by('strategy_type').agg([
            pl.col('slippage').mean().alias('avg_slippage'),
            pl.col('market_impact').mean().alias('avg_impact')
        ]).to_dict()

    def _cost_by_symbol(self, logs: pl.DataFrame) -> Dict:
        """按标的分组统计成本"""
        return logs.group_by('symbol').agg([
            pl.col('slippage').mean().alias('avg_slippage'),
            pl.count().alias('order_count')
        ]).to_dict()
```

---


## 9. 券商交易接口适配

本节为 Phase 2（实盘交易）预留执行层抽象，目标：

- 将“生成调仓计划/订单”的逻辑与“具体券商/交易通道”的实现解耦；
- 保证回测 / 纸面交易 / 实盘交易共用相同的信号与订单对象模型；
- 未来扩展到不同券商或仿真环境时，只需新增适配器，而无需修改核心引擎。

---

### 9.1 核心概念与边界

执行层的主要对象：

- **Order（订单）**
  - 由轮动/策略引擎生成；
  - 包含：标的、买卖方向、数量/金额、价格类型（市价/限价）等。
- **PositionSnapshot（持仓快照）**
  - 从券商/仿真引擎读取的当前持仓状态；
- **AccountSnapshot（账户快照）**
  - 可用资金、总资产、市值等；
- **OrderStatus / Trade**
  - 订单状态及成交记录。

**边界约束：**

- 核心引擎只关心：
  - “我要买/卖什么、多少、在什么约束下”；
- 不关心：
  - “如何连上券商”、“具体使用 MiniQMT 还是其他 API”。

所有与具体券商/通道相关的逻辑，都集中在 `BrokerAdapter` 的实现中。

---

### 9.2 BrokerAdapter 接口草案

以 Python `Protocol` 形式定义执行适配器接口（仅示意，后续可细化类型）：

```python
# packages/engine/src/execution/interfaces.py
from typing import Protocol, Iterable
from dataclasses import dataclass
from datetime import datetime

InstrumentId = str
BrokerOrderId = str


@dataclass
class AccountSnapshot:
    total_equity: float
    cash_available: float
    cash_locked: float
    timestamp: datetime


@dataclass
class PositionSnapshot:
    instrument_id: InstrumentId
    qty: int
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    timestamp: datetime


@dataclass
class Order:
    instrument_id: InstrumentId
    side: str           # 'BUY' or 'SELL'
    qty: int
    order_type: str     # 'MARKET' / 'LIMIT'
    limit_price: float | None
    client_order_id: str | None = None


@dataclass
class OrderStatus:
    broker_order_id: BrokerOrderId
    client_order_id: str | None
    instrument_id: InstrumentId
    side: str
    qty: int
    filled_qty: int
    status: str         # 'NEW'/'PARTIALLY_FILLED'/'FILLED'/'CANCELLED'/...
    avg_fill_price: float | None
    last_updated: datetime


@dataclass
class Trade:
    broker_order_id: BrokerOrderId
    instrument_id: InstrumentId
    side: str
    qty: int
    price: float
    traded_at: datetime


class BrokerAdapter(Protocol):
    """执行适配器统一接口（Phase 2 由具体券商实现）"""

    # 账户 / 持仓查询
    def get_account(self) -> AccountSnapshot: ...
    def get_positions(self) -> list[PositionSnapshot]: ...

    # 下单与撤单
    def send_order(self, order: Order) -> BrokerOrderId: ...
    def cancel_order(self, broker_order_id: BrokerOrderId) -> None: ...

    # 订单 / 成交回报查询
    def get_orders(self, since: datetime | None = None) -> list[OrderStatus]: ...
    def get_trades(self, since: datetime | None = None) -> list[Trade]: ...
```
后续在 Phase 2 中实现例如：

PaperBrokerAdapter：基于 simulated_positions + rebalance_plans 的仿真执行；

MiniQMTBrokerAdapter：封装 MiniQMT/券商 API；

其他券商 / 模拟环境适配器。
