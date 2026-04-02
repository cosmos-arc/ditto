# Ditto 量化系统架构设计 v3.1

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
│  │ Service  │ │ Service  │ │ Service  │ │ Orchestrator       │  │
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
│                       DataHub Layer                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │ Repositories │ │  Pipelines   │ │   DataSources    │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │   Storage    │ │   Runtime    │ │   Config/Meta    │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                      Foundation Layer                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ Config     │ │ Log/Metric │ │ Cache      │ │ Concurrency   │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 依赖关系

```
Presentation Layer
    ↓ 依赖
Application Layer (编排层)
    ↓ 依赖
Domain Layer + DataHub Layer
    ↓ 依赖
Foundation Layer

规则：
1. Domain Layer 不依赖 DataHub（通过 Repository 接口解耦）
2. DataHub 定义 Repository 接口，Domain Engine 通过接口调用
3. Application Layer 注入 Repository 实现
4. Domain Layer 包含 QualityEngine（业务逻辑）
```

---

## 二、各层职责定义

### 2.1 层级职责表

| 层级 | 职责 | 依赖 | 不做什么 |
|------|------|------|---------|
| **Presentation** | 用户交互、API 展示 | Application | 业务逻辑、数据访问 |
| **Application** | 用例编排、事务边界、调度、异常处理 | Domain + DataHub | 业务规则计算、数据访问实现 |
| **Domain** | 业务逻辑、量化规则、算法模型 | Foundation | 数据访问实现、外部服务调用 |
| **DataHub** | 数据访问、存储、外部服务适配 | Foundation + Domain(注入) | 业务规则计算 |
| **Foundation** | 基础组件：日志、缓存、并发、配置 | 无（零依赖） | 业务相关 |

### 2.2 关键组件归属

| 组件 | 归属层 | 理由 |
|------|--------|------|
| **QualityEngine** | Domain | 数据质量规则是量化业务逻辑 |
| **FactorEngine** | Domain | 因子计算是核心业务逻辑 |
| **BacktestEngine** | Domain | 回测是核心业务逻辑 |
| **IngestionOrchestrator** | Application | 数据摄入是业务编排 |
| **Repository** | DataHub | 数据访问抽象 |
| **DataSource** | DataHub | 外部数据源适配器 |
| **Pipeline** | DataHub | ETL 原语 |

---

## 三、DataHub 层架构

### 3.1 Repository 模式

```python
# packages/data/src/ditto_data/repositories/bars.py

from abc import ABC, abstractmethod
from datetime import date
from typing import Literal
import polars as pl


class IBarsRepository(ABC):
    """K 线数据仓储接口"""

    @abstractmethod
    def get_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        freq: Literal["1d", "1m"] = "1d",
        adj: Literal["none", "qfq", "hfq"] = "none",
        as_of: date | None = None,
    ) -> pl.DataFrame:
        """获取 K 线数据"""
        pass

    @abstractmethod
    def write_bars(self, df: pl.DataFrame, dataset: str) -> None:
        """写入 K 线数据"""
        pass

    @abstractmethod
    def get_latest_date(self, symbol: str) -> date | None:
        """获取最新数据日期"""
        pass


class StockBarsRepository(IBarsRepository):
    """股票 K 线仓储"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "stock" / "bars_daily.parquet"

    def get_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        freq: Literal["1d", "1m"] = "1d",
        adj: Literal["none", "qfq", "hfq"] = "none",
        as_of: date | None = None,
    ) -> pl.DataFrame:
        query = pl.scan_parquet(self.path).filter(
            pl.col("symbol").is_in(symbols),
            pl.col("trade_date").between(start_date, end_date),
        )

        if as_of:
            query = query.filter(pl.col("knowledge_date") <= as_of)

        return query.collect()

    def write_bars(self, df: pl.DataFrame, dataset: str) -> None:
        df.write_parquet(self.path)

    def get_latest_date(self, symbol: str) -> date | None:
        result = (
            pl.scan_parquet(self.path)
            .filter(pl.col("symbol") == symbol)
            .select(pl.col("trade_date").max())
            .collect()
        )
        return result[0, "trade_date"] if not result.is_empty() else None


class ETFBarsRepository(IBarsRepository):
    """ETF K 线仓储"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "etf" / "bars_daily.parquet"

    def get_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        freq: Literal["1d", "1m"] = "1d",
        adj: Literal["none", "qfq", "hfq"] = "none",
        as_of: date | None = None,
    ) -> pl.DataFrame:
        query = pl.scan_parquet(self.path).filter(
            pl.col("symbol").is_in(symbols),
            pl.col("trade_date").between(start_date, end_date),
        )

        if as_of:
            query = query.filter(pl.col("knowledge_date") <= as_of)

        return query.collect()

    def write_bars(self, df: pl.DataFrame, dataset: str) -> None:
        df.write_parquet(self.path)

    def get_latest_date(self, symbol: str) -> date | None:
        result = (
            pl.scan_parquet(self.path)
            .filter(pl.col("symbol") == symbol)
            .select(pl.col("trade_date").max())
            .collect()
        )
        return result[0, "trade_date"] if not result.is_empty() else None
```

### 3.2 其他 Repository 接口

```python
# packages/data/src/ditto_data/repositories/factors.py

class IFactorRepository(ABC):
    """因子仓储接口"""

    @abstractmethod
    def get_factor(
        self,
        factor_name: str,
        symbols: list[str],
        start_date: date,
        end_date: date,
        version: str | None = None,
    ) -> pl.DataFrame:
        """获取因子数据"""
        pass

    @abstractmethod
    def save_factor(
        self,
        factor_name: str,
        data: pl.DataFrame,
        version: str,
        metadata: dict,
    ) -> None:
        """保存因子数据"""
        pass


class FactorRepository(IFactorRepository):
    """因子仓储实现"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.base_path = data_root / "derived" / "factors"

    def get_factor(
        self,
        factor_name: str,
        symbols: list[str],
        start_date: date,
        end_date: date,
        version: str | None = None,
    ) -> pl.DataFrame:
        if version:
            path = self.base_path / factor_name / version / "values.parquet"
        else:
            path = self.base_path / factor_name / "latest" / "values.parquet"

        return pl.scan_parquet(path).filter(
            pl.col("symbol").is_in(symbols),
            pl.col("trade_date").between(start_date, end_date),
        ).collect()

    def save_factor(
        self,
        factor_name: str,
        data: pl.DataFrame,
        version: str,
        metadata: dict,
    ) -> None:
        import json
        from pathlib import Path

        factor_dir = self.base_path / factor_name / version
        factor_dir.mkdir(parents=True, exist_ok=True)

        # 保存数据
        data.write_parquet(factor_dir / "values.parquet")

        # 保存元数据
        with open(factor_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

        # 更新 latest 链接
        latest_link = self.base_path / factor_name / "latest"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(version)
```

---

## 四、数据分层设计

### 4.1 目录结构（ETF/Stock 明确划分）

```
data_root/
├── standard/                           # 标准数据
│   ├── stock/                          # 股票数据
│   │   ├── bars_daily.parquet
│   │   ├── bars_minute/
│   │   │   └── trade_date=2024-01-15/
│   │   ├── adj_factor.parquet
│   │   ├── status.parquet              # 股票状态（ST、停牌）
│   │   └── calendar.parquet           # 股票交易日历
│   │
│   ├── etf/                            # ETF 数据
│   │   ├── bars_daily.parquet
│   │   ├── bars_minute/
│   │   ├── adj_factor.parquet
│   │   ├── status.parquet              # ETF 状态
│   │   ├── nav.parquet                 # 净值
│   │   └── calendar.parquet            # ETF 交易日历
│   │
│   ├── index/                          # 指数数据
│   │   ├── bars_daily.parquet
│   │   ├── constituents/               # 成分股
│   │   │   └── trade_date=2024-01-15/
│   │   └── weights/                    # 权重
│   │
│   ├── financials/                     # 财务数据
│   │   ├── balance_sheet.parquet
│   │   ├── income_statement.parquet
│   │   ├── cash_flow.parquet
│   │   └── indicators.parquet
│   │
│   └── metadata/                       # 元数据
│       ├── securities.parquet          # 证券信息
│       ├── industries.parquet          # 行业分类
│       └── universe/                   # 股票池
│           ├── hs300.parquet
│           └── zz500.parquet
│
└── derived/                            # 衍生数据
    ├── factors/                        # 因子库
    │   ├── momentum_20d/
    │   │   └── v1.0.0/
    │   │       ├── metadata.json
    │   │       └── values.parquet
    │   └── pb_ratio/
    ├── features/                       # ML 特征库
    │   └── feature_set_alpha01/
    │       └── v1/
    │           ├── train.parquet
    │           └── metadata.json
    └── labels/                         # 标签库
        ├── fwd_ret_5d/
        └── fwd_ret_20d/
```

### 4.2 存储层级定义

| 层级 | 职责 | 数据特征 | 来源 |
|------|------|---------|------|
| **Standard** | 清晰、标准化的基础数据 | 统一 Schema、类型标准化、去重 | 数据源 → ETL |
| **Derived** | 因子、特征、标签等衍生数据 | 高频访问、版本化 | Domain Engine 计算 |

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


class QualityEngine:
    """质量引擎（Domain Layer）

    职责：
    - 编排质量检查流程
    - 管理检查器规则
    - 生成质量报告

    核心特点：
    - 这是量化业务逻辑，不是技术约束
    - OHLC 一致性、涨跌停检测是金融知识
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

---

## 六、Domain Engine 使用 Repository

### 6.1 FactorEngine 示例

```python
# packages/core/src/ditto_core/factor/engine.py

from datetime import date
from typing import Protocol
import polars as pl


class FactorEngine:
    """因子计算引擎（Domain Layer）

    通过 Repository 接口访问数据，不依赖具体实现
    """

    def __init__(
        self,
        stock_bars_repo: "IBarsRepository",  # 注入接口
        etf_bars_repo: "IBarsRepository",    # 注入接口
        factor_repo: "IFactorRepository",    # 注入接口
    ):
        self.stock_bars_repo = stock_bars_repo
        self.etf_bars_repo = etf_bars_repo
        self.factor_repo = factor_repo

    def calculate_momentum_20d(
        self,
        symbols: list[str],
        asset_type: "stock" | "etf",
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """计算 20 日动量因子"""

        # 1. 根据资产类型选择仓储
        if asset_type == "stock":
            bars = self.stock_bars_repo.get_bars(symbols, start_date, end_date)
        else:
            bars = self.etf_bars_repo.get_bars(symbols, start_date, end_date)

        # 2. 业务逻辑：计算动量
        result = bars.with_columns([
            pl.col("close")
            .pct_change(n=20)
            .over("symbol")
            .alias("momentum_20d")
        ])

        # 3. 保存结果
        self.factor_repo.save_factor(
            factor_name="momentum_20d",
            data=result,
            version="1.0.0",
            metadata={"description": "20日动量因子"},
        )

        return result
```

---

## 七、Application Layer 编排

### 7.1 IngestionOrchestrator

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

    依赖注入：
    - Repository（DataHub）
    - QualityEngine（Domain）
    - DataSource（DataHub）
    """

    def __init__(
        self,
        stock_bars_repo: "IBarsRepository",
        etf_bars_repo: "IBarsRepository",
        quality_engine: "QualityEngine",
        data_source: "IDataSource",
    ):
        self.stock_bars_repo = stock_bars_repo
        self.etf_bars_repo = etf_bars_repo
        self.quality_engine = quality_engine
        self.data_source = data_source

    def run_daily_ingestion(
        self,
        trade_date: date,
        datasets: list[str] | None = None,
    ) -> dict[str, "IngestionResult"]:
        """执行每日数据摄入（业务编排）"""

        results = {}
        datasets = datasets or ["stock_bars", "etf_bars", "financials"]

        for dataset in datasets:
            try:
                # 业务决策：选择对应的仓储
                if dataset == "stock_bars":
                    repo = self.stock_bars_repo
                elif dataset == "etf_bars":
                    repo = self.etf_bars_repo
                else:
                    continue

                # 执行摄入
                result = self._ingest_dataset(dataset, trade_date, repo)
                results[dataset] = result

            except Exception as e:
                logger.error("ingestion_error", dataset=dataset, error=str(e))
                results[dataset] = IngestionResult(success=False, error=str(e))

        return results

    def _ingest_dataset(
        self,
        dataset: str,
        trade_date: date,
        repo: "IBarsRepository",
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

        # 4. Load（委托给 Repository）
        repo.write_bars(clean, dataset)

        return IngestionResult(success=True, rows=len(clean))
```

---

## 八、目录结构

```
ditto/
├── packages/
│   ├── core/                          # Domain Layer（核心业务逻辑）
│   │   └── src/ditto_core/
│   │       ├── quality/                # 质量引擎
│   │       │   ├── engine.py
│   │       │   └── checkers/
│   │       │       ├── technical.py
│   │       │       ├── business.py     # OHLC、涨跌停
│   │       │       └── statistical.py
│   │       ├── factor/                 # 因子引擎
│   │       │   ├── engine.py
│   │       │   └── calculators/
│   │       ├── backtest/               # 回测引擎
│   │       ├── risk/                   # 风险引擎
│   │       ├── strategy/               # 策略引擎
│   │       └── ml/                     # ML 引擎
│   │
│   ├── datahub/                        # DataHub Layer（数据访问）
│   │   └── src/ditto_data/
│   │       ├── repositories/            # 仓储接口和实现
│   │       │   ├── stock/              # 股票仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   ├── adj_factor_repo.py
│   │       │   │   └── status_repo.py
│   │       │   ├── etf/                # ETF 仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   ├── adj_factor_repo.py
│   │       │   │   ├── nav_repo.py
│   │       │   │   └── status_repo.py
│   │       │   ├── index/              # 指数仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   ├── constituent_repo.py
│   │       │   │   └── weight_repo.py
│   │       │   ├── financials/         # 财务仓储
│   │       │   │   ├── balance_sheet_repo.py
│   │       │   │   ├── income_repo.py
│   │       │   │   └── cash_flow_repo.py
│   │       │   ├── factors/            # 因子仓储
│   │       │   │   └── factor_repo.py
│   │       │   └── metadata/           # 元数据仓储
│   │       │       ├── securities_repo.py
│   │       │       ├── calendar_repo.py
│   │       │       └── universe_repo.py
│   │       ├── sources/                # 数据源
│   │       │   ├── tushare/
│   │       │   └── akshare/
│   │       ├── pipelines/              # ETL 管道
│   │       ├── runtime/                # 运行时组件
│   │       │   ├── sid_allocator.py
│   │       │   └── file_lock.py
│   │       └── platform.py             # DataHub Facade
│   │
│   └── foundation/                    # Foundation Layer
│       └── src/ditto_foundation/
│           ├── config/
│           ├── logger/
│           ├── cache/
│           └── concurrency/
│
├── apps/
│   └── port/                          # Application Layer（编排层）
│       └── src/ditto_port/
│           ├── orchestration/          # 编排器
│           │   ├── ingestion.py
│           │   ├── factor.py
│           │   └── backtest.py
│           ├── services/               # 应用服务
│           ├── api/
│           ├── cli/
│           └── jobs/
│
└── data_root/
    ├── standard/                       # 标准数据
    │   ├── stock/
    │   ├── etf/
    │   ├── index/
    │   ├── financials/
    │   └── metadata/
    └── derived/                        # 衍生数据
        ├── factors/
        ├── features/
        └── labels/
```

---

## 九、架构原则总结

### 9.1 核心设计原则

| 原则 | 说明 |
|------|------|
| **Repository 模式** | DataHub 定义仓储接口，Domain 通过接口访问 |
| **ETF/Stock 明确划分** | 不同资产类型有独立的仓储 |
| **Domain 纯净** | 不依赖 DataHub 实现，只依赖 Repository 接口 |
| **QualityEngine 是 Domain** | 数据质量规则是量化业务逻辑 |
| **摄入编排是 Application** | 业务编排，由 Application Layer 负责 |

### 9.2 关键改进点

| 改进项 | 说明 |
|--------|------|
| **Repository 模式** | 替代 Reader/Writer，更符合 DDD |
| **ETF/Stock 划分** | 明确区分不同资产类型 |
| **移除 Core Protocol** | Repository 接口由 DataHub 定义 |
| **保持 datahub 名称** | 不使用 infra |
| **两层数据存储** | Standard + Derived |

---

## 十、下一步行动

### 10.1 短期（1-2 周）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 重构 datahub 仓储结构 | 按资产类型划分 Repository | ⭐⭐⭐⭐⭐ |
| 移动 QualityEngine 到 core | 确认是 Domain Layer | ⭐⭐⭐⭐⭐ |
| 实现 ETF/Stock Repository | 明确区分不同资产类型 | ⭐⭐⭐⭐ |
| 调整数据目录结构 | stock/etf/index/financials | ⭐⭐⭐⭐ |

### 10.2 中期（1-2 个月）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 重构 Domain Engine | 通过 Repository 接口访问数据 | ⭐⭐⭐⭐ |
| 创建 IngestionOrchestrator | Application Layer 编排 | ⭐⭐⭐⭐ |
| 实现两层数据存储 | Standard + Derived | ⭐⭐⭐ |
| 完善质量检查器 | 业务规则检查 | ⭐⭐⭐ |

---

**文档版本**: 3.1
**最后更新**: 2026-02-07
