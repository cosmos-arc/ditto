# Ditto 量化系统架构设计 v4.0

> **核心理念**：简洁的层次、清晰的职责、符合量化业务逻辑
>
> **基于业界最佳实践**：WorldQuant、Two Sigma、Citadel、九坤等领先量化机构的架构模式
>
> **设计日期**: 2026-02-07
>
> **关键更新**：
> - 独立 contracts 包（数据契约）
> - 明确存储引擎选择策略
> - SID 查询模式统一
> - DataQueryService/DataWriteService（Application Layer）

---

## 一、整体架构总览

### 1.1 四层架构 + 独立数据契约

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │   CLI    │ │HTTP API  │ │  Web UI  │ │ Jupyter/Lab        │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                        Application Layer                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  DataQueryService  │  DataWriteService  │ IngestionOrch.  │  │
│  │     (查询编排)      │     (写入编排)      │   (摄入编排)      │  │
│  └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                         Domain Layer                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐ │  │
│  │  │  Alpha  │ │ Factor  │ │Backtest │ │    Quality     │ │  │
│  │  │ Engine  │ │ Engine  │ │ Engine  │ │    Engine       │ │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────────┘ │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────────────────┐      │  │
│  │  │   Risk  │ │ Trading │ │      ML/AI             │      │  │
│  │  │ Engine  │ │ Engine  │ │      Engine             │      │  │
│  │  └─────────┘ └─────────┘ └─────────────────────────┘      │  │
│  └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                        DataHub Layer                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │ Repositories │ │  Transformers│ │   Pipelines      │  │  │
│  │  │  (仓储)       │ │  (转换器)     │ │   (ETL)          │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │  │
│  │  │ DataSources  │ │   Storage     │ │    Runtime       │  │  │
│  │  │  (数据源)     │ │  (引擎)       │ │  (运行时)        │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                      Contracts Layer (独立)                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐ │  │
│  │  │   Bars  │ │ Factors │ │Financial│ │    Metadata     │ │  │
│  │  │ Schema  │ │  Schema │ │  Schema │ │    Schema       │ │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────────┘ │  │
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
Application Layer (DataQueryService, DataWriteService, IngestionOrchestrator)
    ↓ 依赖
Domain Layer + DataHub Layer + Contracts Layer
    ↓ 依赖
Foundation Layer

规则：
1. Domain Layer 不依赖 DataHub（通过 Contracts 接口解耦）
2. DataHub 实现 Contracts 定义的接口
3. Application Layer 编排查询/写入/转换逻辑
4. Contracts Layer 独立，定义数据契约
```

---

## 二、Contracts Layer（独立数据契约）

### 2.1 为什么独立 Contracts？

| 问题 | 如果不独立 | 独立 Contracts |
|------|-----------|---------------|
| Domain 依赖 | Domain 依赖 DataHub | Domain 只依赖 Contracts |
| DataHub 依赖 | DataHub 自定义 Schema | DataHub 实现 Contracts |
| 数据一致性 | Schema 分散在多处 | Schema 集中定义 |
| 测试困难 | 需要 Mock DataHub | 只需 Mock Contracts |

### 2.2 Contracts 目录结构

```
packages/contracts/
└── src/ditto_contracts/
    ├── __init__.py
    ├── bars/                       # K线数据契约
    │   ├── __init__.py
    │   ├── schema.py               # DataFrame Schema 定义
    │   ├── query.py                # 查询参数（BarsQuery）
    │   ├── models.py               # 数据模型（BarsData）
    │   └── enums.py                # 枚举（AdjType, AssetClass）
    │
    ├── factors/                    # 因子数据契约
    │   ├── __init__.py
    │   ├── schema.py
    │   ├── query.py
    │   └── models.py
    │
    ├── financials/                 # 财务数据契约
    │   ├── __init__.py
    │   ├── schema.py
    │   ├── query.py
    │   └── models.py
    │
    ├── metadata/                   # 元数据契约
    │   ├── __init__.py
    │   ├── schema.py
    │   ├── query.py
    │   └── models.py
    │
    └── common/                     # 通用契约
        ├── __init__.py
        ├── enums.py                # Dataset, Domain, Source, OnDuplicate
        └── sid.py                  # SID 相关契约（AssetSidRange）
```

### 2.3 Bars 契约示例

```python
# packages/contracts/src/ditto_contracts/bars/schema.py

import polars as pl


class BarsSchema:
    """K线数据 Schema 定义"""

    @staticmethod
    def standard() -> pl.Schema:
        """标准 K线 Schema（Parquet 存储）"""
        return pl.Schema({
            "sid": pl.Int32,                    # ✅ 统一使用 SID
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })

    @staticmethod
    def pit() -> pl.Schema:
        """PIT K线 Schema（带 knowledge_date）"""
        return pl.Schema({
            "sid": pl.Int32,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,        # ✅ PIT 关键字段
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })

    @staticmethod
    def with_enrichment() -> pl.Schema:
        """增强 K线 Schema（含 symbol, adj_factor 等）"""
        return pl.Schema({
            "sid": pl.Int32,
            "symbol": pl.String,               # ✅ 增强字段
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "close_adj": pl.Float64,         # ✅ 增强字段
            "adj_factor": pl.Float64,         # ✅ 增强字段
            "volume": pl.Float64,
            "amount": pl.Float64,
        })


# packages/contracts/src/ditto_contracts/bars/query.py

from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class BarsQuery:
    """K线查询参数（数据契约）"""

    sids: list[int]                   # ✅ 统一使用 SID 查询
    start_date: date
    end_date: date
    adj: "AdjType" = AdjType.NONE
    as_of: date | None = None         # PIT 查询
    asset_class: "AssetClass" | None = None
    with_symbol: bool = False         # 是否需要 symbol 转换
    with_status: bool = False        # 是否需要状态增强
    raw: bool = False                # 是否跳过增强


# packages/contracts/src/ditto_contracts/bars/enums.py

from enum import Enum


class AdjType(Enum):
    """复权类型"""
    NONE = "none"
    QFQ = "qfq"      # 前复权
    HFQ = "hfq"      # 后复权


class AssetClass(Enum):
    """资产类别"""
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"


# packages/contracts/src/ditto_contracts/bars/models.py

from dataclasses import dataclass
from datetime import date


@dataclass
class BarsData:
    """K线数据模型"""
    sid: int
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None


@dataclass
class BarsWriteResult:
    """K线写入结果"""
    rows_written: int
    rows_updated: int
    rows_skipped: int
    checksum: str
```

---

## 三、存储引擎选择策略

### 3.1 存储引擎选择原则

| 数据类型 | 存储引擎 | 分区策略 | 理由 |
|---------|---------|---------|------|
| **行情数据** | Parquet | 按年分区 | 时序数据、高频查询、列式压缩 |
| **财务数据** | Parquet | 按报告期 | 时序数据、历史版本 |
| **因子数据** | Parquet | 按因子名/版本 | 高频计算、版本管理 |
| **元数据** | SQLite | - | 复杂查询、事务性、低频更新 |
| **交易日历** | SQLite + 内存缓存 | - | 全量加载、O(1) 查询 |
| **成分股** | SQLite | - | 复杂关系、JOIN 查询 |
| **摄取日志** | SQLite | - | 事务性、审计追踪 |

### 3.2 数据目录结构

```
data_root/
├── standard/                           # 标准数据（清晰后的数据）
│   ├── stock/                          # 股票数据
│   │   ├── bars_daily/
│   │   │   ├── 2020.parquet
│   │   │   ├── 2021.parquet
│   │   │   └── ...
│   │   ├── bars_minute/              # 分钟数据（按日分区）
│   │   │   └── trade_date=2024-01-15/
│   │   ├── adj_factor.parquet        # 复权因子
│   │   └── status.parquet             # 股票状态
│   │
│   ├── etf/                            # ETF 数据
│   │   ├── bars_daily/
│   │   │   ├── 2020.parquet
│   │   │   └── ...
│   │   ├── bars_minute/
│   │   ├── adj_factor.parquet
│   │   ├── status.parquet
│   │   └── nav.parquet                # 净值
│   │
│   ├── index/                          # 指数数据
│   │   ├── bars_daily/
│   │   │   ├── 2020.parquet
│   │   │   └── ...
│   │   └── constituents/             # 成分股
│   │       └── trade_date=2024-01-15/
│   │
│   ├── financials/                     # 财务数据
│   │   ├── balance_sheet/
│   │   │   ├── 2023Q3.parquet
│   │   │   └── ...
│   │   ├── income_statement/
│   │   ├── cash_flow/
│   │   └── indicators/                # 财务指标
│   │
│   └── metadata/                       # 元数据（SQLite）
│       ├── catalog.db                 # 元数据目录
│       ├── securities.db              # 证券信息
│       ├── calendar.db                # 交易日历
│       ├── universe.db                # 股票池
│       └── ingestion_log.db           # 摄取日志
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

---

## 四、SID 查询模式统一

### 4.1 SID 设计原则

```python
# packages/contracts/src/ditto_contracts/common/sid.py

from typing import Literal
from dataclasses import dataclass
from enum import Enum


class AssetClass(Enum):
    """资产类别"""
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"


@dataclass
class AssetSidRange:
    """资产类别 SID 范围定义"""
    asset_class: AssetClass
    min_sid: int
    max_sid: int
    name: str

    # 股票: 1M (1,000,000 - 1,999,999)
    STOCK = AssetSidRange(AssetClass.STOCK, 1_000_000, 1_999_999, "stock")
    # ETF: 2M (2,000,000 - 2,999,999)
    ETF = AssetSidRange(AssetClass.ETF, 2_000_000, 2_999_999, "etf")
    # 指数: 3M (3,000,000 - 3,999,999)
    INDEX = AssetSidRange(AssetClass.INDEX, 3_000_000, 3_999_999, "index")

    @classmethod
    def get_range(cls, asset_class: AssetClass) -> "AssetSidRange":
        """获取资产类别的 SID 范围"""
        ranges = {
            AssetClass.STOCK: cls.STOCK,
            AssetClass.ETF: cls.ETF,
            AssetClass.INDEX: cls.INDEX,
        }
        return ranges[asset_class]

    @classmethod
    def detect_asset_class(cls, sids: list[int]) -> AssetClass:
        """从 SID 列表检测资产类别"""
        for range_info in [cls.STOCK, cls.ETF, cls.INDEX]:
            if any(range_info.min_sid <= sid <= range_info.max_sid for sid in sids):
                return range_info.asset_class
        raise ValueError(f"Cannot detect asset class from SIDs: {sids[:5]}")


@dataclass
class SID:
    """统一 SID 标识符

    所有内部数据访问都使用 SID，对外代码通过 InstrumentStore 解析。
    """

    value: int

    @classmethod
    def from_symbol(cls, symbol: str, asset_class: AssetClass) -> "SID":
        """从 symbol 创建 SID（仅用于测试）"""
        # 实际 SID 分配由 InstrumentStore 管理
        raise NotImplementedError("Use InstrumentStore to get SID")

    @property
    def asset_class(self) -> AssetClass:
        """获取资产类别"""
        return AssetSidRange.detect_asset_class([self.value])
```

### 4.2 查询流程

```
用户代码
    │
    │ "000001.SZ"
    ↓
InstrumentStore.resolve_sid("000001.SZ", "tushare")
    │
    │ SID: 1000001
    ↓
DataQueryService.get_bars(BarsQuery(sids=[1000001], ...))
    │
    ↓
Repository.read([1000001], ...)
    │
    ↓
Parquet 文件（按 SID 索引）
```

---

## 五、DataHub Layer 架构

### 5.1 Repository 模式

```python
# packages/datahub/src/ditto_datahub/repositories/bars.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsQuery, BarsData, BarsWriteResult, AdjType


class IBarsRepository(ABC):
    """K线数据仓储接口"""

    @abstractmethod
    def get_bars(self, query: BarsQuery) -> pl.DataFrame:
        """
        获取 K线数据（原始 Schema）

        注意：
        - 返回原始数据（standard Schema）
        - 不包含 symbol、复权等增强字段
        - SID 为唯一标识符
        """
        pass

    @abstractmethod
    def write_bars(self, data: list[BarsData], dataset: str) -> BarsWriteResult:
        """写入 K线数据"""
        pass

    @abstractmethod
    def get_latest_date(self, sid: int) -> str | None:
        """获取最新数据日期"""
        pass

    @abstractmethod
    def get_date_range(self) -> tuple[str | None, str | None]:
        """获取数据日期范围"""
        pass


class StockBarsRepository(IBarsRepository):
    """股票 K线仓储（Parquet 存储）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "stock" / "bars_daily"

    def get_bars(self, query: BarsQuery) -> pl.DataFrame:
        """获取股票 K线数据"""

        # 构建 Parquet 路径
        paths = self._collect_paths(query.start_date, query.end_date)

        if not paths:
            return pl.DataFrame()

        # 扫描并过滤
        df = pl.scan_parquet(paths).filter(
            pl.col("sid").is_in(query.sids),
            pl.col("trade_date").between(query.start_date, query.end_date),
        )

        # PIT 查询
        if query.as_of:
            df = df.filter(pl.col("knowledge_date") <= query.as_of)

        return df.collect()

    def write_bars(self, data: list[BarsData], dataset: str) -> BarsWriteResult:
        """写入股票 K线数据"""

        # 转换为 DataFrame
        df = pl.DataFrame([{
            "sid": d.sid,
            "trade_date": d.trade_date,
            "open": d.open,
            "high": d.high,
            "low": d.low,
            "close": d.close,
            "volume": d.volume,
            "amount": d.amount or 0.0,
            "knowledge_date": d.trade_date,  # 摄取日期即 knowledge_date
        } for d in data])

        # 写入 Parquet（按年分区）
        year = str(data[0].trade_date.year)
        target_path = self.path / f"{year}.parquet"

        # 原子写入
        self._atomic_append(df, target_path)

        return BarsWriteResult(
            rows_written=len(data),
            rows_updated=0,
            rows_skipped=0,
            checksum="",
        )


class ETFBarsRepository(IBarsRepository):
    """ETF K线仓储（Parquet 存储）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "etf" / "bars_daily"

    # 实现与 StockBarsRepository 类似


class IndexBarsRepository(IBarsRepository):
    """指数 K线仓储（Parquet 存储）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "index" / "bars_daily"

    # 实现与 StockBarsRepository 类似
```

### 5.2 Transformer 层（数据转换）

```python
# packages/datahub/src/ditto_datahub/transformers/bars.py

from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsQuery, AdjType


class BarsTransformer:
    """K线数据转换器

    职责：
    - symbol 解析（SID → symbol）
    - 复权计算（NONE → QFQ/HFQ）
    - 状态增强（添加涨跌停状态）
    - PIT 处理

    不包含：
    - 数据访问（由 Repository 负责）
    - 业务逻辑（由 Domain Layer 负责）
    """

    def __init__(
        self,
        instrument_store: "IInstrumentStore",
        adj_factor_store: "IAdjFactorStore",
        status_store: "IStatusStore",
    ):
        self._instrument_store = instrument_store
        self._adj_factor_store = adj_factor_store
        self._status_store = status_store

    def enrich_with_symbol(
        self,
        df: pl.DataFrame,
        asset_class: "AssetClass",
    ) -> pl.DataFrame:
        """添加 symbol 列"""
        sid_to_symbol = self._instrument_store.batch_resolve_symbol(
            df["sid"].unique().to_list(),
            asset_class,
        )

        symbol_map = pl.DataFrame(
            [{"sid": k, "symbol": v} for k, v in sid_to_symbol.items()]
        )

        return df.join(symbol_map, on="sid", how="left")

    def apply_adjustment(
        self,
        df: pl.DataFrame,
        adj: AdjType,
        sids: list[int],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """应用复权计算"""
        if adj == AdjType.NONE:
            return df

        # 获取复权因子
        adj_factors = self._adj_factor_store.get_adj_factors(
            sids, start_date, end_date
        )

        # 应用复权
        if adj == AdjType.QFQ:
            return self._apply_qfq(df, adj_factors)
        elif adj == AdjType.HFQ:
            return self._apply_hfq(df, adj_factors)

        return df

    def enrich_with_status(
        self,
        df: pl.DataFrame,
        sids: list[int],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """添加状态信息（涨跌停）"""
        status = self._status_store.get_status(sids, start_date, end_date)
        return df.join(status, on=["sid", "trade_date"], how="left")

    def _apply_qfq(self, df: pl.DataFrame, adj_factors: pl.DataFrame) -> pl.DataFrame:
        """应用前复权"""
        # 前复权计算逻辑
        result = df.join(adj_factors, on=["sid", "trade_date"], how="left")
        result = result.with_columns([
            (pl.col("close") / pl.col("adj_factor")).alias("close_adj"),
        ])
        return result

    def _apply_hfq(self, df: pl.DataFrame, adj_factors: pl.DataFrame) -> pl.DataFrame:
        """应用后复权"""
        # 后复权计算逻辑
        ...
        return df
```

### 5.3 Metadata Repository（SQLite）

```python
# packages/datahub/src/ditto_datahub/repositories/metadata.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ditto_contracts.metadata import (
    InstrumentQuery,
    CalendarQuery,
    UniverseQuery,
)


class IInstrumentRepository(ABC):
    """证券信息仓储接口（SQLite）"""

    @abstractmethod
    def resolve_sid(
        self,
        src_code: str,
        source: str,
        as_of: str | None = None,
    ) -> Optional[int]:
        """解析 src_code 到 SID（支持 PIT）"""
        pass

    @abstractmethod
    def batch_resolve_symbol(
        self,
        sids: list[int],
        asset_class: "AssetClass",
    ) -> dict[int, str]:
        """批量解析 SID 到 symbol"""
        pass

    @abstractmethod
    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        """查询证券信息"""
        pass


class InstrumentRepository(IInstrumentRepository):
    """证券信息仓储实现（SQLite）"""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def resolve_sid(
        self,
        src_code: str,
        source: str,
        as_of: str | None = None,
    ) -> Optional[int]:
        """解析 src_code 到 SID（支持 PIT）"""
        sql = """
            SELECT sid
            FROM security_mapping
            WHERE src_code = ?
              AND source = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY effective_from DESC
            LIMIT 1
        """

        params = [src_code, source, as_of or "9999-12-31", as_of or "9999-12-31"]

        # 执行查询...
        result = self._execute_sql(sql, params)
        return result["sid"][0] if not result.is_empty() else None
```

---

## 六、Application Layer - DataQueryService

### 6.1 DataQueryService 设计

```python
# apps/port/src/ditto_port/services/data_query_service.py

from datetime import date
from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsQuery, AdjType
from ditto_datahub.repositories import IBarsRepository
from ditto_datahub.transformers import BarsTransformer
from ditto_datahub.repositories.metadata import IInstrumentRepository


class DataQueryService:
    """数据查询服务（Application Layer）

    职责：
    - 编排查询流程
    - 协调 Repository 和 Transformer
    - 提供便捷的查询 API

    特点：
    - 接收简单参数（symbols、日期范围）
    - 自动处理 SID 解析
    - 自动应用转换（复权、状态增强）
    """

    def __init__(
        self,
        # Stock Repositories
        stock_bars_repo: IBarsRepository,
        etf_bars_repo: IBarsRepository,
        index_bars_repo: IBarsRepository,
        # Metadata Repository
        instrument_repo: IInstrumentRepository,
        # Transformers
        bars_transformer: "BarsTransformer",
    ):
        self._stock_bars_repo = stock_bars_repo
        self._etf_bars_repo = etf_bars_repo
        self._index_bars_repo = index_bars_repo
        self._instrument_repo = instrument_repo
        self._bars_transformer = bars_transformer

    def get_bars(
        self,
        symbols: list[str],          # ✅ 用户友好的 symbol 列表
        start_date: date,
        end_date: date,
        adj: Literal["none", "qfq", "hfq"] = "none",
        as_of: date | None = None,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        enrich_with_status: bool = False,
    ) -> pl.DataFrame:
        """
        获取 K线数据（便捷 API）

        处理流程：
        1. 解析 symbols → SIDs
        2. 查询原始数据（Repository）
        3. 应用转换（Transformer）

        Args:
            symbols: 证券代码列表 ["000001.SZ", "510300.SH"]
            start_date: 开始日期
            end_date: 结束日期
            adj: 复权类型
            as_of: PIT 查询日期
            asset_class: 资产类别（None 则自动检测）
            enrich_with_status: 是否添加状态信息

        Returns:
            K线数据 DataFrame（已增强）
        """

        # 1. 解析 symbols → SIDs（如果用户传的是 SIDs，跳过）
        sids = self._resolve_sids(symbols, asset_class)

        # 2. 检测资产类别（如果未指定）
        if asset_class is None:
            asset_class = self._detect_asset_class(sids)

        # 3. 构建 BarsQuery
        query = BarsQuery(
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            adj=AdjType(adj),
            as_of=as_of,
            asset_class=asset_class,
            raw=False,  # 我们需要增强后的数据
        )

        # 4. 获取原始数据（Repository）
        df = self._get_bars_from_repo(query)

        if df.is_empty():
            return df

        # 5. 应用转换（Transformer）
        df = self._apply_transformations(df, query, enrich_with_status)

        return df

    def _resolve_sids(
        self,
        symbols: list[str],
        asset_class: "AssetClass" | None,
    ) -> list[int]:
        """解析 symbols 到 SIDs"""
        # 检查是否已经是 SIDs（纯数字）
        if all(s.isdigit() for s in symbols):
            return [int(s) for s in symbols]

        # 需要解析 symbol → SID
        sids = []
        for symbol in symbols:
            # 提取 source（如 "000001.SZ" → source="tushare"）
            source = self._extract_source(symbol)
            sid = self._instrument_repo.resolve_sid(symbol, source)
            if sid:
                sids.append(sid)
        return sids

    def _detect_asset_class(self, sids: list[int]) -> "AssetClass":
        """检测资产类别"""
        from ditto_contracts.common.sid import AssetSidRange
        return AssetSidRange.detect_asset_class(sids)

    def _get_bars_from_repo(self, query: BarsQuery) -> pl.DataFrame:
        """从 Repository 获取原始数据"""
        if query.asset_class == "stock":
            return self._stock_bars_repo.get_bars(query)
        elif query.asset_class == "etf":
            return self._etf_bars_repo.get_bars(query)
        elif query.asset_class == "index":
            return self._index_bars_repo.get_bars(query)
        raise ValueError(f"Unknown asset class: {query.asset_class}")

    def _apply_transformations(
        self,
        df: pl.DataFrame,
        query: BarsQuery,
        enrich_with_status: bool,
    ) -> pl.DataFrame:
        """应用数据转换"""
        # 1. 添加 symbol
        if query.with_symbol:
            df = self._bars_transformer.enrich_with_symbol(df, query.asset_class)

        # 2. 应用复权
        if query.adj != AdjType.NONE:
            df = self._bars_transformer.apply_adjustment(
                df, query.adj, query.sids, query.start_date, query.end_date
            )

        # 3. 添加状态
        if enrich_with_status and query.asset_class == "stock":
            df = self._bars_transformer.enrich_with_status(
                df, query.sids, query.start_date, query.end_date
            )

        return df
```

---

## 七、Application Layer - DataWriteService

### 7.1 DataWriteService 设计

```python
# apps/port/src/ditto_port/services/data_write_service.py

from datetime import date
from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsData
from ditto_datahub.repositories import IBarsRepository
from ditto_core.quality import QualityEngine, QualityResult


class DataWriteService:
    """数据写入服务（Application Layer）

    职责：
    - 编排写入流程
    - 数据验证（QualityEngine）
    - 数据转换（必要的话）
    - 批量写入优化

    特点：
    - 接收用户友好的数据格式
    - 自动 SID 分配
    - 自动 DQ 检查
    """

    def __init__(
        self,
        # Repositories
        stock_bars_repo: IBarsRepository,
        etf_bars_repo: IBarsRepository,
        # Runtime
        sid_allocator: "SidAllocator",
        # Quality
        quality_engine: QualityEngine,
    ):
        self._stock_bars_repo = stock_bars_repo
        self._etf_bars_repo = etf_bars_repo
        self._sid_allocator = sid_allocator
        self._quality_engine = quality_engine

    def write_bars(
        self,
        df: pl.DataFrame,
        dataset: Literal["stock", "etf", "index"],
        trade_date: date,
        source: str = "tushare",
        validate: bool = True,
    ) -> "WriteResult":
        """
        写入 K线数据（便捷 API）

        处理流程：
        1. 数据转换（symbol → SID）
        2. SID 分配（新证券）
        3. DQ 检查（可选）
        4. 批量写入（Repository）

        Args:
            df: K线数据 DataFrame（包含 symbol 列）
            dataset: 数据集类型
            trade_date: 交易日期
            source: 数据源
            validate: 是否进行 DQ 检查

        Returns:
            写入结果
        """

        # 1. 转换 symbol → SID
        df = self._convert_symbols_to_sids(df, dataset, trade_date, source)

        # 2. DQ 检查
        if validate:
            dq_result = self._quality_engine.check(df, dataset=dataset)
            if not dq_result.is_valid:
                return self._handle_dq_failure(dq_result)

        # 3. 转换为 BarsData
        bars_data = self._convert_to_bars_data(df)

        # 4. 写入 Repository
        if dataset == "stock":
            result = self._stock_bars_repo.write_bars(bars_data, "stock_bars")
        elif dataset == "etf":
            result = self._etf_bars_repo.write_bars(bars_data, "etf_bars")

        return result

    def _convert_symbols_to_sids(
        self,
        df: pl.DataFrame,
        dataset: str,
        trade_date: date,
        source: str,
    ) -> pl.DataFrame:
        """转换 symbol → SID"""
        # 获取已存在的 symbol → SID 映射
        existing_sids = self._batch_resolve_sids(
            df["symbol"].unique().to_list(),
            dataset,
        )

        # 分配新 SIDs
        new_symbols = [s for s in df["symbol"].unique() if s not in existing_sids]
        new_sids = self._allocate_sids(new_symbols, dataset)

        # 替换 symbol 为 SID
        sid_map = {**existing_sids, **new_sids}
        df = df.with_columns([
            pl.col("symbol").map_dict(sid_map).alias("sid")
        ])

        return df

    def _batch_resolve_sids(
        self,
        symbols: list[str],
        asset_class: str,
    ) -> dict[str, int]:
        """批量解析 symbol → SID"""
        # 使用 InstrumentStore 批量查询
        ...

    def _allocate_sids(
        self,
        symbols: list[str],
        asset_class: str,
    ) -> dict[str, int]:
        """分配新 SIDs"""
        sid_map = {}
        for symbol in symbols:
            sid = self._sid_allocator.allocate(symbol, asset_class)
            sid_map[symbol] = sid
        return sid_map

    def _convert_to_bars_data(self, df: pl.DataFrame) -> list[BarsData]:
        """转换 DataFrame 为 BarsData 列表"""
        return [
            BarsData(
                sid=row["sid"],
                trade_date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                amount=row.get("amount"),
            )
            for row in df.iter_rows(named=True)
        ]
```

---

## 八、目录结构（完整版）

```
ditto/
├── packages/
│   ├── contracts/                      # Contracts Layer（独立数据契约）
│   │   └── src/ditto_contracts/
│   │       ├── bars/                   # K线契约
│   │       │   ├── schema.py
│   │       │   ├── query.py
│   │       │   ├── models.py
│   │       │   └── enums.py
│   │       ├── factors/                # 因子契约
│   │       ├── financials/             # 财务契约
│   │       ├── metadata/               # 元数据契约
│   │       └── common/                 # 通用契约
│   │           ├── enums.py            # Dataset, Domain, Source, OnDuplicate
│   │           └── sid.py              # AssetSidRange
│   │
│   ├── core/                           # Domain Layer
│   │   └── src/ditto_core/
│   │       ├── quality/                # 质量引擎
│   │       │   ├── engine.py
│   │       │   └── checkers/
│   │       ├── factor/                 # 因子引擎
│   │       ├── backtest/               # 回测引擎
│   │       ├── risk/                   # 风险引擎
│   │       ├── strategy/               # 策略引擎
│   │       └── ml/                     # ML 引擎
│   │
│   ├── datahub/                        # DataHub Layer
│   │   └── src/ditto_datahub/
│   │       ├── repositories/           # 仓储接口和实现
│   │       │   ├── stock/              # 股票仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   └── adj_factor_repo.py
│   │       │   ├── etf/                # ETF 仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   └── nav_repo.py
│   │       │   ├── index/              # 指数仓储
│   │       │   │   ├── bars_repo.py
│   │       │   │   └── constituent_repo.py
│   │       │   ├── financials/         # 财务仓储
│   │       │   ├── factors/            # 因子仓储
│   │       │   └── metadata/           # 元数据仓储（SQLite）
│   │       │       ├── instrument_repo.py
│   │       │       ├── calendar_repo.py
│   │       │       └── universe_repo.py
│   │       │
│   │       ├── transformers/           # 数据转换器
│   │       │   ├── bars.py             # K线转换器
│   │       │   └── enrichment.py      # 数据增强
│   │       │
│   │       ├── sources/                # 数据源
│   │       │   ├── tushare/
│   │       │   └── akshare/
│   │       │
│   │       ├── pipelines/              # ETL 管道
│   │       │   └── transform.py
│   │       │
│   │       ├── runtime/                # 运行时组件
│   │       │   ├── sid_allocator.py
│   │       │   ├── file_lock.py
│   │       │   └── freeze_manager.py
│   │       │
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
│           ├── services/               # 应用服务
│           │   ├── data_query_service.py    # DataQueryService ✅
│           │   ├── data_write_service.py   # DataWriteService ✅
│           │   ├── ingestion_service.py
│           │   └── ...
│           ├── orchestration/          # 编排器
│           │   ├── ingestion.py
│           │   ├── factor.py
│           │   └── backtest.py
│           ├── api/
│           ├── cli/
│           └── jobs/
│
└── data_root/
    ├── standard/                       # 标准数据
    │   ├── stock/
    │   │   └── bars_daily/
    │   ├── etf/
    │   │   └── bars_daily/
    │   ├── index/
    │   │   └── bars_daily/
    │   ├── financials/
    │   └── metadata/                   # SQLite
    │       ├── catalog.db
    │       ├── securities.db
    │       ├── calendar.db
    │       └── universe.db
    │
    └── derived/                        # 衍生数据
        ├── factors/
        ├── features/
        └── labels/
```

---

## 九、关键设计决策

### 9.1 存储引擎选择

| 数据类型 | 存储引擎 | 理由 |
|---------|---------|------|
| **K线数据** | Parquet（按年分区） | 时序查询、列式压缩、高频访问 |
| **复权因子** | Parquet | 时序数据、历史版本 |
| **财务数据** | Parquet（按报告期） | 时序数据、历史版本 |
| **因子数据** | Parquet（按版本） | 版本管理、高频计算 |
| **证券信息** | SQLite | 复杂查询、JOIN、低频更新 |
| **交易日历** | SQLite + 内存缓存 | O(1) 查询、全量加载 |
| **成分股** | SQLite | 复杂关系、JOIN |
| **摄取日志** | SQLite | 事务性、审计 |

### 9.2 SID 查询模式

```python
# ✅ 正确：统一使用 SID 查询
bars_repo.get_bars(BarsQuery(
    sids=[1000001, 1000002],  # ✅ 统一 SID
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31),
))

# ❌ 错误：直接使用 symbol 查询
bars_repo.get_bars(
    symbols=["000001.SZ"],  # ❌ 不统一
    ...
)
```

### 9.3 转换在 Application Layer

```python
# ✅ 正确：Application Layer 编排转换
class DataQueryService:
    def get_bars(self, symbols, ...):
        # 1. symbol → SID（转换）
        sids = self._resolve_sids(symbols)

        # 2. 查询原始数据
        query = BarsQuery(sids=sids, ...)
        df = self._repo.get_bars(query)

        # 3. 应用转换（复权、状态）
        df = self._transformer.apply_adjustment(df, ...)

        return df

# ❌ 错误：Repository 包含转换逻辑
class SomeRepository:
    def get_bars(self, symbols, ...):
        df = self._parquet_scan(...)
        df = self._apply_qfq(df)  # ❌ 转换逻辑应该在应用层
        return df
```

---

## 十、总结：架构改进要点

| 改进项 | 之前 | 现在 |
|--------|------|------|
| **数据契约** | 分散在 models/ | 独立 contracts 包 |
| **查询模式** | symbol/sid 混用 | 统一 SID 查询 |
| **转换逻辑** | 混在 Service 中 | 独立 Transformer 层 |
| **便捷 API** | 无 | DataQueryService/DataWriteService |
| **存储引擎** | 不清晰 | 明确：Parquet/SQLite 分工 |
| **ETF/Stock** | 在 Service 中区分 | 独立 Repository |

---

**文档版本**: 4.0
**最后更新**: 2026-02-07
