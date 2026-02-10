# Ditto 量化系统架构设计

> **核心理念**：简洁的层次、清晰的职责、符合量化业务逻辑
>
> **基于业界最佳实践**：WorldQuant、Two Sigma、Citadel、九坤等领先量化机构的架构模式
>
> **设计日期**: 2026-02-07
>
> **版本**: 5.15

---

## 一、架构总览

### 1.1 核心领域概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **instrument_id** | 证券唯一标识符（内部分配的长整型 ID） | `1000001`（stock）、`2000001`（etf）、`3000001`（index） |
| **ticker** | 证券代码（纯代码，无后缀） | `"000001"`, `"510300"` |
| **exchange** | 交易所代码（ISO 10383 标准） | `"SSE"`, `"SZSE"`, `"BSE"` |
| **standard_ticker** | 标准格式代码（展示层） | `"000001.SZ"` = `f"{ticker}.{exchange}"` |
| **source_ticker** | 数据源原始代码 | `"000001.SZ"`（tushare 格式） |
| **source** | 数据源标识 | `"tushare"`, `"tdx"`, `"akshare"` |
| **trade_date** | 交易日期 | `2024-01-15` |
| **knowledge_date** | 数据已知日期（PIT安全） | `2024-01-16`（T+1发布） |
| **effective_from/to** | 生效时间范围（PIT） | `2024-01-15` ~ `2024-03-20` |
| **DataFrame** | 核心数据结构（Polars） | `pl.DataFrame` |
| **SourceSchema** | 数据源输出格式标准 | `STOCK_DAILY_SOURCE_SCHEMA` |
| **StorageSchema** | 存储格式标准 | `STOCK_DAILY_SCHEMA` |
| **Query/Result** | 统一查询/写入模式 | `BarsQuery`, `WriteResult` |
| **Service** | 域服务（封装业务逻辑） | `MarketService`, `MetadataService` |

**instrument_id 范围定义**（InstrumentIdRange）：
- **stock**：1,000,000 ~ 1,999,999
- **etf**：2,000,000 ~ 2,999,999
- **index**：3,000,000 ~ 3,999,999

**命名规范**：
- **存储层**：使用 `instrument_id`（Int64，如 1000001）
- **展示层**：使用 `standard_ticker = f"{ticker}.{exchange}"`（如 "000001.SZ"）
- **数据源代码**：保留 `source_ticker` 字段记录原始数据源格式（如 "000001.SZ"）
- **查询方法**：统一使用 Query 对象模式

**领域划分**：

| 域 | 职责 | 数据集示例 |
|----|------|-----------|
| **Market** | 行情数据 | stock_daily, etf_daily, index_daily, adj_factor, stock_status |
| **Metadata** | 元数据 | instrument, calendar, industry, index_member, universe |
| **Fundamental** | 财务数据 | balance_sheet, income_statement, cash_flow, **forecast**（业绩快报） |
| **Capital** | 资本市场数据 | valuation_metrics, dividend, margin_trading, pledge_ratio |
| **Macro** | 宏观数据 | macro_indicators |

**衍生模块**（后续单独设计）：
- **Features**：技术指标计算（基于 Market 数据）
- **Factors**：因子数据（基于 Market/Fundamental/Capital 计算） |

### 1.2 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Port Layer                           │
│  ┌─────────────────────────────────────────────────┐        │
│  │  API Routes (FastAPI)                           │        │
│  │  - Pydantic Models (API 请求/响应)               │        │
│  │  - 依赖注入: dishka 容器管理                     │        │
│  │  - 数据转换: DataFrame ↔ Model                  │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┴─────────────────┐
            ▼                                   ▼
┌─────────────────────────────────────────────────────────────┐
│                      Core Layer                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │  业务逻辑层（仅依赖 DataHub 模型）               │        │
│  │  ┌─────────┬────────────┬──────────────┐        │        │
│  │  │Engine   │  Portfolio │  Strategy     │        │        │
│  │  │Backtest │  Manager   │  Base         │        │        │
│  │  │Risk     │  Builder   │  Signal       │        │        │
│  │  └─────────┴────────────┴──────────────┘        │        │
│  │  使用 DataHub 的模型（dataclass/Schema）         │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      DataHub Layer                          │
│  ┌─────────────────────────────────────────────────┐        │
│  │  数据访问层（模型 + 实现）                       │        │
│  │                                                  │        │
│  │  ┌─────────────────────────────────────────┐    │        │
│  │  │ Models (共享模型定义)                    │    │        │
│  │  │ - Schema: BAR_SCHEMA, QUOTE_SCHEMA      │    │        │
│  │  │ - 模型: Order, Position, Portfolio      │    │        │
│  │  └─────────────────────────────────────────┘    │        │
│  │                                                  │        │
│  │  ┌─────────────────────────────────────────┐    │        │
│  │  │ Sources (返回符合 Schema 的 DataFrame)   │    │        │
│  │  │ - TushareSource → Adapters              │    │        │
│  │  └─────────────────────────────────────────┘    │        │
│  │                                                  │        │
│  │  ┌─────────────────────────────────────────┐    │        │
│  │  │ Services (域服务，Core 不直接使用)       │    │        │
│  │  │ - Market, Metadata, Fundamental          │    │        │
│  │  │ - Capital, Macro                         │    │        │
│  │  └─────────────────────────────────────────┘    │        │
│  │                                                  │        │
│  │  ┌─────────────────────────────────────────┐    │        │
│  │  │ Stores (数据存储，Core 不直接使用)       │    │        │
│  │  │ - OrderStore, PositionStore             │    │        │
│  │  │ - PortfolioStore, TradeStore             │    │        │
│  │  └─────────────────────────────────────────┘    │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Foundation Layer                         │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────────┐     │
│  │  Config   │  │  Logger   │  │       Cache          │     │
│  │ Settings  │  │  Loguru   │  │    Cachebox          │     │
│  └───────────┘  └───────────┘  └─────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 核心原则

| 原则 | 说明 |
|------|------|
| **模型集中** | 所有共享模型定义在 DataHub 层 |
| **Core 依赖限制** | Core 仅依赖 DataHub 的模型定义，不依赖 Service/Store |
| **Schema + 模型** | 数据密集型用 Schema (DataFrame)，逻辑密集型用 dataclass |
| **DataFrame 核心** | 市场数据以 `pl.DataFrame` 为核心，保留计算能力 |
| **单向依赖** | Port → DataHub，Core → DataHub (仅模型)，无循环依赖 |
| **CQRS** | Reader/Writer 分离，读写独立 |
| **Service 闭合** | DataHub 内部所有域都有 Service，Port 不直接依赖 Stores |
| **纯函数优先** | 复权、PIT 等功能使用纯函数，无状态 |
| **YAGNI** | 只实现需要的功能，架构随需求演进 |

### 1.4 数据模型分类使用规范

| 数据类型 | 特点 | 位置 | 传输格式 | 示例 |
|---------|------|------|----------|------|
| **数据密集型** | 大量数据，计算密集 | DataHub 层 (Schema) | DataFrame | Bar, Quote, Fundamental |
| **逻辑密集型** | 状态管理，业务规则 | DataHub 层 (dataclass) | 对象 | Order, Position, Portfolio |
| **API 边界** | 验证、序列化 | Port 层 (Pydantic) | JSON | BarsQuery, BarResponse |

**分类原则**：
- 是否需要向量化计算？→ Schema + DataFrame
- 是否有复杂业务状态？→ dataclass 模型
- 是否跨 API 传输？→ Pydantic（Port 层）

### 1.5 依赖规则

#### 1.5.1 层级依赖关系

| 层级 | 可依赖 | 禁止依赖 | 说明 |
|------|--------|----------|------|
| **Port** | DataHub (Service)、DataHub (模型) | - | 可使用 DataHub 的所有内容 |
| **Core** | **DataHub (模型定义)** | DataHub (Service/Store) | 仅使用模型，不使用实现类 |
| **DataHub** | Foundation | Port/Core | 基础设施层 |

#### 1.5.2 Core 层依赖限制

**Core 层可以使用的 DataHub 内容**：
```python
# ✅ Core 可以使用 DataHub 的模型
from ditto_datahub.models import Order, Position, Portfolio
from ditto_datahub.models.market import BAR_SCHEMA, QUOTE_SCHEMA
```

**Core 层禁止使用的内容**：
```python
# ❌ Core 不能使用 DataHub 的 Service/Store
from ditto_datahub.services import MarketService  # 禁止
from ditto_datahub.stores import BarsStore  # 禁止
```

**强制措施**：
- 代码审查：通过 PR 检查 import 语句
- 架构测试：添加依赖检查测试（可选）

---

## 二、数据集协议与格式

### 2.1 数据流架构

```
Source API → SourceSchema → Normalization → StorageSchema → Parquet
     ↓              ↓              ↓               ↓           ↓
  fetch()      标准输出格式      字段转换        存储格式     持久化
```

### 2.2 数据集分类（完整版）

| 业务域 | 数据集 | SourceSchema | StorageSchema | PIT | 状态 |
|--------|--------|--------------|---------------|-----|------|
| **Market** | stock_daily | STOCK_DAILY_SOURCE_SCHEMA | STOCK_DAILY_SCHEMA | ✓ | ✅ 已实现 |
| **Market** | etf_daily | ETF_DAILY_SOURCE_SCHEMA | ETF_DAILY_SCHEMA | ✓ | ✅ 已实现 |
| **Market** | index_daily | INDEX_DAILY_SOURCE_SCHEMA | INDEX_DAILY_SCHEMA | - | ✅ 已实现 |
| **Market** | adj_factor | ADJ_FACTOR_SOURCE_SCHEMA | ADJ_FACTOR_SCHEMA | ✓ | ✅ 已实现 |
| **Market** | fund_adj | FUND_ADJ_SOURCE_SCHEMA | FUND_ADJ_SCHEMA | ✓ | ✅ 已实现 |
| **Market** | stock_status | STOCK_STATUS_SOURCE_SCHEMA | STOCK_STATUS_SCHEMA | - | ✅ 已实现 |
| **Metadata** | calendar | - | CALENDAR_SCHEMA | - | ✅ 已实现 |
| **Metadata** | instrument | INSTRUMENT_SOURCE_SCHEMA | INSTRUMENT_SCHEMA | - | ✅ 已实现 |
| **Metadata** | industry | INDUSTRY_SOURCE_SCHEMA | INDUSTRY_SCHEMA | ✓ | ✅ 已实现 |
| **Metadata** | index_member | INDEX_MEMBER_SOURCE_SCHEMA | INDEX_WEIGHT_SCHEMA | ✓ | ✅ 已实现 |
| **Metadata** | universe | UNIVERSE_SOURCE_SCHEMA | UNIVERSE_CONSTITUENT_SCHEMA | ✓ | ✅ 已实现 |
| **Fundamental** | balance_sheet | BALANCE_SHEET_SOURCE_SCHEMA | BALANCE_SHEET_SCHEMA | ✓ | ✅ 已实现 |
| **Fundamental** | income_statement | INCOME_STATEMENT_SOURCE_SCHEMA | INCOME_STATEMENT_SCHEMA | ✓ | ✅ 已实现 |
| **Fundamental** | cash_flow | CASH_FLOW_SOURCE_SCHEMA | CASH_FLOW_SCHEMA | ✓ | ✅ 已实现 |
| **Fundamental** | **forecast** | **FORECAST_SOURCE_SCHEMA** | **FORECAST_SCHEMA** | ✓ | ✅ 已实现 |
| **Capital** | valuation_metrics | VALUATION_METRICS_SOURCE_SCHEMA | VALUATION_METRICS_SCHEMA | ✓ | ✅ 已实现 |
| **Capital** | margin_trading | MARGIN_TRADING_SOURCE_SCHEMA | MARGIN_TRADING_SCHEMA | ✓ | ✅ 已实现 |
| **Capital** | pledge_ratio | PLEDGE_RATIO_SOURCE_SCHEMA | PLEDGE_RATIO_SCHEMA | ✓ | ✅ 已实现 |
| **Capital** | dividend | DIVIDEND_SOURCE_SCHEMA | DIVIDEND_SCHEMA | ✓ | ✅ 已实现 |
| **Capital** | futures | FUTURES_SOURCE_SCHEMA | FUTURES_SCHEMA | ✓ | 🔄 部分实现 |
| **Capital** | corporate_actions | CORPORATE_ACTIONS_SOURCE_SCHEMA | CORPORATE_ACTIONS_SCHEMA | ✗ | 🔄 部分实现 |
| **Macro** | macro_indicators | MACRO_INDICATOR_SOURCE_SCHEMA | MACRO_INDICATOR_SCHEMA | ✓ | ✅ 已实现 |

**图例**：
- ✅ 已实现：Store 和 Schema 已完整实现
- 🔄 部分实现：SourceSchema 已定义，Storage 待完善

**说明**：
- **PIT 列**：`knowledge_date`（数据已知日期）或 `effective_from/to`（生效时间范围）
- **universe**：股票池成分数据，支持动态成分权重（PIT）
- **forecast**：业绩快报数据（Fundamental 域）
- **macro_indicators**：宏观指标数据，支持 PIT 查询

### 2.3 标准枚举定义

系统定义了以下标准枚举类型，用于确保数据一致性和类型安全。

#### 交易所枚举

| 枚举值 | 说明 | ISO 10383 MIC |
|--------|------|---------------|
| `SSE` | 上海证券交易所 | XSHG |
| `SZSE` | 深圳证券交易所 | XSHE |
| `BSE` | 北京证券交易所 | XBJG |

#### 数据源枚举

| 枚举值 | 说明 | 状态 |
|--------|------|------|
| `tushare` | Tushare 数据源 | ✅ 已实现 |
| `akshare` | AkShare 数据源 | 📅 预留 |
| `tdx` | 通达信数据源 | ✅ 已实现 |

#### 证券类型枚举

| 枚举值 | 说明 | ISO 10962 CFI |
|--------|------|---------------|
| `stock` | 股票 | ESVUFP |
| `etf` | 交易型开放式指数基金 | ETPUF |
| `index` | 指数 | - |
| `future` | 期货 | FXXXXX |
| `option` | 期权 | OXXXXX |
| `bond` | 债券 | DBXXXX |
| `fund` | 基金 | EUTFP |

#### 货币枚举

| 枚举值 | 说明 | ISO 4217 |
|--------|------|----------|
| `CNY` | 人民币 | CNY |
| `USD` | 美元 | USD |
| `HKD` | 港币 | HKD |
| `EUR` | 欧元 | EUR |

#### 数据域枚举

| 枚举值 | 说明 | 职责 |
|--------|------|------|
| `metadata` | 元数据域 | 证券、日历、行业、成分股 |
| `market` | 行情域 | K线、复权因子、状态 |
| `fundamental` | 财务域 | 财报、业绩快报 |
| `capital` | 资本域 | 估值、分红、融资融券 |
| `macro` | 宏观域 | 经济指标 |

#### 数据集枚举

| 枚举值 | 分类 | 说明 |
|--------|------|------|
| `stock_basic` | 基础类 | 股票基本信息（无需 trade_date） |
| `etf_basic` | 基础类 | ETF 基本信息（无需 trade_date） |
| `calendar` | 日历类 | 交易日历（需日期范围） |
| `stock_daily` | 行情类 | 股票日线行情（需 trade_date） |
| `etf_daily` | 行情类 | ETF 日线行情（需 trade_date） |
| `adj_factor` | 参考类 | 股票复权因子（需 trade_date） |
| `fund_adj` | 参考类 | 基金复权因子（需 trade_date） |

#### 重复处理策略枚举

| 枚举值 | 说明 | 使用场景 |
|--------|------|----------|
| `error` | 遇到重复时报错 | 默认，最安全 |
| `keep_first` | 保留现有数据，忽略新数据 | 信任首批数据 |
| `keep_last` | 使用新数据覆盖现有数据 | Last-Write-Wins |

#### 复权类型枚举

| 枚举值 | 说明 | 支持范围 |
|--------|------|----------|
| `none` | 不复权 | stock/etf/index |
| `qfq` | 前复权 | 仅 stock |
| `hfq` | 后复权 | 仅 stock |

---

## 三、存储引擎与分区策略

### 3.1 存储引擎选择

系统根据数据集的特性选择不同的存储引擎：

| 存储引擎 | 使用场景 | 优势 | 劣势 |
|----------|----------|------|------|
| **ParquetStore** | 大量时序数据（行情、财务、资本） | 列式存储、压缩率高、查询快 | 写入需要合并 |
| **SQLiteStore** | 元数据、关联数据、ID 分配 | 支持复杂查询、事务、易于关联 | 大数据量性能下降 |

#### 存储真相源（SoT）架构

**设计原则**：SQLite 优先，Parquet 为派生副本

| 数据集 | SoT | 派生副本 | 写入顺序 |
|--------|-----|----------|----------|
| **instrument** | SQLite `instruments` 表 | Parquet（可选，只读缓存） | 先 SQLite，后同步 Parquet |
| **calendar** | SQLite `calendar` 表 | Parquet（可选，只读缓存） | 先 SQLite，后同步 Parquet |
| **时序数据** | Parquet（按年分区） | - | 直接写入 Parquet |
| **security_mapping** | SQLite `security_mapping` 表 | - | 直接写入 SQLite |

**说明**：
- SQLite 作为 **唯一真相源**（Single Source of Truth），负责 ID 分配、映射、元数据
- Parquet 作为 **时序数据主存储**，接收所有行情、财务、资本市场数据
- `instrument` 和 `calendar` 可选择性同步到 Parquet，作为只读缓存加速查询

#### ParquetStore 数据集

| 数据集 | 分区策略 | 存储路径 |
|--------|----------|----------|
| stock_daily | YearlyPartition | `market/stock/bars/` |
| etf_daily | YearlyPartition | `market/etf/bars/` |
| index_daily | YearlyPartition | `market/index/bars/` |
| adj_factor | YearlyPartition | `market/stock/adj/` |
| fund_adj | YearlyPartition | `market/etf/adj/` |
| stock_status | YearlyPartition | `market/stock/status/` |
| calendar | YearlyPartition | `metadata/calendar/` |
| instrument | YearlyPartition | `metadata/instrument/` |
| index_member | YearlyPartition | `metadata/index/weight/` |
| universe | YearlyPartition | `metadata/universe/` |
| balance_sheet | YearlyPartition | `fundamental/financial/balance_sheet/` |
| income_statement | YearlyPartition | `fundamental/financial/income_statement/` |
| cash_flow | YearlyPartition | `fundamental/financial/cash_flow/` |
| forecast | YearlyPartition | `fundamental/forecast/` |
| valuation_metrics | YearlyPartition | `capital/valuation_metrics/` |
| margin_trading | YearlyPartition | `capital/margin_trading/` |
| pledge_ratio | YearlyPartition | `capital/pledge_ratio/` |
| dividend | YearlyPartition | `capital/dividend/` |

#### SQLiteStore 数据集

| 数据集 | 表名 | 说明 |
|--------|------|------|
| identity | instruments | SID 分配与映射 |
| industry_mapping | industry_mapping | 行业分类映射 |
| index_constituent | index_constituent | 指数成分股 |
| macro_indicators | macro_indicator_data | 宏观指标数据 |

### 3.2 分区策略

#### YearlyPartition（按年分区）

**适用数据集**：所有 ParquetStore 数据集

**策略说明**：
- 按年份将数据组织到不同的 Parquet 文件中
- 文件命名：`2020.parquet`, `2021.parquet`, `2022.parquet` ...
- 目录结构示例：
  ```
  data/
  └── market/
      └── stock/
          └── bars/
              ├── 2020.parquet
              ├── 2021.parquet
              └── 2022.parquet
  ```

**优势**：
- 查询时按年份过滤，减少 I/O
- 历史数据归档方便
- 并发写入冲突少

**API 示例**：
```python
strategy = YearlyPartition()
key = strategy.get_partition_key("2024-01-15")  # "2024"
filename = strategy.get_filename("2024")  # "2024.parquet"
partitions = strategy.get_partitions_from_filters("2023-01-01", "2024-12-31")  # ["2023", "2024"]
```

#### 无分区（SQLite 表内）

**适用数据集**：所有 SQLiteStore 数据集

**策略说明**：
- 数据存储在单一 SQLite 数据库文件中
- 使用 SQL WHERE 子句进行过滤
- 适合数据量小、需要复杂关联的场景

### 3.3 存储引擎对比

| 特性 | ParquetStore | SQLiteStore |
|------|--------------|-------------|
| 数据格式 | 列式存储 | 行式存储 |
| 压缩率 | 高（Snappy/Zstd） | 低 |
| 查询性能 | 列扫描快（谓词下推） | 索引快，全表扫描慢 |
| 写入模式 | 追加 + 合并 | 直接插入/更新 |
| 并发控制 | 文件锁 + 合并策略 | 事务锁 |
| 事务支持 | 文件级事务 | ACID 事务 |
| 关联查询 | 需应用层处理 | SQL JOIN |
| 适用数据量 | 大数据（GB+） | 小数据（MB） |
| 典型场景 | 时序数据、历史回测 | 元数据、关联查询 |

### 3.4 SQLite 建表脚本

SQLite 数据库的建表脚本位于 `packages/datahub/src/ditto_datahub/scripts/schema.sql`：

```sql
-- ============================================================
-- Instruments 表（证券信息）
-- ============================================================
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id INTEGER PRIMARY KEY,  -- 证券唯一标识（内部分配的整数 ID）
    source_ticker TEXT NOT NULL,        -- 数据源原始代码（如 "000001.SZ"）
    ticker TEXT NOT NULL,               -- 证券代码（如 "000001"）
    name TEXT NOT NULL,                 -- 证券名称
    exchange TEXT NOT NULL,             -- 交易所（SSE/SZSE/BSE）
    list_date TEXT,                     -- 上市日期
    delist_date TEXT,                   -- 退市日期
    instrument_type TEXT NOT NULL,      -- 类型（stock/etf/index）
    source TEXT NOT NULL                -- 数据源（tushare/tdx/akshare）
);

-- ============================================================
-- Industry Mapping 表（行业分类映射）
-- ============================================================
CREATE TABLE IF NOT EXISTS industry_mapping (
    instrument_id INTEGER NOT NULL,
    industry_name TEXT NOT NULL,
    industry_level INTEGER NOT NULL,
    industry_date TEXT NOT NULL,
    knowledge_date TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (instrument_id, industry_date, industry_level),
    FOREIGN KEY (instrument_id) REFERENCES instruments(instrument_id)
);

-- ============================================================
-- Index Constituent 表（指数成分股）
-- ============================================================
CREATE TABLE IF NOT EXISTS index_constituent (
    index_instrument_id INTEGER NOT NULL,
    constituent_instrument_id INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    weight REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (index_instrument_id, constituent_instrument_id, effective_from),
    FOREIGN KEY (index_instrument_id) REFERENCES instruments(instrument_id),
    FOREIGN KEY (constituent_instrument_id) REFERENCES instruments(instrument_id)
);

-- ============================================================
-- Macro Indicator Data 表（宏观指标）
-- ============================================================
CREATE TABLE IF NOT EXISTS macro_indicator_data (
    indicator_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    source TEXT NOT NULL,
    knowledge_date TEXT,
    PRIMARY KEY (indicator_id, date)
);

-- ============================================================
-- 索引（优化查询性能）
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_instruments_type ON instruments(instrument_type);
CREATE INDEX IF NOT EXISTS idx_instruments_exchange ON instruments(exchange);
CREATE INDEX IF NOT EXISTS idx_industry_mapping_date ON industry_mapping(industry_date);
CREATE INDEX IF NOT EXISTS idx_index_constituent_effective ON index_constituent(effective_from);
CREATE INDEX IF NOT EXISTS idx_macro_indicator_date ON macro_indicator_data(indicator_id, date);
```

**注意**：当前代码实现使用 `security` 和 `security_mapping` 表名（见 schema.sql），与文档中的 `instruments` 命名不同。这是代码演进过程中的命名变更，文档保留原始 `instruments` 命名以保持设计一致性。

---

## 四、Source 接口定义

### 3.1 DataSource 抽象基类

```python
class DataSource(ABC):
    """数据源抽象基类"""

    # ========== Market 数据 ==========

    @abstractmethod
    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取交易日历"""
        pass

    @abstractmethod
    def fetch_stock_basic(self) -> pl.DataFrame:
        """获取股票基本信息"""
        pass

    @abstractmethod
    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """获取股票日线行情"""
        pass

    @abstractmethod
    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """获取股票复权因子"""
        pass

    @abstractmethod
    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """获取股票状态"""
        pass

    @abstractmethod
    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """获取涨跌停价"""
        pass

    @abstractmethod
    def fetch_etf_basic(self) -> pl.DataFrame:
        """获取 ETF 基本信息"""
        pass

    @abstractmethod
    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """获取 ETF 日线行情"""
        pass

    @abstractmethod
    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """获取基金复权因子"""
        pass
```

### 3.2 TushareSource 实现结构

```python
class TushareSource(DataSource):
    """Tushare 数据源实现（组合模式）"""

    def __init__(self, settings: DataSourceSettings, token: str | None = None):
        self._calendar = CalendarTushareAdapter(token=token, settings=settings)
        self._stock = StockTushareAdapter(token=token, settings=settings)
        self._etf = ETFTushareAdapter(token=token, settings=settings)

    # 委托方法
    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        return self._calendar.fetch_calendar(start_date, end_date)

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        return self._stock.fetch_stock_daily(trade_date)

    # ... 其他委托方法
```

---

## 五、Source 接口到数据集映射

### 4.1 Market 域映射表

| Source 接口 | SourceSchema | StorageSchema | 映射规则 |
|-------------|--------------|---------------|----------|
| `fetch_stock_daily(trade_date)` | STOCK_DAILY_SOURCE_SCHEMA | STOCK_DAILY_SCHEMA | source_ticker → instrument_id, 增加 status 字段 |
| `fetch_etf_daily(trade_date)` | ETF_DAILY_SOURCE_SCHEMA | ETF_DAILY_SCHEMA | source_ticker → instrument_id |
| `fetch_adj_factor(trade_date)` | ADJ_FACTOR_SOURCE_SCHEMA | ADJ_FACTOR_SCHEMA | source_ticker → instrument_id |
| `fetch_fund_adj(trade_date)` | FUND_ADJ_SOURCE_SCHEMA | (同 adj_factor) | source_ticker → instrument_id |
| `fetch_stock_status(trade_date)` | STOCK_STATUS_SOURCE_SCHEMA | STOCK_STATUS_SCHEMA | source_ticker → instrument_id |
| `fetch_stock_limit(trade_date)` | STOCK_LIMIT_SOURCE_SCHEMA | (内嵌 stock_daily) | source_ticker → instrument_id, 合并到 daily |

### 4.2 字段转换规则

#### 4.2.1 Source → Storage 通用转换

| Source 字段 | Storage 字段 | 转换规则 |
|-------------|--------------|----------|
| `source_ticker` | `instrument_id` | 通过 InstrumentStore 查找或分配内部 ID |
| `source_ticker` | `source_ticker` | 保持原值（记录来源） |
| `knowledge_date` | `knowledge_date` | 保持原值（PIT 安全） |
| `trade_date` | `trade_date` | 保持原值 |
| OHLCV | OHLCV | 保持原值 |

#### 4.2.2 Stock Daily 转换示例

```python
# Source Schema (STOCK_DAILY_SOURCE_SCHEMA)
{
    "source_ticker": pl.String,      # "000001.SZ"
    "trade_date": pl.Date,
    "knowledge_date": pl.Date,  # T+1
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "pct_change": pl.Float64,
}

# Storage Schema (STOCK_DAILY_SCHEMA)
{
    "instrument_id": pl.Int64,    # 内部分配的整数 ID（如 1000001）
    "trade_date": pl.Date,
    "source": pl.Utf8,            # "tushare"
    "source_ticker": pl.Utf8,       # "000001.SZ"
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "pct_change": pl.Float64,
    "turnover": pl.Float64,    # 新增字段
    "is_suspended": pl.Boolean,    # 从 stock_status 合并
    "is_limit_up": pl.Boolean,     # 从 stock_limit 计算
    "is_limit_down": pl.Boolean,   # 从 stock_limit 计算
    "is_st": pl.Boolean,           # 从 stock_status 合并
    "up_limit": pl.Float64,        # 从 stock_limit 合并
    "down_limit": pl.Float64,      # 从 stock_limit 合并
}
```

### 4.3 数据增强规则

| Storage 字段 | 数据来源 | 计算规则 |
|-------------|----------|----------|
| `instrument_id` | InstrumentStore | `source_ticker` → 查找或分配 `instrument_id` |
| `source` | 配置 | 从 Source 名称获取 |
| `turnover` | 计算 | `amount / (close * volume * 100)` |
| `is_suspended` | stock_status | `suspend_timing IS NOT NULL` |
| `is_limit_up` | stock_limit | `close >= up_limit * 0.999` |
| `is_limit_down` | stock_limit | `close <= down_limit * 1.001` |
| `is_st` | stock_status | `st_type IS NOT NULL` |

---

## 六、数据集映射表

### 5.1 数据集映射总表

**表 5.1 - 数据集字段映射表**

| 最终数据集 | 数据集列 | Source 数据集 | Source 数据集列 |
|---------|---------|-------------|---------------|
| **stock_daily** | instrument_id (Int64) | stock_daily | source_ticker (String) → 查找/分配 instrument_id |
| | trade_date (Date) | stock_daily | trade_date (Date) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | source_ticker (Utf8) | stock_daily | source_ticker (String) |
| | open (Float64) | stock_daily | open (Float64) |
| | high (Float64) | stock_daily | high (Float64) |
| | low (Float64) | stock_daily | low (Float64) |
| | close (Float64) | stock_daily | close (Float64) |
| | pre_close (Float64) | stock_daily | pre_close (Float64) |
| | volume (Float64) | stock_daily | volume (Float64) |
| | amount (Float64) | stock_daily | amount (Float64) |
| | pct_change (Float64) | stock_daily | pct_change (Float64) |
| | turnover (Float64) | - | 计算：amount / (close × volume × 100) |
| | is_suspended (Boolean) | stock_status | is_suspended (Boolean) |
| | is_limit_up (Boolean) | stock_limit | 计算：close >= up_limit × 0.999 |
| | is_limit_down (Boolean) | stock_limit | 计算：close <= down_limit × 1.001 |
| | is_st (Boolean) | stock_status | is_st (Boolean) |
| | up_limit (Float64) | stock_limit | up_limit (Float64) |
| | down_limit (Float64) | stock_limit | down_limit (Float64) |
| **etf_daily** | instrument_id (Int64) | etf_daily | source_ticker (String) → 查找/分配 instrument_id |
| | trade_date (Date) | etf_daily | trade_date (Date) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | source_ticker (Utf8) | etf_daily | source_ticker (String) |
| | open/low/high/close (Float64) | etf_daily | 对应字段 (Float64) |
| | pre_close (Float64) | etf_daily | pre_close (Float64) |
| | volume/amount (Float64) | etf_daily | 对应字段 (Float64) |
| | pct_change (Float64) | etf_daily | pct_change (Float64) |
| **adj_factor** | instrument_id (Int64) | adj_factor | source_ticker (String) → 查找/分配 instrument_id |
| | trade_date (Date) | adj_factor | trade_date (Date) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | source_ticker (Utf8) | adj_factor | source_ticker (String) |
| | adj_factor (Float64) | adj_factor | adj_factor (Float64) |
| | knowledge_date (Date) | adj_factor | knowledge_date (Date) |
| **stock_status** | instrument_id (Int64) | stock_status | source_ticker (String) → 查找/分配 instrument_id |
| | trade_date (Date) | stock_status | trade_date (Date) |
| | is_suspended (Boolean) | stock_status | is_suspended (Boolean) |
| | suspend_timing (Utf8) | stock_status | suspend_timing (String) |
| | is_st (Boolean) | stock_status | is_st (Boolean) |
| | st_type (Utf8) | stock_status | st_type (String) |
| | list_status (Utf8) | stock_status | list_status (String) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | source_ticker (Utf8) | stock_status | source_ticker (String) |
| **instrument** | instrument_id (Int64) | instrument | 自动分配或查找 |
| | source_ticker (Utf8) | instrument | source_ticker (String) |
| | ticker (Utf8) | instrument | ticker (String) |
| | name (Utf8) | instrument | name (String) |
| | exchange (Utf8) | instrument | exchange (String) |
| | list_date (Date) | instrument | list_date (Date) |
| | delist_date (Date) | instrument | delist_date (Date) |
| | instrument_type (Utf8) | instrument | instrument_type (String) |
| **calendar** | trade_date (Date) | calendar | trade_date (Date) |
| | is_open (Boolean) | calendar | is_open (Boolean) |
| **index_daily** | instrument_id (Int64) | index_daily | source_ticker (String) → 查找/分配 instrument_id |
| | trade_date (Date) | index_daily | trade_date (Date) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | source_ticker (Utf8) | index_daily | ts_code (String) |
| | open/low/high/close (Float64) | index_daily | 对应字段 (Float64) |
| | pre_close (Float64) | index_daily | pre_close (Float64) |
| | change (Float64) | index_daily | change (Float64) |
| | pct_change (Float64) | index_daily | pct_chg (Float64) |
| | volume/amount (Float64) | index_daily | 对应字段 (Float64) |
| **index_member** | index_instrument_id (Int64) | index_member | index_code (String) → 查找/分配 instrument_id |
| | con_instrument_id (Int64) | index_member | con_code (String) → 查找/分配 instrument_id |
| | trade_date (Date) | index_member | trade_date (Date) |
| | weight (Float64) | index_member | weight (Float64) |
| | source (Utf8) | - | 硬编码 "tushare" |
| | index_code (Utf8) | index_member | index_code (String) |
| | con_code (Utf8) | index_member | con_code (String) |

**说明**：
- `instrument_id` 字段由 InstrumentStore 从 `source_ticker` 查找或自动分配（按 InstrumentIdRange 范围）
- `source_ticker` 字段保留原始数据源格式（如 "000001.SZ"）
- `source` 字段为硬编码的数据源标识
- PIT 相关字段（`knowledge_date`, `effective_from`, `effective_to`）直接保留
- 增强字段（如 `turnover`, `is_limit_up`）由计算或其他数据集合并得到

---

### 5.2 Tushare 适配表

**表 5.2 - Tushare API 适配过程表**

| Source 数据集 | 数据集列 | Tushare API | Tushare 字段 | 转换逻辑 |
|-------------|---------|------------|-------------|---------|
| **stock_daily** | source_ticker | daily | ts_code | 直接映射 |
| | trade_date | daily | trade_date | 直接映射 |
| | knowledge_date | - | - | 设置为 trade_date + 1 天 |
| | open | daily | open | 直接映射 |
| | high | daily | high | 直接映射 |
| | low | daily | low | 直接映射 |
| | close | daily | close | 直接映射 |
| | pre_close | daily | pre_close | 直接映射 |
| | volume | daily | vol | 重命名：vol → volume |
| | amount | daily | amount | 直接映射 |
| | pct_change | daily | pct_chg | 重命名：pct_chg → pct_change |
| **adj_factor** | source_ticker | adj_factor | ts_code | 直接映射 |
| | trade_date | adj_factor | trade_date | 直接映射 |
| | knowledge_date | - | - | 设置为 trade_date + 1 天 |
| | adj_factor | adj_factor | adj_factor | 直接映射 |
| **stock_status** | source_ticker | suspend_d | ts_code | 直接映射 |
| | trade_date | suspend_d | suspend_date | 重命名 |
| | suspend_timing | suspend_d | suspend_timing | 直接映射 |
| | is_suspended | suspend_d | - | 如果有 suspend_timing 则为 True |
| | source_ticker | stock_st | ts_code | 直接映射 |
| | is_st | stock_st | is_st | 直接映射（1/0 转布尔） |
| | st_type | stock_st | name | 直接映射 |
| | source_ticker | stock_basic | ts_code | 直接映射 |
| | list_status | stock_basic | list_status | 直接映射 |
| **stock_limit** | source_ticker | daily (limit) | ts_code | 从日线数据获取 |
| | trade_date | daily (limit) | trade_date | 直接映射 |
| | up_limit | daily (limit) | up_limit | 直接映射 |
| | down_limit | daily (limit) | down_limit | 直接映射 |
| **etf_daily** | source_ticker | fdc daily | ts_code | 直接映射 |
| | trade_date | fdc daily | trade_date | 直接映射 |
| | knowledge_date | - | - | 设置为 trade_date + 1 天 |
| | OHLCV | fdc daily | open/high/low/close | 直接映射 |
| | pre_close | fdc daily | pre_close | 直接映射 |
| | volume | fdc daily | vol | 重命名：vol → volume |
| | amount | fdc daily | amount | 直接映射 |
| | pct_change | fdc daily | pct_chg | 重命名：pct_chg → pct_change |
| **fund_adj** | source_ticker | fund_adj | ts_code | 直接映射 |
| | trade_date | fund_adj | trade_date | 直接映射 |
| | knowledge_date | - | - | 设置为 trade_date + 1 天 |
| | adj_factor | fund_adj | adj_factor | 直接映射 |
| **instrument** | instrument_id | stock_basic | ts_code | 直接映射 |
| | ticker | stock_basic | symbol | 重命名：symbol → ticker |
| | name | stock_basic | name | 直接映射 |
| | exchange | stock_basic | exchange | 直接映射 |
| | list_date | stock_basic | list_date | 直接映射 |
| | delist_date | stock_basic | delist_date | 直接映射 |
| | instrument_type | stock_basic | market | 重命名：market → instrument_type |
| **industry** | instrument_id | industry | ts_code | 直接映射 |
| | industry_name | industry | industry_name | 直接映射 |
| | industry_level | industry | industry_level | 直接映射 |
| | industry_date | industry | end_date | 重命名：end_date → industry_date |
| | knowledge_date | industry | - | 设置为 industry_date（公告日即已知） |
| **index_member** | index_id | index_memberweight | index_code | 直接映射 |
| | instrument_id | index_memberweight | con_code | 直接映射 |
| | weight | index_memberweight | weight | 直接映射 |
| | effective_from | index_memberweight | in_date | 生效开始日期 |
| | effective_to | index_memberweight | out_date | 生效结束日期（NULL = 当前仍在） |
| **calendar** | trade_date | trade_cal | cal_date | 重命名：cal_date → trade_date |
| | is_open | trade_cal | is_open | 直接映射（1/0 转布尔） |
| **index_daily** | source_ticker | index_daily | ts_code | 直接映射 |
| | trade_date | index_daily | trade_date | 直接映射 |
| | OHLCV | index_daily | open/high/low/close | 直接映射 |
| | pre_close | index_daily | pre_close | 直接映射 |
| | change | index_daily | change | 直接映射 |
| | pct_change | index_daily | pct_chg | 重命名：pct_chg → pct_change |
| | volume | index_daily | vol | 重命名：vol → volume |
| | amount | index_daily | amount | 直接映射 |

**Tushare API 命名规范**：
- `daily` - 股票日线行情
- `index_daily` - 指数日线行情
- `adj_factor` - 复权因子
- `suspend_d` - 停牌信息
- `stock_st` - ST股票信息
- `stock_basic` - 股票基本信息
- `fund_adj` - 基金复权因子
- `fdc` - 基金日线（ Funda Data Corner）
- `industry` - 行业分类
- `index_memberweight` - 指数成分权重
- `trade_cal` - 交易日历

---

## 七、数据集 Schema 定义

### 6.1 Market 域 Storage Schema

#### STOCK_DAILY_SCHEMA

```python
STOCK_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "source_ticker": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "pct_change": pl.Float64,
    "turnover": pl.Float64,
    "is_suspended": pl.Boolean,
    "is_limit_up": pl.Boolean,
    "is_limit_down": pl.Boolean,
    "is_st": pl.Boolean,
    "up_limit": pl.Float64,
    "down_limit": pl.Float64,
}
```

#### ETF_DAILY_SCHEMA

```python
ETF_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "source_ticker": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "pct_change": pl.Float64,
}
```

#### ADJ_FACTOR_SCHEMA

```python
ADJ_FACTOR_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "source_ticker": pl.Utf8,
    "adj_factor": pl.Float64,
    "knowledge_date": pl.Date,  # PIT 安全：T+1 发布
}
```

#### STOCK_STATUS_SCHEMA

```python
STOCK_STATUS_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "is_suspended": pl.Boolean,
    "suspend_timing": pl.Utf8,  # "09:30-10:00" or None
    "is_st": pl.Boolean,
    "st_type": pl.Utf8,
    "list_status": pl.Utf8,  # L=正常, D=退市, P=暂停
    "source": pl.Utf8,
    "source_ticker": pl.Utf8,
}
```

### 6.2 Metadata 域 Source Schema

#### INSTRUMENT_SOURCE_SCHEMA

```python
INSTRUMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="instrument",
    key_columns=("source_ticker",),
    schema={
        "source_ticker": pl.String,  # 数据源原始代码（如 "000001.SZ"）
        "ticker": pl.String,
        "name": pl.String,
        "exchange": pl.String,
        "list_date": pl.Date,
        "delist_date": pl.Date,
        "instrument_type": pl.String,
    },
)
```

#### INDUSTRY_SOURCE_SCHEMA

```python
INDUSTRY_SOURCE_SCHEMA = SourceSchema(
    dataset="industry",
    key_columns=("source_ticker", "industry_date"),
    schema={
        "source_ticker": pl.String,  # 数据源原始代码
        "industry_name": pl.String,
        "industry_level": pl.Int32,  # 1=一级行业, 2=二级行业
        "industry_date": pl.Date,
        "knowledge_date": pl.Date,
    },
)
```

### 6.3 Capital 域 Source Schema（部分示例）

#### BALANCE_SHEET_SOURCE_SCHEMA

```python
BALANCE_SHEET_SOURCE_SCHEMA = SourceSchema(
    dataset="balance_sheet",
    key_columns=("source_ticker", "report_date", "effective_from"),
    schema={
        "source_ticker": pl.String,  # 数据源原始代码
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "total_assets": pl.Float64,
        "total_liabilities": pl.Float64,
        "net_assets": pl.Float64,
        "current_assets": pl.Float64,
        "current_liabilities": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)
```

#### VALUATION_METRICS_SOURCE_SCHEMA

```python
VALUATION_METRICS_SOURCE_SCHEMA = SourceSchema(
    dataset="valuation_metrics",
    key_columns=("source_ticker", "trade_date", "effective_from"),
    schema={
        "source_ticker": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "pe_ratio": pl.Float64,
        "pb_ratio": pl.Float64,
        "ps_ratio": pl.Float64,
        "dividend_yield": pl.Float64,
        "market_cap": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)
```

---

## 七、Sources/Adapter 架构设计

### 7.1 架构原则

**职责分离**：
- **DataSource（接口）**：定义数据源抽象契约
- **Source 实现**：API 调用，返回原始格式（`src_code`）
- **Adapter**：字段映射 + 类型转换 + PIT 字段计算
- **Service**：`src_code` → `instrument_id` 分配 + 写入 Store

**数据流**：
```
Tushare API → TushareSource → Adapter → SourceSchema(src_code)
                                               ↓
                                    Service 写入时分配 instrument_id
                                               ↓
                                            StorageSchema(instrument_id)
```

### 7.2 目录结构

```
DataHub/sources/
├── base.py                    # DataSource 抽象基类
├── normalization.py           # Exchange/InstrumentType 枚举
├── source_schema.py           # SourceSchema 定义
│
├── tushare/
│   ├── tushare_source.py      # TushareSource（组合模式入口）
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py            # BaseTushareAdapter
│   │   ├── calendar.py        # CalendarTushareAdapter
│   │   ├── stock.py           # StockTushareAdapter
│   │   ├── etf.py             # ETFTushareAdapter
│   │   ├── capital.py         # CapitalTushareAdapter
│   │   └── industry.py        # IndustryTushareAdapter
│   ├── client.py              # TushareClient（HTTP 封装）
│   └── utils/
│       ├── http_utils.py
│       └── rate_limiter.py
│
├── tdx/
│   └── ...
│
└── schemas/
    ├── __init__.py
    ├── market_schemas.py      # Market SourceSchema 定义
    ├── metadata_schemas.py    # Metadata SourceSchema 定义
    └── capital_schemas.py     # Capital SourceSchema 定义
```

### 7.3 职责划分

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **DataSource (ABC)** | 接口契约定义 | - | - |
| **TushareSource** | 组合入口，委托给 Adapter | - | - |
| **BaseTushareAdapter** | 共享 Client 初始化 | settings, token | _client |
| **StockTushareAdapter** | API 调用 + 字段映射 | trade_date | SourceSchema |
| **TushareClient** | HTTP 封装 + 重试 + 限流 | api_name, params | raw dict |
| **SourceSchema** | 字段定义 + 验证 | - | - |

### 7.4 数据转换（在 Adapter 内完成）

**Adapter 内置转换逻辑**：

```python
# adapters/stock.py

class StockTushareAdapter(BaseTushareAdapter):
    """股票数据适配器"""

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        # 1. API 调用
        raw = self._client.query(api_name="daily", trade_date=trade_date)

        # 2. 转换为 DataFrame
        df = pl.DataFrame(raw)

        # 3. 字段映射（内置在 Adapter 内）
        df = df.rename({
            "ts_code": "src_code",
            "vol": "volume",
            "pct_chg": "pct_change",
        })

        # 4. 类型转换
        df = df.with_columns([
            pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
            pl.col("open").cast(pl.Float64),
            # ...
        ])

        # 5. 计算 PIT 字段
        df = df.with_columns(
            knowledge_date=pl.col("trade_date") + pl.duration(days=1)
        )

        # 6. 选择输出列
        df = df.select([
            "src_code", "trade_date", "knowledge_date",
            "open", "high", "low", "close", "pre_close",
            "volume", "amount", "pct_change",
        ])

        return df
```

### 7.5 instrument_id 分配（在 Service 层）

**Source 返回 `src_code`，Service 写入时分配 `instrument_id`**：

```python
# MarketService

def write_bars(self, df: pl.DataFrame) -> WriteResult:
    """写入 K线数据

    Args:
        df: Source 格式 DataFrame（包含 src_code 列）

    Returns:
        WriteResult
    """
    # 1. src_code → instrument_id 转换
    df = self._instrument_store.ensure_ids(df)

    # 2. 写入 Store
    return self._bars_store.write(df)
```

### 7.6 设计优势

| 优势 | 说明 |
|------|------|
| **单一职责** | Adapter 只做 API + 字段映射，Service 负责 ID 分配 |
| **可测试** | Adapter 可独立测试（不需要 InstrumentStore） |
| **可复用** | Source 输出格式稳定，Service 可灵活处理 |
| **类型安全** | SourceSchema 定义明确的字段契约 |

---

## 八、配置设计

### 8.1 配置架构原则

**统一使用 Pydantic Settings**：
- 类型安全（自动类型转换和验证）
- env 文件支持（原生支持）
- 文档即模型（模型即文档）
- FastAPI 生态标准

### 8.2 配置文件结构

```
config/
├── development/
│   ├── data_store.env      # Stores 配置
│   └── data_source.env     # Sources 配置
├── testing/
└── production/
```

### 8.3 data_store.env

```bash
# ========== 基础路径 ==========
DATA_ROOT=data
DATA_LOGS_ROOT=data/logs
DATA_BACKUP_ROOT=data/backups
DATA_TEMP_ROOT=data/temp
DATA_DB_ROOT=data/db

# ========== 元数据配置 ==========
METADATA_DB_ENABLED=true
METADATA_DB_PATH=data/db/metadata.sqlite

# ========== Parquet 存储配置 ==========
PARQUET_COMPRESSION=snappy
PARQUET_STATISTICS=true
PARQUET_ROW_GROUP_SIZE=100000

# ========== 分区配置 ==========
PARTITION_STRATEGY=yearly
PARTITION_YEARLY_ENABLED=true

# ========== 缓存配置 ==========
CALENDAR_CACHE_ENABLED=true
CALENDAR_CACHE_TTL=3600
INSTRUMENT_CACHE_ENABLED=true
INSTRUMENT_CACHE_TTL=1800

# ========== PIT 配置 ==========
PIT_ENABLED=true
PIT_DEFAULT_KNOWLEDGE_DELAY=1
```

### 8.3 data_source.env

```bash
# ========== Tushare 配置 ==========
TUSHARE_TOKEN=your_token_here
TUSHARE_BASE_URL=http://api.tushare.pro
TUSHARE_TIMEOUT=30.0

# ========== HTTP 配置 ==========
HTTP_TIMEOUT=30.0
HTTP_MAX_CONNECTIONS=100
HTTP_MAX_KEEPALIVE_CONNECTIONS=20

# ========== 重试配置 ==========
RETRY_MAX_ATTEMPTS=3
RETRY_MULTIPLIER=1.0
RETRY_MIN_WAIT=1.0
RETRY_MAX_WAIT=10.0
RETRY_JITTER_MAX=2.0

# ========== 限流配置 ==========
RATE_LIMIT_PROFILE=free
RATE_LIMIT_GLOBAL_RATE=1000
RATE_LIMIT_DAILY_RATE=5000

# ========== 通达信配置 ==========
TDX_ENABLED=false
TDX_PATH=D:\new_tdx\vipdoc
```

### 8.4 Settings 类

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class DataStoreSettings(BaseSettings):
    """Stores 配置"""
    model_config = SettingsConfigDict(
        env_prefix="DATA_",
        env_file="config/development/data_store.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root: Path = Path("data")
    logs_root: Path = Path("data/logs")
    backup_root: Path = Path("data/backups")
    db_root: Path = Path("data/db")

    # Parquet 配置
    parquet_compression: str = "snappy"
    parquet_statistics: bool = True

    # 分区配置
    partition_strategy: str = "yearly"

    # 缓存配置
    calendar_cache_enabled: bool = True
    calendar_cache_ttl: int = 3600

class DataSourceSettings(BaseSettings):
    """Sources 配置"""
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file="config/development/data_source.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Tushare 配置
    tushare_token: str = ""
    tushare_base_url: str = "http://api.tushare.pro"
    tushare_timeout: float = 30.0

    # HTTP 配置
    http_timeout: float = 30.0
    http_max_connections: int = 100

    # 重试配置
    retry_max_attempts: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 10.0

# 使用示例
store_settings = DataStoreSettings()  # 自动从环境变量和 .env 文件加载
source_settings = DataSourceSettings()
```

---

## 九、CQRS 模式（读写分离）

### 9.1 接口定义

```python
class IBarsReader(ABC):
    """K线数据读取接口"""

    @abstractmethod
    def get_bars(
        self,
        instrument_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """读取 K线数据，返回 DataFrame"""
        pass

    @abstractmethod
    def get_latest_date(self, instrument_id: int) -> date | None:
        """获取最新数据日期"""
        pass


class IBarsWriter(ABC):
    """K线数据写入接口"""

    @abstractmethod
    def write_bars(self, df: pl.DataFrame) -> int:
        """写入 K线数据，接收 DataFrame

        Args:
            df: DataFrame，应包含 BARS_SCHEMA 的所有列

        Returns:
            写入行数
        """
        pass

    @abstractmethod
    def delete_bars(
        self,
        instrument_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> int:
        """删除 K线数据，返回删除行数"""
        pass

    @abstractmethod
    def begin_transaction(self) -> "ITransaction":
        """开始事务（写入端特有）"""
        pass
```

### 9.2 实现示例

```python
class StockBarsReader(IBarsReader):
    def __init__(self, config: DataStoreSettings):
        self._config = config
        self._store = ParquetStore(config.root, YearlyPartition())

    def get_bars(
        self,
        instrument_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        return self._store.read(
            "market/stock/bars",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )

    def get_latest_date(self, instrument_id: int) -> date | None:
        df = self._store.read("market/stock/bars", instrument_ids=[instrument_id])
        if df.is_empty():
            return None
        return df["trade_date"].max()


class StockBarsWriter(IBarsWriter):
    def __init__(self, config: DataStoreSettings):
        self._config = config
        self._store = ParquetStore(config.root, YearlyPartition())

    def write_bars(self, df: pl.DataFrame) -> int:
        """写入 K线数据，支持跨年批次

        按年份分组后逐分区写入，避免跨年数据写入错误分区。
        """
        total_written = 0

        # 按年份分组
        for year, group_df in df.group_by(pl.col("trade_date").dt.year()):
            year_val = year[0]  # 提取年份值
            result = self._store.write("market/stock/bars", group_df, year=year_val)
            total_written += result.added + result.updated

        return total_written

    def delete_bars(
        self,
        instrument_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> int:
        return self._store.delete(
            "market/stock/bars",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )
```

---

## 十、DataHub 域服务设计

### 10.1 设计原则

**所有域都有 Service**，即使只是简单代理转发：

| 原则 | 说明 |
|------|------|
| **全覆盖** | Market、Metadata、Fundamental、Capital、Macro 都有 Service |
| **封装性** | Port 层只依赖 Service，不直接依赖 Stores |
| **可复用** | FactorService、StrategyService 都依赖 DataService |
| **可演进度** | 简单代理以后可添加缓存、聚合等逻辑 |
| **统一 API** | 查询：Query 对象 → DataFrame，写入：DataFrame → Result 对象 |

### 10.1.1 统一 API 模式

所有域 Service 遵循统一的查询/写入模式：

```python
# ========== 查询模式：Query 对象 → DataFrame ==========
@dataclass(frozen=True)
class BarsQuery:
    """K线查询参数（使用内部分配的整数 ID）"""
    instrument_ids: list[int]      # [1000001, 1000002] - 内部长整型 ID
    start_date: str | None = None   # "2024-01-01"
    end_date: str | None = None     # "2024-12-31"
    adj: Literal["none", "qfq", "hfq"] = "none"
    as_of: str | None = None        # PIT 查询日期

df = service.query(BarsQuery(instrument_ids=[1000001, 1000002]))

# ========== 写入模式：DataFrame → Result 对象 ==========
@dataclass
class WriteResult:
    """写入结果"""
    added: int
    updated: int
    failed: int

result = service.write(df)  # df 包含 instrument_id 列
```

**为什么使用 Query 对象？**

| 优势 | 说明 |
|------|------|
| **参数扩展友好** | 新增参数不影响现有调用 |
| **类型安全** | dataclass + 类型注解 |
| **文档清晰** | 单个类定义所有参数 |
| **可复用** | Query 对象可跨层传递 |

### 10.1.2 写入在 Service 内完成

**不再有 Port 层 DataWriteService**，所有写入操作在 DataHub 域服务内完成：

```python
# Port 层（简化）
@router.post("/ingest/bars")
async def ingest_bars(
    query: IngestQuery,
    service: MarketService = Depends(resolve(MarketService)),
) -> WriteResult:
    """数据摄入 API"""
    # 1. 从数据源获取数据
    source_df = source.fetch(query)

    # 2. 调用 Service 写入
    return service.write_bars(source_df, on_duplicate=query.strategy)

# DataHub Service 内部
class MarketService:
    def write_bars(
        self,
        df: pl.DataFrame,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> WriteResult:
        """写入 K线数据"""
        # 1. 数据增强和验证
        df = self._enrich(df)

        # 2. 调用 Store 写入
        return self._store.write(df, on_duplicate)
```

### 10.2 MarketService 组件拆分设计

**问题**：单一 Service 类承担过多职责（解析、读取、复权、增强），容易膨胀。

**解决方案**：保留门面 Service，但拆分为独立组件。

#### 组件架构

```
MarketService (门面/Facade)
    ├── QueryPlanner      # 查询规划（ticker 解析、资产类别检测）
    ├── DataReader        # 数据读取（委托给 Store）
    ├── EnrichmentService # 数据增强（状态、symbol）
    └── AdjustmentService # 复权计算（调用纯函数）
```

#### 组件职责

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **QueryPlanner** | 解析查询参数，生成执行计划 | MarketBarsQuery | ExecutionPlan |
| **DataReader** | 按计划读取数据 | ExecutionPlan | pl.DataFrame |
| **EnrichmentService** | 数据增强（状态、symbol） | DataFrame + Plan | DataFrame |
| **AdjustmentService** | 复权计算 | DataFrame + Plan | DataFrame |

#### 拆分后实现

```python
# 执行计划
@dataclass(frozen=True)
class ExecutionPlan:
    """查询执行计划"""
    instrument_ids: list[int]
    asset_class: Literal["stock", "etf", "index"]
    start_date: date | None
    end_date: date | None
    with_status: bool
    adj: AdjType
    asof: date | None

# 门面 Service
class MarketService:
    """Market 域统一服务（门面模式）"""

    def __init__(
        self,
        query_planner: QueryPlanner,
        data_reader: DataReader,
        enrichment: EnrichmentService,
        adjustment: AdjustmentService,
    ):
        self._planner = query_planner
        self._reader = data_reader
        self._enrichment = enrichment
        self._adjustment = adjustment

    def get_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        # 1. 解析查询
        plan = self._planner.plan(query)

        # 2. 读取数据
        df = self._reader.read(plan)

        if df.is_empty():
            return pl.DataFrame()

        # 3. 数据增强
        if not query.raw:
            df = self._enrichment.enrich(df, plan)

        # 4. 复权处理
        if not query.raw and query.adj != AdjType.NONE and plan.asset_class == "stock":
            df = self._adjustment.apply(df, plan)

        return df
```

### 10.3 Metadata 域服务示例

```python
@dataclass(frozen=True)
class InstrumentQuery:
    """证券查询参数"""
    instrument_ids: list[int] | None = None
    instrument_types: list[str] | None = None
    exchanges: list[str] | None = None


class MetadataService:
    """Metadata 域统一服务"""

    def query(self, query: InstrumentQuery) -> pl.DataFrame:
        """查询证券信息"""
        return self._instrument.read(
            instrument_ids=query.instrument_ids,
            instrument_types=query.instrument_types,
            exchanges=query.exchanges,
        )

    def write_instruments(
        self,
        df: pl.DataFrame,
        on_duplicate: str = "error",
    ) -> WriteResult:
        """写入证券信息"""
        return self._instrument.write(df, on_duplicate=on_duplicate)
```

### 10.4 Port 层使用

Port 层直接注入 DataHub 的 Service，使用 Query 对象：

```python
# apps/port/api/routes/market.py

from ditto_datahub.services.market import MarketService, BarsQuery

router = APIRouter(prefix="/api/v1/market")

@router.post("/bars/query")
async def query_bars(
    query: BarsQuery,
    service: MarketService = Depends(...),
) -> pl.DataFrame:
    """查询 K线数据 API（统一入口，支持多种查询方式）"""
    return service.query(query)


# ========== 使用示例 ==========

# 示例 1：精确查询（列表页，已有 instrument_id）
query1 = BarsQuery(
    instrument_ids=[1000001, 1000002],  # 内部长整型 ID
    start_date="2024-01-01",
    end_date="2024-12-31",
)

# 示例 2：裸 ticker 查询（搜索框，自动匹配所有交易所）
query2 = BarsQuery(
    tickers=["000001", "600000"],  # 用户输入的 ticker
    start_date="2024-01-01",
    end_date="2024-12-31",
)

# 示例 3：ticker + 交易所过滤（搜索框，用户选择交易所）
query3 = BarsQuery(
    tickers=["000001"],           # 用户输入的 ticker
    exchanges=["SSE", "SZSE"],  # 用户选择的交易所
    start_date="2024-01-01",
    end_date="2024-12-31",
)
```

### 10.5 后续扩展

Features/Factors 域依赖基础域的 Service：

```python
# datahub/services/factors/factor_service.py

class FactorService:
    """因子计算服务"""

    def __init__(
        self,
        market_service: MarketService,
        fundamental_service: FundamentalService,
    ):
        self._market = market_service
        self._fundamental = fundamental_service

    def calculate_momentum(
        self,
        query: FactorQuery,
    ) -> pl.DataFrame:
        """计算动量因子"""
        # 调用基础域 Service
        bars = self._market.query(
            BarsQuery(
                tickers=query.tickers,          # 使用 ticker 查询
                start_date=query.start_date,
                end_date=query.end_date,
            )
        )
        # 因子计算逻辑...
        return factors
```

## 十一、Port 层设计（轻量级）

### 11.1 职责

Port 层职责简化为：
1. **API 适配**：HTTP → 内部调用
2. **参数转换**：Pydantic Model → Query 对象
3. **响应转换**：DataFrame → Response Contract
4. **依赖注入**：管理 Service 容器（使用当前项目 `port/registry`）

### 11.2 API Response Contract 规范

**原则**：API 层固定使用 Pydantic/Arrow/Parquet response contract，DataFrame 仅留在内部。

#### Response 类型选择

| 场景 | Response 类型 | 说明 |
|------|---------------|------|
| **查询 API** | `list[Pydantic Model]` | 清晰、易用、FastAPI 集成 |
| **批量导出** | `Parquet` 文件 | 高效、兼容性好 |
| **大数据传输** | `Arrow IPC` | 流式、高性能 |

#### Pydantic Response 示例（推荐）

```python
# apps/port/api/models.py

class BarResponse(BaseModel):
    """单条 K线响应（API 层）"""
    instrument_id: int
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float

    class Config:
        # 支持 DataFrame → Pydantic 转换
        from_attributes = True

# apps/port/api/routes/market.py

@router.get("/bars", response_model=list[BarResponse])
async def get_bars(
    query: BarsQueryRequest,
    service: MarketService = Depends(...),
) -> list[BarResponse]:
    """查询 K线数据 API"""
    # 1. API 请求 → 内部 Query
    internal_query = BarsQuery(
        instrument_ids=query.instrument_ids,
        start_date=query.start_date,
        end_date=query.end_date,
        adj=query.adj,
    )

    # 2. 调用 Service（返回 DataFrame）
    df = service.get_bars(internal_query)

    # 3. DataFrame → Pydantic Response
    return df.to_dicts()  # FastAPI 自动转为 list[BarResponse]
```

#### Parquet Export 示例

```python
@router.post("/bars/export")
async def export_bars(
    query: BarsQueryRequest,
    service: MarketService = Depends(...),
) -> Response:
    """导出 K线数据为 Parquet"""
    df = service.get_bars(query.to_internal())

    stream = io.BytesIO()
    df.write_parquet(stream, compression="snappy")

    return Response(
        content=stream.getvalue(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=bars.parquet"},
    )
```

### 11.2 API 路由使用（dishka 集成）

使用 dishka 提供的依赖注入，通过 `Depends` 自动注入 Service：

```python
# apps/port/api/routes/market.py

from fastapi import APIRouter, Depends
from ditto_datahub.services.market import MarketService, MarketBarsQuery
from ditto_port.registry import get_market_service

router = APIRouter(prefix="/api/v1/market")

@router.post("/bars/query", response_model=list[BarResponse])
async def query_bars(
    query: BarsQueryRequest,
    service: MarketService = Depends(get_market_service),
) -> list[BarResponse]:
    """查询 K线数据 API（统一入口，支持多种查询方式）"""
    df = service.query(query.to_internal())
    return df.to_dicts()  # FastAPI 自动转为 list[BarResponse]

@router.post("/bars/export")
async def export_bars(
    query: BarsQueryRequest,
    service: MarketService = Depends(get_market_service),
) -> Response:
    """导出 K线数据为 Parquet"""
    df = service.query(query.to_internal())

    stream = io.BytesIO()
    df.write_parquet(stream, compression="snappy")

    return Response(
        content=stream.getvalue(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=bars.parquet"},
    )
```

---

## 十二、DataHub 模型层

### 12.1 设计原则

**DataHub 模型层**是所有共享模型定义的中心，负责定义跨层共享的数据结构：

1. **数据密集型用 Schema** - Bar/Quote 等，DataFrame 传输
2. **逻辑密集型用 dataclass** - Order/Position 等，对象传输
3. **集中管理** - 所有模型定义在 DataHub 层
4. **类型安全** - Schema 提供类型约束，dataclass 提供业务规则

### 12.2 目录结构

```
packages/datahub/src/ditto_datahub/
├── models/                # 模型层（新增）
│   ├── __init__.py
│   │
│   ├── market/            # 市场数据（Schema）
│   │   ├── __init__.py
│   │   ├── bar.py         # BAR_SCHEMA
│   │   ├── quote.py       # QUOTE_SCHEMA
│   │   └── fundamental.py # FUNDAMENTAL_SCHEMA
│   │
│   ├── trading/           # 交易数据（模型）
│   │   ├── __init__.py
│   │   ├── order.py       # Order (dataclass)
│   │   ├── trade.py       # Trade (dataclass)
│   │   └── position.py    # Position (dataclass)
│   │
│   ├── portfolio/         # 组合数据（模型）
│   │   ├── __init__.py
│   │   ├── portfolio.py   # Portfolio (dataclass)
│   │   └── account.py     # Account (dataclass)
│   │
│   └── strategy/          # 策略数据（模型）
│       ├── __init__.py
│       ├── signal.py      # Signal (dataclass)
│       └── state.py       # MarketState (dataclass)
│
├── sources/               # 数据源
├── stores/                # 数据存储
├── services/              # 域服务
└── meta/                  # 元数据
```

### 12.3 Schema 定义示例（市场数据）

```python
# packages/datahub/src/ditto_datahub/models/market/bar.py

"""K线数据 Schema 定义"""

import polars as pl

# 标准 K线 Schema
BAR_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}

# 增强 K线 Schema（含涨跌幅）
BAR_ENRICHED_SCHEMA = {
    **BAR_SCHEMA,
    "pct_change": pl.Float64,
    "turnover": pl.Float64,
}
```

### 12.4 模型定义示例（交易数据）

```python
# packages/datahub/src/ditto_datahub/models/trading/order.py

"""订单模型定义"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Order:
    """订单模型（业务逻辑型）

    使用场景：
    - 状态管理（pending → filled）
    - 业务规则验证（quantity > 0）
    - 方法封装（is_fully_filled()）
    """
    order_id: str
    instrument_id: int
    side: OrderSide
    quantity: int
    price: float | None      # None = 市价单
    status: OrderStatus
    created_at: datetime
    filled_at: datetime | None = None
    filled_quantity: int = 0
    filled_price: float | None = None

    def is_fully_filled(self) -> bool:
        """是否完全成交"""
        return (
            self.status == OrderStatus.FILLED
            and self.filled_quantity == self.quantity
        )

    def is_market_order(self) -> bool:
        """是否市价单"""
        return self.price is None
```

### 12.5 模型定义示例（组合数据）

```python
# packages/datahub/src/ditto_datahub/models/portfolio/position.py

"""持仓模型定义"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Position:
    """持仓模型（业务逻辑型）

    使用场景：
    - 聚合计算（从 Trade 计算持仓）
    - 业务规则（不能为负）
    - 盈亏计算（unrealized_pnl）
    """
    instrument_id: int
    quantity: int           # 可正（多头）可负（空头）
    avg_price: Decimal      # 平均成本价
    market_price: Decimal   # 当前市价
    market_value: Decimal   # 市值
    unrealized_pnl: Decimal # 浮动盈亏

    @classmethod
    def from_trades(cls, trades: list[Trade]) -> "Position":
        """从成交记录计算持仓"""
        ...

    def is_long(self) -> bool:
        """是否多头持仓"""
        return self.quantity > 0

    def is_short(self) -> bool:
        """是否空头持仓"""
        return self.quantity < 0
```

### 12.6 数据流向

#### Bar 的流向（DataFrame）
```
DataHub Source ──→ pl.DataFrame (符合 BAR_SCHEMA)
                        │
                        ▼
                Port 验证 Schema
                        │
                        ▼
                Core Engine (直接用 DataFrame 计算)
```

#### Order 的流向（dataclass）
```
Core Strategy ──→ Order (dataclass，来自 DataHub 模型)
                    │
                    ▼
            Port 验证/转换
                    │
                    ▼
            DataHub OrderStore.save(Order)
```

### 12.7 依赖关系

```
     Port
      ↓
   DataHub Models ← 模型定义中心
      ↑
    Core
```

**说明**：
- **Port 层**：可使用 DataHub 的所有内容（模型、Service、Store）
- **Core 层**：仅使用 DataHub 的模型定义（dataclass/Schema）
- **DataHub 层**：包含模型定义、数据源、存储、服务等

---

## 十三、目录结构

```
ditto/
├── packages/
│   ├── core/                          # Core Layer（业务逻辑层）
│   │   └── src/ditto_core/
│   │       ├── engine/                # 引擎模块
│   │       │   ├── backtest/          # 回测引擎
│   │       │   ├── factor/            # 因子引擎
│   │       │   ├── risk/              # 风险引擎
│   │       │   └── regime/            # 市场状态识别
│   │       │
│   │       ├── portfolio/             # 组合管理模块
│   │       │   ├── manager.py         # PortfolioManager
│   │       │   ├── builder.py         # PortfolioBuilder
│   │       │   └── position.py        # Position 计算逻辑
│   │       │
│   │       ├── strategy/              # 策略模块
│   │       │   ├── base.py            # Strategy 抽象基类
│   │       │   ├── signal/            # 信号生成
│   │       │   └── execution/         # 订单执行
│   │       │
│   │       └── quality/               # 数据质量模块
│   │           ├── checkers/          # DQ 检查器
│   │           ├── engine.py          # QualityEngine
│   │           └── spec.py            # DQ 配置
│   │
│   ├── datahub/                       # DataHub Layer（数据访问层）
│   │   └── src/ditto_datahub/
│   │       ├── config/                # 配置
│   │       │   ├── data_root.py       # DataRootConfig
│   │       │   └── data_source.py     # DataSourceSettings
│   │       │
│   │       ├── models/                # 模型定义（Schema + dataclass）
│   │       │   ├── market/            # 市场数据模型
│   │       │   │   ├── bar.py         # BAR_SCHEMA
│   │       │   │   ├── quote.py       # QUOTE_SCHEMA
│   │       │   │   └── fundamental.py # FUNDAMENTAL_SCHEMA
│   │       │   ├── trading/           # 交易数据模型
│   │       │   │   ├── order.py       # Order (dataclass)
│   │       │   │   ├── trade.py       # Trade (dataclass)
│   │       │   │   └── position.py    # Position (dataclass)
│   │       │   ├── portfolio/         # 组合数据模型
│   │       │   │   ├── portfolio.py   # Portfolio (dataclass)
│   │       │   │   └── account.py     # Account (dataclass)
│   │       │   └── strategy/          # 策略数据模型
│   │       │       ├── signal.py      # Signal (dataclass)
│   │       │       └── state.py       # MarketState (dataclass)
│   │       │
│   │       ├── sources/               # 数据源
│   │       │   ├── base.py            # DataSource ABC
│   │       │   ├── source_schema.py   # SourceSchema
│   │       │   ├── schemas/           # SourceSchema 定义
│   │       │   │   ├── market_schemas.py
│   │       │   │   ├── metadata_schemas.py
│   │       │   │   └── capital_schemas.py
│   │       │   └── tushare/           # Tushare 实现
│   │       │
│   │       ├── stores/                # 数据存储
│   │       │   ├── market/            # 市场数据存储
│   │       │   │   ├── stock/bars.py
│   │       │   │   ├── etf/bars.py
│   │       │   │   └── index/bars.py
│   │       │   ├── metadata/          # 元数据存储
│   │       │   │   ├── instrument.py
│   │       │   │   └── calendar.py
│   │       │   ├── fundamental/       # 财务数据存储
│   │       │   ├── capital/           # 资本数据存储
│   │       │   └── base/              # 基础存储类
│   │       │
│   │       ├── services/              # 域服务
│   │       │   ├── market/            # MarketService
│   │       │   ├── metadata/          # MetadataService
│   │       │   ├── fundamental/       # FundamentalService
│   │       │   ├── capital/           # CapitalService
│   │       │   └── macro/             # MacroService
│   │       │
│   │       ├── runtime/               # 运行时
│   │       │   ├── sid_allocator.py   # ID 分配器
│   │       │   ├── freeze_manager.py  # 冻结管理器
│   │       │   └── ingestion/         # 摄入日志
│   │
│   └── foundation/                    # Foundation Layer（基础设施层）
│       └── src/ditto_foundation/
│           ├── config/                # 配置加载
│           ├── logger/                # 日志（loguru）
│           └── cache/                 # 缓存（cachebox）
│
├── apps/
│   └── port/                          # Application Layer（应用层）
│       └── src/ditto_port/
│           ├── registry/              # DI 容器（dishka Provider）
│           │   ├── __init__.py        # make_container()
│           │   ├── config.py          # ConfigProvider
│           │   ├── core.py            # CoreProvider
│           │   ├── domain.py          # DomainServiceProvider
│           │   ├── datahub.py         # DataHubProvider
│           │   └── sources.py         # DataSourcesProvider
│           ├── api/
│           │   ├── models.py          # Pydantic API 模型（请求/响应）
│           │   └── routes/            # FastAPI 路由
│           │       ├── market.py
│           │       ├── metadata.py
│           │       ├── portfolio.py     # 组合/订单 API
│           │       └── ingestion.py
│           └── config/                # Port 层配置加载器
│
└── config/
    ├── development/
    │   ├── data_store.env
    │   └── data_source.env
    ├── testing/
    └── production/
```

### 13.1 设计说明

| 组件 | 职责 | 说明 |
|------|------|------|
| **datahub/models/** | 共享模型 | 定义 Schema（数据密集型）+ 模型（逻辑密集型） |
| **core/** | 业务逻辑 | 依赖 DataHub 模型，实现回测、组合、策略等业务逻辑 |
| **datahub/stores/** | 数据存储 | 使用 models 定义的 Schema，返回符合 Schema 的 DataFrame |
| **datahub/services/** | 域服务 | 组合 Store 操作，提供统一查询接口 |
| **datahub/runtime/** | 运行时服务 | ID 分配器、冻结管理、DQ 检查 |
| **datahub/sources/** | 数据源 | 返回符合 models 定义的 Schema 的 DataFrame |
| **port/api/** | API 边界 | Pydantic 模型，负责 DataFrame ↔ Model 转换 |
| **datahub/meta/** | 元数据 | Storage Schema 定义 |

**Service 设计原则**：
- **全覆盖**：所有域都有对应的 Service（即使是简单代理）
- **封装性**：Port 层只依赖 Service，不直接依赖 Stores
- **统一入口**：单一 `query()` 方法支持多种查询方式
- **智能解析**：Service 内部自动转换 ticker → instrument_id
- **可演进度**：Service 内部可添加缓存、聚合等逻辑

**查询方式对比**：

| 层级 | 查询参数 | 说明 | 示例 |
|------|----------|------|------|
| **API 层** | `BarsQuery` | 支持三种模式，用户友好 | `{instrument_ids: [1000001]}` 或 `{tickers: ["000001"]}` |
| **Service 层** | `query(BarsQuery)` | 统一入口，内部解析 | 调用 `_resolve_instrument_ids()` 转换 |
| **Store 层** | `instrument_ids: list[int]` | 只接收整数 ID，高效 | `[1000001, 1000002]` |

**移除的设计**：
- ~~domains/~~ - 与 stores/ 重复
- ~~core/~~ - 复权作为纯函数移至 services/

---

## 十四、PIT（Point-in-Time）设计

### 14.1 PIT Policy 配置

每个数据集声明独立的 PITPolicy，避免使用通用 helper 猜测。

```python
@dataclass(frozen=True)
class PITPolicy:
    """Point-in-Time 策略配置"""
    primary_key: tuple[str, ...]      # 主键列
    version_column: str                # 版本列（knowledge_date 或 effective_from）
    interval_type: Literal["point", "interval"]  # 单点或区间
    interval_end: str | None = None    # 区间结束列（effective_to）
    dedup_strategy: Literal["keep_last", "interval_check"] = "keep_last"
```

### 14.2 预定义 PIT 策略

| 数据集 | primary_key | version_column | interval_type | interval_end | dedup_strategy |
|--------|-------------|----------------|---------------|--------------|-----------------|
| stock_daily | (instrument_id, trade_date) | knowledge_date | point | - | keep_last |
| adj_factor | (instrument_id, trade_date) | knowledge_date | point | - | keep_last |
| index_member | (index_id, con_id, effective_from) | effective_from | interval | effective_to | interval_check |
| balance_sheet | (instrument_id, report_date, effective_from) | effective_from | interval | effective_to | interval_check |
| valuation_metrics | (instrument_id, trade_date, effective_from) | effective_from | interval | effective_to | interval_check |

**代码定义**：
```python
# 预定义策略
PIT_POLICIES: dict[str, PITPolicy] = {
    "stock_daily": PITPolicy(
        primary_key=("instrument_id", "trade_date"),
        version_column="knowledge_date",
        interval_type="point",
        dedup_strategy="keep_last",
    ),
    "adj_factor": PITPolicy(
        primary_key=("instrument_id", "trade_date"),
        version_column="knowledge_date",
        interval_type="point",
        dedup_strategy="keep_last",
    ),
    "index_member": PITPolicy(
        primary_key=("index_id", "con_id", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
    ),
    "balance_sheet": PITPolicy(
        primary_key=("instrument_id", "report_date", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
    ),
}
```

### 14.3 PIT 数据集

| 数据集 | PIT 列 | knowledge_date 语义 |
|--------|--------|-------------------|
| stock_daily | knowledge_date | T+1（次日开盘前可知） |
| adj_factor | knowledge_date | T+1（次日开盘前可知） |
| balance_sheet | effective_from/to | 公告日期 + 1 |
| valuation_metrics | effective_from/to | T+1 |
| industry | knowledge_date | 公告日期 |

### 14.3 PIT 查询模式

```python
# 查询某个时间点已知的数据
def get_bars_as_of(
    instrument_ids: list[int],
    start_date: date,
    end_date: date,
    as_of: date,  # 时间点
) -> pl.DataFrame:
    df = reader.get_bars(instrument_ids, start_date, end_date)

    # 过滤：knowledge_date <= as_of
    df = df.filter(pl.col("knowledge_date") <= as_of)

    # 去重：每个 (instrument_id, trade_date) 保留最新记录
    df = df.sort("knowledge_date").unique(
        subset=["instrument_id", "trade_date"],
        keep="last",
    )

    return df
```

### 14.4 Universe 域设计（股票池）

Universe 域管理股票池成分数据，支持动态权重和 PIT 查询。

**数据集**：`universe`

**Schema**：
```python
UNIVERSE_CONSTITUENT_SCHEMA = {
    "universe_id": pl.String,      # 股票池标识（如 "csi500", "my_custom_pool"）
    "instrument_id": pl.Int64,     # 成分证券 ID
    "effective_from": pl.Date,     # 生效起始日期
    "effective_to": pl.Date,       # 生效结束日期（NULL = 当前有效）
    "weight": pl.Float64,          # 权重（可选，用于加权计算）
    "reason": pl.String,           # 加入/移除原因（可选）
}
```

**PIT 查询**：
```python
# 获取某个时间点的股票池成分
def get_universe_as_of(
    universe_id: str,
    as_of: date,
) -> pl.DataFrame:
    df = universe_store.read(universe_id=universe_id)

    # PIT 过滤：effective_from <= as_of AND (effective_to IS NULL OR effective_to > as_of)
    df = df.filter(
        (pl.col("effective_from") <= as_of) &
        (pl.col("effective_to").is_null() | (pl.col("effective_to") > as_of))
    )

    return df
```

**应用场景**：
- 指数增强：在基准指数基础上调整成分股权重
- 自定义股票池：动态管理策略选股范围
- 回测：获取历史时点的有效成分股

### 14.5 Features 和 Factors 域（衍生模块）

Features 和 Factors 是**数据衍生模块**，基于 Market/Fundamental/Capital/Metadata 域的原始数据进行计算。

#### Features 域（技术指标）

**职责**：计算各类技术指标

**示例指标**：
- 趋势类：MA、EMA、MACD
- 动量类：RSI、KDJ、CCI
- 波动性：ATR、Bollinger Bands
- 成交量：OBV、Volume MA

**存储格式**：窄表模式（Wide Table → Narrow）
```
instrument_id | trade_date | indicator_id | value
--------------|------------|--------------|------
1000001       | 2024-01-15 | ma_5         | 10.5
1000001       | 2024-01-15 | ma_10        | 10.3
1000001       | 2024-01-15 | rsi_14       | 65.2
```

#### Factors 域（因子数据）

**职责**：存储和管理因子数据，支持因子挖掘和回测

**因子分类**：
- **Fundamental Factors**：PE、PB、ROE、ROA
- **Technical Factors**：动量、反转、波动率
- **Macro Factors**：宏观经济指标
- **Statistical Factors**：统计套利因子

**存储格式**：
```
instrument_id | trade_date | factor_id | factor_class | factor_family | exposure | raw_value | effective_from | effective_to
--------------|------------|-----------|--------------|---------------|----------|-----------|----------------|---------------
1000001       | 2024-01-15 | momentum  | technical    | momentum      | 0.85     | 0.15      | 2024-01-16     | NULL
```

**PIT 支持**：因子数据支持 Point-in-Time 查询，可追溯历史因子值。

**后续设计**：Features 和 Factors 域的详细设计将在单独的文档中说明。

---

## 十五、复权计算（Services）

### 15.1 纯函数设计

复权计算使用纯函数实现，无状态、无类、可组合：

```python
# packages/datahub/src/ditto_datahub/services/adjustment.py

"""复权计算服务（纯函数）"""

import polars as pl
from datetime import date


def apply_qfq(
    df: pl.DataFrame,
    adj_factors: pl.DataFrame,
    as_of: date | None = None,
) -> pl.DataFrame:
    """前复权计算（QFQ）

    Args:
        df: K线数据，需包含 instrument_id, trade_date, OHLCV 字段
        adj_factors: 复权因子，需包含 instrument_id, trade_date, adj_factor, knowledge_date
        as_of: 时间点，过滤 knowledge_date <= as_of 的因子

    Returns:
        复权后的 DataFrame

    公式：adj_price = orig_price × cur_factor / latest_factor
    """
    # 1. PIT 过滤
    if as_of is not None:
        adj_factors = adj_factors.filter(
            pl.col("knowledge_date") <= as_of
        )

    # 2. 获取每个 instrument_id 的最新因子
    latest_factors = adj_factors.group_by("instrument_id").agg(
        pl.col("adj_factor").last().alias("latest_factor")
    )

    # 3. 合并因子
    df = df.join(
        adj_factors.select("instrument_id", "trade_date", "adj_factor"),
        on=["instrument_id", "trade_date"],
        how="left",
    )
    df = df.join(latest_factors, on="instrument_id", how="left")

    # 4. 应用 QFQ 公式
    price_cols = ["open", "high", "low", "close", "pre_close"]
    result = df.with_columns([
        (pl.col(col) * pl.col("adj_factor") / pl.col("latest_factor")).alias(col)
        for col in price_cols
    ]).drop(["adj_factor", "latest_factor"])

    return result


def apply_hfq(
    df: pl.DataFrame,
    adj_factors: pl.DataFrame,
    as_of: date | None = None,
) -> pl.DataFrame:
    """后复权计算（HFQ）

    Args:
        df: K线数据
        adj_factors: 复权因子
        as_of: 时间点

    Returns:
        复权后的 DataFrame

    公式：adj_price = orig_price × cur_factor
    """
    # 1. PIT 过滤
    if as_of is not None:
        adj_factors = adj_factors.filter(
            pl.col("knowledge_date") <= as_of
        )

    # 2. 合并因子
    df = df.join(
        adj_factors.select("instrument_id", "trade_date", "adj_factor"),
        on=["instrument_id", "trade_date"],
        how="left",
    )

    # 3. 应用 HFQ 公式
    price_cols = ["open", "high", "low", "close", "pre_close"]
    result = df.with_columns([
        (pl.col(col) * pl.col("adj_factor")).alias(col)
        for col in price_cols
    ]).drop("adj_factor")

    return result
```

### 15.2 使用示例

```python
from ditto_datahub.services.adjustment import apply_qfq
from ditto_datahub.services.pit import filter_as_of

# 1. 读取原始数据和因子
bars = stock_bars_reader.get_bars(instrument_ids=[1000001, 1000002], start_date=..., end_date=...)
adj_factors = adj_reader.get_factors(instrument_ids=[1000001, 1000002], start_date=..., end_date=...)

# 2. 应用前复权（带 PIT 过滤）
as_of_date = date(2024, 1, 15)
bars_qfq = apply_qfq(bars, adj_factors, as_of=as_of_date)
```

### 15.3 PIT 辅助函数

```python
# packages/datahub/src/ditto_datahub/services/pit.py

"""PIT（Point-in-Time）辅助函数"""

import polars as pl
from datetime import date


def filter_as_of(
    df: pl.DataFrame,
    as_of: date,
    policy: PITPolicy,
) -> pl.DataFrame:
    """过滤时间点已知的数据（使用 PITPolicy）

    Args:
        df: 包含 PIT 列的 DataFrame
        as_of: 时间点
        policy: PIT 策略配置

    Returns:
        过滤后的 DataFrame，保留最新记录
    """
    # 1. 过滤：version_column <= as_of
    df = df.filter(pl.col(policy.version_column) <= as_of)

    # 2. 去重：保留最新记录
    if policy.dedup_strategy == "keep_last":
        df = df.sort(policy.version_column).unique(
            subset=policy.primary_key,
            keep="last",
        )
    elif policy.dedup_strategy == "interval_check":
        # 区间类型：过滤出 as_of 时间点有效的记录
        if policy.interval_type == "interval" and policy.interval_end:
            df = df.filter(
                (pl.col(policy.interval_end) > as_of) |
                (pl.col(policy.interval_end).is_null())
            )

    return df
```

---

## 十六、依赖注入（dishka）

### 16.1 架构原则

**使用 dishka 库**：基于 Provider 模式的依赖注入，在 Port 层做唯一 root 注入。

**分层 Provider**：
- `ConfigProvider`：配置提供者（Composition Root）
- `CoreProvider`：Core 层组件（DQ 引擎等）
- `DomainServiceProvider`：封装所有 DataHub Store 的创建
- `DataHubProvider`：组合 Domain Services
- `DataSourcesProvider`：外部数据源组件

**应用级单例**：使用 `Scope.APP` 和 `Iterator` 管理生命周期。

### 16.2 Provider 结构

```python
# apps/port/src/ditto_port/registry/__init__.py

"""
Composition Root - 统一入口。

使用 make_container() 创建所有 Provider 的组合容器，
这是 Port 层唯一的 DI 容器入口。
"""

from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, make_container
from fastapi import FastAPI
from fastapi.dependencies.utils import get_typed_signature

from ditto_port.registry.config import ConfigProvider
from ditto_port.registry.core import CoreProvider
from ditto_port.registry.domain import DomainServiceProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.sources import DataSourcesProvider

__all__ = ["make_container", "inject_into_fastapi"]


def make_container() -> Iterator[object]:
    """
    创建完整的 DI 容器（Composition Root）.

    组合所有 Provider，返回一个完整的容器实例。
    这是 Port 层唯一的 DI 容器入口。
    """
    return make_container(
        ConfigProvider(),
        CoreProvider(),
        DomainServiceProvider(),
        DataSourcesProvider(),
        DataHubProvider(),
    )
```

### 16.3 ConfigProvider（配置提供者）

```python
# apps/port/src/ditto_port/registry/config.py

"""配置 Provider（Composition Root）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config import DataRootConfig, DataSourceSettings
from ditto_foundation.config import ConfigLoader, Environment

__all__ = ["ConfigProvider"]


class ConfigProvider(Provider):
    """统一配置提供者（仅在 Port 层加载配置）。"""

    scope = Scope.APP

    @provide
    def environment(self) -> Environment:
        """提供运行环境枚举。"""
        import os
        env_str = os.getenv("ENVIRONMENT", "development")
        return Environment.from_str(env_str)

    @provide
    def config_loader(self, environment: Environment) -> ConfigLoader:
        """提供配置文件加载器。"""
        return ConfigLoader(environment)

    @provide
    def data_root_config(self, config_loader: ConfigLoader) -> DataRootConfig:
        """加载数据根目录配置。"""
        from ditto_port.config import load_env_file
        data_store_values = load_env_file(config_loader, "data_store")
        return DataRootConfig.model_validate(data_store_values)

    @provide
    def data_root(self, data_root_config: DataRootConfig) -> Path:
        """提供数据根目录路径。"""
        return data_root_config.data_root

    @provide
    def data_source_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DataSourceSettings:
        """加载数据源配置。"""
        from ditto_port.config import load_env_file
        data_source_values = load_env_file(config_loader, "data_source")
        return DataSourceSettings.model_validate(data_source_values)
```

### 16.4 DomainServiceProvider（Store 提供者）

```python
# apps/port/src/ditto_port/registry/domain.py

"""
Domain Store Provider - 封装所有 Store 的导入和创建.

将所有 DataHub Store 类的导入和创建逻辑封装在此 Provider 中，
避免 DataHubProvider 直接依赖具体的 Store 类。
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.stores.market.stock.bars import StockBarsStore
from ditto_datahub.stores.market.stock.status import StockStatusStore
from ditto_datahub.stores.market.stock.adj import StockAdjFactorStore
from ditto_datahub.stores.metadata.instrument import InstrumentStore

__all__ = ["DomainServiceProvider"]


class DomainServiceProvider(Provider):
    """
    Domain Store Provider - 封装所有 Store 的创建.

    职责：
    - 导入所有 DataHub Store 类（封装在此文件中）
    - 提供 Store 实例的创建方法
    - 通过 dishka 容器管理依赖注入
    """

    scope = Scope.APP

    @provide
    def instrument_store(self, sqlite_client: SQLiteClient) -> InstrumentStore:
        """证券数据存储."""
        return InstrumentStore(sqlite_client)

    @provide
    def stock_bars_store(self, config: DataRootConfig) -> StockBarsStore:
        """股票 K线存储."""
        return StockBarsStore(config.data_root)

    @provide
    def stock_status_store(self, config: DataRootConfig) -> StockStatusStore:
        """股票状态存储."""
        return StockStatusStore(config.data_root)

    @provide
    def stock_adj_store(self, config: DataRootConfig) -> StockAdjFactorStore:
        """股票复权因子存储."""
        return StockAdjFactorStore(config.data_root)

    # ... 其他 Store
```

### 16.5 DataHubProvider（Service 组合）

```python
# apps/port/src/ditto_port/registry/datahub.py

"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.

架构说明：
- Store 的导入和创建已移至 DomainServiceProvider
- DataHubProvider 只负责组合 Domain Services
- Port 层不再直接依赖 Store 类
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from dishka import Provider, Scope, provide

if TYPE_CHECKING:
    from ditto_datahub.services.market import MarketService
    from ditto_datahub.services.metadata import MetadataService
    from ditto_datahub import DataHub

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """
    DataHub 组件 Provider.

    架构说明：
    - Store 的创建由 DomainServiceProvider 负责
    - 此 Provider 只负责组合 Domain Services
    - Store 依赖通过 dishka 容器自动注入
    """

    scope = Scope.APP

    @provide
    def market_query_service(  # noqa: PLR0913
        self,
        stock_bars_store: StockBarsStore,
        stock_status_store: StockStatusStore,
        stock_adj_store: StockAdjFactorStore,
        instrument_store: InstrumentStore,
    ) -> MarketService:
        """Market 查询服务（支持读写）。"""
        return MarketService(
            stock_bars_store=stock_bars_store,
            stock_status_store=stock_status_store,
            stock_adj_store=stock_adj_store,
            instrument_store=instrument_store,
        )

    @provide
    def metadata_query_service(
        self,
        instrument_store: InstrumentStore,
    ) -> MetadataService:
        """Metadata 查询服务."""
        return MetadataService(
            instrument_store=instrument_store,
        )

    @provide
    def datahub(  # noqa: PLR0913
        self,
        data_root: Path,
        metadata_query_service: MetadataService,
        market_query_service: MarketService,
    ) -> Iterator[DataHub]:
        """
        DataHub 主入口（应用级单例）.

        所有依赖通过 Provider 注入，DataHub 不再使用 @cached_property.
        移除了 Accessor 层，直接使用 Domain Services.
        """
        from ditto_datahub import DataHub

        # 创建 DataHub 并注入所有依赖
        hub = DataHub(
            data_root=data_root,
            metadata_query_service=metadata_query_service,
            market_query_service=market_query_service,
        )

        yield hub
```

### 16.6 FastAPI 集成

```python
# apps/port/src/ditto_port/api/routes/market.py

from fastapi import APIRouter, Depends
from dishka import AsyncContainer

from ditto_datahub.services.market import MarketService, BarsQuery

router = APIRouter(prefix="/api/v1/market")


def get_market_service() -> MarketService:
    """
    获取 MarketService 实例（通过 dishka 注入）.

    注意：在 FastAPI 启动时，会通过 inject_into_fastapi() 设置容器。
    """
    # 通过 FastAPI 的 request.state 获取容器
    # 实际实现中，这是由 dishka 的 make_fastapi_wrapper 处理的
    ...


@router.post("/bars/query")
async def query_bars(
    query: BarsQuery,
    service: MarketService = Depends(get_market_service),
) -> list[BarResponse]:
    """查询 K线数据 API（统一入口，支持多种查询方式）"""
    df = service.query(query)
    return df.to_dicts()  # FastAPI 自动转为 list[BarResponse]
```

---

**文档版本**: 5.15
**最后更新**: 2026-02-07
