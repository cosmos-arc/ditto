# Feature & Factor Calculation Engines Design

**目标**: 设计 Core 层的特征和因子计算引擎，实现计算与存储的清晰分离。

**实现状态**:
- ✅ **Phase 7-8 (存储层)**: 已实现 - DataHub 层的 Macro/Features/Factors 三域存储
- ⏳ **Phase 9-10 (计算引擎)**: 待实现 - Core 层的计算引擎

> **注意**: 本文档包含的代码实现是**设计示例**，用于说明接口和架构设计。实际实现时应创建独立的源代码文件（如 `packages/core/src/ditto_core/features/calculator.py`），而非直接复制本文档中的代码。

**架构原则**:
- **Core 层**: 纯计算逻辑，无状态
- **DataHub 层**: 纯存储，无计算逻辑
- **Port 层**: 编排服务，协调工作流

---

## 目录

- [1. 架构概览](#1-架构概览)
- [2. Feature Engine 设计](#2-feature-engine-设计)
- [3. Factor Engine 设计](#3-factor-engine-设计)
- [4. Alpha 表达式引擎](#4-alpha-表达式引擎)
- [5. Calculator Registry 模式](#5-calculator-registry-模式)
- [6. 配置驱动设计](#6-配置驱动设计)
- [7. 层间接口](#7-层间接口)
- [8. 错误处理](#8-错误处理)
- [9. 性能优化](#9-性能优化)
- [10. 业界最佳实践](#10-业界最佳实践)

---

## 1. 架构概览

### 1.1 三层分离

```
┌─────────────────────────────────────────────────────────────┐
│                    Port Layer (Orchestration)                │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │ FeatureCalculationService│  │ FactorCalculationService │ │
│  └──────────────────────────┘  └──────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────┐
│                      Core Layer (Calculation)                │
│  ┌──────────────────────────┐  ┌──────────────────────────┐ │
│  │    FeatureEngine         │  │     FactorEngine         │ │
│  │  ┌────────────────────┐  │  │  ┌────────────────────┐  │ │
│  │  │ FeatureCalculator  │  │  │  │  FactorCalculator  │  │ │
│  │  │   Registry         │  │  │  │    Registry        │  │ │
│  │  └────────────────────┘  │  │  └────────────────────┘  │ │
│  └──────────────────────────┘  └──────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────┐
│                      DataHub Layer (Storage)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │Indicator │  │ Indicator│  │  Factor  │  │  Factor  │    │
│  │  Store   │  │Metadata  │  │  Store   │  │Metadata  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据分层逻辑

**核心原则**: 严格区分"指标/特征"和"因子/信号"，避免概念混淆。

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层 (模型)                             │
│  ┌──────────────────┐  ┌──────────────────────────┐          │
│  │ Alpha 组合模型    │  │    风险模型 (Barra)     │          │
│  │ (取用 Factors)   │  │    (取用 Factors)      │          │
│  └──────────────────┘  └──────────────────────────┘          │
└───────────────────────────────┬─────────────────────────────┘
                                │ 取用因子
┌───────────────────────────────▼─────────────────────────────┐
│                  Factors 域 (信号层) - DataHub                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  所有因子都需要 PIT                                    │   │
│  │  - Alpha101/191/360: alpha101_001, alpha191_001...    │   │
│  │  - Barra 风格: factor_momentum_12m, factor_size...    │   │
│  │  - A 股特有: factor_northbound_flow...               │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────┘
                                │ 取用特征
┌───────────────────────────────▼─────────────────────────────┐
│                  Features 域 (指标层) - DataHub                  │
│  ┌────────────────────────┐  ┌──────────────────────────┐    │
│  │ Technical (无需 PIT)    │  │ Fundamental (需要 PIT)   │    │
│  │ - indicator_sma_20     │  │ - indicator_pe           │    │
│  │ - indicator_rsi_14     │  │ - indicator_roe           │    │
│  │ - indicator_macd       │  │ - indicator_eps           │    │
│  │ - indicator_atr_14     │  │ - indicator_pb_ratio      │    │
│  └────────────────────────┘  └──────────────────────────┘    │
└───────────────────────────────┬─────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────┐
│                      Market/Fundamental 域 - DataHub            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐       │
│  │   Bars   │  │Financial │  │     Metadata         │       │
│  └──────────┘  └──────────┘  └──────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

#### 1.2.1 PIT 需求明确

| 类型 | 子类型 | PIT 需求 | 示例 |
|------|--------|----------|------|
| **Features** | Technical | **无需 PIT** | SMA, RSI, MACD - 公式固定 |
| **Features** | Fundamental | **需要 PIT** | PE, ROE - 财报可能重述 |
| **Factors** | 所有类型 | **需要 PIT** | Alpha101, Barra, A股特有 |

#### 1.2.2 命名规范

| 层级 | 前缀 | 示例 | 存储位置 |
|------|------|------|----------|
| Technical Features | `indicator_*` | indicator_sma_20, indicator_rsi_14 | features/technical/ |
| Fundamental Features | `indicator_*` | indicator_pe, indicator_roe | features/fundamental/ |
| Alpha Factors | `alpha101_*`, `alpha191_*` | alpha101_001, alpha191_001 | factors/alpha/ |
| Barra Factors | `factor_*` | factor_momentum_12m | factors/barra/ |
| A股 Factors | `factor_*` | factor_northbound_flow | factors/a_share/ |

### 1.3 核心设计原则

| 原则 | Core 层 | DataHub 层 | Port 层 |
|------|---------|------------|---------|
| **职责** | 计算逻辑 | 数据存储 | 工作流编排 |
| **状态** | 无状态 | 持久化 | 无状态 |
| **依赖** | 依赖 DataHub Store | 无依赖 Core | 依赖 Core + DataHub |
| **测试** | 单元测试（纯计算） | 集成测试 | 端到端测试 |

---

## 2. Feature Engine 设计

### 2.1 FeatureCalculator 基类

```python
"""
packages/core/src/ditto_core/features/calculator.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from ditto_core.features.types import IndicatorSpec


class FeatureCalculator(ABC):
    """
    特征计算器基类.

    每个 Indicator 对应一个 Calculator 实现:
    - 负责具体的计算逻辑
    - 声明所需的数据列
    - 声明支持的参数

    Calculator 是无状态的，所有配置通过 __init__ 传入。
    """

    # Class-level registry for calculator lookup
    _registry: dict[str, type[FeatureCalculator]] = {}

    def __init__(self, spec: IndicatorSpec) -> None:
        """
        Initialize calculator with indicator specification.

        Args:
            spec: Indicator specification with parameters.

        """
        self._spec = spec

    @classmethod
    def register(cls, indicator_id: str) -> callable:
        """
        装饰器：注册 Calculator 到 registry.

        Usage:
            @FeatureCalculator.register("indicator_rsi_14")
            class RSI14Calculator(FeatureCalculator):
                ...
        """
        def decorator(calc_class: type[FeatureCalculator]) -> type[FeatureCalculator]:
            cls._registry[indicator_id] = calc_class
            return calc_class
        return decorator

    @classmethod
    def get_calculator(cls, indicator_id: str, spec: IndicatorSpec) -> FeatureCalculator:
        """
        根据 indicator_id 获取 Calculator 实例.

        Args:
            indicator_id: Indicator 标识符 (e.g., "indicator_rsi_14")
            spec: Indicator specification.

        Returns:
            Calculator instance.

        Raises:
            ValueError: 如果 indicator_id 未注册.

        """
        if indicator_id not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unknown indicator_id: {indicator_id}. "
                f"Available: {available}"
            )
        calc_class = cls._registry[indicator_id]
        return calc_class(spec)

    @classmethod
    def list_indicators(cls) -> list[str]:
        """获取所有已注册的 indicator_id."""
        return sorted(cls._registry.keys())

    # ============ Abstract methods (must implement) ============

    @property
    @abstractmethod
    def required_columns(self) -> list[str]:
        """
        声明计算所需的数据列.

        Returns:
            列名列表，例如 ["close", "volume"].

        """
        ...

    @property
    def min_periods(self) -> int:
        """
        声明计算所需的最小周期数.

        Returns:
            最小周期数，默认为参数中的 period.

        """
        # Default implementation: use period from spec
        return self._spec.params.get("period", 1)

    @abstractmethod
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        执行计算.

        Args:
            df: 输入数据，包含 sid, trade_date 和 required_columns.
                数据已按 (sid, trade_date) 排序.

        Returns:
            计算结果，包含三列:
            - sid: security ID
            - trade_date: 交易日期
            - value: 计算值

        Raises:
            ValueError: 如果缺少必需的列.

        """
        ...

    def validate_input(self, df: pl.DataFrame) -> None:
        """
        验证输入数据.

        Args:
            df: 输入数据.

        Raises:
            ValueError: 如果缺少必需的列.

        """
        missing = set(self.required_columns) - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Required: {self.required_columns}, Got: {df.columns}"
            )
```

### 2.2 具体 Calculator 实现

```python
"""
packages/core/src/ditto_core/features/calculators/indicators.py
"""

from __future__ import annotations

import polars as pl
from ditto_core.features.calculator import FeatureCalculator
from ditto_core.features.types import IndicatorSpec


# Trend Indicators


@FeatureCalculator.register("indicator_sma_20")
class SMA20Calculator(FeatureCalculator):
    """20-day Simple Moving Average."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 20

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        period = self._spec.params.get("period", 20)
        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("close")
                .rolling_mean(window_size=period, min_periods=period)
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


@FeatureCalculator.register("indicator_ema_12")
class EMA12Calculator(FeatureCalculator):
    """12-day Exponential Moving Average."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 12

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        period = self._spec.params.get("period", 12)
        alpha = 2 / (period + 1)
        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("close")
                .ewm_mean(alpha=alpha, adjust=False)
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


# Momentum Indicators


@FeatureCalculator.register("indicator_rsi_14")
class RSI14Calculator(FeatureCalculator):
    """14-day Relative Strength Index."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 15  # period + 1

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        period = self._spec.params.get("period", 14)

        # Calculate price changes
        result = (
            df.sort("trade_date")
            .with_columns(
                (pl.col("close") - pl.col("close").shift(1))
                .alias("delta")
            )
            .with_columns(
                pl.when(pl.col("delta") > 0)
                .then(pl.col("delta"))
                .otherwise(0)
                .alias("gain"),
                pl.when(pl.col("delta") < 0)
                .then(-pl.col("delta"))
                .otherwise(0)
                .alias("loss"),
            )
            .with_columns(
                pl.col("gain")
                .rolling_mean(window_size=period, min_periods=1)
                .alias("avg_gain"),
                pl.col("loss")
                .rolling_mean(window_size=period, min_periods=1)
                .alias("avg_loss"),
            )
            .with_columns(
                rs=pl.col("avg_gain") / pl.col("avg_loss"),
            )
            .with_columns(
                (100 - (100 / (1 + pl.col("rs"))))
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


@FeatureCalculator.register("indicator_macd")
class MACDCalculator(FeatureCalculator):
    """MACD (Moving Average Convergence Divergence)."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 26

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        fast = self._spec.params.get("fast", 12)
        slow = self._spec.params.get("slow", 26)
        signal = self._spec.params.get("signal", 9)

        fast_alpha = 2 / (fast + 1)
        slow_alpha = 2 / (slow + 1)
        signal_alpha = 2 / (signal + 1)

        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("close")
                .ewm_mean(alpha=fast_alpha, adjust=False)
                .alias("ema_fast"),
                pl.col("close")
                .ewm_mean(alpha=slow_alpha, adjust=False)
                .alias("ema_slow"),
            )
            .with_columns(
                (pl.col("ema_fast") - pl.col("ema_slow"))
                .alias("macd_line")
            )
            .with_columns(
                pl.col("macd_line")
                .ewm_mean(alpha=signal_alpha, adjust=False)
                .alias("signal_line")
            )
            .with_columns(
                (pl.col("macd_line") - pl.col("signal_line"))
                .alias("value")  # MACD histogram
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


# Volatility Indicators


@FeatureCalculator.register("indicator_bollinger_bands_20")
class BollingerBands20Calculator(FeatureCalculator):
    """20-day Bollinger Bands (returns bandwidth)."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 20

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        period = self._spec.params.get("period", 20)
        std_dev = self._spec.params.get("std_dev", 2)

        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("close")
                .rolling_mean(window_size=period, min_periods=period)
                .alias("sma"),
                pl.col("close")
                .rolling_std(window_size=period, min_periods=period)
                .alias("std"),
            )
            .with_columns(
                upper=pl.col("sma") + pl.col("std") * std_dev,
                lower=pl.col("sma") - pl.col("std") * std_dev,
            )
            .with_columns(
                # Bandwidth: (upper - lower) / sma
                ((pl.col("upper") - pl.col("lower")) / pl.col("sma"))
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


@FeatureCalculator.register("indicator_atr_14")
class ATR14Calculator(FeatureCalculator):
    """14-day Average True Range."""

    @property
    def required_columns(self) -> list[str]:
        return ["high", "low", "close"]

    @property
    def min_periods(self) -> int:
        return 14

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        period = self._spec.params.get("period", 14)

        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("high").alias("prev_high"),
                pl.col("low").alias("prev_low"),
                pl.col("close").shift(1).alias("prev_close"),
            )
            .with_columns(
                pl.max_horizontal(
                    pl.col("high") - pl.col("low"),
                    (pl.col("high") - pl.col("prev_close")).abs(),
                    (pl.col("low") - pl.col("prev_close")).abs(),
                ).alias("tr")
            )
            .with_columns(
                pl.col("tr")
                .rolling_mean(window_size=period, min_periods=1)
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result


# Volume Indicators


@FeatureCalculator.register("indicator_obv")
class OBVCalculator(FeatureCalculator):
    """On-Balance Volume."""

    @property
    def required_columns(self) -> list[str]:
        return ["close", "volume"]

    @property
    def min_periods(self) -> int:
        return 1

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        result = (
            df.sort("trade_date")
            .with_columns(
                pl.when(pl.col("close") > pl.col("close").shift(1))
                .then(pl.col("volume"))
                .when(pl.col("close") < pl.col("close").shift(1))
                .then(-pl.col("volume"))
                .otherwise(0)
                .alias("obv_delta")
            )
            .with_columns(
                pl.col("obv_delta")
                .cum_sum()
                .alias("value")
            )
            .select(["sid", "trade_date", "value"])
        )
        return result
```

### 2.3 FeatureEngine

```python
"""
packages/core/src/ditto_core/features/engine.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import logger, traced

if TYPE_CHECKING:
    from ditto_datahub.domains.features import FeatureService
    from ditto_datahub.domains.market import MarketService


@dataclass(frozen=True)
class CalculationResult:
    """计算结果."""
    indicator_id: str
    added: int
    failed: int
    duration_ms: float


class FeatureEngine:
    """
    Feature calculation engine.

    职责:
    - 协调多个 Calculator 的执行
    - 读取源数据
    - 批量计算
    - 写入结果到 DataHub

    不负责:
    - 数据存储 (由 DataHub 负责)
    - 工作流编排 (由 Port Service 负责)
    """

    def __init__(
        self,
        feature_service: FeatureService,
        market_service: MarketService,
    ) -> None:
        """
        Initialize FeatureEngine.

        Args:
            feature_service: DataHub FeatureService for storage.
            market_service: DataHub MarketService for source data.

        """
        self._features = feature_service
        self._market = market_service

    @traced("features.calculate_batch")
    def calculate_batch(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
        indicator_specs: list[IndicatorSpec],
    ) -> list[CalculationResult]:
        """
        批量计算多个 indicator.

        Args:
            sids: Security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_specs: Indicator specifications to calculate.

        Returns:
            List of calculation results.

        """
        import time
        from ditto_core.features.calculator import FeatureCalculator

        results: list[CalculationResult] = []

        # 读取源数据 (一次读取，多个 calculator 共享)
        logger.info(
            "Reading source data for feature calculation",
            event="feature_calculation_start",
            sids_count=len(sids),
            start_date=start_date,
            end_date=end_date,
            indicators_count=len(indicator_specs),
        )

        source_df = self._market.get_bars(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )

        if source_df.is_empty():
            logger.warning(
                "No source data found",
                event="feature_calculation_empty",
            )
            return results

        # 对每个 indicator 进行计算
        for spec in indicator_specs:
            start = time.time()
            indicator_id = spec.indicator_id

            try:
                calculator = FeatureCalculator.get_calculator(indicator_id, spec)

                # 分组计算 (按 sid)
                calculated_dfs = []
                for sid in sids:
                    sid_df = source_df.filter(pl.col("sid") == sid)
                    if sid_df.len() < calculator.min_periods:
                        logger.warning(
                            f"Insufficient data for {indicator_id} sid={sid}",
                            event="feature_calculation_insufficient_data",
                            indicator_id=indicator_id,
                            sid=sid,
                            rows=sid_df.len(),
                            min_periods=calculator.min_periods,
                        )
                        continue

                    calculator.validate_input(sid_df)
                    result_df = calculator.calculate(sid_df)
                    calculated_dfs.append(result_df)

                if not calculated_dfs:
                    logger.warning(
                        f"No data calculated for {indicator_id}",
                        event="feature_calculation_no_data",
                        indicator_id=indicator_id,
                    )
                    results.append(CalculationResult(
                        indicator_id=indicator_id,
                        added=0,
                        failed=0,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                    continue

                # 合并结果
                combined = pl.concat(calculated_dfs)

                # 添加 indicator_id 列
                combined = combined.with_columns(
                    pl.lit(indicator_id).alias("indicator_id")
                )

                # 写入 DataHub (按年份分区)
                added_total = 0
                for year in combined["trade_date"].dt.year().unique():
                    year_df = combined.filter(
                        pl.col("trade_date").dt.year() == year
                    )
                    write_result = self._features.write_indicator(
                        df=year_df,
                        year=year,
                    )
                    added_total += write_result.added

                duration_ms = (time.time() - start) * 1000
                results.append(CalculationResult(
                    indicator_id=indicator_id,
                    added=added_total,
                    failed=0,
                    duration_ms=duration_ms,
                ))

                logger.info(
                    f"Calculated {indicator_id}",
                    event="feature_calculation_complete",
                    indicator_id=indicator_id,
                    added=added_total,
                    duration_ms=round(duration_ms, 2),
                )

            except Exception as e:
                logger.error(
                    f"Failed to calculate {indicator_id}: {e}",
                    event="feature_calculation_failed",
                    indicator_id=indicator_id,
                    error=str(e),
                )
                results.append(CalculationResult(
                    indicator_id=indicator_id,
                    added=0,
                    failed=len(sids),
                    duration_ms=(time.time() - start) * 1000,
                ))

        return results

    @traced("features.list_indicators")
    def list_indicators(self) -> list[str]:
        """获取所有可用的 indicator_id."""
        from ditto_core.features.calculator import FeatureCalculator
        return FeatureCalculator.list_indicators()
```

---

## 3. Factor Engine 设计

### 3.1 FactorCalculator 基类

```python
"""
packages/core/src/ditto_core/factors/calculator.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from ditto_core.factors.types import FactorSpec


class FactorCalculator(ABC):
    """
    因子计算器基类.

    与 FeatureCalculator 的区别:
    - 计算原始因子值 (raw_value)
    - 自动标准化为因子暴露 (exposure, z-score)
    - 生成 PIT 元数据 (effective_from, effective_to)

    Calculator 是无状态的，所有配置通过 __init__ 传入。
    """

    # Class-level registry
    _registry: dict[str, type[FactorCalculator]] = {}

    def __init__(self, spec: FactorSpec) -> None:
        """
        Initialize calculator with factor specification.

        Args:
            spec: Factor specification with parameters.

        """
        self._spec = spec

    @classmethod
    def register(cls, factor_id: str) -> callable:
        """
        装饰器：注册 Calculator 到 registry.

        Usage:
            @FactorCalculator.register("factor_momentum_12m")
            class Momentum12MCalculator(FactorCalculator):
                ...
        """
        def decorator(calc_class: type[FactorCalculator]) -> type[FactorCalculator]:
            cls._registry[factor_id] = calc_class
            return calc_class
        return decorator

    @classmethod
    def get_calculator(cls, factor_id: str, spec: FactorSpec) -> FactorCalculator:
        """
        根据 factor_id 获取 Calculator 实例.

        Args:
            factor_id: Factor 标识符.
            spec: Factor specification.

        Returns:
            Calculator instance.

        Raises:
            ValueError: 如果 factor_id 未注册.

        """
        if factor_id not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unknown factor_id: {factor_id}. "
                f"Available: {available}"
            )
        calc_class = cls._registry[factor_id]
        return calc_class(spec)

    @classmethod
    def list_factors(cls) -> list[str]:
        """获取所有已注册的 factor_id."""
        return sorted(cls._registry.keys())

    # ============ Abstract methods ============

    @property
    @abstractmethod
    def required_features(self) -> list[str]:
        """
        声明计算所需的 features.

        Returns:
            indicator_id 列表，例如 ["indicator_sma_20", "indicator_rsi_14"].

        """
        ...

    @property
    def required_columns(self) -> list[str]:
        """
        声明计算所需的其他数据列.

        Returns:
            列名列表，例如 ["close", "market_cap"].

        """
        return []

    @abstractmethod
    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        计算原始因子值.

        Args:
            df: 输入数据，包含 sid, trade_date, required_features, required_columns.
                数据已按 (sid, trade_date) 排序.

        Returns:
            计算结果，包含三列:
            - sid: security ID
            - trade_date: 交易日期
            - raw_value: 原始因子值 (未标准化)

        """
        ...

    # ============ Common methods ============

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        标准化为因子暴露 (z-score).

        Args:
            df: 包含 raw_value 的 DataFrame.

        Returns:
            添加 exposure 列的 DataFrame.

        """
        # 按日期分组计算 z-score
        result = df.with_columns(
            pl.col("raw_value")
            .rank()  # 先做 rank 避免极端值影响
            .alias("rank")
        )
        # 按 trade_date 分组标准化
        mean = result.group_by("trade_date").agg(
            pl.col("rank").mean().alias("mean")
        )
        std = result.group_by("trade_date").agg(
            pl.col("rank").std().alias("std")
        )

        result = result.join(mean, on="trade_date").join(std, on="trade_date")
        result = result.with_columns(
            ((pl.col("rank") - pl.col("mean")) / pl.col("std"))
            .alias("exposure")
        )
        return result.drop(["rank", "mean", "std"])

    def add_pit_metadata(
        self,
        df: pl.DataFrame,
        calculation_date: str,
    ) -> pl.DataFrame:
        """
        添加 PIT 元数据.

        Args:
            df: 包含 exposure 的 DataFrame.
            calculation_date: 计算日期 (YYYY-MM-DD).

        Returns:
            添加 effective_from, effective_to 的 DataFrame.

        """
        return df.with_columns(
            pl.lit(calculation_date).str.strptime(pl.Date, "%Y-%m-%d").alias("effective_from"),
            pl.lit(None, dtype=pl.Date).alias("effective_to"),
        )

    def validate_input(self, df: pl.DataFrame) -> None:
        """
        验证输入数据.

        Args:
            df: 输入数据.

        Raises:
            ValueError: 如果缺少必需的列.

        """
        missing = set(self.required_features + self.required_columns) - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Required: {self.required_features + self.required_columns}"
            )

    def calculate(
        self,
        df: pl.DataFrame,
        calculation_date: str,
    ) -> pl.DataFrame:
        """
        完整计算流程: raw → normalize → add_pit.

        Args:
            df: 输入数据.
            calculation_date: 计算日期.

        Returns:
            包含 sid, trade_date, raw_value, exposure, effective_from, effective_to 的 DataFrame.

        """
        self.validate_input(df)

        # Step 1: 计算原始值
        raw_df = self.calculate_raw(df)

        # Step 2: 标准化
        normalized_df = self.normalize(raw_df)

        # Step 3: 添加 PIT 元数据
        result_df = self.add_pit_metadata(normalized_df, calculation_date)

        return result_df
```

### 3.2 具体 Calculator 实现

```python
"""
packages/core/src/ditto_core/factors/calculators/factors.py
"""

from __future__ import annotations

import polars as pl
from ditto_core.factors.calculator import FactorCalculator
from ditto_core.factors.types import FactorSpec


# Value Factors


@FactorCalculator.register("factor_value_pe")
class ValuePECalculator(FactorCalculator):
    """
    P/E Ratio factor (inverse).

    低 PE = 高 value score.
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["pe_ratio"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        # PE 取倒数，值越大越好
        result = df.with_columns(
            (1 / pl.col("pe_ratio"))
            .fill_null(0)  # 无 PE 数据时默认为 0
            .alias("raw_value")
        )
        return result.select(["sid", "trade_date", "raw_value"])


@FactorCalculator.register("factor_value_pb")
class ValuePBCalculator(FactorCalculator):
    """P/B Ratio factor (inverse)."""

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["pb_ratio"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        result = df.with_columns(
            (1 / pl.col("pb_ratio"))
            .fill_null(0)
            .alias("raw_value")
        )
        return result.select(["sid", "trade_date", "raw_value"])


# Momentum Factors


@FactorCalculator.register("factor_momentum_12m")
class Momentum12MCalculator(FactorCalculator):
    """
    12-month momentum factor.

    累计过去 12 个月收益率 (扣除最近 1 个月).
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        # 12-month return, skip most recent month
        result = (
            df.sort("trade_date")
            .with_columns(
                pl.col("close")
                .shift(20)  # 跳过最近 1 个月 (约 20 个交易日)
                .alias("close_1m_ago")
            )
            .with_columns(
                pl.col("close")
                .shift(240)  # 12 个月前 (约 240 个交易日)
                .alias("close_12m_ago")
            )
            .with_columns(
                ((pl.col("close_1m_ago") - pl.col("close_12m_ago")) /
                 pl.col("close_12m_ago"))
                .alias("raw_value")
            )
            .select(["sid", "trade_date", "raw_value"])
        )
        return result


@FactorCalculator.register("factor_momentum_reversal")
class MomentumReversalCalculator(FactorCalculator):
    """
    Short-term reversal factor.

    最近 1 个月收益率的负值.
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        result = (
            df.sort("trade_date")
            .with_columns(
                ((pl.col("close") - pl.col("close").shift(20)) /
                 pl.col("close").shift(20))
                .alias("raw_value")
            )
            .with_columns(
                -pl.col("raw_value").alias("raw_value")  # 取负
            )
            .select(["sid", "trade_date", "raw_value"])
        )
        return result


# Quality Factors


@FactorCalculator.register("factor_quality_roe")
class QualityROECalculator(FactorCalculator):
    """ROE (Return on Equity) factor."""

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["roe"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        result = df.with_columns(
            pl.col("roe")
            .fill_null(0)
            .alias("raw_value")
        )
        return result.select(["sid", "trade_date", "raw_value"])


@FactorCalculator.register("factor_quality_accruals")
class QualityAccrualsCalculator(FactorCalculator):
    """
    Accruals factor (低 accruals = 高质量).

    Accruals = (Net Income - Cash Flow from Operations) / Total Assets
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["net_income", "cfo", "total_assets"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        result = df.with_columns(
            ((pl.col("net_income") - pl.col("cfo")) / pl.col("total_assets"))
            .fill_null(0)
            .alias("accruals")
        )
        # 低 accruals = 高质量
        result = result.with_columns(
            -pl.col("accruals").alias("raw_value")
        )
        return result.select(["sid", "trade_date", "raw_value"])


# Size Factors


@FactorCalculator.register("factor_size_log_cap")
class SizeLogCapCalculator(FactorCalculator):
    """
    Market cap factor (log).

    小市值效应.
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["market_cap"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        # 小市值 = 高因子值 (取负 log)
        result = df.with_columns(
            -pl.col("market_cap").log()
            .alias("raw_value")
        )
        return result.select(["sid", "trade_date", "raw_value"])


# Volatility Factors


@FactorCalculator.register("factor_volatility_hist")
class VolatilityHistCalculator(FactorCalculator):
    """
    Historical volatility factor.

    低波动 = 高因子值.
    """

    @property
    def required_features(self) -> list[str]:
        return []

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    def calculate_raw(self, df: pl.DataFrame) -> pl.DataFrame:
        period = 20  # 20-day volatility
        result = (
            df.sort("trade_date")
            .with_columns(
                ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1))
                .alias("return")
            )
            .with_columns(
                pl.col("return")
                .rolling_std(window_size=period, min_periods=period)
                .alias("volatility")
            )
            .with_columns(
                -pl.col("volatility").alias("raw_value")  # 取负
            )
            .select(["sid", "trade_date", "raw_value"])
        )
        return result
```

### 3.3 FactorEngine

```python
"""
packages/core/src/ditto_core/factors/engine.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import logger, traced

if TYPE_CHECKING:
    from ditto_core.factors.types import FactorSpec
    from ditto_datahub.domains.factors import FactorService
    from ditto_datahub.domains.features import FeatureService
    from ditto_datahub.domains.market import MarketService


@dataclass(frozen=True)
class FactorCalculationResult:
    """因子计算结果."""
    factor_id: str
    added: int
    failed: int
    duration_ms: float


class FactorEngine:
    """
    Factor calculation engine.

    职责:
    - 协调多个 FactorCalculator 的执行
    - 读取源数据 (Features + Market)
    - 计算原始值 → 标准化 → 添加 PIT 元数据
    - 写入结果到 DataHub

    不负责:
    - 数据存储 (由 DataHub 负责)
    - 工作流编排 (由 Port Service 负责)
    """

    def __init__(
        self,
        factor_service: FactorService,
        feature_service: FeatureService,
        market_service: MarketService,
    ) -> None:
        """
        Initialize FactorEngine.

        Args:
            factor_service: DataHub FactorService for storage.
            feature_service: DataHub FeatureService for source features.
            market_service: DataHub MarketService for source data.

        """
        self._factors = factor_service
        self._features = feature_service
        self._market = market_service

    @traced("factors.calculate_batch")
    def calculate_batch(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
        factor_specs: list[FactorSpec],
        calculation_date: str | None = None,
    ) -> list[FactorCalculationResult]:
        """
        批量计算多个 factor.

        Args:
            sids: Security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            factor_specs: Factor specifications to calculate.
            calculation_date: 计算日期 (默认为今天).

        Returns:
            List of calculation results.

        """
        import time

        if calculation_date is None:
            calculation_date = datetime.now().strftime("%Y-%m-%d")

        from ditto_core.factors.calculator import FactorCalculator

        results: list[FactorCalculationResult] = []

        logger.info(
            "Reading source data for factor calculation",
            event="factor_calculation_start",
            sids_count=len(sids),
            start_date=start_date,
            end_date=end_date,
            factors_count=len(factor_specs),
            calculation_date=calculation_date,
        )

        # 对每个 factor 进行计算
        for spec in factor_specs:
            start = time.time()
            factor_id = spec.factor_id

            try:
                calculator = FactorCalculator.get_calculator(factor_id, spec)

                # 收集所需的 features
                required_features = calculator.required_features
                feature_dfs = []
                if required_features:
                    feature_df = self._features.get_indicators(
                        sids=sids,
                        start_date=start_date,
                        end_date=end_date,
                        indicator_ids=required_features,
                    )
                    feature_dfs.append(feature_df)

                # 收集所需的 market 数据
                required_columns = calculator.required_columns
                market_dfs = []
                if required_columns:
                    # 检查需要哪些 market 表
                    if "close" in required_columns or "open" in required_columns:
                        bars_df = self._market.get_bars(
                            sids=sids,
                            start_date=start_date,
                            end_date=end_date,
                        )
                        market_dfs.append(bars_df)

                # 合并所有源数据
                source_df = self._merge_sources(
                    sids=sids,
                    feature_dfs=feature_dfs,
                    market_dfs=market_dfs,
                )

                if source_df.is_empty():
                    logger.warning(
                        f"No source data found for {factor_id}",
                        event="factor_calculation_no_data",
                        factor_id=factor_id,
                    )
                    results.append(FactorCalculationResult(
                        factor_id=factor_id,
                        added=0,
                        failed=0,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                    continue

                # 分组计算 (按 sid)
                calculated_dfs = []
                for sid in sids:
                    sid_df = source_df.filter(pl.col("sid") == sid)
                    if sid_df.len() < 20:  # 最小数据量
                        continue

                    calculator.validate_input(sid_df)
                    result_df = calculator.calculate(sid_df, calculation_date)
                    calculated_dfs.append(result_df)

                if not calculated_dfs:
                    logger.warning(
                        f"No data calculated for {factor_id}",
                        event="factor_calculation_no_result",
                        factor_id=factor_id,
                    )
                    results.append(FactorCalculationResult(
                        factor_id=factor_id,
                        added=0,
                        failed=0,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                    continue

                # 合并结果
                combined = pl.concat(calculated_dfs)

                # 添加 factor_id 列
                combined = combined.with_columns(
                    pl.lit(factor_id).alias("factor_id")
                )

                # 写入 DataHub (按年份分区)
                added_total = 0
                for year in combined["trade_date"].dt.year().unique():
                    year_df = combined.filter(
                        pl.col("trade_date").dt.year() == year
                    )
                    write_result = self._factors.write_factor(
                        df=year_df,
                        year=year,
                    )
                    added_total += write_result.added

                duration_ms = (time.time() - start) * 1000
                results.append(FactorCalculationResult(
                    factor_id=factor_id,
                    added=added_total,
                    failed=0,
                    duration_ms=duration_ms,
                ))

                logger.info(
                    f"Calculated {factor_id}",
                    event="factor_calculation_complete",
                    factor_id=factor_id,
                    added=added_total,
                    duration_ms=round(duration_ms, 2),
                )

            except Exception as e:
                logger.error(
                    f"Failed to calculate {factor_id}: {e}",
                    event="factor_calculation_failed",
                    factor_id=factor_id,
                    error=str(e),
                )
                results.append(FactorCalculationResult(
                    factor_id=factor_id,
                    added=0,
                    failed=len(sids),
                    duration_ms=(time.time() - start) * 1000,
                ))

        return results

    def _merge_sources(
        self,
        sids: list[int],
        feature_dfs: list[pl.DataFrame],
        market_dfs: list[pl.DataFrame],
    ) -> pl.DataFrame:
        """
        合并多个源数据.

        Args:
            sids: Security IDs.
            feature_dfs: Feature DataFrames.
            market_dfs: Market DataFrames.

        Returns:
            合并后的 DataFrame.

        """
        # 收集所有 DataFrame
        all_dfs = feature_dfs + market_dfs

        if not all_dfs:
            return pl.DataFrame(schema={"sid": pl.Int32, "trade_date": pl.Date})

        # 从第一个 DataFrame 开始
        result = all_dfs[0]

        # 依次 join 其他 DataFrame
        for df in all_dfs[1:]:
            result = result.join(
                df,
                on=["sid", "trade_date"],
                how="outer",
            )

        # 过滤到指定的 sids
        result = result.filter(pl.col("sid").is_in(sids))

        return result

    @traced("factors.list_factors")
    def list_factors(self) -> list[str]:
        """获取所有可用的 factor_id."""
        from ditto_core.factors.calculator import FactorCalculator
        return FactorCalculator.list_factors()
```

---

## 4. Alpha 表达式引擎

### 4.1 设计目标

支持 WorldQuant Alpha101、国泰君安 Alpha191、Microsoft Qlib Alpha360 等公式化因子库。

**关键特点**:
- 表达式 → Polars LazyFrame 转换
- 延迟计算，优化性能
- 支持自定义函数注册

### 4.2 表达式函数库

```python
"""
packages/core/src/ditto_core/alpha/expression.py
"""

from __future__ import annotations

from typing import Any, Callable

import polars as pl
from polars import Expr


class AlphaExpression:
    """
    Alpha 表达式引擎.

    支持 WorldQuant Alpha101/191/360 风格的公式化表达式.
    """

    # 支持的表达式函数
    FUNCTIONS: dict[str, Callable[..., Expr]] = {
        # ============ 时间序列函数 ============
        "ts_rank": lambda col, n: col.shift(n).rank(),
        "ts_sum": lambda col, n: col.rolling_sum(window_size=n),
        "ts_mean": lambda col, n: col.rolling_mean(window_size=n),
        "ts_std": lambda col, n: col.rolling_std(window_size=n),
        "ts_var": lambda col, n: col.rolling_var(window_size=n),
        "ts_skew": lambda col, n: col.rolling_skew(window_size=n),
        "ts_kurt": lambda col, n: col.rolling_kurt(window_size=n),
        "ts_argmax": lambda col, n: col.shift(n).arg_max(),
        "ts_argmin": lambda col, n: col.shift(n).arg_min(),
        "ts_max": lambda col, n: col.rolling_max(window_size=n),
        "ts_min": lambda col, n: col.rolling_min(window_size=n),
        "ts_median": lambda col, n: col.rolling_median(window_size=n),
        "ts_percentile": lambda col, n, p: col.rolling_quantile(q=p/100, window_size=n),
        "ts_delta": lambda col, n: col.shift(n) - col,
        "ts_corr": lambda col1, col2, n: col1.rolling_corr(col2, window_size=n),
        "ts_cov": lambda col1, col2, n: col1.rolling_cov(col2, window_size=n),

        # ============ 统计函数 ============
        "rank": lambda col: col.rank(),
        "zscore": lambda col: (col - col.mean()) / col.std(),
        "neutralize": lambda col, by_col: (col - col.group_by(by_col).transform_mean()) / col.group_by(by_col).transform_std(),
        "scale": lambda col: (col - col.min()) / (col.max() - col.min()),
        "sign": lambda col: pl.sign(col),
        "log": lambda col: pl.log(col),
        "abs": lambda col: pl.abs(col),
        "exp": lambda col: pl.exp(col),
        "sqrt": lambda col: pl.sqrt(col),
        "square": lambda col: col * col,
        "power": lambda col, n: col.pow(n),
        "clip": lambda col, min_val, max_val: pl.clip(col, min_val, max_val),

        # ============ 延迟函数 ============
        "delay": lambda col, n: col.shift(n),
        "delta": lambda col, n: col - col.shift(n),
        "return": lambda col, n: (col - col.shift(n)) / col.shift(n),

        # ============ 条件函数 ============
        "cond": lambda condition, true_val, false_val: pl.when(condition).then(true_val).otherwise(false_val),
        "if_else": lambda condition, true_val, false_val: pl.when(condition).then(true_val).otherwise(false_val),

        # ============ 聚合函数 (跨资产) ============
        "group_mean": lambda col, by: col.group_by(by).mean(),
        "group_sum": lambda col, by: col.group_by(by).sum(),
        "group_rank": lambda col, by: col.group_by(by).rank(),

        # ============ 数学函数 ============
        "sin": lambda col: pl.sin(col),
        "cos": lambda col: pl.cos(col),
        "tan": lambda col: pl.tan(col),
        "asin": lambda col: pl.arcsin(col),
        "acos": lambda col: pl.arccos(col),
        "atan": lambda col: pl.arctan(col),
    }

    @classmethod
    def register_function(cls, name: str, func: Callable[..., Expr]) -> None:
        """注册自定义表达式函数."""
        cls.FUNCTIONS[name] = func

    @classmethod
    def parse_expression(
        cls,
        expression: str,
        context: dict[str, Expr],
    ) -> Expr:
        """
        解析表达式字符串为 Polars Expr.

        Args:
            expression: 表达式字符串，例如 "ts_rank(close, 10)"
            context: 上下文变量，例如 {"close": pl.col("close")}

        Returns:
            Polars 表达式.

        Raises:
            ValueError: 如果表达式解析失败.

        """
        import re

        # 简单解析：提取函数名和参数
        # 例如: "ts_rank(close, 10)" -> ("ts_rank", ["close", "10"])

        pattern = r"(\w+)\(([^)]*)\)"
        match = re.match(pattern, expression.strip())

        if not match:
            # 尝试直接作为变量名
            if expression.strip() in context:
                return context[expression.strip()]
            raise ValueError(f"Cannot parse expression: {expression}")

        func_name = match.group(1)
        args_str = match.group(2)

        if func_name not in cls.FUNCTIONS:
            available = ", ".join(sorted(cls.FUNCTIONS.keys()))
            raise ValueError(
                f"Unknown function: {func_name}. "
                f"Available: {available}"
            )

        # 解析参数
        args = []
        if args_str.strip():
            for arg in args_str.split(","):
                arg = arg.strip()
                # 尝试作为数字
                try:
                    args.append(float(arg))
                except ValueError:
                    # 尝试作为变量
                    if arg in context:
                        args.append(context[arg])
                    else:
                        # 递归解析嵌套表达式
                        args.append(cls.parse_expression(arg, context))

        func = cls.FUNCTIONS[func_name]
        return func(*args)
```

### 4.3 Alpha101 示例实现

```python
"""
packages/core/src/ditto_core/alpha/alpha101.py
"""

from __future__ import annotations

import polars as pl
from ditto_core.alpha.expression import AlphaExpression
from ditto_core.features.calculator import FeatureCalculator
from ditto_core.features.types import IndicatorSpec


# Alpha 001
@FeatureCalculator.register("alpha101_001")
class Alpha001Calculator(FeatureCalculator):
    """
    Alpha 001: rank(ts_argmax(close, 10))

    价格在最近 10 天内达到最高点的排名.
    """

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def min_periods(self) -> int:
        return 10

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        # 构建上下文
        context = {
            "close": pl.col("close"),
        }

        # 解析表达式
        expr = AlphaExpression.parse_expression(
            "rank(ts_argmax(close, 10))",
            context
        )

        result = (
            df.sort("trade_date")
            .with_columns(expr.alias("value"))
            .select(["sid", "trade_date", "value"])
        )
        return result


# Alpha 002
@FeatureCalculator.register("alpha101_002")
class Alpha002Calculator(FeatureCalculator):
    """
    Alpha 002: (-1 * correlation(rank(delta(log(volume), 1)), rank(((close - open) / open)), 6))

    成交量变化与价格收益率的相关性 (负号).
    """

    @property
    def required_columns(self) -> list[str]:
        return ["close", "open", "volume"]

    @property
    def min_periods(self) -> int:
        return 7

    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        context = {
            "close": pl.col("close"),
            "open": pl.col("open"),
            "volume": pl.col("volume"),
        }

        # 复杂表达式，分步构建
        df_calc = (
            df.sort("trade_date")
            .with_columns([
                # delta(log(volume), 1)
                (pl.col("volume").log() - pl.col("volume").shift(1).log()).alias("vol_delta"),
                # (close - open) / open
                ((pl.col("close") - pl.col("open")) / pl.col("open")).alias("price_change"),
            ])
            .with_columns([
                # rank(delta(log(volume), 1))
                pl.col("vol_delta").rank().alias("vol_rank"),
                # rank(((close - open) / open))
                pl.col("price_change").rank().alias("price_rank"),
            ])
            .with_columns([
                # correlation(..., ..., 6)
                pl.col("vol_rank").rolling_corr(pl.col("price_rank"), window_size=6).alias("corr")
            ])
            .with_columns[
                (-1 * pl.col("corr")).alias("value")
            ]
            .select(["sid", "trade_date", "value"])
        )
        return df_calc
```

### 4.4 Alpha 引擎

```python
"""
packages/core/src/ditto_core/alpha/engine.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import logger, traced

if TYPE_CHECKING:
    from ditto_core.features.types import IndicatorSpec


@dataclass(frozen=True)
class AlphaCalculationResult:
    """Alpha 计算结果."""
    alpha_id: str
    added: int
    failed: int
    duration_ms: float


class AlphaEngine:
    """
    Alpha 表达式计算引擎.

    职责:
    - 解析 Alpha 公式表达式
    - 转换为 Polars 表达式
    - 批量计算

    支持:
    - WorldQuant Alpha101
    - 国泰君安 Alpha191
    - Microsoft Qlib Alpha360
    """

    def __init__(self) -> None:
        """初始化 Alpha 引擎."""
        from ditto_core.alpha.expression import AlphaExpression
        self._expression_engine = AlphaExpression

    @traced("alpha.calculate_batch")
    def calculate_batch(
        self,
        source_df: pl.DataFrame,
        alpha_specs: list[IndicatorSpec],
    ) -> list[AlphaCalculationResult]:
        """
        批量计算 Alpha 表达式.

        Args:
            source_df: 源数据，包含 sid, trade_date, OHLCV.
            alpha_specs: Alpha 规格列表.

        Returns:
            计算结果列表.

        """
        import time

        results: list[AlphaCalculationResult] = []

        for spec in alpha_specs:
            start = time.time()
            alpha_id = spec.indicator_id

            try:
                # 获取 calculator
                from ditto_core.features.calculator import FeatureCalculator
                calculator = FeatureCalculator.get_calculator(alpha_id, spec)

                # 验证输入
                calculator.validate_input(source_df)

                # 按分组计算
                calculated_dfs = []
                for sid in source_df["sid"].unique():
                    sid_df = source_df.filter(pl.col("sid") == sid)
                    if sid_df.len() < calculator.min_periods:
                        continue

                    result_df = calculator.calculate(sid_df)
                    calculated_dfs.append(result_df)

                if not calculated_dfs:
                    results.append(AlphaCalculationResult(
                        alpha_id=alpha_id,
                        added=0,
                        failed=0,
                        duration_ms=(time.time() - start) * 1000,
                    ))
                    continue

                combined = pl.concat(calculated_dfs)
                results.append(AlphaCalculationResult(
                    alpha_id=alpha_id,
                    added=len(combined),
                    failed=0,
                    duration_ms=(time.time() - start) * 1000,
                ))

                logger.info(
                    f"Calculated {alpha_id}",
                    event="alpha_calculation_complete",
                    alpha_id=alpha_id,
                    added=len(combined),
                    duration_ms=round((time.time() - start) * 1000, 2),
                )

            except Exception as e:
                logger.error(
                    f"Failed to calculate {alpha_id}: {e}",
                    event="alpha_calculation_failed",
                    alpha_id=alpha_id,
                    error=str(e),
                )
                results.append(AlphaCalculationResult(
                    alpha_id=alpha_id,
                    added=0,
                    failed=1,
                    duration_ms=(time.time() - start) * 1000,
                ))

        return results
```

---

## 5. Calculator Registry 模式

### 5.1 Registry 实现

```python
"""
packages/core/src/ditto_core/features/registry.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_core.features.calculator import FeatureCalculator
    from ditto_core.features.types import IndicatorSpec


class CalculatorRegistry:
    """
    全局 Calculator 注册表.

    职责:
    - 管理 calculator 的注册和查找
    - 防止重复注册
    - 提供查询接口
    """

    _feature_calculators: dict[str, type[FeatureCalculator]] = {}
    _factor_calculators: dict[str, type] = {}  # FactorCalculator

    @classmethod
    def register_feature_calculator(
        cls,
        indicator_id: str,
        calculator_class: type[FeatureCalculator],
    ) -> None:
        """
        注册 Feature Calculator.

        Args:
            indicator_id: Indicator 标识符.
            calculator_class: Calculator 类.

        Raises:
            ValueError: 如果 indicator_id 已被注册.

        """
        if indicator_id in cls._feature_calculators:
            raise ValueError(
                f"indicator_id '{indicator_id}' already registered "
                f"with {cls._feature_calculators[indicator_id].__name__}"
            )
        cls._feature_calculators[indicator_id] = calculator_class

    @classmethod
    def get_feature_calculator(
        cls,
        indicator_id: str,
        spec: IndicatorSpec,
    ) -> FeatureCalculator:
        """
        获取 Feature Calculator 实例.

        Args:
            indicator_id: Indicator 标识符.
            spec: Indicator specification.

        Returns:
            Calculator 实例.

        """
        if indicator_id not in cls._feature_calculators:
            available = ", ".join(sorted(cls._feature_calculators.keys()))
            raise ValueError(
                f"Unknown indicator_id: {indicator_id}. "
                f"Available: {available}"
            )
        calc_class = cls._feature_calculators[indicator_id]
        return calc_class(spec)
```

### 5.2 自动注册机制

```python
"""
packages/core/src/ditto_core/features/__init__.py
"""

from __future__ import annotations

# 导入所有 calculator 以触发注册
from ditto_core.features.calculators import (
    indicators,  # noqa: F401
)

__all__: list[str] = []
```

---

## 6. 配置驱动设计

### 6.1 YAML 配置文件

```yaml
# config/features/indicators.yaml

indicators:
  - indicator_id: indicator_sma_20
    type: trend
    name: "20-Day Simple Moving Average"
    description: "Simple moving average over 20 periods"
    params:
      period: 20
    required_columns: ["close"]
    min_periods: 20

  - indicator_id: indicator_rsi_14
    type: momentum
    name: "14-Day RSI"
    description: "Relative Strength Index with 14-period lookback"
    params:
      period: 14
    required_columns: ["close"]
    min_periods: 15

  - indicator_id: indicator_macd
    type: trend
    name: "MACD"
    description: "Moving Average Convergence Divergence"
    params:
      fast: 12
      slow: 26
      signal: 9
    required_columns: ["close"]
    min_periods: 26
```

```yaml
# config/factors/factors.yaml

factors:
  - factor_id: factor_momentum_12m
    class: technical
    family: momentum
    name: "12-Month Momentum"
    description: "Cumulative return over 12 months (excluding most recent month)"
    required_features: []
    required_columns: ["close"]

  - factor_id: factor_value_pe
    class: fundamental
    family: value
    name: "P/E Ratio"
    description: "Price-to-earnings ratio (inverse)"
    required_features: []
    required_columns: ["pe_ratio"]

  - factor_id: factor_quality_roe
    class: fundamental
    family: quality
    name: "ROE"
    description: "Return on Equity"
    required_features: []
    required_columns: ["roe"]
```

### 6.2 配置加载

```python
"""
packages/core/src/ditto_core/features/config.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class IndicatorParams:
    """Indicator 参数."""
    period: int | None = None
    fast: int | None = None
    slow: int | None = None
    signal: int | None = None
    std_dev: float | None = None


class IndicatorConfig(BaseModel):
    """Indicator 配置."""
    indicator_id: str
    type: str = Field(..., pattern="^(trend|momentum|volatility|volume)$")
    name: str
    description: str
    params: dict[str, int | float] = Field(default_factory=dict)
    required_columns: list[str]
    min_periods: int

    def to_spec(self) -> IndicatorSpec:
        """转换为 IndicatorSpec."""
        from ditto_core.features.types import IndicatorSpec
        return IndicatorSpec(
            indicator_id=self.indicator_id,
            type=self.type,
            name=self.name,
            description=self.description,
            params=IndicatorParams(**self.params),
        )


class FeatureConfigLoader:
    """加载 Feature 配置."""

    @staticmethod
    def load_indicators(path: Path) -> list[IndicatorConfig]:
        """加载 indicators.yaml."""
        with open(path) as f:
            data = yaml.safe_load(f)

        configs = [
            IndicatorConfig(**item)
            for item in data.get("indicators", [])
        ]
        return configs
```

---

## 7. 层间接口

### 7.1 Core → DataHub

```python
"""
Core 层直接调用 DataHub Store 接口.

不经过 Service 层，避免不必要的抽象。
"""

# FeatureEngine → IndicatorStore
class FeatureEngine:
    def calculate_batch(...):
        # 直接写入 Store
        self._features._indicator_store.write(year_df, year=year)

# FactorEngine → FactorStore
class FactorEngine:
    def calculate_batch(...):
        # 直接写入 Store
        self._factors._factor_store.write(year_df, year=year)
```

### 7.2 Port → Core

```python
"""
Port 层编排服务，调用 Core 层 Engine.
"""

from ditto_core.features.engine import FeatureEngine
from ditto_core.factors.engine import FactorEngine


class FeatureCalculationService:
    """
    Port 层特征计算服务.

    职责:
    - 编排计算工作流
    - 任务调度
    - 错误处理和重试
    - 进度报告
    """

    def __init__(
        self,
        datahub: DataHub,
        feature_engine: FeatureEngine,
    ) -> None:
        self._datahub = datahub
        self._engine = feature_engine

    async def calculate_universe_features(
        self,
        universe_id: str,
        calculation_date: str,
        indicator_ids: list[str] | None = None,
    ) -> dict[str, int]:
        """
        计算全市场特征.

        Args:
            universe_id: 股票池 ID.
            calculation_date: 计算日期.
            indicator_ids: 要计算的 indicator_id (None = 全部).

        Returns:
            {indicator_id: 计算数量} 字典.

        """
        # 1. 获取股票池
        sids = self._datahub.metadata.get_universe_sids(universe_id)

        # 2. 确定计算范围
        if indicator_ids is None:
            indicator_ids = self._engine.list_indicators()

        # 3. 加载配置
        specs = self._load_indicator_specs(indicator_ids)

        # 4. 调用 Core 层计算
        results = self._engine.calculate_batch(
            sids=sids,
            start_date=self._get_calculation_start(calculation_date),
            end_date=calculation_date,
            indicator_specs=specs,
        )

        # 5. 返回统计
        return {r.indicator_id: r.added for r in results}
```

---

## 8. 错误处理

### 8.1 Calculator 错误处理

```python
class FeatureCalculator(ABC):
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        计算时错误处理原则:
        1. 输入验证失败 → ValueError
        2. 数据不足 → 返回空 DataFrame (不抛错)
        3. 计算错误 → 抛出具体异常
        """
        try:
            # 计算逻辑
            ...
        except pl.ComputeError as e:
            raise ValueError(f"Computation failed: {e}") from e
        except Exception as e:
            raise
```

### 8.2 Engine 错误处理

```python
class FeatureEngine:
    def calculate_batch(...) -> list[CalculationResult]:
        """
        批量计算错误处理原则:
        1. 单个 indicator 失败不影响其他
        2. 记录详细错误信息到日志
        3. 返回部分成功结果
        """
        results = []
        for spec in indicator_specs:
            try:
                # 计算逻辑
                ...
            except Exception as e:
                logger.error(...)
                results.append(CalculationResult(
                    indicator_id=spec.indicator_id,
                    added=0,
                    failed=len(sids),
                    duration_ms=...,
                ))
        return results
```

---

## 9. 性能优化

### 9.1 批量读取策略

```python
class FeatureEngine:
    def calculate_batch(...):
        # 策略 1: 一次读取所有源数据，多个 calculator 共享
        source_df = self._market.get_bars(sids=sids, ...)

        # 策略 2: 并行计算多个 indicator (使用 TaskTool)
        # 需要确保无状态计算
```

### 9.2 分区写入优化

```python
class FeatureEngine:
    def calculate_batch(...):
        # 按年份分区写入
        for year in combined["trade_date"].dt.year().unique():
            year_df = combined.filter(pl.col("trade_date").dt.year() == year)
            self._features.write_indicator(year_df, year=year)
```

### 9.3 内存优化

```python
class FeatureEngine:
    def calculate_batch(...):
        # 策略: 按分组迭代，避免全量加载
        for sid in sids:
            sid_df = source_df.filter(pl.col("sid") == sid)
            result_df = calculator.calculate(sid_df)
            # 立即写入，不累积
```

---

## 10. 业界最佳实践

### 10.1 Feature Store 架构

基于 Feast、Tecton 等开源 Feature Store 的最佳实践：

| 组件 | Feast | Tecton | Ditto 设计 |
|------|-------|--------|-----------|
| Offline Store | Parquet/S3 | Parquet/Snowflake | DataHub (Parquet) |
| Online Store | Redis/DynamoDB | Redis | (未来) Redis |
| Feature Definition | Python | Python/SQL | Python (Calculator) |
| Transformation | Pandas/Spark | Spark | Polars |
| Point-in-Time | ✅ | ✅ | ✅ (Factors only) |

**关键设计决策**:
1. **Technical Features** (技术特征): 无需 PIT (SMA, RSI, MACD - 公式固定，历史值不变)
2. **Fundamental Features** (基本面特征): 需要 PIT (PE, ROE, EPS - 财报可能重述)
3. **All Factors** (所有因子): 需要 PIT (Alpha101, Barra, A股特有 - 因子值可能修订)
4. **Alpha Signals**: 表达式驱动，延迟计算

### 10.2 因子分类体系

基于业界标准 (TA-Lib、Barra CNE5、Alpha101/191/360)：

#### 技术指标分类 (TA-Lib 标准)

| 类别 | 示例 | 数量 |
|------|------|------|
| Overlap Studies | SMA, EMA, Bollinger Bands | ~15 |
| Momentum Indicators | RSI, MACD, Stochastic | ~30 |
| Volume Indicators | OBV, AD, MFI | ~15 |
| Volatility Indicators | ATR, StdDev | ~10 |
| Cycle Indicators | Hilbert Transform | ~5 |
| Price Transform | AvgPrice, MedianPrice | ~5 |
| Pattern Recognition | Doji, Hammer | ~60 |

#### 因子分类 (Barra CNE5 + 学术界)

| 类别 | Family | 示例 | 来源 |
|------|--------|------|------|
| Fundamental | Value | PE, PB, PS | Barra CNE5 |
| Fundamental | Quality | ROE, Accruals | Barra CNE5 |
| Fundamental | Growth | Earnings Growth | Barra CNE5 |
| Technical | Momentum | 12M Momentum | Fama-French |
| Technical | Reversal | Short-term Reversal | Academic |
| Technical | Size | Log Market Cap | Fama-French |
| Technical | Volatility | Historical Volatility | Barra CNE5 |
| Macro | Interest Rate | Rate Change | (未来) |

#### Alpha 因子库

| 库 | 来源 | 数量 | 特点 |
|----|------|------|------|
| Alpha101 | WorldQuant | 101 | 公式化表达式 |
| Alpha191 | 国泰君安 | 191 | A 股优化 |
| Alpha360 | Microsoft Qlib | 360 | 标准化特征 |

### 10.3 计算模式对比

| 模式 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **Calculator (类)** | 复杂计算逻辑 | 类型安全、可测试 | 代码量大 |
| **Expression (公式)** | Alpha101/191/360 | 灵活、声明式 | 调试困难 |
| **SQL (查询)** | 简单聚合 | 熟悉、高效 | 不适合复杂逻辑 |

**Ditto 选择**:
- 技术指标: Calculator 模式
- Alpha 因子: Expression 模式
- 简单因子: Calculator 模式

### 10.4 标准化方法

| 方法 | 公式 | 适用场景 | 特点 |
|------|------|----------|------|
| **Z-Score** | (x - μ) / σ | 正态分布假设 | 极端值敏感 |
| **Rank** | rank(x) | 非参数 | 稳健性好 |
| **Min-Max** | (x - min) / (max - min) | 有界区间 | 受极端值影响 |
| **Robust Z-Score** | (x - median) / MAD | 稳健标准化 | 抗极端值 |

**Ditto 选择**: Rank → Z-Score (两步法，先 rank 避免极端值)

### 10.5 PIT (Point-in-Time) 实现

基于业界实践 (Feast、Tecton、DolphinDB)：

```python
# Parquet 存储格式
schema = {
    "sid": pl.Int32,
    "trade_date": pl.Date,
    "factor_id": pl.String,
    "raw_value": pl.Float64,
    "exposure": pl.Float64,  # z-score
    "effective_from": pl.Date,  # PIT: 生效日期
    "effective_to": pl.Date,    # PIT: 失效日期 (NULL = 当前有效)
}
```

**查询示例**:
```python
# 查询 2024-01-15 的因子暴露
SELECT factor_id, exposure
FROM factors
WHERE sid = 1
  AND trade_date = '2024-01-15'
  AND effective_from <= '2024-01-15'
  AND (effective_to IS NULL OR effective_to > '2024-01-15')
```

### 10.6 性能基准

基于业界数据 (Feast、Qlib、DolphinDB)：

| 操作 | Qlib | DolphinDB | Ditto (目标) |
|------|------|-----------|-------------|
| 计算 100 指标 (3000 股) | ~30s | ~10s | ~15s (Polars) |
| 查询 5 年因子数据 | ~2s | ~0.5s | ~1s (Parquet) |
| PIT 查询单日 | ~0.1s | ~0.02s | ~0.05s |

**优化策略**:
1. Polars LazyFrame: 延迟计算，查询优化
2. Parquet 年份分区: 减少扫描数据量
3. 批量计算: 一次读取，多个计算器共享

### 10.7 参考资源

| 项目 | URL | 说明 |
|------|-----|------|
| Feast | https://feast.dev/ | 开源 Feature Store |
| Tecton | https://www.tecton.ai/ | 企业 Feature Store |
| Qlib | https://github.com/microsoft/qlib | Microsoft 量化平台 |
| TA-Lib | https://ta-lib.org/ | 技术指标库 |
| Alphalens | https://github.com/quantopian/alphalens | 因子分析 |
| DolphinDB | https://www.dolphindb.com/ | 时序数据库 |

---

## 总结

本文档定义了 Core 层计算引擎的完整设计:

1. **FeatureEngine**: 特征计算引擎，管理 FeatureCalculator
2. **FactorEngine**: 因子计算引擎，管理 FactorCalculator
3. **AlphaEngine**: 表达式计算引擎，支持 Alpha101/191/360
4. **Calculator Registry**: 动态注册和查找机制
5. **表达式引擎**: 支持公式化因子 (WorldQuant 风格)
6. **配置驱动**: YAML 配置文件支持
7. **层间接口**: Core/DataHub/Port 清晰分离
8. **错误处理**: 部分失败容错机制
9. **性能优化**: 批量读取、分区写入、内存优化
10. **业界最佳实践**: 符合 Feature Store 标准架构

**关键原则**:
- Core 层纯计算，无状态
- DataHub 层纯存储，无计算
- Port 层编排，不执行计算逻辑
- Technical Features: 无需 PIT (SMA, RSI, MACD - 公式固定，历史值不变)
- Fundamental Features: 需要 PIT (PE, ROE, EPS - 财报可能重述)
- All Factors: 需要 PIT (Alpha101, Barra, A股特有 - 因子值可能修订)
- Alpha: 表达式驱动，延迟计算

**业界对齐**:
- TA-Lib 150+ 技术指标标准
- Barra CNE5 十大风格因子
- WorldQuant Alpha101/191/360
- Feast/Tecton Feature Store 架构
