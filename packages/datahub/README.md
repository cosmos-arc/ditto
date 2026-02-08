# ditto-datahub

**版本**: v0.14.0
**最后更新**: 2026-02-06
**状态**: ✅ 稳定

## 概要

Ditto 量化系统的数据层，统一管理数据获取、存储、查询和 PIT (Point-in-Time) 安全。

## 核心功能

- **统一数据入口**: DataHub 门面类，封装所有数据访问
- **PIT 安全**: 时点安全的数据查询，避免未来函数
- **高性能存储**: Parquet 文件存储 + SQLite 元数据
- **数据质量检查**: 多维度 DQ 检查和报告
- **多数据源支持**: Tushare、Akshare 等
- **SourceSchema**: 数据源输出格式标准协议，确保数据质量
- **域驱动设计**: Metadata、Market、Capital、Fundamental、Macro、Features、Factors 七域

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
│ Runtime层    │ │  Store层     │ │  Helpers层   │ │  Sources层   │
│              │ │              │ │              │ │              │
│ SQLitePool   │ │ InstrumentStore│ │ adjustment   │ │ Tushare      │
│ FileLock     │ │ CalendarStore│ │ pit          │ │ Akshare      │
│ InstrumentIdAllocator│ │ BarsStore    │ │              │ │              │
│ DQChecker    │ │ AdjFactor... │ │ (纯函数工具)  │ │              │
│ FreezeMgr    │ │              │ │              │ │              │
│ SqlEngine    │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### SourceSchema 层

SourceSchema 定义数据源输出格式标准协议，作为 Source 和 Store 之间的契约：

**核心功能**：

| 功能 | 说明 |
|------|------|
| 列完整性验证 | 检查 DataFrame 是否包含所有必需的列 |
| 类型兼容性验证 | 检查列类型是否符合预期（支持数值类型向上兼容） |
| 主键唯一性验证 | 确保主键组合在数据集中唯一 |
| PIT 支持 | 支持定义 PIT 列（effective_from, effective_to） |

**Market 域 SourceSchema**：

| Schema | 数据集 | 说明 |
|--------|--------|------|
| `STOCK_DAILY_SOURCE_SCHEMA` | 股票日线 | OHLCV 行情数据 |
| `ETF_DAILY_SOURCE_SCHEMA` | ETF 日线 | OHLCV 行情数据 |
| `ADJ_FACTOR_SOURCE_SCHEMA` | 复权因子 | 带 knowledge_date |
| `STOCK_STATUS_SOURCE_SCHEMA` | 股票状态 | 允许重复主键 |
| `STOCK_LIMIT_SOURCE_SCHEMA` | 涨跌停价 | 限价数据 |
| `FUND_ADJ_SOURCE_SCHEMA` | 基金复权因子 | 带 knowledge_date |

**使用示例**：

```python
from ditto_datahub.sources.schemas import STOCK_DAILY_SOURCE_SCHEMA
import polars as pl

# 获取数据源数据
df = source.fetch_stock_daily("2024-01-02")

# 验证 Schema
STOCK_DAILY_SOURCE_SCHEMA.validate(df)

# 检查通过后写入 Store
store.write(df, on_duplicate=OnDuplicate.KEEP_FIRST)
```

### 基础层

基础层提供统一的数据存储抽象接口：

| 组件 | 说明 |
|------|------|
| `BaseStore` | 抽象基类，定义所有存储实现的统一接口 (read/write/delete) |
| `ParquetStore` | Parquet 文件存储实现，支持按年分区、自动去重 |
| `SQLiteStore` | SQLite 数据库存储实现，支持事务、PIT 查询 |

**配置系统**：从多路径配置简化为单 `data_root` 配置（`data_store.env`），所有路径自动生成：

```python
from ditto_datahub.config import DataRootConfig

# 初始化配置（来自 data_store.env）
config = DataRootConfig()
# 默认: data
# 自动生成: data/market/stock/bars/daily/, data/metadata/metadata.sqlite, 等

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

#### Macro 域

- `domains/macro/`: Macro 域（宏观经济指标数据）
  - `indicator/`: 宏观指标子域
    - `indicator_store.py`: IndicatorStore（宏观数据存储，支持 PIT 查询）
    - `metadata_store.py`: IndicatorMetadataStore（宏观指标元数据）
  - `macro_service.py`: MacroService（域级统一 `query()/write()` 服务）

**数据类型**（4 类）：
- `economic`: 经济指标（GDP、CPI、PPI、PMI）
- `interest_rate`: 利率指标（SHIBOR、LPR、国债收益率）
- `exchange_rate`: 汇率指标
- `money_supply`: 货币供应量（M0、M1、M2）

**PIT 查询支持**：
- 基于 SQLite 的 PIT 实现，使用 `effective_from/effective_to` 字段
- 支持 `knowledge_date` 字段记录数据发布时间
- PIT 查询模式：`effective_from <= as_of_date AND (effective_to IS NULL OR effective_to > as_of_date)`

**存储结构**：
- 指标值：SQLite 表 `macro_indicator_data`
- 指标元数据：SQLite 表 `macro_indicators`

**使用示例**：
```python
from datetime import date

import polars as pl
from ditto_datahub import DataHub
from ditto_datahub.domains.macro import MacroQuery

hub = DataHub()

# 写入宏观指标（统一 write 契约）
hub.macro.write(
    pl.DataFrame(
        {
            "indicator_code": ["CPI_YOY"],
            "indicator_name": ["CPI同比"],
            "category": ["economic"],
            "frequency": ["monthly"],
            "need_pit": [True],
            "date": [date(2024, 1, 1)],
            "value": [2.5],
            "knowledge_date": [date(2024, 1, 2)],
        }
    )
)

# 查询宏观经济指标（统一 query 契约，支持 PIT）
query = MacroQuery(
    indicators=["CPI_YOY", "SHIBOR_1M"],
    start="2024-01-01",
    end="2024-01-31",
    asof="2024-06-30",  # 只使用截至该日期已知的数据
    category="economic",
)
data = hub.macro.query(query)
```

#### Features 域

- `domains/features/`: Features 域（技术指标与衍生特征域）
  - `technical/`: 技术指标子域
    - `indicator_store.py`: IndicatorStore（技术指标存储，Parquet 按年分区）
    - `indicator_metadata_store.py`: IndicatorMetadataStore（技术指标元数据）
    - `metadata.py`: 技术指标类型定义
  - `feature_service.py`: FeatureService（域级统一查询服务）

**指标类型**（4 类）：
- `trend`: 趋势指标（SMA、EMA、MACD）
- `momentum`: 动量指标（RSI、KDJ、CCI）
- `volatility`: 波动率指标（ATR、布林带）
- `volume`: 成交量指标（OBV、VWAP）

**PIT 支持**：
- 技术指标无需 PIT 支持（计算公式固定且可重现）
- 任何时间点重新计算都会得到相同结果

**存储路径**：
- 数据：`data_root/features/technical/indicators_narrow/YYYY.parquet`
- 元数据：`data_root/features/technical/metadata.sqlite`

**使用示例**：
```python
from ditto_datahub import DataHub
from ditto_datahub.domains.features import FeatureQuery

hub = DataHub()

# 查询技术指标
query = FeatureQuery(
    indicators=["indicator_rsi_14", "indicator_ma_20"],
    start="2024-01-01",
    end="2024-01-31",
    indicator_types=["momentum", "trend"],
)
data = hub.features.query(query)
```

#### Factors 域

- `domains/factors/`: Factors 域（因子信号域）
  - `factor_store.py`: FactorStore（因子存储，支持 PIT 查询）
  - `factor_metadata_store.py`: FactorMetadataStore（因子元数据）
  - `metadata.py`: 因子分类定义
  - `factor_service.py`: FactorService（域级统一查询服务）

**因子分类**：

**FactorClass**（4 类）：
- `fundamental`: 基本面因子（PE、PB、ROE）
- `technical`: 技术面因子（动量、反转）
- `macro`: 宏观因子（利率、汇率）
- `statistical`: 统计因子（波动率、偏度）

**FactorFamily**（5 类）：
- `value`: 价值因子
- `momentum`: 动量因子
- `quality`: 质量因子
- `size`: 规模因子
- `volatility`: 波动率因子

**PIT 查询支持**：
- 基于 Parquet 的轻量级 PIT 实现，使用 `effective_from/effective_to` 列
- PIT 查询模式：`effective_from <= as_of_date AND (effective_to IS NULL OR effective_to > as_of_date)`

**存储路径**：
- 数据：`data_root/factors/factors_narrow/YYYY.parquet`
- 元数据：`data_root/factors/metadata.sqlite`

**使用示例**：
```python
from ditto_datahub import DataHub
from ditto_datahub.domains.factors import FactorQuery

hub = DataHub()

# 查询因子信号（PIT 安全）
query = FactorQuery(
    factors=["factor_momentum_12m", "factor_value_pe"],
    start="2024-01-01",
    end="2024-01-31",
    as_of="2024-06-30",  # 只使用截至该日期已知的数据
    factor_classes=["fundamental", "technical"],
)
data = hub.factors.query(query)
```

#### Capital 域使用示例：
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

### Helpers 层

纯函数工具模块（无状态、可测试、可组合）：

| 模块 | 说明 |
|------|------|
| `adjustment.py` | 复权计算（QFQ/HFQ） |
| `pit.py` | PIT 查询辅助函数 |

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
from ditto_datahub.domains.market import AdjType, MarketBarsQuery

# DataHub 由 dishka 容器注入（示例）
hub: DataHub = container.get(DataHub)

# 查询交易日历
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")

# 查询行情数据（带复权）
bars = hub.market.query(
    MarketBarsQuery(
    instrument_ids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    adj=AdjType.QFQ,  # 前复权
    )
)
```

### Metadata 查询（新 API）

DataHub v0.7.0 引入了域级查询服务 `MetadataService`，提供统一的 Metadata 域查询接口：

```python
from ditto_datahub import DataHub

# DataHub 由 dishka 容器注入（示例）
hub: DataHub = container.get(DataHub)

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

# DataHub 由 dishka 容器注入（示例）
hub: DataHub = container.get(DataHub)

# 查询股票 K线数据（支持复权）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    adj=AdjType.QFQ,  # 前复权
)
bars = hub.market.query(query)

# 查询带状态信息的 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    with_status=True,  # 添加停牌、ST 等状态信息
)
bars = hub.market.query(query)

# PIT 安全查询（只使用 asof 日期之前的数据）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    asof="2024-06-30",  # 只使用 2024-06-30 之前已知的数据
)
bars = hub.market.query(query)

# 查询 ETF K线数据
query = MarketBarsQuery(
    instrument_ids=[510010, 510050],  # ETF Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="etf",
)
bars = hub.market.query(query)

# 查询指数 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2],  # 指数 Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="index",
)
bars = hub.market.query(query)
```

#### 统一接口约定

DataHub 对外统一通过域服务接口访问，不再建议依赖历史别名。

```python
instrument_id = hub.metadata.resolve_instrument_id("600000.SH", source="tushare")
df = hub.metadata.get_instruments(instrument_ids=[1, 2, 3])
trading_days = hub.metadata.get_trading_days("2024-01-01", "2024-01-31")
```

### PIT 安全查询

```python
from ditto_datahub import DataHub
from ditto_datahub.domains.market import MarketBarsQuery

# DataHub 由 dishka 容器注入（示例）
hub: DataHub = container.get(DataHub)
decision_date = "2024-01-15"

# 使用统一 query 入口执行 PIT 查询
bars = hub.market.query(
    MarketBarsQuery(
        instrument_ids=[1],
        start="2024-01-01",
        end=decision_date,
        asof=decision_date,  # PIT 查询：只使用 decision_date 之前的数据
    )
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
- [Port 层重构计划](../../../../docs/plans/2026-02-02-port-layer-refactor.md)

## 变更记录

### v0.14.0 (2026-02-06)
**重构**
- 架构清理：移除 Accessor 层，引入 Helpers 层
  - `accessors/` → `helpers/`：只保留纯函数工具（adjustment.py、pit.py）
  - 移除 `enrichment.py`（已搬迁到 ditto-port）
  - 移除 `instrument_accessor.py`（功能迁移到 MetadataService）
  - 移除 `internal/` 子目录

**新增**
- `helpers/README.md`：纯函数工具模块文档
- `helpers/adjustment.py`：复权计算纯函数（QFQ/HFQ）
- `helpers/pit.py`：PIT 查询辅助函数

**改进**
- 更新 `stores/README.md`：明确 stores/ 作为基础设施的定位
- 更新 `packages/datahub/README.md`：架构图和层级说明
- 架构一致性：业务逻辑统一在 Domain Service 层

**文档**
- `docs/plans/2026-02-06-datahub-cleanup-refactor-design.md` - 重构设计文档

### v0.13.0 (2026-02-02)
**重构**
- 架构清理：移除 DataHub 层的业务编排组件
  - 删除 `IngestionCoordinator`（业务编排应在 Port 层，而非 DataHub 层）
  - 保留 `IngestionDataWriter` 作为通用写入工具类
  - DataHub 职责明确：只负责底层读写，不负责业务编排

**新增**
- Market 域 SourceSchema 定义：`sources/schemas/market_schemas.py`
  - `STOCK_DAILY_SOURCE_SCHEMA`：股票日线行情
  - `ETF_DAILY_SOURCE_SCHEMA`：ETF 日线行情
  - `ADJ_FACTOR_SOURCE_SCHEMA`：复权因子
  - `STOCK_STATUS_SOURCE_SCHEMA`：股票状态（允许重复主键）
  - `STOCK_LIMIT_SOURCE_SCHEMA`：涨跌停价
  - `FUND_ADJ_SOURCE_SCHEMA`：基金复权因子

**改进**
- SourceSchema 集成测试更新：使用正式定义的 Schema，而非临时定义
- Market 域 Schema 单元测试：10 个测试覆盖所有 Market 数据集
- 更新 `sources/schemas/__init__.py`：按字母顺序排序所有 Schema 导出

**测试**
- 单元测试：1559 passed, 5 skipped
- 集成测试：SourceSchema 验证通过
- 测试覆盖率：92.81%（超过 80% 要求）
- 类型检查：basedpyright 0 errors
- 代码质量：ruff All checks passed

**文档**
- `docs/plans/2026-02-02-port-layer-refactor.md` - Port 层重构计划

### v0.12.0 (2026-02-02)
**新增**
- Macro 域架构：`domains/macro/` 目录结构
  - **宏观经济指标**（4 类）：
    - `economic`: 经济指标（GDP、CPI、PPI、PMI）
    - `interest_rate`: 利率指标（SHIBOR、LPR、国债收益率）
    - `exchange_rate`: 汇率指标
    - `money_supply`: 货币供应量（M0、M1、M2）
  - **PIT 支持**：基于 SQLite 的 PIT 实现，使用 `effective_from/effective_to` 字段
  - **存储路径**：`data_root/macro/indicators_narrow/YYYY.parquet`

- Features 域架构：`domains/features/` 目录结构
  - **技术指标**（4 类）：
    - `trend`: 趋势指标（SMA、EMA、MACD）
    - `momentum`: 动量指标（RSI、KDJ、CCI）
    - `volatility`: 波动率指标（ATR、布林带）
    - `volume`: 成交量指标（OBV、VWAP）
  - **PIT 支持**：无需 PIT（计算公式固定且可重现）
  - **存储路径**：`data_root/features/technical/indicators_narrow/YYYY.parquet`

- Factors 域架构：`domains/factors/` 目录结构
  - **因子信号**（FactorClass × FactorFamily）：
    - `FactorClass`: fundamental, technical, macro, statistical（4 类）
    - `FactorFamily`: value, momentum, quality, size, volatility（5 类）
  - **PIT 支持**：基于 Parquet 的轻量级 PIT 实现
  - **存储路径**：`data_root/factors/factors_narrow/YYYY.parquet`

**实现**
- MacroService：统一查询接口，支持 `asof` PIT 查询
- FeatureService：统一查询接口，支持类型过滤
- FactorService：统一查询接口，支持 PIT 安全查询
- MetadataStore：三个域各自的元数据管理（SQLite）
- 数据存储：Macro（SQLite PIT），Features/Factors（Parquet 按年分区）

**集成**
- DataRootConfig：添加新域路径配置
- DataHub：注册三个新域服务（`hub.macro`, `hub.features`, `hub.factors`）
- 依赖注入：`apps/port/src/ditto_port/registry/datahub.py`

**改进**
- 架构一致性：三域统一使用 Service + Store + MetadataStore 模式
- 类型安全：使用 `Literal` 类型限制枚举值
- 测试覆盖：60 个单元测试全部通过
- 代码质量：basedpyright 0 errors, ruff All checks passed

**测试**
- Macro 域测试：10 个测试
- Features 域测试：14 个测试
- Factors 域测试：17 个测试
- Hub 单元测试：19 个测试
- 总计：60 个测试，全部通过 ✅

**文档**
- `docs/design/2026-02-01-factor-library-taxonomy.md` - 因子库分类体系
- `docs/design/2026-02-01-feature-factor-engines.md` - 特征和因子引擎架构
- `docs/plans/2026-02-01-datahub-macro-domain-design.md` - Macro 域设计
- `docs/plans/2026-02-01-features-factors-compute-storage-separation.md` - 计算存储分离
- `docs/plans/2026-02-01-features-factors-domain-design.md` - 域设计规范
- `docs/plans/2026-02-01-features-factors-implementation.md` - 实施计划

### v0.11.0 (2026-01-30)
**重构**
- 域重构：将 Capital 域拆分为 Fundamental 域和 Capital 域
  - **原因**: 原 Capital 域混合了"企业基本面"（由公司公告驱动）和"资金面"（由交易行为驱动）两类不同驱动变量的数据，架构边界不清
  - Fundamental 域：企业基本面数据（财务报表、公司行为、业绩预告/快报）
  - Capital 域：资金与资本市场数据（估值指标、融资融券、股权质押、期货、指数成分股）
- Service 命名统一：
  - `MarketQueryService` → `MarketService`
  - `MetadataQueryService` → `MetadataService`

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
- 错误处理统一：CapitalStore 的 write 方法添加完整的 try-except/rollback/logger/M.data_records
- 测试覆盖：所有新域和子域的单元测试和集成测试，新增数据修正场景的 PIT 测试
- 文档更新：README 更新城架构说明，设计文档标记版本差异

**测试**
- Fundamental 域单元测试：financial、corporate、forecast 子域的完整测试覆盖
- Capital 域单元测试：margin、pledge 子域的完整测试覆盖
- PIT 数据修正测试：为 forecast/express/valuation_metrics/margin_trading 添加数据修正场景测试
- 集成测试更新：更新 Capital 域集成测试，移除已迁移到 Fundamental 的数据类型
- 测试通过：所有单元测试和集成测试通过（408 passed），类型检查通过（0 errors）

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
- 接口收敛：统一由 `MarketService` 提供行情查询能力

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
- 接口收敛：统一由 `MetadataService` 提供元数据查询能力
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
- 从多路径配置简化为单 `data_root` 配置（`data_store.env`）
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
