# ditto-datahub

**版本**: v0.18.0
**最后更新**: 2026-03-24
**状态**: ✅ 稳定

## 概要

Ditto 量化系统的数据层，统一管理数据获取、存储、查询和 PIT (Point-in-Time) 安全。

## 核心功能

- **CQRS 架构**: Store 层采用 Reader/Writer 模式，读写分离
- **PIT 安全**: 时点安全的数据查询，避免未来函数
- **高性能存储**: Parquet 文件存储 + SQLite 元数据
- **数据质量检查**: 多维度 DQ 检查和报告
- **多数据源支持**: Tushare、Akshare 等
- **SourceSchema**: 数据源输出格式标准协议，确保数据质量
- **域驱动设计**: Metadata、Market、Capital、Fundamental、Macro、Features、Factors 七域

## 架构

DataHub 采用分层架构，Store 层实现 CQRS 模式（Reader/Writer 分离）：

```
┌─────────────────────────────────────────────────────────┐
│                    Port Layer (apps/port)                │
│                  通过 DI 容器注入 Domain Services        │
└─────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬───────────────┐
        ▼           ▼           ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Runtime层    │ │  Store层     │ │  Service层   │ │  Sources层   │
│              │ │  (CQRS)      │ │              │ │              │
│ SQLitePool   │ │ Reader/      │ │ MetadataSvc  │ │ Tushare      │
│ FileLock     │ │ Writer       │ │ MarketSvc    │ │ Akshare      │
│ Allocator    │ │              │ │ Fundamental  │ │              │
│ FreezeMgr    │ │ ParquetStore │ │ CapitalSvc   │ │              │
│ SqlEngine    │ │ SQLiteStore  │ │ MacroSvc     │ │              │
│              │ │              │ │ FeaturesSvc  │ │              │
└──────────────┘ └──────────────┘ │ FactorsSvc   │ └──────────────┘
                                  └──────────────┘
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
| `BaseReader` | 抽象基类，定义查询接口 (read/count/get_*) |
| `BaseWriter` | 抽象基类，定义写入接口 (write/delete) |
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

数据存储组件采用 CQRS 模式，每个 Store 拆分为 Reader 和 Writer：

**CQRS 模式说明**：
- `*_reader.py`：负责查询操作（read/count/get_*）
- `*_writer.py`：负责写入/删除操作（write/delete）
- 读写分离，便于独立优化和测试

| Reader 组件 | Writer 组件 | 说明 | 存储格式 |
|------------|-------------|------|----------|
| `InstrumentReader` | `InstrumentWriter` | 标的主数据 | SQLite |
| `IdentityReader` | `IdentityWriter` | 标识符映射 | SQLite (PIT) |
| `CalendarReader` | `CalendarWriter` | 交易日历 | SQLite + 内存缓存 |
| `IndustryBasicReader` | `IndustryBasicWriter` | 行业主数据 | SQLite |
| `IndustryMappingReader` | `IndustryMappingWriter` | 行业映射 | SQLite (PIT) |
| `UniverseReader` | `UniverseWriter` | 标的池 | SQLite |
| `BarsReader` | `BarsWriter` | OHLCV 行情 | Parquet (分区: instrument_id/year) |
| `AdjFactorReader` | `AdjFactorWriter` | 复权因子 | Parquet (分区: instrument_id/year) |
| `IndexConstituentReader` | `IndexConstituentWriter` | 指数成分股 | SQLite (PIT) |
| `BalanceSheetReader` | `BalanceSheetWriter` | 资产负债表 | SQLite (PIT) |
| `IncomeStatementReader` | `IncomeStatementWriter` | 利润表 | SQLite (PIT) |
| `CashFlowReader` | `CashFlowWriter` | 现金流量表 | SQLite (PIT) |
| `DividendReader` | `DividendWriter` | 股息分红 | SQLite (PIT) |
| `CorporateActionsReader` | `CorporateActionsWriter` | 公司行为 | SQLite |
| `ForecastReader` | `ForecastWriter` | 业绩预告 | SQLite (PIT) |
| `ExpressReader` | `ExpressWriter` | 业绩快报 | SQLite (PIT) |
| `MarginTradingReader` | `MarginTradingWriter` | 融资融券 | SQLite (PIT) |
| `PledgeRatioReader` | `PledgeRatioWriter` | 股权质押 | SQLite (PIT) |
| `IndicatorReader` | `IndicatorWriter` | 宏观指标 | SQLite (PIT) |
| `IndicatorMetadataReader` | `IndicatorMetadataWriter` | 宏观元数据 | SQLite |
| `TechnicalIndicatorReader` | `TechnicalIndicatorWriter` | 技术指标 | Parquet (按年分区) |
| `TechnicalIndicatorMetadataReader` | `TechnicalIndicatorMetadataWriter` | 技术指标元数据 | SQLite |
| `FactorReader` | `FactorWriter` | 因子信号 | Parquet (按年分区) |
| `FactorMetadataReader` | `FactorMetadataWriter` | 因子元数据 | SQLite |
| `TradingRuleReader` | `TradingRuleWriter` | 交易规则 | 内存 (PIT, V1) |
| `FeeScheduleReader` | `FeeScheduleWriter` | 费率表 | 内存 (PIT, V1) |

### 域级组织

DataHub 采用域驱动设计（DDD），按业务域组织代码结构：

#### Metadata 域

- `stores/metadata/`: Metadata 域
  - `instrument/`: 标的主数据
    - `instrument_reader.py`: InstrumentReader（标的查询）
    - `instrument_writer.py`: InstrumentWriter（标的写入）
  - `identity/`: 标识符映射
    - `identity_reader.py`: IdentityReader（标识符查询，支持 PIT）
    - `identity_writer.py`: IdentityWriter（标识符写入，支持 PIT）
  - `industry/`: 申万行业分类
    - `industry_basic_reader.py`: IndustryBasicReader（行业主数据查询）
    - `industry_basic_writer.py`: IndustryBasicWriter（行业主数据写入）
    - `industry_mapping_reader.py`: IndustryMappingReader（行业映射查询，支持 PIT）
    - `industry_mapping_writer.py`: IndustryMappingWriter（行业映射写入，支持 PIT）
  - `calendar/`: 交易日历
    - `calendar_reader.py`: CalendarReader（交易日历查询）
    - `calendar_writer.py`: CalendarWriter（交易日历写入）
  - `universe/`: 标的池
    - `universe_reader.py`: UniverseReader（标的池查询）
    - `universe_writer.py`: UniverseWriter（标的池写入）
  - `services/metadata_service.py`: MetadataService（域级统一服务）

#### Market 域

- `stores/market/`: Market 域
  - `stock/`: 股票行情数据
    - `bars/bars_reader.py`: StockBarsReader（股票 K线查询）
    - `bars/bars_writer.py`: StockBarsWriter（股票 K线写入）
    - `status/status_reader.py`: StockStatusReader（股票状态查询）
    - `status/status_writer.py`: StockStatusWriter（股票状态写入）
    - `adj/adj_factor_reader.py`: StockAdjFactorReader（股票复权因子查询）
    - `adj/adj_factor_writer.py`: StockAdjFactorWriter（股票复权因子写入）
  - `etf/`: ETF 行情数据
    - `bars/bars_reader.py`: EtfBarsReader（ETF K线查询）
    - `bars/bars_writer.py`: EtfBarsWriter（ETF K线写入）
    - `status/status_reader.py`: EtfStatusReader（ETF 状态查询）
    - `status/status_writer.py`: EtfStatusWriter（ETF 状态写入）
    - `nav/nav_reader.py`: EtfNavReader（ETF 净值查询）
    - `nav/nav_writer.py`: EtfNavWriter（ETF 净值写入）
    - `adj/adj_factor_reader.py`: EtfAdjFactorReader（ETF 复权因子查询）
    - `adj/adj_factor_writer.py`: EtfAdjFactorWriter（ETF 复权因子写入）
  - `index/`: 指数行情数据
    - `bars/bars_reader.py`: IndexBarsReader（指数 K线查询）
    - `bars/bars_writer.py`: IndexBarsWriter（指数 K线写入）
    - `constituent/constituent_reader.py`: IndexConstituentReader（指数成分股查询）
    - `constituent/constituent_writer.py`: IndexConstituentWriter（指数成分股写入）
  - `services/market_service.py`: MarketService（域级统一服务）

#### Fundamental 域

- `stores/fundamental/`: Fundamental 域（企业基本面数据）
  - `financial/`: 财务报表数据子域
    - `balance_sheet_reader.py`: BalanceSheetReader（资产负债表查询，支持 PIT）
    - `balance_sheet_writer.py`: BalanceSheetWriter（资产负债表写入）
    - `income_statement_reader.py`: IncomeStatementReader（利润表查询，支持 PIT）
    - `income_statement_writer.py`: IncomeStatementWriter（利润表写入）
    - `cash_flow_reader.py`: CashFlowReader（现金流量表查询，支持 PIT）
    - `cash_flow_writer.py`: CashFlowWriter（现金流量表写入）
  - `corporate/`: 公司行为数据子域
    - `dividend_reader.py`: DividendReader（股息分红查询，支持 PIT）
    - `dividend_writer.py`: DividendWriter（股息分红写入）
    - `corporate_actions_reader.py`: CorporateActionsReader（公司行为查询）
    - `corporate_actions_writer.py`: CorporateActionsWriter（公司行为写入）
  - `forecast/`: 业绩预告/快报数据子域
    - `forecast_reader.py`: ForecastReader（业绩预告查询，支持 PIT）
    - `forecast_writer.py`: ForecastWriter（业绩预告写入）
    - `express_reader.py`: ExpressReader（业绩快报查询，支持 PIT）
    - `express_writer.py`: ExpressWriter（业绩快报写入）
  - `services/fundamental_service.py`: FundamentalService（域级统一服务）

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

- `stores/capital/`: Capital 域（资金与资本市场数据）
  - `margin/`: 融资融券数据子域
    - `margin_trading_reader.py`: MarginTradingReader（融资融券查询，支持 PIT）
    - `margin_trading_writer.py`: MarginTradingWriter（融资融券写入）
  - `pledge/`: 股权质押数据子域
    - `pledge_ratio_reader.py`: PledgeRatioReader（股权质押查询，支持 PIT）
    - `pledge_ratio_writer.py`: PledgeRatioWriter（股权质押写入）
  - `valuation/`: 估值指标子域
    - `valuation_metrics_reader.py`: ValuationMetricsReader（估值指标查询，支持 PIT）
    - `valuation_metrics_writer.py`: ValuationMetricsWriter（估值指标写入）
  - `futures/`: 期货数据子域
    - `futures_reader.py`: FuturesReader（期货数据查询，支持 PIT）
    - `futures_writer.py`: FuturesWriter（期货数据写入）
  - `index_composition/`: 指数成分股子域
    - `index_composition_reader.py`: IndexCompositionReader（指数成分股查询，支持 PIT）
    - `index_composition_writer.py`: IndexCompositionWriter（指数成分股写入）
  - `services/capital_service.py`: CapitalService（域级统一服务）

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

- `stores/macro/`: Macro 域（宏观经济指标数据）
  - `indicator/`: 宏观指标子域
    - `indicator_reader.py`: IndicatorReader（宏观指标查询，支持 PIT）
    - `indicator_writer.py`: IndicatorWriter（宏观指标写入）
    - `metadata_reader.py`: IndicatorMetadataReader（宏观指标元数据查询）
    - `metadata_writer.py`: IndicatorMetadataWriter（宏观指标元数据写入）
  - `services/macro_service.py`: MacroService（域级统一服务）

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
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.models.macro import MacroQuery

# MacroService 由 dishka 容器注入
service: MacroService = container.get(MacroService)

# 写入宏观指标（统一 write 契约）
service.write(
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
data = service.query(query)
```

#### Features 域

- `stores/features/`: Features 域（技术指标与衍生特征域）
  - `technical/`: 技术指标子域
    - `technical_indicator_reader.py`: TechnicalIndicatorReader（技术指标查询）
    - `technical_indicator_writer.py`: TechnicalIndicatorWriter（技术指标写入）
    - `technical_indicator_metadata_reader.py`: TechnicalIndicatorMetadataReader（技术指标元数据查询）
    - `technical_indicator_metadata_writer.py`: TechnicalIndicatorMetadataWriter（技术指标元数据写入）
    - `metadata.py`: 技术指标类型定义
  - `services/feature_service.py`: FeatureService（域级统一服务）

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
from ditto_datahub.services.feature_service import FeatureService
from ditto_datahub.models.features import FeatureQuery

# FeatureService 由 dishka 容器注入
service: FeatureService = container.get(FeatureService)

# 查询技术指标
query = FeatureQuery(
    indicators=["indicator_rsi_14", "indicator_ma_20"],
    start="2024-01-01",
    end="2024-01-31",
    indicator_types=["momentum", "trend"],
)
data = service.query(query)
```

#### Factors 域

- `stores/factors/`: Factors 域（因子信号域）
  - `factor_reader.py`: FactorReader（因子信号查询，支持 PIT）
  - `factor_writer.py`: FactorWriter（因子信号写入）
  - `factor_metadata_reader.py`: FactorMetadataReader（因子元数据查询）
  - `factor_metadata_writer.py`: FactorMetadataWriter（因子元数据写入）
  - `metadata.py`: 因子分类定义
  - `services/factor_service.py`: FactorService（域级统一服务）

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
from ditto_datahub.services.factor_service import FactorService
from ditto_datahub.models.factors import FactorQuery

# FactorService 由 dishka 容器注入
service: FactorService = container.get(FactorService)

# 查询因子信号（PIT 安全）
query = FactorQuery(
    factors=["factor_momentum_12m", "factor_value_pe"],
    start="2024-01-01",
    end="2024-01-31",
    as_of="2024-06-30",  # 只使用截至该日期已知的数据
    factor_classes=["fundamental", "technical"],
)
data = service.query(query)
```

#### Capital 域使用示例：
```python
from datetime import date
import polars as pl
from ditto_datahub.services.capital_service import CapitalService

# CapitalService 由 dishka 容器注入
service: CapitalService = container.get(CapitalService)

# 写入估值指标数据
df = pl.DataFrame({
    "instrument_id": ["600000.SH"],
    "report_date": [date(2024, 3, 31)],
    "knowledge_date": [date(2024, 4, 30)],
    "effective_from": [date(2024, 5, 1)],
    "effective_to": [None],
    "pe_ratio": [15.5],
    "pb_ratio": [1.8],
    "ps_ratio": [2.3],
    "dividend_yield": [3.2],
    "market_cap": [1000000000.0],
})
service.write_valuation_metrics(df)

# PIT 查询：查询 2024-05-15 时点的估值指标
result = service.get_valuation_metrics(
    instrument_id="600000.SH",
    as_of_date=date(2024, 5, 15),
)
```

#### 架构优势

- **高内聚**: 相关业务逻辑聚合在同一域内
- **低耦合**: 域之间通过明确的接口（QueryService）交互
- **可扩展**: 新增域不影响现有域的实现
- **易测试**: 每个域可独立测试

#### Strategy 域

- `services/strategy/`: Strategy 域（策略规则组装 + 策略目录服务）
  - `instrument_rule_provider.py`: InstrumentRuleProvider（三层规则组装）
  - `strategy_catalog_service.py`: StrategyCatalogService（Spec CRUD + 发布治理）
  - `strategy_artifact_service.py`: StrategyArtifactService（产物生命周期管理）
  - `strategy_run_service.py`: StrategyRunService（策略运行记录 CRUD）

- `services/audit/`: 审计域（执行审计日志持久化）
  - `execution_audit_service.py`: ExecutionAuditService（审计记录写入 SQLite）

- `models/strategy_run.py`: StrategyRunRecord（运行记录模型）
- `models/strategy_audit.py`: AuditRecordType / PreTradeDecisionPayload / RiskScanPayload

**三层规则 (R6)**：
- `DefinitionRecord`: 标的静态定义（asset_class, exchange, tick_size, lot_size 等）
- `TradingRuleRecord`: 交易规则（PIT 版本化 — settlement_cycle, price_limit_pct 等）
- `FeeScheduleRecord`: 费率表（PIT 版本化 — commission_rate, stamp_duty_rate 等）

**策略目录**：
- `StrategySpecRecord`: 策略 Spec 存储记录（strategy_id, name, spec_json, version, status）
- `StrategyArtifactRecord`: 策略产物记录（artifact_id, strategy_id, run_id, artifact_type, file_path）
- `StrategyCatalogService`: Spec CRUD + `publish_spec()`（draft → published 状态治理）
- `StrategyArtifactService`: 产物 CRUD + `archive_artifact()`（active → archived）

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
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.models.market import AdjType, MarketBarsQuery

# Domain Services 由 dishka 容器注入
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 查询交易日历
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")

# 查询行情数据（带复权）
query = MarketBarsQuery(
    instrument_ids=[1, 2],
    start="2024-01-01",
    end="2024-01-31",
    adj=AdjType.QFQ,  # 前复权
)
bars = market_service.query(query)
```

### Metadata 查询

MetadataService 提供统一的 Metadata 域查询接口：

```python
from ditto_datahub.services.metadata_service import MetadataService

# MetadataService 由 dishka 容器注入
metadata_service: MetadataService = container.get(MetadataService)

# 标识符解析（支持 PIT）
instrument_id = metadata_service.resolve_instrument_id("600000.SH", source="tushare")
instrument_id = metadata_service.resolve_instrument_id("600000.SH", source="tushare", asof="2024-06-30")

# 查询标的情報
df = metadata_service.get_instruments(instrument_ids=[1, 2, 3])
df = metadata_service.get_instruments(instrument_ids=[1], asset_class="stock", exchange="SSE")

# 查询交易日历
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31", only_open=True)

# 交易日历便捷方法
is_trading = metadata_service.is_trading_day("2024-01-15")
prev_day = metadata_service.get_prev_trading_day("2024-01-15")
next_day = metadata_service.get_next_trading_day("2024-01-15")

# 查询行业分类
industries = metadata_service.get_industries(level=1)  # 一级行业
mappings = metadata_service.get_industry_mappings(instrument_ids=[1, 2, 3], asof="2024-06-30")

# 查询标的池
universe = metadata_service.get_universe(name="csi300")
```

### Market 查询

MarketService 提供统一的 Market 域查询接口：

```python
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.models.market import AdjType, MarketBarsQuery

# MarketService 由 dishka 容器注入
market_service: MarketService = container.get(MarketService)

# 查询股票 K线数据（支持复权）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    adj=AdjType.QFQ,  # 前复权
)
bars = market_service.query(query)

# 查询带状态信息的 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    with_status=True,  # 添加停牌、ST 等状态信息
)
bars = market_service.query(query)

# PIT 安全查询（只使用 asof 日期之前的数据）
query = MarketBarsQuery(
    instrument_ids=[1, 2, 3],
    start="2024-01-01",
    end="2024-01-31",
    asof="2024-06-30",  # 只使用 2024-06-30 之前已知的数据
)
bars = market_service.query(query)

# 查询 ETF K线数据
query = MarketBarsQuery(
    instrument_ids=[510010, 510050],  # ETF Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="etf",
)
bars = market_service.query(query)

# 查询指数 K线数据
query = MarketBarsQuery(
    instrument_ids=[1, 2],  # 指数 Instrument ID
    start="2024-01-01",
    end="2024-01-31",
    asset_class="index",
)
bars = market_service.query(query)
```

#### 统一接口约定

Port 层通过 Domain Services 访问 DataHub 数据，所有 Services 都通过 DI 容器注入：

```python
from dishka import Container
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.market_service import MarketService

# 通过 DI 容器注入 Services
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 使用 Services
instrument_id = metadata_service.resolve_instrument_id("600000.SH", source="tushare")
df = metadata_service.get_instruments(instrument_ids=[1, 2, 3])
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")
```

### PIT 安全查询

```python
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.models.market import MarketBarsQuery

# MarketService 由 dishka 容器注入
market_service: MarketService = container.get(MarketService)
decision_date = "2024-01-15"

# 使用统一 query 入口执行 PIT 查询
bars = market_service.query(
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
from ditto_engine.quality import QualityEngine

# QualityEngine 由容器注入（DataHub 本身不持有 dq_checker）
engine: QualityEngine = container.get(QualityEngine)

# 运行 DQ 检查
result = engine.check(
    df=bars_df,
    dataset="stock_daily",
    levels=["l1", "l2"],
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

### v0.18.0 (2026-03-24)
**新增** — Strategy 运行与审计支持
- `services/strategy/strategy_run_service.py`: StrategyRunService（运行记录 CRUD）
- `services/audit/execution_audit_service.py`: ExecutionAuditService（审计日志持久化）
- `models/strategy_run.py`: StrategyRunRecord（RunStatus 枚举 + 运行记录模型）
- `models/strategy_audit.py`: AuditRecordType / PreTradeDecisionPayload / RiskScanPayload

### v0.17.0 (2026-03-23)
**新增** — Strategy 域控制面服务
- `models/strategy.py`: StrategySpecRecord（策略 Spec 存储）、StrategyArtifactRecord（策略产物记录）
- `services/strategy/strategy_catalog_service.py`: StrategyCatalogService（Spec CRUD + DRAFT/PUBLISHED 状态治理）
- `services/strategy/strategy_artifact_service.py`: StrategyArtifactService（产物 CRUD + 生命周期管理）
- 21 个新测试（catalog 10 + artifact 11），全部通过

### v0.16.0 (2026-03-21)
**新增** — Phase 0 Part 4: DataHub 层策略规则支持
- `TradingRuleReader` / `TradingRuleWriter`: PIT 版本化交易规则存储 (V1 内存实现)
- `FeeScheduleReader` / `FeeScheduleWriter`: PIT 版本化费率表存储 (V1 内存实现)
- `_pit_base.py`: 泛型 PIT 基类 (`PITRecordReader[RecordT]`, `PITRecordWriter[RecordT]`, `PITRecord` Protocol)
- `InstrumentRuleProvider`: 三层规则组装 (`DefinitionRecord`, `TradingRuleRecord`, `FeeScheduleRecord`)
- 26 个单元测试覆盖边界条件（effective_from/effective_to、版本选择、空值处理）

**设计决策**
- DataHub 层不依赖 Core 层，返回 Records 由调用方转换为 Core 模型

### v0.15.0 (2026-02-10)
**破坏性重构**
- 移除 DataHub Facade：Port 层直接注入 Domain Services
  - 不再通过 `DataHub` 门面类访问数据
  - Port 层通过 DI 容器直接注入 `MetadataService`、`MarketService` 等 Domain Services
  - Service 层保持不变，继续提供统一的域级 API
- CQRS 架构实现：Store 层拆分为 Reader/Writer 模式
  - 所有 `*_store.py` 拆分为 `*_reader.py` + `*_writer.py`
  - Reader 负责查询操作（read/count/get_*）
  - Writer 负责写入/删除操作（write/delete）
  - 读写分离，便于独立优化和测试
- 新增基础抽象类：`BaseReader` 和 `BaseWriter`
  - `BaseReader` 定义查询接口
  - `BaseWriter` 定义写入接口
  - 替代原有的 `BaseStore` 统一接口

**改进**
- 架构更简洁：移除 Facade 层，减少间接层级
- 职责更清晰：读写分离，便于独立优化和测试
- 类型安全：所有 Service 方法都有完整类型注解
- 测试覆盖：所有 Reader/Writer 都有对应的单元测试

**文档**
- 更新 README.md 反映 CQRS 架构
- 更新架构图，移除 DataHub Facade
- 更新所有使用示例为 Service 直接访问模式

**测试**
- 单元测试：所有新增 Reader/Writer 的单元测试
- 集成测试：验证 CQRS 模式的端到端功能
- 测试覆盖率：保持 ≥ 80%

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
