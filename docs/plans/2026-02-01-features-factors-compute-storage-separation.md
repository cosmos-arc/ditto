# Features & Factors 计算与存储分离架构设计

**创建日期**: 2026-02-01
**状态**: 架构设计草案
**实现状态**:
- ✅ **Phase 1-2 (DataHub 层)**: 已实现 - Macro/Features/Factors 三域存储
- ⏳ **Phase 3-4 (Core 层)**: 待实现 - 计算引擎和 Calculator Registry
**相关**: `docs/plans/2026-02-01-features-factors-domain-design.md`

---

## 一、架构原则

### 1.1 核心分离原则

| 层级 | 职责 | 不做什么 |
|------|------|---------|
| **Core (计算)** | 定义计算逻辑，执行计算 | 不直接访问数据库，通过 DataHub 读写 |
| **DataHub (存储)** | 存储/查询数据，版本管理 | 不包含任何计算函数 |
| **Port (编排)** | 协调计算流程，任务调度 | 不实现计算逻辑 |

### 1.2 数据流向

```
Market/Fundamental Data (DataHub)
    ↓ 读取
FeatureCalculator (Core) → 计算 → 写入 → Features (DataHub)
    ↓ 读取
FactorCalculator (Core) → 计算 → 标准化 → 写入 → Factors (DataHub)
    ↓ 读取
BacktestEngine (Core) → 读取 Features/Factors → 回测
```

---

## 二、Core 层：计算引擎

### 2.1 目录结构

```
packages/core/src/ditto_core/
├── feature/                    # 新增：特征计算引擎
│   ├── __init__.py
│   ├── calculator.py            # 特征计算器基类和注册表
│   ├── technical/               # 技术指标计算器
│   │   ├── __init__.py
│   │   ├── trend.py              # MA, EMA, MACD
│   │   ├── momentum.py           # RSI, CCI, Stochastic
│   │   ├── volatility.py         # ATR, Bollinger Bands
│   │   └── volume.py             # OBV, Volume ROC
│   └── engine.py                # FeatureEngine (协调器)
│
├── factor/                     # 扩展：因子计算引擎
│   ├── __init__.py
│   ├── calculator.py            # 因子计算器基类
│   ├── technical/               # 技术因子
│   │   ├── __init__.py
│   │   ├── momentum.py           # Momentum 因子
│   │   └── reversal.py           # Reversal 因子
│   ├── fundamental/             # 基本面因子
│   │   ├── __init__.py
│   │   ├── value.py              # Value 因子
│   │   └── quality.py            # Quality 因子
│   ├── normalization.py          # 标准化处理
│   └── engine.py                # FactorEngine (协调器)
│
└── models/                     # 数据模型
    ├── feature.py                # Feature, FeatureQuery
    └── factor.py                 # Factor, FactorQuery
```

### 2.2 FeatureCalculator 设计

**基类定义** (`feature/calculator.py`):

```python
"""Feature calculator base class and registry."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

import polars as pl
from ditto_foundation import traced


class FeatureCalculator(ABC):
    """
    Base class for feature calculators.

    Each calculator defines a specific technical indicator
    (e.g., RSI, MACD) with declarative input/output schema.
    """

    # Registry: {indicator_id: calculator_class}
    _registry: dict[str, type[FeatureCalculator]] = {}

    @classmethod
    def register(cls, indicator_id: str) -> callable:
        """Decorator to register a calculator."""
        def decorator(calc_class: type[FeatureCalculator]) -> type:
            cls._registry[indicator_id] = calc_class
            return calc_class
        return decorator

    @classmethod
    def get_calculator(cls, indicator_id: str) -> "FeatureCalculator":
        """Get calculator instance by indicator_id."""
        calc_class = cls._registry.get(indicator_id)
        if calc_class is None:
            msg = f"Unknown indicator_id: {indicator_id}"
            raise ValueError(msg)
        return calc_class()

    @abstractmethod
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate feature from input data.

        Args:
            df: Input DataFrame with required columns.

        Returns:
            DataFrame with calculated feature columns.

        """
        ...

    @property
    @abstractmethod
    def required_columns(self) -> list[str]:
        """Return list of required column names."""
        ...

    @property
    def indicator_id(self) -> str:
        """Return indicator identifier."""
        ...

    @property
    def indicator_type(self) -> str:
        """Return indicator type (trend/momentum/volatility/volume)."""
        ...

    def validate_input(self, df: pl.DataFrame) -> None:
        """Validate input DataFrame has required columns."""
        missing = [col for col in self.required_columns if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)
```

**具体计算器示例** (`feature/technical/momentum.py`):

```python
"""Momentum feature calculators."""

from polars import col

from ditto_core.feature.calculator import FeatureCalculator


@FeatureCalculator.register("indicator_rsi_14")
class RSI14Calculator(FeatureCalculator):
    """14-day RSI calculator."""

    @property
    def required_columns(self) -> list[str]:
        return ["close"]

    @property
    def indicator_id(self) -> str:
        return "indicator_rsi_14"

    @property
    def indicator_type(self) -> str:
        return "momentum"

    @traced("feature.calculate.rsi_14")
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate RSI(14).

        Args:
            df: DataFrame with 'close' column.

        Returns:
            DataFrame with RSI values.
        """
        # 1. Calculate price changes
        df = df.with_columns(
            (col("close") - col("close").shift(1))
            .alias("delta")
        )

        # 2. Separate gains and losses
        df = df.with_columns(
            pl.when(col("delta") > 0)
            .then(col("delta"))
            .otherwise(0)
            .alias("gain")
        )
        df = df.with_columns(
            pl.when(col("delta") < 0)
            .then(-col("delta"))
            .otherwise(0)
            .alias("loss")
        )

        # 3. Calculate average gain/loss
        df = df.with_columns([
            col("gain").rolling_mean(14).alias("avg_gain"),
            col("loss").rolling_mean(14).alias("avg_loss"),
        ])

        # 4. Calculate RS and RSI
        df = df.with_columns(
            (col("avg_gain") / col("avg_loss").fill_null(float("inf")))
            .alias("rs")
        )
        df = df.with_columns(
            (100 - (100 / (1 + col("rs"))))
            .alias("value")
        )

        return df.select(["value"])
```

### 2.3 FeatureEngine 设计

```python
"""FeatureEngine - feature calculation coordinator."""

from __future__ import annotations
from typing import Any

import polars as pl
from ditto_foundation import logger, traced

from ditto_core.feature.calculator import FeatureCalculator
from ditto_datahub.domains.features import FeatureQuery, FeatureService


class FeatureEngine:
    """
    Feature calculation engine.

    Coordinates feature calculation by:
    1. Reading raw data from DataHub (Market, Fundamental)
    2. Applying feature calculators
    3. Writing results to DataHub Features

    This engine does NOT store data; it only orchestrates calculation.
    """

    def __init__(self, feature_service: FeatureService, datahub: Any) -> None:
        """
        Initialize FeatureEngine.

        Args:
            feature_service: Features domain service (for storage).
            datahub: DataHub for reading source data.
        """
        self._features = feature_service
        self._datahub = datahub

    @traced("feature.engine.calculate_batch")
    def calculate_batch(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
        indicator_ids: list[str],
    ) -> dict[str, int]:
        """
        Calculate a batch of features for given securities.

        Args:
            sids: Security IDs to calculate.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            indicator_ids: List of indicator IDs to calculate.

        Returns:
            Dictionary {indicator_id: record_count}.

        """
        logger.info(
            "Starting feature calculation batch",
            sids_count=len(sids),
            indicators=indicator_ids,
            start=start_date,
            end=end_date,
        )

        # 1. Read source data from DataHub
        # TODO: Based on indicator requirements, read from Market/Fundamental
        source_df = self._datahub.market.get_bars(
            BarsQuery(
                sids=sids,
                start=start_date,
                end=end_date,
                adj=AdjType.NONE,
            )
        )

        # 2. Calculate each indicator
        results: dict[str, pl.DataFrame] = {}
        for indicator_id in indicator_ids:
            calculator = FeatureCalculator.get_calculator(indicator_id)

            # Validate input
            calculator.validate_input(source_df)

            # Calculate
            result_df = calculator.calculate(source_df)

            # Prepare output DataFrame
            output_df = pl.DataFrame({
                "sid": sids * len(source_df) // len(sids),  # Broadcast
                "trade_date": source_df["trade_date"],
                "indicator_id": indicator_id,
                "indicator_type": calculator.indicator_type,
                "value": result_df["value"],
                "calc_time": pl.datetime.now(),
            })

            results[indicator_id] = output_df

        # 3. Write to DataHub Features
        total_written = 0
        for indicator_id, df in results.items():
            # Extract year from trade_date for partitioning
            df = df.with_columns(
                pl.col("trade_date").dt().year().alias("year")
            )

            # Write by year partition
            for year in df["year"].unique().to_list():
                year_df = df.filter(pl.col("year") == year)
                # Drop temporary year column
                year_df = year_df.drop("year")

                # TODO: Call IndicatorStore.write()
                # self._features._indicator_store.write(year_df, year=year)
                total_written += len(year_df)

        logger.info(
            "Feature calculation batch completed",
            indicators=indicator_ids,
            total_written=total_written,
        )

        return {iid: len(df) for iid, df in results.items()}
```

### 2.4 FactorCalculator 设计

```python
"""Factor calculator base class."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Literal

import polars as pl
from ditto_foundation import traced


class FactorCalculator(ABC):
    """
    Base class for factor calculators.

    Factors are derived from features (or raw data) through
    statistical validation, normalization, and combination.
    """

    _registry: dict[str, type["FactorCalculator"]] = {}

    @classmethod
    def register(cls, factor_id: str) -> callable:
        """Decorator to register a factor calculator."""
        def decorator(calc_class: type) -> type:
            cls._registry[factor_id] = calc_class
            return calc_class
        return decorator

    @classmethod
    def get_calculator(cls, factor_id: str) -> "FactorCalculator":
        """Get calculator instance by factor_id."""
        calc_class = cls._registry.get(factor_id)
        if calc_class is None:
            msg = f"Unknown factor_id: {factor_id}"
            raise ValueError(msg)
        return calc_class()

    @abstractmethod
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate factor exposure from input data.

        Args:
            df: Input DataFrame with feature columns.

        Returns:
            DataFrame with factor exposure (standardized).
        """
        ...

    @property
    @abstractmethod
    def required_features(self) -> list[str]:
        """Return list of required feature IDs."""
        ...

    @property
    def factor_id(self) -> str:
        """Return factor identifier."""
        ...

    @property
    def factor_class(self) -> Literal["fundamental", "technical", "macro", "statistical"]:
        """Return factor class."""
        ...

    @property
    def factor_family(self) -> Literal["value", "momentum", "quality", "size", "volatility"]:
        """Return factor family."""
        ...

    def normalize(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalize factor exposure to z-scores.

        Default implementation uses rolling z-score normalization.
        Subclass can override with custom logic.
        """
        # z-score: (x - mean) / std
        return df.with_columns(
            ((pl.col("raw_value") - pl.col("raw_value").mean()) /
             pl.col("raw_value").std())
            .alias("exposure")
        )
```

**示例：动量因子计算器** (`factor/technical/momentum.py`):

```python
"""Momentum factor calculators."""

from polars import col

from ditto_core.factor.calculator import FactorCalculator
from ditto_core.factor.normalization importwinsorize


@FactorCalculator.register("factor_momentum_12m")
class Momentum12MFatherFactor(FactorCalculator):
    """12-month momentum factor (technical)."""

    @property
    def required_features(self) -> list[str]:
        # Requires raw price data (not pre-calculated features)
        return ["close"]

    @property
    def factor_id(self) -> str:
        return "factor_momentum_12m"

    @property
    def factor_class(self) -> Literal["technical"]:
        return "technical"

    @property
    def factor_family(self) -> Literal["momentum"]:
        return "momentum"

    @traced("factor.calculate.momentum_12m")
    def calculate(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate 12-month momentum factor.

        Args:
            df: DataFrame with 'close' column.

        Returns:
            DataFrame with momentum exposure.
        """
        # Calculate 12-month return
        df = df.with_columns(
            (col("close") / col("close").shift(252) - 1)
            .alias("raw_value")
        )

        # Winsorize extreme values (3 sigma)
        df = winsorize(df, "raw_value", sigma=3.0)

        # Normalize
        df = self.normalize(df)

        return df.select(["sid", "trade_date", "factor_id", "factor_class",
                          "factor_family", "exposure", "raw_value"])
```

### 2.5 FactorEngine 设计

```python
"""FactorEngine - factor calculation coordinator."""

from __future__ import annotations

import polars as pl
from ditto_foundation import logger, traced

from ditto_core.factor.calculator import FactorCalculator
from ditto_datahub.domains.factors import FactorQuery, FactorService


class FactorEngine:
    """
    Factor calculation engine.

    Coordinates factor calculation by:
    1. Reading features from DataHub Features
    2. Applying factor calculators
    3. Writing results to DataHub Factors (with PIT metadata)

    This engine does NOT store data; it only orchestrates calculation.
    """

    def __init__(
        self,
        factor_service: FactorService,
        feature_service: FeatureService,  # May need features as input
        datahub: Any,
    ) -> None:
        """
        Initialize FactorEngine.

        Args:
            factor_service: Factors domain service (for storage).
            feature_service: Features domain service (may read as input).
            datahub: DataHub for reading source data.
        """
        self._factors = factor_service
        self._features = feature_service
        self._datahub = datahub

    @traced("factor.engine.calculate_batch")
    def calculate_batch(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
        factor_ids: list[str],
        as_of_date: str | None = None,
    ) -> dict[str, int]:
        """
        Calculate a batch of factors for given securities.

        Args:
            sids: Security IDs to calculate.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            factor_ids: List of factor IDs to calculate.
            as_of_date: PIT query date for features.

        Returns:
            Dictionary {factor_id: record_count}.

        """
        logger.info(
            "Starting factor calculation batch",
            sids_count=len(sids),
            factors=factor_ids,
            start=start_date,
            end=end_date,
            as_of_date=as_of_date,
        )

        results: dict[str, pl.DataFrame] = {}

        for factor_id in factor_ids:
            calculator = FactorCalculator.get_calculator(factor_id)

            # 1. Get required features
            feature_df = self._features.get_indicators(
                FeatureQuery(
                    indicators=calculator.required_features,
                    start=start_date,
                    end=end_date,
                )
            )

            if feature_df.is_empty():
                logger.warning(
                    "No input features for factor calculation",
                    factor_id=factor_id,
                    required_features=calculator.required_features,
                )
                continue

            # 2. Calculate factor
            factor_df = calculator.calculate(feature_df)

            # 3. Add PIT metadata
            factor_df = factor_df.with_columns([
                pl.lit(factor_id).alias("factor_id"),
                pl.lit(calculator.factor_class).alias("factor_class"),
                pl.lit(calculator.factor_family).alias("factor_family"),
                pl.lit(start_date).alias("effective_from"),  # For simplicity
                pl.lit(None).alias("effective_to"),
            ])

            results[factor_id] = factor_df

        # 4. Write to DataHub Factors
        total_written = 0
        for factor_id, df in results.items():
            # Extract year for partitioning
            df = df.with_columns(
                pl.col("trade_date").dt().year().alias("year")
            )

            for year in df["year"].unique().to_list():
                year_df = df.filter(pl.col("year") == year)
                year_df = year_df.drop("year")

                # TODO: Call FactorStore.write()
                # self._factors._factor_store.write(year_df, year=year)
                total_written += len(year_df)

        logger.info(
            "Factor calculation batch completed",
            factors=factor_ids,
            total_written=total_written,
        )

        return {fid: len(df) for fid, df in results.items()}
```

---

## 三、Port 层：计算编排

### 3.1 目录结构

```
apps/port/src/ditto_port/services/
├── feature/                    # 新增：特征计算编排服务
│   ├── __init__.py
│   ├── calculation_service.py   # 特征计算编排
│   └── config.py                # 计算配置
│
└── factor/                     # 扩展：因子计算编排服务
    ├── __init__.py
    ├── calculation_service.py   # 因子计算编排
    └── config.py                # 计算配置
```

### 3.2 FeatureCalculationService 设计

```python
"""Feature calculation service (Port layer)."""

from __future__ import annotations

from pathlib import Path

from ditto_foundation import logger, traced

from ditto_core.feature.engine import FeatureEngine
from ditto_datahub import DataHub


class FeatureCalculationService:
    """
    Feature calculation orchestration service.

    Orchestrates the feature calculation workflow:
    1. Determine which securities need calculation (incremental logic)
    2. Call FeatureEngine to calculate
    3. Handle errors and retries
    4. Log calculation metrics

    This is an application service (use case orchestrator),
    not a calculation engine (no calculation logic).
    """

    def __init__(
        self,
        datahub: DataHub,
        feature_engine: FeatureEngine,
        config_path: Path | None = None,
    ) -> None:
        """
        Initialize FeatureCalculationService.

        Args:
            datahub: DataHub for reading source data and writing features.
            feature_engine: Feature engine for calculation.
            config_path: Path to feature configuration.
        """
        self._datahub = datahub
        self._engine = feature_engine
        self._config = self._load_config(config_path) if config_path else {}

    @traced("port.service.calculate_features")
    def calculate_universe_features(
        self,
        universe_ids: list[int],
        start_date: str,
        end_date: str,
        indicator_ids: list[str] | None = None,
    ) -> dict[str, int]:
        """
        Calculate features for a universe of securities.

        Args:
            universe_ids: List of security IDs.
            start_date: Start date.
            end_date: End date.
            indicator_ids: List of indicators to calculate (None = all configured).

        Returns:
            Dictionary with calculation results.

        """
        logger.info(
            "Starting universe feature calculation",
            universe_size=len(universe_ids),
            start=start_date,
            end=end_date,
            indicators=indicator_ids,
        )

        # Get indicators to calculate
        if indicator_ids is None:
            indicator_ids = self._config.get("default_indicators", [])

        # Call FeatureEngine
        results = self._engine.calculate_batch(
            sids=universe_ids,
            start_date=start_date,
            end_date=end_date,
            indicator_ids=indicator_ids,
        )

        logger.info(
            "Universe feature calculation completed",
            results=results,
        )

        return results

    def _load_config(self, config_path: Path) -> dict:
        """Load feature calculation configuration."""
        # TODO: Implement YAML/JSON config loading
        return {}
```

### 3.3 FactorCalculationService 设计

```python
"""Factor calculation service (Port layer)."""

from ditto_foundation import logger, traced

from ditto_core.factor.engine import FactorEngine
from ditto_datahub import DataHub


class FactorCalculationService:
    """
    Factor calculation orchestration service.

    Orchestrates the factor calculation workflow:
    1. Determine which factors need recalculation
    2. Call FactorEngine to calculate
    3. Write to DataHub with PIT metadata
    4. Track calculation metadata
    """

    def __init__(
        self,
        datahub: DataHub,
        factor_engine: FactorEngine,
    ) -> None:
        """
        Initialize FactorCalculationService.

        Args:
            datahub: DataHub for reading features and writing factors.
            factor_engine: Factor engine for calculation.
        """
        self._datahub = datahub
        self._engine = factor_engine

    @traced("port.service.calculate_factors")
    def calculate_universe_factors(
        self,
        universe_ids: list[int],
        start_date: str,
        end_date: str,
        factor_ids: list[str] | None = None,
        as_of_date: str | None = None,
    ) -> dict[str, int]:
        """
        Calculate factors for a universe of securities.

        Args:
            universe_ids: List of security IDs.
            start_date: Start date.
            end_date: End date.
            factor_ids: List of factors to calculate.
            as_of_date: PIT query date for input features.

        Returns:
            Dictionary with calculation results.
        """
        logger.info(
            "Starting universe factor calculation",
            universe_size=len(universe_ids),
            start=start_date,
            end=end_date,
            factors=factor_ids,
            as_of_date=as_of_date,
        )

        # Call FactorEngine
        results = self._engine.calculate_batch(
            sids=universe_ids,
            start_date=start_date,
            end_date=end_date,
            factor_ids=factor_ids,
            as_of_date=as_of_date,
        )

        logger.info(
            "Universe factor calculation completed",
            results=results,
        )

        return results
```

---

## 四、数据流详解

### 4.1 特征计算流程

```
┌─────────────────────────────────────────────────────────────┐
│ Port Layer: FeatureCalculationService                      │
│  - 接收计算请求                                             │
│  - 确定需要计算的证券范围                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Core Layer: FeatureEngine                                   │
│  - datahub.market.get_bars()  ← 读取原始数据                │
│  - FeatureCalculator.get_calculator()  → 获取计算器        │
│  - calculator.calculate()  → 执行计算                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ 写入
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ DataHub Layer: Features Domain                             │
│  - IndicatorStore.write()  ← 写入 Parquet 文件             │
│  - IndicatorMetadataStore  ← 元数据管理                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 因子计算流程

```
┌─────────────────────────────────────────────────────────────┐
│ Port Layer: FactorCalculationService                       │
│  - 接收计算请求                                             │
│  - 确定需要计算的因子列表                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Core Layer: FactorEngine                                   │
│  - datahub.features.get_indicators()  ← 读取特征            │
│  - FactorCalculator.get_calculator()  → 获取计算器        │
│  - calculator.calculate()  → 计算因子暴露度                │
│  - 添加 PIT 元数据                                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ 写入
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ DataHub Layer: Factors Domain                              │
│  - FactorStore.write()  ← 写入 Parquet 文件                │
│  - 支持 PIT 查询                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、接口契约

### 5.1 Core → DataHub 接口

**Core 层调用 DataHub 的方式**：

```python
# 读取原始数据
source_df = datahub.market.get_bars(
    BarsQuery(sids=[1, 2, 3], start="2024-01-01", end="2024-01-31")
)

# 读取特征（用于因子计算）
feature_df = datahub.features.get_indicators(
    FeatureQuery(
        indicators=["indicator_rsi_14", "indicator_ma_20"],
        start="2024-01-01",
        end="2024-01-31",
        asof="2024-01-15",  # PIT 查询
    )
)

# 写入计算结果
# 注意：Core 层直接调用 Store，不通过 Service
# （为了性能，避免 Service 层的不必要抽象）
datahub.features._indicator_store.write(df, year=2024)
```

### 5.2 Port → Core 接口

**Port 层调用 Core 引擎的方式**：

```python
# Port Service 只做编排，不实现计算
class FeatureCalculationService:
    def calculate_universe_features(...):
        # 1. 准备参数
        # 2. 调用 Core 引擎
        results = self._engine.calculate_batch(...)
        # 3. 返回结果
        return results
```

---

## 六、配置化设计

### 6.1 特征计算配置

```yaml
# config/features/technical_indicators.yaml
indicators:
  - id: indicator_rsi_14
    name: RSI(14)
    type: momentum
    calculator: ditto_core.feature.technical.momentum.RSI14Calculator
    required_columns: [close]
    parameters:
      period: 14

  - id: indicator_ma_20
    name: MA(20)
    type: trend
    calculator: ditto_core.feature.technical.trend.MA20Calculator
    required_columns: [close]
    parameters:
      period: 20

  - id: indicator_macd
    name: MACD
    type: trend
    calculator: ditto_core.feature.technical.trend.MACDCalculator
    required_columns: [close]
    parameters:
      fast_period: 12
      slow_period: 26
      signal_period: 9
```

### 6.2 因子计算配置

```yaml
# config/factors/technical_factors.yaml
factors:
  - id: factor_momentum_12m
    name: 12-Month Momentum
    class: technical
    family: momentum
    calculator: ditto_core.factor.technical.momentum.Momentum12MFatherFactor
    required_features: [close]
    normalization: zscore
    parameters:
      period: 252  # 12 months ~ 252 trading days

  - id: factor_value_pe
    name: PE Value Factor
    class: fundamental
    family: value
    calculator: ditto_core.factor.fundamental.value.PEValueFactor
    required_features: [pe_ttm]  # From Fundamental domain
    normalization: winsorize_zscore
    parameters:
      lookback: 500
```

---

## 七、实施任务清单

### Phase 7: Features Domain (存储层)
1. ✅ 已在 `docs/plans/2026-02-01-features-factors-implementation.md` 定义

### Phase 7: Core 计算引擎 (新增)
1. 创建 `packages/core/src/ditto_core/feature/` 目录结构
2. 实现 `FeatureCalculator` 基类和注册表
3. 实现技术指标计算器（Trend, Momentum, Volatility, Volume）
4. 实现 `FeatureEngine` 协调器

### Phase 8: Core 计算引擎 (新增)
1. 创建 `packages/core/src/ditto_core/factor/` 目录结构
2. 实现 `FactorCalculator` 基类和注册表
3. 实现技术因子和基本面因子计算器
4. 实现 `FactorEngine` 协调器
5. 实现标准化模块

### Phase 9: Port 编排服务 (新增)
1. 创建 `apps/port/src/ditto_port/services/feature/`
2. 实现 `FeatureCalculationService`
3. 创建 `apps/port/src/ditto_port/services/factor/`
4. 实现 `FactorCalculationService`

### Phase 10: 配置与编排
1. 设计特征/因子配置 YAML 格式
2. 实现配置加载器
3. 与 Prefect 集成（定时计算任务）

---

## 八、关键设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **Core 调用 DataHub** | 直接调用 Store，不通过 Service | 避免不必要抽象，性能考虑 |
| **计算器注册表** | 装饰器模式 + 注册表 | 声明式配置，易于扩展 |
| **PIT 元数据** | Core 层生成，DataHub 存储 | Core 负责逻辑，DataHub 负责存储 |
| **配置驱动** | YAML 定义特征/因子 | 无需修改代码即可新增计算 |
| **错误处理** | Port 层负责重试和日志 | Core 层专注计算逻辑 |

---

**文档版本**: v1.0
**最后更新**: 2026-02-01
**相关文档**:
- [2026-02-01-features-factors-domain-design.md](../plans/2026-02-01-features-factors-domain-design.md)
- [2026-02-01-features-factors-implementation.md](../plans/2026-02-01-01-features-factors-implementation.md)
- [01_system_design.md](../design/01_system_design.md)
- [03_engine_design.md](../design/03_engine_design.md)
