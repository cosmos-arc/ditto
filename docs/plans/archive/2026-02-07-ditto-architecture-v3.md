# Ditto 量化系统架构设计 v3.0

> **核心理念**：简洁的层次、清晰的职责、符合量化业务逻辑
>
> **基于业界最佳实践**：WorldQuant、Two Sigma、Citadel、九坤等领先量化机构的架构模式
>
> **设计日期**：2026-02-07

---

## 一、整体架构总览

### 1.1 四层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │   CLI    │ │HTTP API  │ │  Web UI  │ │ Jupyter/Lab        │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                        Application Layer                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ Factor   │ │ Backtest │ │ Trading  │ │ Ingestion          │  │
│  │ Orch.    │ │ Orch.    │ │ Orch.    │ │ Orchestrator       │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                         Domain Layer                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐ │  │
│  │  │  Alpha  │ │ Factor  │ │Backtest │ │    Quality     │ │ │  │
│  │  │ Engine  │ │ Engine  │ │ Engine  │ │    Engine       │ │ │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────────┘ │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────────────────┐      │  │
│  │  │   Risk  │ │ Trading │ │      ML/AI             │      │  │
│  │  │ Engine  │ │ Engine  │ │      Engine             │      │  │
│  │  └─────────┘ └─────────┘ └─────────────────────────┘      │  │
│  └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                      Infrastructure Layer                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │ DataReaders  │ │ DataWriters  │ │  DataSources     │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │  Pipelines   │ │   Storage    │ │  Config/Logger   │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 依赖关系

```
Presentation Layer
    ↓ 依赖
Application Layer (编排层)
    ↓ 依赖
Domain Layer + Infrastructure Layer
    ↓ 依赖
Foundation Layer

规则：
1. Domain Layer 不依赖任何外层（纯净业务逻辑）
2. Domain Layer 通过 Protocol 定义需求接口
3. Infrastructure Layer 实现 Domain 定义的接口
4. Application Layer 编排 Domain 和 Infrastructure
```

---

## 二、各层职责定义

### 2.1 层级职责表

| 层级 | 职责 | 依赖 | 不做什么 |
|------|------|------|---------|
| **Presentation** | 用户交互、API 展示 | Application | 业务逻辑、数据访问 |
| **Application** | 用例编排、事务边界、调度、异常处理 | Domain + Infrastructure | 业务规则计算、数据访问实现 |
| **Domain** | 业务逻辑、量化规则、算法模型 | Foundation | 数据访问、外部服务调用 |
| **Infrastructure** | 数据访问、外部服务适配、技术实现 | Foundation + Domain(Protocol) | 业务逻辑、业务规则 |
| **Foundation** | 基础组件：日志、缓存、并发、配置 | 无（零依赖） | 业务相关 |

### 2.2 关键组件归属

| 组件 | 归属层 | 理由 |
|------|--------|------|
| **QualityEngine** | Domain | 数据质量规则是量化业务逻辑（OHLC 校验、涨跌停检测） |
| **FactorEngine** | Domain | 因子计算是核心业务逻辑 |
| **BacktestEngine** | Domain | 回测是核心业务逻辑 |
| **IngestionOrchestrator** | Application | 数据摄入是业务编排（调度、重试、失败处理） |
| **DataReader/Writer** | Infrastructure | 纯数据访问，技术实现 |
| **DataSource** | Infrastructure | 外部数据源适配器 |
| **Pipeline** | Infrastructure | ETL 原语，无状态，可复用 |

---

## 三、数据分层设计（个人量化简化版）

### 3.1 两层架构

```
data_root/
├── standard/               # 标准数据（清晰后的数据）
│   ├── bars_daily.parquet
│   ├── bars_minute/
│   │   └── trade_date=2024-01-15/
│   ├── financials.parquet
│   ├── securities.parquet
│   ├── calendar.parquet
│   ├── adj_factor.parquet
│   └── universe/
│       ├── hs300.parquet
│       └── zz500.parquet
│
└── derived/                # 衍生数据（因子、特征、标签）
    ├── factors/
    │   ├── momentum_20d/
    │   │   └── v1.0.0/
    │   │       ├── metadata.json
    │   │       └── values.parquet
    │   └── pb_ratio/
    ├── features/
    │   └── feature_set_alpha01/
    │       └── v1/
    │           ├── train.parquet
    │           └── metadata.json
    └── labels/
        ├── fwd_ret_5d/
        └── fwd_ret_20d/
```

### 3.2 层级定义

| 层级 | 职责 | 数据特征 | 来源 |
|------|------|---------|------|
| **Standard** | 清晰、标准化的基础数据 | 统一 Schema、类型标准化、去重 | 数据源 → ETL |
| **Derived** | 因子、特征、标签等衍生数据 | 高频访问、版本化 | Domain Engine 计算 |

**为什么不需要 Raw 层？**
- 个人量化通常数据量不大
- 数据源稳定（TuShare、AkShare），可重新拉取
- 简化架构，降低维护成本
- 如需追溯，可在 Standard 层保留 `_raw_snapshot` 列

---

## 四、核心接口设计

### 4.1 Domain Layer 定义需求接口

```python
# packages/core/src/ditto_core/protocols/data.py

from abc import ABC, abstractmethod
from datetime import date
from typing import Protocol
import polars as pl


class IDataSource(Protocol):
    """数据源接口（Domain 定义需求）"""

    @abstractmethod
    def fetch(self, dataset: str, trade_date: date) -> pl.DataFrame:
        """从外部数据源获取数据"""
        ...


class IDataReader(Protocol):
    """数据读取器接口（Domain 定义需求）"""

    @abstractmethod
    def read(self, dataset: str, **kwargs) -> pl.DataFrame:
        """读取数据"""
        ...

    @abstractmethod
    def get_latest_date(self, dataset: str) -> date | None:
        """获取最新数据日期"""
        ...


class IDataWriter(Protocol):
    """数据写入器接口（Domain 定义需求）"""

    @abstractmethod
    def write(self, df: pl.DataFrame, dataset: str, layer: str) -> None:
        """写入数据到指定层"""
        ...


class IDataProvider(Protocol):
    """数据提供者接口（Domain Engine 使用的统一接口）"""

    @abstractmethod
    def get_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """获取 K 线数据"""
        ...

    @abstractmethod
    def get_financials(
        self,
        symbols: list[str],
        report_period: str,
    ) -> pl.DataFrame:
        """获取财务数据"""
        ...
```

### 4.2 Infrastructure Layer 实现接口

```python
# packages/infrastructure/src/ditto_infrastructure/readers/bars.py

from pathlib import Path
import polars as pl
from ditto_core.protocols import IDataReader


class ParquetBarsReader(IDataReader):
    """Parquet K 线读取器（Infrastructure）

    职责：
    - 实现 IDataReader 接口
    - 纯技术实现，无业务逻辑
    """

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "bars_daily.parquet"

    def read(self, dataset: str, **kwargs) -> pl.DataFrame:
        symbols = kwargs.get("symbols", [])
        start = kwargs.get("start_date")
        end = kwargs.get("end_date")

        query = pl.scan_parquet(self.path)

        if symbols:
            query = query.filter(pl.col("symbol").is_in(symbols))
        if start:
            query = query.filter(pl.col("trade_date") >= start)
        if end:
            query = query.filter(pl.col("trade_date") <= end)

        return query.collect()

    def get_latest_date(self, dataset: str) -> date | None:
        result = (
            pl.scan_parquet(self.path)
            .select(pl.col("trade_date").max())
            .collect()
        )
        return result[0, "trade_date"] if not result.is_empty() else None


class ParquetBarsWriter(IDataWriter):
    """Parquet K 线写入器（Infrastructure）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root

    def write(self, df: pl.DataFrame, dataset: str, layer: str) -> None:
        target = self.data_root / layer / f"{dataset}.parquet"
        df.write_parquet(target)
```

---

## 五、QualityEngine（Domain Layer）

### 5.1 引擎设计

```python
# packages/core/src/ditto_core/quality/engine.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
import polars as pl


class Severity(Enum):
    """问题严重程度"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IChecker(ABC):
    """质量检查器接口"""

    @abstractmethod
    def check(self, df: pl.DataFrame) -> list["QualityIssue"]:
        ...


@dataclass
class QualityIssue:
    """质量问题"""
    checker: str
    severity: Severity
    column: str | None
    row: int | None
    message: str
    value: object | None


@dataclass
class QualityResult:
    """质量检查结果"""
    is_valid: bool
    issues: list[QualityIssue]
    stats: dict

    @classmethod
    def valid(cls) -> "QualityResult":
        return cls(is_valid=True, issues=[], stats={})

    @classmethod
    def invalid(cls, issues: list[QualityIssue]) -> "QualityResult":
        return cls(is_valid=False, issues=issues, stats={})


class QualityEngine:
    """质量引擎（Domain Layer）

    职责：
    - 编排质量检查流程
    - 管理检查器规则
    - 生成质量报告

    核心特点：
    - 这是量化业务逻辑，不是技术约束
    - OHLC 一致性、涨跌停检测是金融知识
    - 可被 Application Layer 调用
    """

    def __init__(self, checkers: list[IChecker] | None = None):
        self.checkers = checkers or []

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        rules: list[str] | None = None,
    ) -> QualityResult:
        """执行质量检查"""

        # 1. 加载规则
        active_checkers = self._load_checkers(dataset, rules)

        # 2. 执行检查
        all_issues = []
        for checker in active_checkers:
            issues = checker.check(df)
            all_issues.extend(issues)

        # 3. 判断结果
        errors = [i for i in all_issues if i.severity == Severity.ERROR]
        is_valid = len(errors) == 0

        return QualityResult(
            is_valid=is_valid,
            issues=all_issues,
            stats={
                "total_checks": len(active_checkers),
                "total_issues": len(all_issues),
                "errors": len(errors),
            },
        )

    def _load_checkers(self, dataset: str, rules: list[str] | None) -> list[IChecker]:
        """加载检查器"""
        if rules:
            return [c for c in self.checkers if c.name in rules]
        return self.checkers
```

### 5.2 业务规则示例

```python
# packages/core/src/ditto_core/quality/checkers/business.py

from ditto_core.quality import IChecker, QualityIssue, Severity
import polars as pl


class OHLCConsistencyChecker(IChecker):
    """OHLC 一致性检查（金融业务规则）

    职责：验证 high >= close >= low，这是金融市场的约束
    这是业务逻辑，不是技术约束！
    """

    name = "ohlc_consistency"

    def check(self, df: pl.DataFrame) -> list[QualityIssue]:
        issues = []

        # 业务规则：high >= close >= low
        invalid = df.filter(
            (pl.col("high") < pl.col("close")) |
            (pl.col("close") < pl.col("low"))
        )

        for row in invalid.iter_rows(named=True):
            issues.append(QualityIssue(
                checker=self.name,
                severity=Severity.ERROR,
                column="ohlc",
                row=row.get("id"),
                message=f"OHLC 不一致: h={row['high']}, c={row['close']}, l={row['low']}",
                value=row,
            ))

        return issues


class LimitUpChecker(IChecker):
    """涨跌停检查（交易规则）

    职责：检测涨跌停，这是交易规则的约束
    这是业务逻辑！
    """

    name = "limit_up_check"

    def __init__(self, limit: float = 0.10):
        self.limit = limit

    def check(self, df: pl.DataFrame) -> list[QualityIssue]:
        issues = []

        # 业务规则：涨幅超过阈值
        df_with_pct = df.with_columns([
            (pl.col("close") / pl.col("prev_close") - 1).alias("pct_change")
        ])

        limit_up = df_with_pct.filter(
            pl.col("pct_change") >= self.limit
        )

        for row in limit_up.iter_rows(named=True):
            issues.append(QualityIssue(
                checker=self.name,
                severity=Severity.WARNING,
                column="close",
                row=row.get("id"),
                message=f"触及涨停: {row['pct_change']:.2%}",
                value=row,
            ))

        return issues
```

---

## 六、IngestionOrchestrator（Application Layer）

### 6.1 编排器设计

```python
# apps/port/src/ditto_port/orchestration/ingestion.py

from datetime import date
from typing import Literal
from ditto_foundation import logger


class IngestionOrchestrator:
    """数据摄入编排器（Application Layer）

    职责：
    - 编排数据摄入流程
    - 业务决策：增量/全量、重试策略
    - 异常处理：失败重试、降级策略
    - 调度协调：触发下游任务

    依赖注入：
    - IDataReader/IDataWriter（Infrastructure）
    - QualityEngine（Domain）
    - IDataSource（Infrastructure）
    """

    def __init__(
        self,
        data_reader: "IDataReader",
        data_writer: "IDataWriter",
        quality_engine: "QualityEngine",
        data_source: "IDataSource",
    ):
        self.data_reader = data_reader
        self.data_writer = data_writer
        self.quality_engine = quality_engine
        self.data_source = data_source

    def run_daily_ingestion(
        self,
        trade_date: date,
        datasets: list[str] | None = None,
    ) -> dict[str, "IngestionResult"]:
        """执行每日数据摄入（业务编排）"""

        results = {}
        datasets = datasets or self._get_active_datasets()

        for dataset in datasets:
            try:
                # 业务决策：确定摄入模式
                mode = self._determine_mode(dataset, trade_date)

                # 业务决策：执行摄入
                result = self._ingest_dataset(dataset, trade_date, mode)
                results[dataset] = result

                # 业务逻辑：成功后处理
                if result.success:
                    self._on_success(dataset, result)
                else:
                    result = self._handle_failure(dataset, result)
                    results[dataset] = result

            except Exception as e:
                logger.error("ingestion_error", dataset=dataset, error=str(e))
                results[dataset] = IngestionResult(success=False, error=str(e))

        return results

    def _ingest_dataset(
        self,
        dataset: str,
        trade_date: date,
        mode: Literal["incremental", "full"],
    ) -> "IngestionResult":
        """摄入单个数据集（编排）"""

        # 1. Extract（委托给 DataSource）
        raw = self.data_source.fetch(dataset, trade_date)

        # 2. Transform（委托给 Pipeline）
        clean = self._transform_data(raw, dataset)

        # 3. Validate（委托给 QualityEngine）
        dq_result = self.quality_engine.check(clean, dataset=dataset)
        if not dq_result.is_valid:
            return self._handle_dq_failure(dataset, dq_result)

        # 4. Load（委托给 DataWriter）
        self.data_writer.write(clean, dataset=dataset, layer="standard")

        return IngestionResult(success=True, rows=len(clean))

    def _determine_mode(self, dataset: str, trade_date: date) -> Literal["incremental", "full"]:
        """业务决策：确定摄入模式"""
        latest = self.data_reader.get_latest_date(dataset)
        if latest and latest >= trade_date:
            return "incremental"
        return "full"

    def _handle_dq_failure(self, dataset: str, dq_result) -> "IngestionResult":
        """业务逻辑：处理质量检查失败"""
        errors = [i for i in dq_result.issues if i.severity == Severity.ERROR]
        if errors:
            logger.error("dq_failed", dataset=dataset, errors=len(errors))
            return IngestionResult(success=False, error="DQ check failed")
        return IngestionResult(success=True, warning="DQ warnings")

    def _on_success(self, dataset: str, result: "IngestionResult"):
        """业务逻辑：成功后处理"""
        logger.info("ingestion_success", dataset=dataset, rows=result.rows)
        # 触发下游任务
```

---

## 七、目录结构

```
ditto/
├── packages/
│   ├── core/                      # Domain Layer（核心业务逻辑）
│   │   └── src/ditto_core/
│   │       ├── quality/            # 质量引擎
│   │       │   ├── engine.py       # QualityEngine
│   │       │   └── checkers/       # 检查器
│   │       │       ├── technical.py
│   │       │       ├── business.py  # OHLC、涨跌停
│   │       │       └── statistical.py
│   │       ├── factor/             # 因子引擎
│   │       │   ├── engine.py
│   │       │   └── calculators/
│   │       ├── backtest/           # 回测引擎
│   │       │   └── engine.py
│   │       ├── risk/               # 风险引擎
│   │       │   └── engine.py
│   │       ├── strategy/           # 策略引擎
│   │       │   └── engine.py
│   │       └── protocols/          # Domain 定义的需求接口
│   │           └── data.py         # IDataSource, IDataReader, IDataWriter
│   │
│   ├── infrastructure/             # Infrastructure Layer（技术实现）
│   │   └── src/ditto_infrastructure/
│   │       ├── readers/            # 数据读取器
│   │       │   ├── bars.py         # ParquetBarsReader
│   │       │   ├── factors.py
│   │       │   └── financials.py
│   │       ├── writers/            # 数据写入器
│   │       │   ├── bars.py         # ParquetBarsWriter
│   │       │   └── factors.py
│   │       ├── sources/            # 数据源
│   │       │   ├── tushare/
│   │       │   └── akshare/
│   │       ├── pipelines/          # ETL 管道（无状态）
│   │       │   └── transform.py
│   │       ├── storage/            # 存储相关
│   │       │   ├── sid_allocator.py
│   │       │   └── file_lock.py
│   │       └── config/             # 配置管理
│   │
│   └── foundation/                 # Foundation Layer（基础组件）
│       └── src/ditto_foundation/
│           ├── logger.py
│           ├── cache.py
│           └── concurrency.py
│
├── apps/
│   └── port/                      # Application Layer（编排层）
│       └── src/ditto_port/
│           ├── orchestration/      # 编排器
│           │   ├── ingestion.py    # IngestionOrchestrator
│           │   ├── factor.py       # FactorOrchestrator
│           │   └── backtest.py     # BacktestOrchestrator
│           ├── services/           # 应用服务（对外 API）
│           │   ├── factor_service.py
│           │   └── backtest_service.py
│           ├── api/                # HTTP API
│           ├── cli/                # CLI
│           └── jobs/               # 定时任务
│
└── data_root/
    ├── standard/                   # 标准数据
    └── derived/                    # 衍生数据
```

---

## 八、架构原则总结

### 8.1 核心设计原则

| 原则 | 说明 |
|------|------|
| **Domain 纯净** | 不依赖外部，只包含业务逻辑 |
| **Infrastructure 薄** | 只负责技术实现，无业务逻辑 |
| **Application 编排** | 协调 Domain 和 Infrastructure |
| **接口由 Domain 定义** | Domain 定义 Protocol，Infrastructure 实现 |
| **质量引擎是 Domain** | 数据质量规则是量化业务逻辑 |
| **摄入编排是 Application** | 业务编排，不是技术能力 |

### 8.2 关键改进点

| 改进项 | 说明 |
|--------|------|
| **QualityEngine 归属** | Domain Layer（是业务逻辑） |
| **IngestionOrchestrator 归属** | Application Layer（是业务编排） |
| **数据分层** | 两层（Standard + Derived），适合个人量化 |
| **Pipeline 职责** | 无状态 ETL 原语，可复用 |
| **依赖关系** | Domain 定义接口，Infrastructure 实现 |
| **模块划分** | Infrastructure 薄，Domain 厚 |

---

## 九、下一步行动

### 9.1 短期（1-2 周）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 创建 infrastructure 包 | 从 datahub 迁移纯数据访问组件 | ⭐⭐⭐⭐⭐ |
| 移动 QualityEngine 到 core | 确认是 Domain Layer | ⭐⭐⭐⭐⭐ |
| 创建 protocols 模块 | Domain 定义需求接口 | ⭐⭐⭐⭐ |
| 实现 ParquetBarsReader/Writer | Infrastructure 实现接口 | ⭐⭐⭐⭐ |

### 9.2 中期（1-2 个月）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 重构目录结构 | 按新架构组织代码 | ⭐⭐⭐⭐ |
| 实现两层数据存储 | Standard + Derived | ⭐⭐⭐⭐ |
| 创建 IngestionOrchestrator | Application Layer 编排 | ⭐⭐⭐ |
| 完善 Domain Protocols | 所有 Domain 需求接口 | ⭐⭐⭐ |

### 9.3 长期（3-6 个月）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 因子库版本管理 | Derived 层完整实现 | ⭐⭐⭐⭐ |
| 特征库管理 | ML 特征存储 | ⭐⭐⭐ |
| 数据血缘追踪 | lineage 追踪 | ⭐⭐ |

---

**文档版本**: 1.0
**最后更新**: 2026-02-07
