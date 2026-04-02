# Ditto 当前架构分析与重构建议

> **分析日期**: 2026-02-07
> **分析范围**: datahub + port 层现有设计
> **目标**: 找出可借鉴的部分，明确改进方向，解决数据契约定位问题

---

## 一、当前设计优点（可直接借鉴）

### 1.1 清晰的域划分

```
domains/
├── market/              # ✅ 市场行情域
│   ├── stock/          # ✅ 股票子域
│   │   ├── bars/       # ✅ K线 Store
│   │   ├── adj/        # ✅ 复权因子 Store
│   │   └── status/     # ✅ 状态 Store
│   ├── etf/            # ✅ ETF 子域（明确划分）
│   └── index/          # ✅ 指数子域
├── metadata/           # ✅ 元数据域
│   ├── calendar/       # ✅ 交易日历
│   ├── instrument/     # ✅ 证券信息
│   └── universe/       # ✅ 股票池
├── fundamental/        # ✅ 基本面域
├── capital/            # ✅ 资金域
├── factors/            # ✅ 因子域
└── features/           # ✅ 特征域
```

**优点**：
- ✅ 域划分符合 DDD 原则
- ✅ ETF/Stock/Index 明确分开
- ✅ 每个子域有独立的 Store

### 1.2 优秀的抽象设计

```python
# stores/base/parquet_store.py
class ParquetStore:
    """统一的 Parquet 存储实现"""

    def read(self, dataset, sids, start_date, end_date) -> pl.DataFrame
    def write(self, dataset, df, on_duplicate, year) -> WriteResultStore
    def delete(self, dataset, sids, start_date, end_date) -> int
    def count(self, dataset, sids, start_date, end_date) -> int
    def get_checksum(self, dataset, partition_key) -> str
    ...

# domains/market/base/bars_store_base.py
class MarketBarsStoreBase:
    """Market Bars Store 基类（组合模式）"""

    def __init__(self, data_root: Path):
        self._store = ParquetStore(data_root, YearlyPartition())
        self._dataset: str  # 子类设置

    def read(self, sids, start_date, end_date) -> pl.DataFrame:
        return self._store.read(self._dataset, sids, start_date, end_date)
```

**优点**：
- ✅ 组合模式优于继承
- ✅ ParquetStore 统一实现，避免重复代码
- ✅ 分区策略可插拔（YearlyPartition）
- ✅ 子类只需定义 dataset 名称

### 1.3 完善的枚举定义

```python
# models/common.py
class Dataset(str, Enum):
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
    ADJ_FACTOR = "adj_factor"

class Domain(str, Enum):
    METADATA = "metadata"
    MARKET = "market"
    CAPITAL = "capital"
    FUNDAMENTAL = "fundamental"

class Source(str, Enum):
    TUSHARE = "tushare"
    AKSHARE = "akshare"

class OnDuplicate(Enum):
    ERROR = "error"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"

class AssetSidRange(NamedTuple):
    """SID 范围管理（百万级）"""
    stock: (1_000_000, 1_999_999)
    etf: (2_000_000, 2_999_999)
    index: (3_000_000, 3_999_999)
```

**优点**：
- ✅ 类型安全的枚举
- ✅ 统一的数据集命名
- ✅ 清晰的 SID 范围划分

### 1.4 正确的编排层设计

```python
# port/services/ingestion/coordinator.py
class IngestionCoordinator:
    """数据摄入协调器（Application Layer）✅"""

    def ingest_date(self, dataset, trade_date, force) -> IngestionResult:
        # 1. 检查是否跳过
        if skip := self._check_should_skip(...):
            return skip

        # 2. 检查交易日
        if not self._is_trading_day_for_dataset(...):
            return self._create_skipped_result(...)

        # 3. 获取数据
        df = self._fetch_data(dataset, trade_date)

        # 4. 写入数据
        write_result = self._data_writer.write_data(...)

        # 5. 处理结果
        return self._result_handler.handle_success(...)
```

**优点**：
- ✅ 编排逻辑在 Application Layer
- ✅ 职责清晰：协调、检查、调用、处理结果
- ✅ 异常处理完善

### 1.5 良好的依赖注入

```python
# hub.py
class DataHub:
    def __init__(
        self,
        # Runtime
        sqlite_pool: SQLitePool,
        sid_allocator: SidAllocator,
        # Domain Services
        metadata_query_service: MetadataService,
        market_query_service: MarketService,
        # Sources
        sources: DataSources,
        ...
    ):
        # 所有依赖通过构造函数注入
```

**优点**：
- ✅ 使用 dishka 容器管理
- ✅ 依赖关系清晰
- ✅ 易于测试

---

## 二、当前设计问题（需要改进）

### 2.1 Service 职责过重

```python
# domains/market/market_service.py
class MarketService:
    """❌ 问题：既做查询又做数据转换"""

    def get_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        # 1. 解析参数
        sids, asset_class = self._resolve_sids_and_asset_class(query)

        # 2. 加载数据
        df = self._load_bars_core(...)

        # 3. 添加 symbol 列 ❌ 数据转换逻辑
        if query.with_symbol:
            df = self._instrument_store.enrich_with_symbol(df)

        # 4. 应用复权 ❌ 业务逻辑混在数据访问中
        if query.adj != AdjType.NONE:
            df = self._apply_adjustment(...)

        # 5. 添加状态 ❌ 数据转换逻辑
        if query.with_status:
            df = self._enrich_with_status(...)

        return df
```

**问题**：
- ❌ Service 既做数据访问（调用 Store）
- ❌ 又做数据转换（复权、状态增强、symbol 解析）
- ❌ 职责不清晰，违反 SRP

### 2.2 数据契约位置不清晰

当前 `models/common.py` 主要定义了枚举，但缺少：
- ❌ 数据 Schema 定义（DataFrame 的结构）
- ❌ 数据契约接口（输入/输出规范）
- ❌ 数据转换规则（复权、PIT 等）

```python
# 当前 models/ 结构
models/
├── __init__.py
├── common.py           # ✅ 枚举定义
├── ingestion.py        # ❓ 摄入相关模型（应该在 Domain？）
└── storage.py          # ❓ 存储相关模型
```

**问题**：
- ❌ 数据契约分散在多处
- ❌ 没有统一的数据 Schema 定义
- ❌ Domain 和 DataHub 都依赖 models，但定位不清

### 2.3 DQ 检查位置问题

```python
# 当前 DQ 检查的位置？
# 可能在 datahub/quality/ 或 runtime/quality/
# ❌ 这应该是 Domain Layer 的业务逻辑
```

**问题**：
- ❌ DQ 规则是量化业务逻辑（OHLC 校验、涨跌停检测）
- ❌ 应该在 Domain Layer（ditto-core/quality/）
- ❌ 当前可能在 datahub 中

---

## 三、数据契约定位建议

### 3.1 数据契约应该在哪里？

| 方案 | 位置 | 优点 | 缺点 |
|------|------|------|------|
| **A. 独立 contracts 包** | `packages/contracts/` | ✅ 完全独立<br>✅ Domain 和 DataHub 都依赖 | ❌ 增加一个包 |
| **B. 放在 Domain** | `packages/core/contracts/` | ✅ 契约由 Domain 定义<br>✅ DataHub 实现 | ❌ Domain 依赖数据结构 |
| **C. 放在 DataHub** | `packages/data/contracts/` | ✅ 数据相关<br>✅ 实现靠近定义 | ❌ Domain 依赖 DataHub |
| **D. 放在 Foundation** | `packages/foundation/contracts/` | ✅ 基础类型<br>✅ 双方都依赖 | ❌ Foundation 不应包含业务契约 |

### 3.2 推荐方案：独立 contracts 包

```
packages/
├── contracts/                      # 数据契约包（独立）
│   └── src/ditto_contracts/
│       ├── __init__.py
│       ├── bars/                   # K线数据契约
│       │   ├── schema.py           # DataFrame Schema
│       │   ├── query.py             # 查询参数
│       │   └── models.py            # 数据模型
│       ├── factors/                # 因子数据契约
│       ├── financials/             # 财务数据契约
│       └── metadata/               # 元数据契约
│
├── core/                           # Domain Layer
│   └── src/ditto_core/
│       ├── quality/
│       ├── factor/
│       └── ...
│       # 依赖 contracts
│
├── datahub/                        # DataHub Layer
│   └── src/ditto_data/
│       ├── repositories/
│       ├── stores/
│       └── ...
│       # 依赖 contracts，实现接口
│
└── foundation/                     # Foundation Layer
    └── src/ditto_foundation/
        # 不依赖 contracts（纯技术）
```

### 3.3 contracts 包结构

```python
# packages/contracts/src/ditto_contracts/bars/schema.py

import polars as pl
from datetime import date


class BarsSchema:
    """K线数据 Schema 定义"""

    @staticmethod
    def standard_schema() -> pl.Schema:
        """标准 K线 Schema"""
        return pl.Schema({
            "sid": pl.Int32,
            "trade_date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })

    @staticmethod
    def pit_schema() -> pl.Schema:
        """PIT K线 Schema（带 knowledge_date）"""
        return pl.Schema({
            "sid": pl.Int32,
            "trade_date": pl.Date,
            "knowledge_date": pl.Date,  # PIT 关键字段
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })


class BarsQuery:
    """K线查询参数（数据契约）"""

    def __init__(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adj: "AdjType" = AdjType.NONE,
        as_of: date | None = None,
        asset_class: "AssetClass" | None = None,
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.adj = adj
        self.as_of = as_of
        self.asset_class = asset_class


# packages/contracts/src/ditto_contracts/bars/models.py

from dataclasses import dataclass
from enum import Enum


class AdjType(Enum):
    """复权类型（数据契约）"""
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class AssetClass(Enum):
    """资产类别（数据契约）"""
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"


@dataclass
class BarsData:
    """K线数据模型（数据契约）"""
    sid: int
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
```

### 3.4 DataHub 实现契约

```python
# packages/data/src/ditto_data/repositories/bars.py

from ditto_contracts.bars import BarsSchema, BarsQuery, BarsData
from abc import ABC, abstractmethod


class IBarsRepository(ABC):
    """K线数据仓储接口（基于数据契约）"""

    @abstractmethod
    def get_bars(self, query: BarsQuery) -> pl.DataFrame:
        """获取 K线数据"""
        pass

    @abstractmethod
    def write_bars(self, data: list[BarsData], dataset: str) -> None:
        """写入 K线数据"""
        pass


class StockBarsRepository(IBarsRepository):
    """股票 K线仓储实现"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "stock" / "bars_daily.parquet"

    def get_bars(self, query: BarsQuery) -> pl.DataFrame:
        # 使用契约定义的 Schema 进行验证
        df = pl.scan_parquet(self.path).filter(...).collect()

        # 可选：验证 Schema
        BarsSchema.standard_schema().validate(df)

        return df

    def write_bars(self, data: list[BarsData], dataset: str) -> None:
        df = pl.DataFrame([d.__dict__ for d in data])
        df.write_parquet(self.path)
```

### 3.5 Domain 使用契约

```python
# packages/core/src/ditto_core/factor/engine.py

from ditto_contracts.bars import BarsQuery, BarsData
from ditto_data.repositories import IBarsRepository


class FactorEngine:
    """因子引擎（使用数据契约）"""

    def __init__(
        self,
        bars_repo: IBarsRepository,  # 依赖接口，不依赖实现
    ):
        self.bars_repo = bars_repo

    def calculate_momentum(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        # 1. 使用契约定义查询
        query = BarsQuery(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

        # 2. 获取数据（通过接口）
        bars = self.bars_repo.get_bars(query)

        # 3. 计算因子（Domain 逻辑）
        result = bars.with_columns([
            pl.col("close").pct_change(20).alias("momentum_20d")
        ])

        return result
```

---

## 四、具体重构建议

### 4.1 短期改进（保持现有结构，调整职责）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 拆分 MarketService | 查询逻辑保留，转换逻辑移到 Transformer | ⭐⭐⭐⭐⭐ |
| 创建 contracts 包 | 独立的数据契约定义 | ⭐⭐⭐⭐⭐ |
| 移动 QualityEngine 到 core | DQ 是 Domain 业务逻辑 | ⭐⭐⭐⭐ |
| 调整 stores 为 repositories | 统一命名 | ⭐⭐⭐ |

### 4.2 中期重构（调整架构）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 Repository 接口层 | 基于 contracts 定义接口 | ⭐⭐⭐⭐ |
| 创建 Transformer 层 | 数据转换逻辑独立 | ⭐⭐⭐⭐ |
| 重构 Domain Engine | 使用 contracts 接口 | ⭐⭐⭐ |
| 调整数据目录结构 | standard/derived 分层 | ⭐⭐⭐ |

### 4.3 目录结构调整

```
# 建议的调整（渐进式）

packages/
├── contracts/              # 新增：独立数据契约
│   └── src/ditto_contracts/
│       ├── bars/
│       ├── factors/
│       └── metadata/
│
├── core/                   # 调整：Domain Layer
│   └── src/ditto_core/
│       ├── quality/        # 移入：DQ Engine
│       ├── factor/
│       └── ...
│
├── datahub/                # 调整：DataHub Layer
│   └── src/ditto_data/
│       ├── repositories/   # 重命名：stores -> repositories
│       │   ├── stock/
│       │   ├── etf/
│       │   └── ...
│       ├── transformers/   # 新增：数据转换层
│       │   ├── adjustment.py
│       │   └── enrichment.py
│       ├── sources/
│       ├── pipelines/
│       └── ...
│
└── foundation/             # 保持不变
    └── src/ditto_foundation/
```

---

## 五、总结：可直接借鉴的部分

| 当前设计 | 可借鉴程度 | 说明 |
|---------|-----------|------|
| **domains 域划分** | ✅✅✅ 完全保留 | market/stock/etf/index 划分清晰 |
| **stores/base 抽象** | ✅✅✅ 完全保留 | ParquetStore、组合模式 |
| **枚举定义** | ✅✅ 移到 contracts | Dataset、Domain、Source 等 |
| **AssetSidRange** | ✅✅ 移到 contracts | SID 范围管理 |
| **依赖注入** | ✅✅✅ 完全保留 | dishka 容器 |
| **ingestion/coordinator** | ✅✅✅ 完全保留 | Application Layer 编排 |
| **partition_strategy** | ✅✅ 完全保留 | 分区策略抽象 |

需要调整的部分：
- MarketService 拆分为 Service + Transformer
- models/ 内容移到 contracts/
- QualityEngine 移到 core/quality/
- stores 重命名为 repositories

---

**文档版本**: 1.0
**最后更新**: 2026-02-07
