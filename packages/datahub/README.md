# ditto-datahub

**版本**: v0.11.0
**最后更新**: 2026-01-30
**状态**: ✅ 稳定

## 概要

Ditto 量化系统的数据层，统一管理数据获取、存储、查询和 PIT (Point-in-Time) 安全。

## 核心功能

- **统一数据入口**: DataHub 门面类，封装所有数据访问
- **PIT 安全**: 时点安全的数据查询，避免未来函数
- **高性能存储**: Parquet 文件存储 + SQLite 元数据
- **数据质量检查**: 多维度 DQ 检查和报告
- **多数据源支持**: Tushare、Akshare 等
- **数据摄入**: 分层 Ingestion 架构，统一数据摄入流程

## 架构

DataHub 采用分层架构，使用 `@cached_property` 实现延迟加载：

```
┌─────────────────────────────────────────────────────────┐
│                       DataHub                          │
│                   (统一入口/Facade)                      │
└─────────────────────────────────────────────────────────┘
                │
        ┌───────┴───────┬───────────────┬───────────────┐
        ▼               ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Runtime层    │ │  Store层     │ │ Accessor层   │ │  Sources层   │
│              │ │              │ │              │ │              │
│ SQLitePool   │ │ InstrumentStore│ │ Instruments │ │ Tushare      │
│ FileLock     │ │ CalendarStore│ │ Bars         │ │ Akshare      │
│ InstrumentIdAllocator│ │ BarsStore    │ │ Calendar     │ │              │
│ DQChecker    │ │ AdjFactor... │ │ Universe     │ │              │
│ FreezeMgr    │ │              │ │ Index        │ │              │
│ SqlEngine    │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### Ingestion 层

Ingestion 层负责数据摄入，采用三层架构：

```
┌─────────────────────────────────────────────────────────┐
│              IngestionCoordinator (路由层)               │
│         根据 Domain 枚举路由到对应的域 Ingestion          │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│MetadataInges.│ │ MarketIngest.│ │ CapitalIngest.│
│ (待实现)      │ │  (待实现)     │ │  (已实现)     │
└──────────────┘ └──────────────┘ └──────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ MetadataStore│ │  MarketStore │ │ CapitalStore │
└──────────────┘ └──────────────┘ └──────────────┘
```

**核心组件**：

| 组件 | 说明 | 状态 |
|------|------|------|
| `IngestionCoordinator` | 路由协调器，根据 Domain 枚举路由到对应的域 Ingestion 服务 | ✅ 已实现 |
| `IngestionDataWriter` | 数据写入工具，支持 Parquet 和 SQLite，提供重复数据处理策略 | ✅ 已实现 |
| `CapitalIngestion` | Capital 域摄入服务，支持 10 种数据类型 | ✅ 已实现 |
| `MetadataIngestion` | Metadata 域摄入服务（待实现） | ⏳ 待实现 |
| `MarketIngestion` | Market 域摄入服务（待实现） | ⏳ 待实现 |

**数据写入策略**：

`IngestionDataWriter` 提供三种重复数据处理策略：

| 策略 | 说明 | 使用场景 |
|------|------|----------|
| `OnDuplicate.ERROR` | 遇到重复数据时报错（默认，最安全） | 初始加载、数据验证 |
| `OnDuplicate.KEEP_FIRST` | 保留现有数据，忽略新数据 | 增量更新、信任首次入库数据 |
| `OnDuplicate.KEEP_LAST` | 使用新数据覆盖现有数据（Last-Write-Wins） | 数据修正、重新计算 |

**使用示例**：

```python
from ditto_datahub.ingestion.coordinator import IngestionCoordinator
from ditto_datahub.ingestion.data_writer import IngestionDataWriter
from ditto_datahub.models.common import OnDuplicate
from ditto_datahub.models import Domain, Source
from datetime import date
import polars as pl

# 1. 使用 IngestionDataWriter 写入数据
result = IngestionDataWriter.write_parquet(
    df=dataframe,
    path=Path("data.parquet"),
    on_duplicate=OnDuplicate.KEEP_FIRST,
    key_columns=("instrument_id", "trade_date"),
)
print(f"写入 {result.rows_written} 行，总计 {result.rows_total} 行")

# 2. 使用 IngestionCoordinator 路由到对应的域
coordinator = IngestionCoordinator(
    metadata=metadata_ingestion,
    capital=capital_ingestion,
)

result = await coordinator.ingest(
    domain=Domain.CAPITAL,
    data_type="balance_sheet",
    source=Source.TUSHARE,
    trade_date=date(2024, 1, 2),
)

if result.success:
    print(f"成功写入 {result.records_written} 条记录")
else:
    print(f"摄入失败: {result.error}")
```

### 基础层

基础层提供统一的数据存储抽象接口：

| 组件 | 说明 |
|------|------|
| `BaseStore` | 抽象基类，定义所有存储实现的统一接口 (read/write/delete) |
| `ParquetStore` | Parquet 文件存储实现，支持按年分区、自动去重 |
| `SQLiteStore` | SQLite 数据库存储实现，支持事务、PIT 查询 |

**配置系统**：从多路径配置简化为单 `DATA_ROOT` 配置，所有路径自动生成：

```python
from ditto_datahub.config import DataRootConfig

# 初始化配置（可通过 DATA_ROOT 环境变量设置）
config = DataRootConfig()
# 默认: /data/ditto
# 自动生成: market/stock/bars/daily/, metadata/metadata.sqlite, 等

# 使用配置
store = BarsStore(config.data_root)
```

### Runtime 层

运行时基础设施组件：

| 组件 | 说明 |
|------|------|
| `SQLitePool` | SQLite 连接池，管理元数据数据库 |
| `FileLockManager` | 文件锁管理器，保证并发写入安全 |
| `InstrumentIdAllocator` | Instrument ID 分配器 |
| `DQChecker` | 数据质量检查引擎 |
| `FreezeManager` | 数据冻结管理器 |
| `SqlEngine` | SQL 执行引擎，支持慢查询监控 |
| `DataCache` | 统一缓存层（基于 cachebox） |
| `PitHelper` | PIT SQL 辅助函数 |

### Store 层

数据存储组件（Parquet 文件 + SQLite 元数据）：

| 组件 | 说明 | 存储格式 |
|------|------|----------|
| `InstrumentStore` | 标的主数据 | SQLite |
| `CalendarStore` | 交易日历 | SQLite + 内存缓存 |
| `BarsStore` | OHLCV 行情 | Parquet (分区: instrument_id/year) |
| `AdjFactorStore` | 复权因子 | Parquet (分区: instrument_id/year) |
| `UniverseStore` | 股票池 | SQLite |
| `IndexWeightStore` | 指数权重 | SQLite |
| `IngestionLogStore` | 数据摄取事件日志 | SQLite |
| `QuarantineStore` | 数据隔离区 | SQLite |

### 域级组织

DataHub 采用域驱动设计（DDD），按业务域组织代码结构：

#### Metadata 域

- `domains/metadata/`: Metadata 域
  - `instrument/`: 标的主数据
    - `instrument_store.py`: InstrumentStore（标的存储）
    - `identity_store.py`: IdentityStore（标识符映射存储，支持 PIT）
  - `identity/`: 标识符映射（待迁移）
  - `industry/`: 申万行业分类
    - `industry_basic_store.py`: IndustryBasicStore（行业主数据）
    - `industry_mapping_store.py`: IndustryMappingStore（标的-行业映射，支持 PIT）
  - `calendar/`: 交易日历
    - `calendar_store.py`: CalendarStore（交易日历存储）
  - `universe/`: 标的池
  - `metadata_query_service.py`: 域级统一查询服务

#### Market 域

- `domains/market/`: Market 域
  - `base/`: 基础抽象类
    - `bars_store_base.py`: MarketBarsStoreBase（行情数据基类）
  - `stock/`: 股票行情数据
    - `bars/bars_store.py`: StockBarsStore（股票 K线数据）
    - `status/status_store.py`: StockStatusStore（股票状态数据）
    - `adj/adj_factor_store.py`: StockAdjFactorStore（股票复权因子）
  - `etf/`: ETF 行情数据
    - `bars/bars_store.py`: EtfBarsStore（ETF K线数据）
    - `status/status_store.py`: EtfStatusStore（ETF 状态数据）
    - `nav/nav_store.py`: EtfNavStore（ETF 净值数据）
    - `adj/adj_factor_store.py`: EtfAdjFactorStore（ETF 复权因子）
  - `index/`: 指数行情数据
    - `bars/bars_store.py`: IndexBarsStore（指数 K线数据）
    - `constituent/constituent_store.py`: IndexConstituentStore（指数成分股）
  - `market_query_service.py`: MarketService（域级统一查询服务）

#### Fundamental 域

- `domains/fundamental/`: Fundamental 域（企业基本面数据）
  - `financial/`: 财务报表数据子域
  - `corporate/`: 公司行为数据子域
  - `forecast/`: 业绩预告/快报数据子域
  - `fundamental_store.py`: FundamentalStore（基本面数据存储，支持 PIT 查询）

**数据类型**（9 种）：

1. **财务报表数据**（PIT）
   - `balance_sheet`: 资产负债表
   - `income_statement`: 利润表
   - `cash_flow`: 现金流量表

2. **公司行为数据**
   - `dividend`: 股息分红（PIT）
   - `corporate_actions`: 公司行为（非 PIT）

3. **业绩预告/快报数据**（PIT）
   - `forecast`: 业绩预告
   - `express`: 业绩快报

**PIT 查询支持**：
- 8 种数据类型支持 PIT 查询（除 corporate_actions 外）
- PIT 查询模式：`effective_from <= as_of_date AND (effective_to IS NULL OR effective_to > as_of_date)`

#### Capital 域

- `domains/capital/`: Capital 域（资金与资本市场数据）
  - `margin/`: 融资融券数据子域
    - `margin_trading_store.py`: MarginTradingStore（融资融券存储）
  - `pledge/`: 股权质押数据子域
    - `pledge_ratio_store.py`: PledgeRatioStore（股权质押存储）
  - `capital_store.py`: CapitalStore（资金数据存储，支持 PIT 查询）
  - `capital_ingestion.py`: CapitalIngestion（资金数据摄入服务）

**数据类型**（5 种）：

1. **估值指标数据**（PIT）
   - `valuation_metrics`: 估值指标（PE/PB/PS/股息率/市值）

2. **融资融券数据**（PIT）
   - `margin_trading`: 融资融券（融资余额/融券余额/融资买入额/融券卖出额）

3. **股权质押数据**（PIT）
   - `pledge_ratio`: 股权质押（质押比例/质押股数/总股本）

4. **期货数据**（PIT）
   - `futures`: 期货数据（持仓量/结算价/成交量/成交额）

5. **成分股数据**（PIT）
   - `index_composition`: 指数成分股（指数ID/标的ID/权重）

**PIT 查询支持**：
- 所有 5 种数据类型支持 PIT 查询
- PIT 查询模式：`effective_from <= as_of_date AND (effective_to IS NULL OR effective_to > as_of_date)`

**使用示例**：
```python
from ditto_datahub.domains.capital import CapitalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool

# 初始化
pool = SQLitePool("path/to/capital.db")
client = SQLiteClient(pool)
store = CapitalStore(client)

# 写入资产负债表数据
import polars as pl
df = pl.DataFrame({
    "instrument_id": ["600000.SH"],
    "report_date": [date(2024, 3, 31)],
    "knowledge_date": [date(2024, 4, 30)],
    "effective_from": [date(2024, 5, 1)],
    "effective_to": [None],
    "total_assets": [1000000.0],
    "total_liabilities": [600000.0],
    "net_assets": [400000.0],
    "current_assets": [300000.0],
    "current_liabilities": [200000.0],
})
store.write_balance_sheet(df)

# PIT 查询：查询 2024-05-15 时点的资产负债表
result = store.get_balance_sheet(
    instrument_id="600000.SH",
    as_of_date=date(2024, 5, 15),
)
```

#### 架构优势

- **高内聚**: 相关业务逻辑聚合在同一域内
- **低耦合**: 域之间通过明确的接口（QueryService）交互
- **可扩展**: 新增域不影响现有域的实现
- **易测试**: 每个域可独立测试

### Accessor 层

业务逻辑封装层：

| 组件 | 说明 |
|------|------|
| `InstrumentsAccessor` | 标的查询、注册、标识符解析 |
| `BarsAccessor` | 行情查询、复权计算 |
| `CalendarAccessor` | 交易日历查询、日期偏移 |
| `UniverseAccessor` | 股票池管理 |
| `IndexAccessor` | 指数成分股管理 |

### Sources 层

外部数据源适配器：

| 组件 | 说明 |
|------|------|
| `TushareClient` | Tushare API 客户端 |
| `TushareSource` | Tushare 数据源实现 |
| `DataSources` | 数据源统一访问入口 |

## 使用示例

### 基础层使用

直接使用基础层存储组件：

```python
from ditto_datahub.config import DataRootConfig
from ditto_datahub.stores.base import ParquetStore, SQLiteStore
import polars as pl

# 初始化配置
config = DataRootConfig()

# ParquetStore：按年分区存储
parquet_store = ParquetStore(config.market_stock_bars_path)

# 写入数据
df = pl.DataFrame({
    "instrument_id": [1, 1, 2],
    "trade_date": ["2024-01-02", "2024-01-03", "2024-01-02"],
    "close": [10.5, 10.8, 20.3],
})
result = parquet_store.write(
    dataset="stock_daily",
    data=df,
    on_duplicate="keep_last",
    year=2024,
)

# 读取数据
df = parquet_store.read(
    dataset="stock_daily",
    instrument_ids=[1, 2],
    start_date="2024-01-01",
    end_date="2024-01-31",
)

# SQLiteStore：元数据存储
sqlite_store = SQLiteStore(config.metadata_db_path)

# 执行 SQL 查询
rows = sqlite_store.fetchall("SELECT * FROM instruments WHERE instrument_id IN (1, 2)")
```

### 基本用法

```python
from ditto_datahub import DataHub

# 初始化 DataHub（使用默认数据目录）
hub = DataHub()

# 查询标的情報
instrument = hub.instruments.get_by_instrument_id(1)

# 查询交易日历
trading_days = hub.calendar.get_range("2024-01-01", "2024-01-31")

# 查询行情数据（带复权）
bars = hub.bars.get_bars(
    instrument_ids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    adjust="qfq"  # 前复权
)
```

### Metadata 查询（新 API）

DataHub v0.7.0 引入了域级查询服务 `MetadataService`，提供统一的 Metadata 域查询接口：

```python
from ditto_datahub import DataHub

hub = DataHub()

# 标识符解析（支持 PIT）
instrument_id = hub.metadata.resolve_instrument_id("600000.SH", source="tushare")
instrument_id = hub.metadata.resolve_instrument_id("600000.SH", source="tushare", asof="2024-06-30")

# 查询标的情報
df = hub.metadata.get_instruments(instrument_ids=[1, 2, 3])
df = hub.metadata.get_instruments(instrument_ids=[1], asset_class="stock", exchange="SSE")

# 查询交易日历
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31", only_open=True)

# 交易日历便捷方法
is_trading = hub.metadata.is_trading_day("2024-01-15")
prev_day = hub.metadata.get_prev_trading_day("2024-01-15")
next_day = hub.metadata.get_next_trading_day("2024-01-15")

# 查询行业分类
industries = hub.metadata.get_industries(level=1)  # 一级行业
mappings = hub.metadata.get_industry_mappings(instrument_ids=[1, 2, 3], asof="2024-06-30")

# 查询标的池
universe = hub.metadata.get_universe(name="csi300")
```

### Market 查询（新 API）

DataHub 引入了域级查询服务 `MarketService`，提供统一的 Market 域查询接口：

```python
from ditto_datahub import DataHub
from ditto_datahub.domains.market import AdjType, MarketBarsQuery

hub = DataHub()

# 查询股票 K线数据（支持复权）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    adj=AdjType.QFQ,  # 前复权
)
bars = hub.market.get_bars(query)

# 查询带状态信息的 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    with_status=True,  # 添加停牌、ST 等状态信息
)
bars = hub.market.get_bars(query)

# PIT 安全查询（只使用 asof 日期之前的数据）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    asof="2024-06-30",  # 只使用 2024-06-30 之前已知的数据
)
bars = hub.market.get_bars(query)

# 查询 ETF K线数据
query = MarketBarsQuery(
    instrument_ids=[510010, 510050],  # ETF Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="etf",
)
bars = hub.market.get_bars(query)

# 查询指数 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2],  # 指数 Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="index",
)
bars = hub.market.get_bars(query)
```

#### 向后兼容

为了平滑迁移，DataHub 保留了旧的 API 别名：

```python
# 旧 API（仍然支持）
instrument_id = hub.securities.resolve_instrument_id("600000.SH", source="tushare")
df = hub.securities.get(instrument_ids=[1, 2, 3])
trading_days = hub.calendar.get("2024-01-01", "2024-01-31")

# 新 API（推荐）
instrument_id = hub.metadata.resolve_instrument_id("600000.SH", source="tushare")
df = hub.metadata.get_instruments(instrument_ids=[1, 2, 3])
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")
```

**迁移建议**：新代码优先使用 `hub.metadata` 接口，旧代码可逐步迁移。

### PIT 安全查询

```python
from ditto_datahub import DataHub

hub = DataHub()
decision_date = "2024-01-15"

# 使用 Accessor 层的 PIT 安全方法
bars = hub.bars.get(
    instrument_ids=[1],
    start="2024-01-01",
    end=decision_date,
    asof=decision_date,  # PIT 查询：只使用 decision_date 之前的数据
)
```

### 数据质量检查

DataHub 提供三级数据质量检查机制：

**L1 技术检查**: 非空、唯一、类型、外键、必需列
**L2 业务检查**: 正值、表达式、范围、非零成交量
**L3 统计检查**: Z-score 异常检测、完整性检查

```python
from ditto_datahub import DataHub

hub = DataHub()

# 运行 DQ 检查
result = hub.dq_checker.check(
    data=bars_df,
    checkers=["business", "statistical", "technical"]
)
```

## PIT 安全核心规则

### PIT 安全三原则

1. **knowledge_date 字段**：所有数据表必须包含此字段，表示数据"已知时间"
2. **closed="left"**：Polars rolling 窗口必须显式指定，避免使用当日数据
3. **T日信号→T+1执行**：信号生成日不能执行，次一交易日才能执行

### 正确示例

```python
# ✅ 正确：使用 knowledge_date 过滤
baseline_df = adj_df.filter(pl.col("knowledge_date") <= asof_date)

# ✅ 正确：rolling 显式指定 closed="left"
pl.col("close").rolling_mean(20, closed="left")
```

### 错误示例

```python
# ❌ 错误：使用 trade_date 过滤（构成未来函数）
baseline_df = adj_df.filter(pl.col("trade_date") <= asof_date)

# ❌ 错误：rolling 使用默认值（包含当日）
pl.col("close").rolling_mean(20)
```

## 数据目录结构

```
${data_root}/
├── meta/
│   ├── hub.sqlite          # 元数据数据库（标的、日历等）
│   └── pipeline.sqlite     # ETL 流水
├── bars/
│   ├── instrument_id=1/
│   │   ├── year=2023/
│   │   │   └── data.parquet
│   │   └── year=2024/
│   └── instrument_id=2/
├── adj_factor/
│   └── (同上)
├── locks/                  # 文件锁目录
├── quarantine/             # 数据隔离区
└── freezes/                # Freeze 管理器清单
```

## 性能优化

### 缓存策略

- **CalendarStore**：启动时全部加载到内存（~1MB，7500条记录）
- **DataCache**：基于 cachebox.TTLCache，支持 TTL + LRU
- **延迟加载**：使用 `@cached_property` 按需初始化组件

### Parquet 分区策略

```
bars/
├── instrument_id=1/          # 按 instrument_id 分区（减少扫描文件数）
│   ├── year=2023/  # 按年份分区（支持时间范围查询）
│   └── year=2024/
└── instrument_id=2/
```

### 并发安全

- **文件锁**：`FileLockManager` 保证并发写入安全
- **连接池**：`SQLitePool` 复用连接，避免频繁打开/关闭

## 相关文档

- [PIT 安全指南](../../../../.claude/skills/pit-guide/SKILL.md)
- [Polars 使用指南](../../../../.claude/skills/polars-guide/SKILL.md)
- [数据设计文档](../../../../docs/design/02_data_design.md)

## 变更记录

### v0.11.0 (2026-01-30)
**重构**
- 域重构：将 Capital 域拆分为 Fundamental 域和 Capital 域
  - Fundamental 域：企业基本面数据（财务报表、公司行为、业绩预告/快报）
  - Capital 域：资金与资本市场数据（估值指标、融资融券、股权质押、期货、指数成分股）

**新增**
- Fundamental 域架构：`domains/fundamental/` 目录结构
  - `financial/`: 财务报表数据子域
  - `corporate/`: 公司行为数据子域
  - `forecast/`: 业绩预告/快报数据子域
  - `fundamental_store.py`: FundamentalStore（基本面数据统一入口）
- Capital 域子域结构：
  - `margin/`: 融资融券数据子域
    - `margin_trading_store.py`: MarginTradingStore
  - `pledge/`: 股权质押数据子域
    - `pledge_ratio_store.py`: PledgeRatioStore

**迁移**
- 从 Capital 域迁移到 Fundamental 域：
  - 财务报表：balance_sheet, income_statement, cash_flow
  - 公司行为：dividend, corporate_actions
  - 业绩数据：forecast, express
- Capital 域保留数据类型：
  - 估值指标：valuation_metrics
  - 融资融券：margin_trading
  - 股权质押：pledge_ratio
  - 期货：futures
  - 指数成分股：index_composition

**改进**
- 域职责更清晰：Fundamental 聚焦企业基本面，Capital 聚焦资金与资本市场
- 子域模式：复杂域使用子域存储（如 Capital 的 margin/pledge，Fundamental 的 financial/corporate/forecast）
- 测试覆盖：所有新域和子域的单元测试和集成测试
- 文档更新：README 更新城架构说明

**测试**
- Fundamental 域单元测试：financial、corporate、forecast 子域的完整测试覆盖
- Capital 域单元测试：margin、pledge 子域的完整测试覆盖
- 集成测试更新：更新 Capital 域集成测试，移除已迁移到 Fundamental 的数据类型
- 测试通过：所有单元测试和集成测试通过，类型检查通过

### v0.10.0 (2026-01-29)
**新增**
- Ingestion 层架构：`ingestion/` 目录
  - `coordinator.py`: IngestionCoordinator（路由协调器）
  - `data_writer.py`: IngestionDataWriter（数据写入工具）
- Ingestion 层支持三种数据写入策略：
  - `OnDuplicate.ERROR`: 遇到重复数据时报错（默认，最安全）
  - `OnDuplicate.KEEP_FIRST`: 保留现有数据，忽略新数据
  - `OnDuplicate.KEEP_LAST`: 使用新数据覆盖现有数据（Last-Write-Wins）

**实现**
- IngestionCoordinator：根据 Domain 枚举路由到对应的域 Ingestion 服务
- IngestionDataWriter：支持 Parquet 和 SQLite 写入，提供重复数据处理策略
- IngestionResult：数据摄入结果数据类（success、records_written、error）
- 异步支持：所有 Ingestion 服务支持异步操作

**测试**
- Ingestion 层单元测试：coordinator、data_writer 的完整测试覆盖
- Ingestion 层集成测试：端到端摄入流程测试
- 测试覆盖率：coordinator 95%，data_writer 59%（SQLite 部分待完善）

**改进**
- 类型安全：所有代码通过 basedpyright strict 模式检查
- 代码质量：所有代码通过 ruff 检查
- 文档更新：README 添加 Ingestion 层架构说明和使用示例

### v0.9.0 (2026-01-29)
**新增**
- Capital 域架构：`domains/capital/` 目录结构
  - `capital_store.py`: CapitalStore（资金数据存储，支持 PIT 查询）
  - `capital_ingestion.py`: CapitalIngestion（资金数据摄入服务）
- Capital 域支持 10 种数据类型：
  - 财务报表：balance_sheet, income_statement, cash_flow（PIT）
  - 估值指标：valuation_metrics（PIT）
  - 衍生品：futures（PIT）
  - 成分股：index_composition（PIT）
  - 股息分红：dividend（PIT）
  - 融资融券：margin_trading（PIT）
  - 股权质押：pledge_ratio（PIT）
  - 公司行为：corporate_actions（非 PIT）

**实现**
- CapitalStore：10 种数据类型的 write/get 方法（支持 PIT 查询）
- CapitalIngestion：10 种数据类型的摄入方法（Source → Store）
- PIT 查询支持：9 种数据类型支持 PIT 查询
- 数据缓存支持：DataCache 集成
- 测试覆盖：所有 10 种数据类型的单元测试和集成测试

**改进**
- 测试覆盖：Capital 域覆盖率 ≥ 60%（capital_store: 60.17%, capital_ingestion: 72.93%）
- 类型安全：所有代码通过 basedpyright strict 模式检查
- 代码质量：所有代码通过 ruff 检查
- 文档更新：README 添加 Capital 域说明和使用示例

### v0.8.0 (2026-01-29)
**重构**
- 命名标准化：`security` → `instrument`（业界标准术语）
  - `SecurityStore` → `InstrumentStore`
  - `SecuritiesAccessor` → `InstrumentsAccessor`
  - `sid` → `instrument_id`（更明确的标识符）
  - `src_code` → `source_ticker`（数据源原始格式）
  - `SidAllocator` → `InstrumentIdAllocator`
- SourceSchema 层实现：
  - 实现 `SourceSchema` dataclass（验证列完整性、类型兼容性、主键唯一性）
  - 实现 `NormalizationConfig`（Exchange、InstrumentType、Currency 枚举）
  - 扩展 `ColumnMapping`（添加 `source_schema` 和 `normalization` 字段）
  - 更新 `TushareDataTransformer`（转换后自动验证 Schema）
- Metadata 域形式化：
  - 定义所有 Metadata 数据集的 SourceSchema
  - 实现 `IndustryTushareAdapter`（申万行业分类）
  - 所有代码统一使用新命名

**改进**
- 类型安全：所有代码通过 basedpyright strict 模式检查
- 测试覆盖：1266+ 个测试全部通过（覆盖率 ≥ 80%）
- 代码质量：所有代码通过 ruff 检查
- 文档更新：README 和示例代码使用新命名

### v0.8.0 (2026-01-28)
**新增**
- Market 域架构：`domains/market/` 目录结构
  - `stock/`: 股票行情数据域（StockBarsStore、StockStatusStore、StockAdjFactorStore）
  - `etf/`: ETF 行情数据域（EtfBarsStore、EtfStatusStore、EtfNavStore、EtfAdjFactorStore）
  - `index/`: 指数行情数据域（IndexBarsStore、IndexConstituentStore）
- MarketService：域级统一查询服务（`hub.market`）
  - 股票 K线查询（支持复权、状态增强）
  - ETF K线查询
  - 指数 K线查询
  - PIT 安全查询（asof 参数）

**重构**
- StockBarsStore 迁移到 `domains/market/stock/bars/`
- StockStatusStore 迁移到 `domains/market/stock/status/`
- StockAdjFactorStore 迁移到 `domains/market/stock/adj/`
- 新增 ETF 相关 Store（EtfBarsStore、EtfStatusStore、EtfNavStore、EtfAdjFactorStore）
- 新增指数相关 Store（IndexBarsStore、IndexConstituentStore）
- DataHub 集成 MarketService，提供 `hub.market` 统一查询接口

**改进**
- 域驱动设计（DDD）：Market 域完整实现
- 增强类型安全，完善文档注释
- 向后兼容性：保留 `hub.bars` 接口

### v0.7.0 (2026-01-27)
**新增**
- Metadata 域架构：`domains/metadata/` 目录结构
  - `security/`: 证券主数据域（SecurityStore、IdentityStore）
  - `industry/`: 申万行业分类域（IndustryBasicStore、IndustryMappingStore）
  - `calendar/`: 交易日历域（CalendarStore）
  - `universe/`: 标的池域
- MetadataService：域级统一查询服务（`hub.metadata`）
  - 标识符解析（支持 PIT）
  - 证券信息查询
  - 交易日历查询
  - 行业分类查询
  - 标的池查询

**重构**
- SecurityStore 迁移到 `domains/metadata/security/`
- CalendarStore 迁移到 `domains/metadata/calendar/`
- IndustryBasicStore、IndustryMappingStore 新增
- IdentityStore 新增（支持 PIT 标识符映射）
- DataHub 集成 MetadataService，提供 `hub.metadata` 统一查询接口

**改进**
- 向后兼容性：保留 `hub.securities`、`hub.calendar` 别名
- 所有 Store 继承 SQLiteStore 基类
- 增强类型安全，完善文档注释
- 域驱动设计（DDD）：高内聚、低耦合、易扩展

### v0.6.0 (2026-01-27)
**新增**
- 基础层架构：添加 `BaseStore` 抽象基类，定义统一存储接口
- `ParquetStore`：Parquet 文件存储实现，支持按年分区、自动去重
- `SQLiteStore`：SQLite 数据库存储实现，支持事务、PIT 查询
- `DataRootConfig`：统一数据根路径配置，简化路径管理

**改进**
- 从多路径配置简化为单 `DATA_ROOT` 配置
- 所有存储实现继承 `BaseStore`，保证接口一致性
- 增强类型安全和代码可维护性

### v0.5.0 (2026-01-23)
**新增**
- README 标准化，添加版本、日期、状态元数据
- 添加变更记录部分

**改进**
- 完善架构说明
- 重新组织文档结构

### v0.4.0 (2025-12-27)
**新增**
- Sprint 1 P0 任务全部完成
- DataHub Facade 实现
- SqlEngine 实现

### v0.1.0 (2025-12-08)
**新增**
- 初始数据层实现
- Stores 层基础功能
- Runtime 层基础组件
