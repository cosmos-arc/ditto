# DataHub 数据层完整重构设计

> 创建日期: 2026-01-26
> 版本: v3.4
> 状态: 设计草案
>
> **更新记录**:
> - v3.4 (2026-01-26): 数据集命名优化 - adj_factor→stock_adj_factor，universe_def→universe，board→top_board，删除 dividend 数据集
> - v3.3 (2026-01-26): 修正 industry_flow 实现方式 - 改为从 stock_flow 按 industry_mapping 聚合生成，使用申万行业分类而非同花顺行业
> - v3.2 (2026-01-26): 修正 limit_board 数据源接口 - Tushare 提供 `limit_list_d` (298) 和 `limit_step` (356) 接口，无需使用 AkShare
> - v3.1 (2026-01-26): 新增详细数据源接口映射 - 为每个数据集添加 Tushare 接口名称、字段映射、积分要求等详细信息
> - v3.0 (2026-01-26): 重大扩展 - 新增 Capital 域（资金流向、融资融券、龙虎榜、打板、筹码）、扩展 Fundamental 域（财务报表、业绩预告、机构持仓、大股东持股）、新增 Industry 域（申万行业分类与映射）、新增交易日历；简化配置为单 DATAROOT + 单 SQLite 库
> - v2.0 (2026-01-26): 重大扩展 - 新增指数数据（index_basic、index_daily、index_constituent）、ETF成分股（etf_constituent）、ETF复权因子（etf_adj_factor）、宏观数据（macro_indicators，支持PIT查询）；重新定义universe职责为用户自定义标的池
> - v1.2 (2026-01-26): 添加 etf_daily（ETF日线行情）规格，与 stock_daily 对齐冗余存储 symbol；确认 identity_mapping 简化字段用于 PIT 查询
> - v1.1 (2026-01-26): 添加完整的 ETF 数据集规格（etf_basic, etf_status, etf_nav），对齐 stock_status 和 etf_status 字段
> - v1.0 (2026-01-26): 初始版本，包含完整的数据层重构设计
>
> **目的**: 基于 ETF 行业轮动策略的需求，设计一套符合量化业界最佳实践的数据架构，支持基础数据、特征和因子的分层管理，彻底重构 DataHub 数据层。

---

## 一、设计背景

### 1.1 当前问题

| 问题 | 说明 | 影响 |
|------|------|------|
| **Accessor 层冗余** | Store → Accessor → Port 三层，职责重叠 | 维护成本高 |
| **子层级 Service 过多** | 每个子域都有独立的 Service | 层次过深，理解困难 |
| **职责边界不清** | 计算逻辑混在数据访问层 | 难以维护和测试 |
| **同层依赖混乱** | DataHub 层存在跨域依赖 | 违反分层原则 |
| **缺少特征/因子支持** | 只有基础数据，无特征/因子存储 | 无法支持策略研究 |

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **职责清晰** | DataHub 纯数据存取，Core Engine 负责计算 |
| **分层明确** | Port 层编排，DataHub 层纯净，Core Engine 独立 |
| **完整支持** | 支持基础数据、特征、因子的完整存储层 |
| **企业级规范** | 详细到字段级别的数据集格式规范 |
| **易于测试** | 各层独立，职责单一 |

---

## 二、核心架构决策

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Port 层（应用编排层）                              │
│                                                                         │
│  职责：                                                                 │
│  - Identity 解析的统一入口                                              │
│  - 跨域编排（Market → Features → Factors）                             │
│  - 业务流程组合                                                         │
│  - 向外部暴露简单的 API                                                 │
│                                                                         │
│  依赖：✅ DataHub, Core Engine                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌─────────────────────────────┐     ┌─────────────────────────────────────┐
│      DataHub（纯数据访问）    │     │      Core Engines（计算引擎）        │
├─────────────────────────────┤     ├─────────────────────────────────────┤
│                             │     │                                     │
│  - Store: Parquet/SQLite    │     │  - FeatureEngine: 特征计算           │
│  - 只负责读写               │     │  - FactorEngine: 因子计算            │
│  - 无业务逻辑               │     │  - ExpressionEngine: 表达式引擎       │
│  - 无 async                 │     │  - AdjFactorEngine: 复权计算         │
│  - 配置化存储路径           │     │  - 无 async                           │
│                             │     │                                     │
│  QueryService:              │     │  Features/Factors:                  │
│  - 编排多个 Store           │     │  - 具体计算逻辑（MA、RSI、PE等）     │
│  - 只接收 sid               │     │  - 因子后处理（去极值、标准化）     │
│  - 无同层依赖               │     │                                     │
└─────────────────────────────┘     └─────────────────────────────────────┘
```

### 2.2 关键设计原则

| 原则 | 说明 |
|------|------|
| **DataHub 纯净** | 只负责数据存取，不包含业务逻辑，不依赖其他域服务 |
| **Port 层编排** | Identity 解析、跨域编排统一在 Port 层处理 |
| **Core Engine 独立** | 计算逻辑独立于数据访问层 |
| **禁止同层依赖** | DataHub 域级服务之间完全独立，无相互依赖 |
| **配置化路径** | 存储路径从配置文件读取，不硬编码 |

---

## 三、完整数据域设计

### 3.1 目录结构

```
packages/
├── datahub/src/ditto_datahub/
│   ├── domains/
│   │   ├── market/                      # Market 域：基础市场数据
│   │   │   ├── stock/
│   │   │   │   ├── bars/bars_store.py
│   │   │   │   ├── status/status_store.py
│   │   │   │   └── adj/stock_adj_factor_store.py
│   │   │   ├── etf/
│   │   │   │   ├── bars/bars_store.py
│   │   │   │   ├── status/status_store.py
│   │   │   │   ├── nav/nav_store.py
│   │   │   │   └── adj/etf_adj_factor_store.py
│   │   │   ├── index/
│   │   │   │   ├── bars/bars_store.py
│   │   │   │   └── constituent/constituent_store.py
│   │   │   └── market_query_service.py
│   │   │
│   │   ├── capital/                     # Capital 域：资金与交易行为（新增）
│   │   │   ├── flow/
│   │   │   │   ├── market_flow_store.py       # 市场级别资金流
│   │   │   │   ├── industry_flow_store.py     # 行业级别资金流
│   │   │   │   └── stock_flow_store.py        # 个股级别资金流
│   │   │   ├── margin/
│   │   │   │   ├── margin_detail_store.py     # 融资融券明细
│   │   │   │   └── margin_summary_store.py    # 融资融券汇总
│   │   │   ├── top_board/top_board_store.py   # 龙虎榜
│   │   │   ├── limit/limit_board_store.py     # 打板数据
│   │   │   ├── chip/chip_distribution_store.py # 筹码分布
│   │   │   └── capital_query_service.py
│   │   │
│   │   ├── fundamental/                 # Fundamental 域：财务与公司行为（扩展）
│   │   │   ├── financial/
│   │   │   │   ├── balance_sheet_store.py
│   │   │   │   ├── income_statement_store.py
│   │   │   │   └── cash_flow_store.py
│   │   │   ├── indicator/financial_indicator_store.py
│   │   │   ├── forecast/
│   │   │   │   ├── forecast_store.py
│   │   │   │   └── express_store.py
│   │   │   ├── holding/
│   │   │   │   ├── fund_holding_store.py     # 公募基金持仓
│   │   │   │   ├── inst_holding_store.py     # 其他机构持仓
│   │   │   │   └── shareholder_store.py      # 大股东持股
│   │   │   ├── dividend/dividend_store.py    # 分红送转
│   │   │   └── fundamental_query_service.py
│   │   │
│   │   ├── metadata/                    # Metadata 域：元数据（单 SQLite 库）
│   │   │   ├── security/security_store.py
│   │   │   ├── industry/
│   │   │   │   ├── industry_basic_store.py
│   │   │   │   └── industry_mapping_store.py
│   │   │   ├── index/
│   │   │   │   ├── index_basic_store.py
│   │   │   │   └── index_constituent_store.py
│   │   │   ├── etf/
│   │   │   │   ├── etf_basic_store.py
│   │   │   │   └── etf_constituent_store.py
│   │   │   ├── universe/
│   │   │   │   ├── universe_store.py
│   │   │   │   └── universe_constituent_store.py
│   │   │   ├── identity/identity_store.py
│   │   │   ├── calendar/
│   │   │   │   ├── trading_calendar_store.py
│   │   │   │   └── trading_session_store.py
│   │   │   └── metadata_query_service.py
│   │   │
│   │   ├── features/                    # Features 域：特征数据
│   │   │   ├── technical/price/
│   │   │   ├── technical/volume/
│   │   │   ├── technical/volatility/
│   │   │   ├── fundamental/
│   │   │   └── features_query_service.py
│   │   │
│   │   ├── factors/                     # Factors 域：因子数据
│   │   │   ├── style/value/
│   │   │   ├── style/momentum/
│   │   │   ├── style/quality/
│   │   │   └── factors_query_service.py
│   │   │
│   │   └── macro/                       # Macro 域：宏观数据
│   │       ├── indicator/
│   │       │   ├── indicator_store.py
│   │       │   └── indicator_metadata_store.py
│   │       └── macro_query_service.py
│   │
│   └── stores/                          # 通用 Store
│       ├── base_store.py
│       ├── parquet/parquet_store.py
│       └── sqlite/sqlite_store.py
│
├── core/src/ditto_core/
│   ├── engines/
│   │   ├── feature_engine.py
│   │   ├── factor_engine.py
│   │   ├── expression_engine.py
│   │   ├── adj_factor_engine.py
│   │   └── post_processor.py
│   ├── features/
│   │   ├── technical/price/
│   │   ├── technical/volume/
│   │   └── fundamental/
│   └── factors/
│       ├── style/
│       └── post_processing/
│
└── port/src/ditto_port/
    └── services/
        ├── source_service.py
        ├── data_service.py
        ├── writer.py
        ├── ingestion_service.py
        ├── reconciliation_service.py
        └── strategy_service.py
```

---

## 四、企业级数据集格式规范

### 4.1 规范模板

每个数据集必须定义以下内容：

```yaml
dataset_id: "stock_daily"
domain: "market"
subdomain: "market/stock/bars"
storage_format: "parquet"
partition_strategy: "yearly"
storage_path: "data_root/market/stock/bars/daily/{year}.parquet"
config_key: "MARKET_STOCK_BARS_PATH"  # 配置键

# === 键列定义 ===
key_columns:
  - name: "sid"
    type: "int32"
    description: "证券内部标识符"
    nullable: false
    range: "[1_000_000, 1_999_999]"

  - name: "trade_date"
    type: "date"
    description: "交易日期"
    nullable: false

  - name: "source"
    type: "string"
    description: "数据源标识"
    nullable: false
    enum: ["tushare", "tdx", "akshare"]

# === 数据列定义 ===
data_columns:
  - name: "sid"
    type: "int32"
    description: "证券内部标识符"
    nullable: false

  - name: "symbol"
    type: "string"
    description: "证券代码（冗余存储，存储当时的值）"
    nullable: false
    note: "冗余存储用于查询便利和调试，与 securities.symbol 可能不同"

  - name: "src_code"
    type: "string"
    description: "数据源原始代码（用于数据溯源）"
    nullable: false
    example: "600000.SH"

  - name: "source"
    type: "string"
    description: "数据源标识"
    nullable: false

  - name: "open"
    type: "float64"
    description: "开盘价"
    unit: "元"
    precision: 2
    nullable: true

  - name: "high"
    type: "float64"
    description: "最高价"
    nullable: true

  - name: "low"
    type: "float64"
    description: "最低价"
    nullable: true

  - name: "close"
    type: "float64"
    description: "收盘价"
    nullable: true

  - name: "pre_close"
    type: "float64"
    description: "昨收价"
    nullable: true

  - name: "vol"
    type: "float64"
    description: "成交量（手）"
    unit: "手"
    precision: 0
    nullable: true

  - name: "amount"
    type: "float64"
    description: "成交额（元）"
    nullable: true

  - name: "pct_chg"
    type: "float64"
    description: "涨跌幅（小数）"
    unit: "小数"
    precision: 4
    nullable: true

# === 约束规则 ===
constraints:
  - rule: "ohlc_invariant"
    description: "low <= open/close <= high"
    severity: "error"

  - rule: "positive_volume"
    description: "vol >= 0"
    severity: "error"
```

---

## 五、完整数据集字段清单

### 5.1 Market 域数据集

#### stock_daily（股票日线行情）

| 列名 | 类型 | 描述 | 单位 | 精度 | 可空 |
|------|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | - | ✗ |
| symbol | string | 证券代码 | - | - | ✗ |
| src_code | string | 数据源原始代码 | - | - | ✗ |
| source | string | 数据源标识 | - | - | ✗ |
| trade_date | date | 交易日期 | - | - | ✗ |
| open | float64 | 开盘价 | 元 | 2 | ✓ |
| high | float64 | 最高价 | 元 | 2 | ✓ |
| low | float64 | 最低价 | 元 | 2 | ✓ |
| close | float64 | 收盘价 | 元 | 2 | ✓ |
| pre_close | float64 | 昨收价 | 元 | 2 | ✓ |
| vol | float64 | 成交量 | 手 | 0 | ✓ |
| amount | float64 | 成交额 | 元 | 2 | ✓ |
| pct_chg | float64 | 涨跌幅 | 小数 | 4 | ✓ |

**配置**：
- `MARKET_STOCK_BARS_PATH=data_root/market/stock/bars/daily`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

---

#### etf_daily（ETF日线行情）

| 列名 | 类型 | 描述 | 单位 | 精度 | 可空 |
|------|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | - | ✗ |
| symbol | string | 证券代码（冗余存储） | - | - | ✗ |
| src_code | string | 数据源原始代码 | - | - | ✗ |
| source | string | 数据源标识 | - | - | ✗ |
| trade_date | date | 交易日期 | - | - | ✗ |
| open | float64 | 开盘价 | 元 | 2 | ✓ |
| high | float64 | 最高价 | 元 | 2 | ✓ |
| low | float64 | 最低价 | 元 | 2 | ✓ |
| close | float64 | 收盘价 | 元 | 2 | ✓ |
| pre_close | float64 | 昨收价 | 元 | 2 | ✓ |
| vol | float64 | 成交量 | 手 | 0 | ✓ |
| amount | float64 | 成交额 | 元 | 2 | ✓ |
| pct_chg | float64 | 涨跌幅 | 小数 | 4 | ✓ |

**配置**：
- `MARKET_ETF_BARS_PATH=data_root/market/etf/bars/daily`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

**与 stock_daily 的对齐**：
- 字段结构完全一致，确保跨资产类型的统一处理
- symbol 冗余存储，便于查询便利和调试
- ETF 同样支持 OHLCV 数据，支持技术分析和特征计算

---

#### stock_status（股票状态）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| **共同字段** | - | - | - | - |
| sid | int32 | 证券内部标识符 | ✗ | - |
| symbol | string | 证券代码（冗余存储） | ✗ | 用于查询便利和调试 |
| src_code | string | 数据源原始代码 | ✗ | 用于数据溯源 |
| source | string | 数据源标识 | ✗ | - |
| trade_date | date | 交易日期 | ✗ | - |
| is_suspended | boolean | 是否停牌 | ✗ | - |
| suspension_reason | string | 停牌原因 | ✓ | 如：重大事项、筹划重大资产重组等 |
| **股票独有字段** | - | - | - | - |
| suspend_timing | string | 停牌时机 | ✓ | 枚举：开盘停牌/盘中停牌/复盘 |
| is_st | boolean | 是否ST股 | ✗ | 包括ST、*ST等 |
| st_type | string | ST类型 | ✓ | 如：ST、*ST、S*ST、SST等 |
| is_limit_up | boolean | 是否涨停 | ✗ | - |
| is_limit_down | boolean | 是否跌停 | ✗ | - |
| up_limit | float64 | 涨停价 | ✓ | 根据涨跌停板规则计算 |
| down_limit | float64 | 跌停价 | ✓ | 根据涨跌停板规则计算 |

**配置**：
- `MARKET_STOCK_STATUS_PATH=data_root/market/stock/status`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

---

#### etf_status（ETF状态）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| **共同字段** | - | - | - | - |
| sid | int32 | 证券内部标识符 | ✗ | - |
| symbol | string | 证券代码（冗余存储） | ✗ | 用于查询便利和调试 |
| src_code | string | 数据源原始代码 | ✗ | 用于数据溯源 |
| source | string | 数据源标识 | ✗ | - |
| trade_date | date | 交易日期 | ✗ | - |
| is_suspended | boolean | 是否停牌 | ✗ | 交易停牌 |
| suspension_reason | string | 停牌原因 | ✓ | - |
| **ETF独有字段** | - | - | - | - |
| is_suspended_subscription | boolean | 是否暂停申购 | ✗ | 申购状态 |
| is_suspended_redemption | boolean | 是否暂停赎回 | ✗ | 赎回状态 |
| suspension_duration_days | int32 | 停牌持续天数 | ✓ | 从停牌开始到当前的天数 |
| suspension_start_date | date | 停牌开始日期 | ✓ | - |
| suspension_end_date | date | 停牌结束日期 | ✓ | 预期或实际复牌日期 |
| total_assets | float64 | 基金资产总值 | ✓ | 单位：元 |
| total_shares | float64 | 基金份额 | ✓ | 单位：份 |
| discount_rate | float64 | 折溢价率 | ✓ | （市价-净值）/净值，小数形式 |
| is_discount | boolean | 是否折价 | ✗ | 折溢价率 < 0 |
| is_premium | boolean | 是否溢价 | ✗ | 折溢价率 > 0 |

**配置**：
- `MARKET_ETF_STATUS_PATH=data_root/market/etf/status`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

**对齐说明**：
- 共同字段确保跨资产类型的一致性，便于统一查询
- 股票独有字段反映股票市场特有机制（涨跌停、ST制度）
- ETF独有字段反映ETF特有机制（申赎状态、折溢价）

---

#### etf_nav（ETF净值）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ | - |
| symbol | string | 证券代码（冗余存储） | ✗ | 用于查询便利和调试 |
| src_code | string | 数据源原始代码 | ✗ | 用于数据溯源 |
| source | string | 数据源标识 | ✗ | - |
| trade_date | date | 交易日期 | ✗ | - |
| unit_nav | float64 | 单位净值 | ✓ | 单位：元 |
| accumulated_nav | float64 | 累计净值 | ✓ | 单位：元 |
| nav_date | date | 净值日期 | ✗ | 净值计算的基准日期 |
| total_assets | float64 | 基金资产总值 | ✓ | 单位：元 |
| total_shares | float64 | 基金份额 | ✓ | 单位：份 |

**配置**：
- `MARKET_ETF_NAV_PATH=data_root/market/etf/nav`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

---

#### stock_adj_factor（股票复权因子）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| source | string | 数据源标识 | ✗ |
| src_code | string | 数据源原始代码 | ✗ |
| adj_factor | float64 | 复权因子 | ✗ |
| knowledge_date | date | 知识生效日期 | ✗ |

**配置**：
- `MARKET_STOCK_ADJ_PATH=data_root/market/stock/adj`
- 存储格式：Parquet
- 分区策略：按年

---

#### etf_adj_factor（ETF复权因子）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| source | string | 数据源标识 | ✗ |
| src_code | string | 数据源原始代码 | ✗ |
| adj_factor | float64 | 复权因子 | ✗ |
| knowledge_date | date | 知识生效日期 | ✗ |

**配置**：
- `MARKET_ETF_ADJ_PATH=data_root/market/etf/adj`
- 存储格式：Parquet
- 分区策略：按年

**与 adj_factor 的关系**：
- 结构完全一致，便于统一处理
- 计算逻辑不同：ETF 主要处理现金分红，股票处理分红+送股+配股

---

#### index_daily（指数日线行情）

| 列名 | 类型 | 描述 | 单位 | 精度 | 可空 |
|------|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | - | ✗ |
| symbol | string | 证券代码（冗余存储） | - | - | ✗ |
| src_code | string | 数据源原始代码 | - | - | ✗ |
| source | string | 数据源标识 | - | - | ✗ |
| trade_date | date | 交易日期 | - | - | ✗ |
| open | float64 | 开盘点数 | 点 | 2 | ✓ |
| high | float64 | 最高点数 | 点 | 2 | ✓ |
| low | float64 | 最低点数 | 点 | 2 | ✓ |
| close | float64 | 收盘点数 | 点 | 2 | ✓ |
| pre_close | float64 | 昨收点数 | 点 | 2 | ✓ |
| vol | float64 | 成交量 | 手 | 0 | ✓ |
| amount | float64 | 成交额 | 元 | 2 | ✓ |
| pct_chg | float64 | 涨跌幅 | 小数 | 4 | ✓ |

**配置**：
- `MARKET_INDEX_BARS_PATH=data_root/market/index/bars/daily`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

**与 stock_daily/etf_daily 的对齐**：
- 字段结构完全一致，确保跨资产类型的统一处理
- 指数无"涨跌停"概念，但不影响核心 OHLCV 结构

---

### 5.2 Metadata 域数据集

#### securities（证券主数据-股票）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符（主键） | ✗ |
| symbol | string | 证券代码 | ✗ |
| name | string | 证券名称 | ✗ |
| display_name | string | 展示名称 | ✗ |
| exchange | string | 交易所 | ✗ |
| board | string | 板块 | ✓ |
| asset_class | string | 资产类别 | ✗ |
| list_date | date | 上市日期 | ✓ |
| delist_date | date | 退市日期 | ✓ |
| is_active | boolean | 是否活跃 | ✗ |
| is_st | boolean | 是否ST股 | ✗ |

**配置**：
- `SECURITY_DB_PATH=data_root/metadata/security/security.sqlite`
- 存储格式：SQLite

---

#### etf_basic（ETF主数据）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符（主键） | ✗ |
| symbol | string | 证券代码 | ✗ |
| name | string | 基金名称 | ✗ |
| display_name | string | 展示名称 | ✗ |
| exchange | string | 交易所 | ✗ |
| list_date | date | 上市日期 | ✓ |
| delist_date | date | 退市日期 | ✓ |
| is_active | boolean | 是否活跃 | ✗ |
| fund_type | string | 基金类型 | ✗ |
| tracking_index | string | 跟踪指数 | ✓ |
| fund_manager | string | 基金经理 | ✓ |
| fund_company | string | 基金公司 | ✓ |
| establishment_date | date | 成立日期 | ✓ |
| total_assets | float64 | 基金资产总值 | ✓ |
| total_shares | float64 | 基金份额 | ✓ |

**配置**：
- `ETF_BASIC_DB_PATH=data_root/metadata/etf/etf_basic.sqlite`
- 存储格式：SQLite

**与 securities 的关系**：
- etf_basic 与 securities 为独立的表，分别存储股票和ETF的主数据
- 两者使用不同的 sid 范围区分（详见 SID 分配策略）

---

#### index_basic（指数主数据）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符（主键） | ✗ | 使用独立段（3xxx） |
| symbol | string | 指数代码 | ✗ | 如：000300.SH |
| name | string | 指数名称 | ✗ | 如：沪深300 |
| display_name | string | 展示名称 | ✗ | - |
| exchange | string | 交易所/发布机构 | ✗ | SSE/SZSE/CIS/中证等 |
| asset_class | string | 资产类别 | ✗ | 固定值：INDEX |
| list_date | date | 发布日期 | ✗ | - |
| base_date | date | 基日 | ✗ | - |
| base_point | float64 | 基点 | ✗ | 通常为 100 或 1000 |
| index_type | string | 指数类型 | ✗ | 宽基/行业/主题/策略/债券 |
| weighting_method | string | 加权方式 | ✗ | 市值加权/等权/多因子 |
| num_constituents | int32 | 成分股数量 | ✓ | - |
| is_active | boolean | 是否活跃 | ✗ | - |

**配置**：
- `INDEX_BASIC_DB_PATH=data_root/metadata/index/index_basic.sqlite`
- 存储格式：SQLite

**与 securities 的关系**：
- index_basic 与 securities 为独立的表
- 指数作为一种特殊的证券类型，但因为有特有字段（基点、分类、加权方式），故独立存储

---

#### index_constituent（指数成分股）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| index_sid | int32 | 指数内部标识符 | ✗ | 关联 index_basic.sid |
| sid | int32 | 成分股标识符 | ✗ | 关联 securities.sid |
| source | string | 数据源标识 | ✗ | 如：中证、国证 |
| effective_from | date | 生效开始日期 | ✗ | - |
| effective_to | date | 生效结束日期 | ✓ | NULL 表示当前有效 |
| weight | float64 | 权重（小数） | ✓ | 如：0.05 表示 5% |
| entry_date | date | 入选日期 | ✗ | - |
| exit_date | date | 剔除日期 | ✓ | - |
| entry_reason | string | 入选原因 | ✓ | 如：定期调整、临时调整 |

**配置**：
- `INDEX_CONSTITUENT_DB_PATH=data_root/metadata/index/constituent/index_constituent.sqlite`
- 存储格式：SQLite
- 支持 PIT 查询

**核心作用**：
- 追踪指数成分历史变化（定期调整、临时调整）
- 支持权重查询（行业轮动策略需要）
- 支持反向查询（某股票在哪些指数中）

**约束规则**：
- `effective_from <= entry_date`
- `effective_to` 为 NULL 或 `effective_to > exit_date`
- `weight` 在 0-1 之间（如果提供）

---

#### etf_constituent（ETF成分股）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| etf_sid | int32 | ETF内部标识符 | ✗ | 关联 etf_basic.sid |
| sid | int32 | 成分股标识符 | ✗ | 关联 securities.sid |
| source | string | 数据源标识 | ✗ | 如：基金公司 |
| effective_from | date | 生效开始日期 | ✗ | - |
| effective_to | date | 生效结束日期 | ✓ | NULL 表示当前有效 |
| weight | float64 | 权重（小数） | ✓ | 如：0.05 表示 5% |
| shares | float64 | 持有股数 | ✓ | - |
| entry_date | date | 入选日期 | ✗ | - |
| exit_date | date | 剔除日期 | ✓ | - |
| entry_reason | string | 入选原因 | ✓ | 如：申购、赎回、定期调整 |

**配置**：
- `ETF_CONSTITUENT_DB_PATH=data_root/metadata/etf/constituent/etf_constituent.sqlite`
- 存储格式：SQLite
- 支持 PIT 查询

**与 index_constituent 的关系**：
- 结构基本一致，职责清晰分离
- ETF 特有字段：shares（持有股数）
- ETF 调整频率通常低于指数

---

#### universe（标的池定义）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| universe_id | string | 标的池标识符 | ✗ |
| universe_name | string | 标的池名称 | ✗ |
| universe_type | string | 标的池类型 | ✗ |
| description | string | 描述 | ✓ |
| created_at | datetime | 创建时间 | ✗ |
| created_by | string | 创建者 | ✗ |
| is_active | boolean | 是否活跃 | ✗ |

#### universe_constituent（标的池成分股）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| universe_id | string | 标的池标识符 | ✗ |
| sid | int32 | 成分股标识符 | ✗ |
| source | string | 数据源标识 | ✗ |
| effective_from | date | 生效开始日期 | ✗ |
| effective_to | date | 生效结束日期 | ✓ |
| weight | float64 | 权重 | ✓ |
| entry_reason | string | 入选原因 | ✓ |

**配置**：
- `UNIVERSE_DB_PATH=data_root/metadata/universe/universe.sqlite`
- 存储格式：SQLite
- 支持 PIT 查询

**职责重新定义**：

| 表 | 职责 | 数据来源 |
|---|---|------|
| **universe** | 用户自定义标的池定义 | 用户定义 |
| **universe_constituent** | 用户自定义标的池成分 | 用户定义 |
| **index_constituent** | 指数成分股（官方数据） | 官方 |
| **etf_constituent** | ETF 成分股（官方数据） | 官方 |

**universe 使用场景示例**：
- 策略股票池：白马股池、高股息池
- 行业轮动池：各行业代表股
- 回测标的池：剔除 ST、新股等

---

#### identity_mapping（Identity 映射）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ | - |
| source | string | 数据源标识 | ✗ | 如：tushare, tdx, akshare |
| src_code | string | 数据源原始代码 | ✗ | 用于与该数据源交互 |
| effective_from | date | 生效开始日期 | ✗ | - |
| effective_to | date | 生效结束日期 | ✓ | NULL 表示当前有效 |
| is_primary | boolean | 是否主标识符 | ✗ | 同一 source 下的主标识符 |

**配置**：
- `IDENTITY_DB_PATH=data_root/metadata/identity/identity_mapping.sqlite`
- 存储格式：SQLite
- 支持 PIT 查询

**核心作用：PIT（Point-in-Time）查询**

场景 1：股票更名
```
# 2024-01-01: 平安银行
(sid=1000001, source="tushare", src_code="000001.SZ",
 effective_from="2024-01-01", effective_to="2024-05-31")

# 2024-06-01: 更名为平安银行股份有限公司
(sid=1000001, source="tushare", src_code="000001.SZ",
 effective_from="2024-06-01", effective_to=NULL)
```

场景 2：不同源的代码对应关系
```
# Tushare 格式
(sid=1000001, source="tushare", src_code="600000.SH", ...)

# TDX 格式
(sid=1000001, source="tdx", src_code="SH600000", ...)
```

**设计原则**：
- ✅ 保留：用于 PIT 查询，记录 SID → src_code 的时序映射
- ✅ 简化：只保留核心字段，去除冗余
- ✅ 灵活：支持同一 SID 在不同时期对应不同 src_code
- ✅ 多源：支持不同数据源的代码映射

#### universe（标的池定义）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| universe_id | string | 标的池标识符 | ✗ |
| universe_name | string | 标的池名称 | ✗ |
| universe_type | string | 标的池类型 | ✗ |
| description | string | 描述 | ✓ |
| created_at | datetime | 创建时间 | ✗ |
| created_by | string | 创建者 | ✗ |
| is_active | boolean | 是否活跃 | ✗ |

#### universe_constituent（成分股）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| universe_id | string | 标的池标识符 | ✗ |
| sid | int32 | 成分股标识符 | ✗ |
| source | string | 数据源标识 | ✗ |
| effective_from | date | 生效开始日期 | ✗ |
| effective_to | date | 生效结束日期 | ✓ |
| weight | float64 | 权重 | ✓ |
| entry_reason | string | 入选原因 | ✓ |

**配置**：
- `UNIVERSE_DB_PATH=data_root/metadata/universe/universe.sqlite`
- 存储格式：SQLite
- 支持 PIT 查询

---

### 5.3 Features 域数据集

#### price_features（价格特征窄表）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| feature_id | string | 特征标识符 | ✗ |
| version | string | 版本号 | ✗ |
| value | float64 | 特征值 | ✓ |
| metadata | string | 元数据（JSON） | ✓ |

**特征 ID 示例**：
- 趋势类：`ma_5`, `ma_20`, `ema_12`
- 动量类：`rsi_14`, `macd`, `cci_20`
- 波动率类：`atr_14`, `hist_vol_20`

**配置**：
- `FEATURES_TECHNICAL_PRICE_PATH=data_root/features/technical/price`
- 存储格式：Parquet
- 分区策略：按年
- 版本管理：append_only

#### price_features_wide（价格特征宽表）

| 列名 | 类型 | 描述 |
|------|------|------|
| sid | int32 | 证券标识符 |
| trade_date | date | 交易日期 |
| ma_5 | float64 | 5日均线 |
| ma_20 | float64 | 20日均线 |
| rsi_14 | float64 | 14日RSI |
| ... | ... | 所有价格特征 |

**生成策略**：
- 从窄表 Pivot 生成
- 每周生成一次
- 用于高性能查询和 ML 训练

---

### 5.4 Factors 域数据集

#### style_factors（风格因子窄表）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券标识符 | ✗ |
| trade_date | date | 交易日期 | ✗ |
| factor_id | string | 因子标识符 | ✗ |
| version | string | 版本号 | ✗ |
| exposure | float64 | 因子暴露度（标准化后） | ✓ |
| raw_value | float64 | 原始因子值 | ✓ |
| metadata | string | 处理元数据（JSON） | ✓ |

**因子 ID 示例**：
- 价值类：`value_pe`, `value_pb`, `value_composite`
- 动量类：`momentum_1m`, `momentum_12m`
- 质量类：`quality_roe`, `quality_financial_health`
- 波动率类：`volatility_hist`, `volatility_idiosyncratic`

**配置**：
- `FACTORS_NARROW_STYLE_PATH=data_root/factors/narrow/style`
- 存储格式：Parquet
- 分区策略：按年
- 版本管理：append_only

#### style_factors_wide（风格因子宽表）

| 列名 | 类型 | 描述 |
|------|------|------|
| sid | int32 | 证券标识符 |
| trade_date | date | 交易日期 |
| value_pe | float64 | PE价值因子 |
| value_pb | float64 | PB价值因子 |
| momentum_12m | float64 | 12月动量因子 |
| quality_roe | float64 | ROE质量因子 |
| ... | ... | 所有风格因子 |

**生成策略**：
- 从窄表 Pivot 生成
- 每周生成一次
- 用于高性能查询和 ML 训练

---

### 5.5 Macro 域数据集

#### macro_indicators（宏观指标窄表，支持 PIT）

| 列名 | 类型 | 描述 | 可空 | 说明 |
|------|------|------|------|------|
| indicator_id | string | 指标标识符 | ✗ | 如：CPI_CN、GDP_CN、FED_RATE |
| indicator_name | string | 指标名称 | ✗ | 如：中国CPI、中国GDP |
| region | string | 区域/国家 | ✗ | CN、US、EU 等 |
| frequency | string | 频率 | ✗ | daily/monthly/quarterly/yearly |
| report_date | date | 报告期 | ✗ | 数据归属的统计周期 |
| publish_date | date | 发布日期 | ✗ | 数据实际发布日期 |
| knowledge_date | date | 知识生效日期 | ✗ | 市场知晓该数据的日期 |
| value | float64 | 指标值 | ✓ | - |
| unit | string | 单位 | ✓ | %、亿元、万人等 |
| source | string | 数据源标识 | ✗ | 如：央行、统计局、FRED |
| revision_type | string | 修正类型 | ✗ | 初值/修订值/最终值 |
| revision_version | int32 | 修正版本号 | ✗ | 0=初值, 1=第一次修订, 2=最终 |
| effective_from | date | 生效开始日期 | ✗ | 用于 PIT 查询 |
| effective_to | date | 生效结束日期 | ✓ | NULL 表示当前有效 |
| is_primary | boolean | 是否主值 | ✗ | 同一 report_date 下的主值 |

**配置**：
- `MACRO_INDICATORS_PATH=data_root/macro/indicators`
- 存储格式：Parquet
- 分区策略：按年
- 键列：`(indicator_id, report_date, revision_version, effective_from)`

**PIT 查询场景**：

```python
# 场景 1：2024年3月1日查询 2024年2月 CPI
# 结果：初值（假设 3月9日发布）
query(date="2024-03-01", indicator="CPI_CN", report_date="2024-02")
→ value=0.7, revision_type="初值", revision_version=0

# 场景 2：2024年3月15日查询 2024年2月 CPI
# 结果：修订值（假设 3月12日发布修订）
query(date="2024-03-15", indicator="CPI_CN", report_date="2024-02")
→ value=0.6, revision_type="修订值", revision_version=1
```

**指标 ID 示例**：

| 类别 | 指标 ID | 指标名称 | 频率 |
|------|---------|----------|------|
| **中国核心** | CPI_CN | 居民消费价格指数 | 月度 |
| | PPI_CN | 工业生产者出厂价格指数 | 月度 |
| | PMI_CN | 制造业采购经理指数 | 月度 |
| | M2_CN | 广义货币供应量 | 月度 |
| | SHIBOR_ON | 上海银行间同业拆放利率(隔夜) | 日度 |
| **美国核心** | FED_RATE | 联邦基金利率 | 日度 |
| | CPI_US | 美国CPI | 月度 |
| | NONFARM_PAYROLLS | 非农就业人数 | 月度 |
| | GDP_US | 美国GDP | 季度 |

---

#### macro_indicators_wide（宏观指标宽表）

| 列名 | 类型 | 描述 |
|------|------|------|
| report_date | date | 报告期 |
| region | string | 区域/国家 |
| CPI_CN | float64 | 中国CPI |
| PPI_CN | float64 | 中国PPI |
| PMI_CN | float64 | 中国PMI |
| M2_CN | float64 | 中国M2 |
| FED_RATE | float64 | 联邦基金利率 |
| CPI_US | float64 | 美国CPI |
| ... | ... | 所有宏观指标 |

**生成策略**：
- 从窄表 Pivot 生成
- 每周生成一次
- 用于宏观分析和可视化

---

#### macro_metadata（指标元数据）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| indicator_id | string | 指标标识符（主键） | ✗ |
| indicator_name | string | 指标名称 | ✗ |
| region | string | 区域/国家 | ✗ |
| frequency | string | 频率 | ✗ |
| unit | string | 单位 | ✓ |
| source | string | 数据源 | ✗ |
| source_url | string | 数据源URL | ✓ |
| description | string | 描述 | ✓ |
| is_active | boolean | 是否活跃 | ✗ |

**配置**：
- `MACRO_METADATA_DB_PATH=data_root/macro/metadata/macro_metadata.sqlite`
- 存储格式：SQLite

---

## 六、数据流转链路

### 6.1 完整流转图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         外部数据源层                                    │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │  Tushare API │  │   TDX 数据   │  │  AkShare API │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Port 层 - 数据摄入                                │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  IngestionService                                                 │ │
│  │                                                                   │ │
│  │  调用：                                                             │ │
│  │  1. SourceService.fetch_daily_bars()                               │ │
│  │     └─ TushareSource.fetch_daily_bars() → 标准格式                  │ │
│  │     └─ Enrichment → 添加 sid, symbol, source                       │ │
│  │  2. Writer.write_bars()                                          │ │
│  │     └─ BarsStore.write_bars()                                    │ │
│  │  3. ReconciliationService.reconcile_bars()                        │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DataHub 层（纯净存储）                             │
│                                                                         │
│  BarsStore → Parquet 文件                                              │
│  StatusStore → Parquet 文件                                            │
│  SecurityStore → SQLite 数据库                                         │
│  IdentityStore → SQLite 数据库                                         │
│  PriceFeaturesStore → Parquet 文件                                    │
│  StyleFactorsStore → Parquet 文件                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌─────────────────────────────┐     ┌─────────────────────────────────────┐
│      Port 层 - 数据查询      │     │      Core Engines（计算引擎）        │
├─────────────────────────────┤     ├─────────────────────────────────────┤
│                             │     │                                     │
│  DataService                │     │  FeatureEngine                       │
│  ├─ resolve_identity()      │     │  ├─ compute_features()                │
│  ├─ get_stock_bars()         │     │  └─ 编排具体特征计算器               │
│  └─ compute_features()       │     │                                     │
│                             │     │  FactorEngine                        │
│  调用：                      │     │  ├─ compute_factors()                 │
│  - MetadataQueryService      │     │  └─ 编排具体因子计算器               │
│  - MarketQueryService        │     │                                     │
│  - FeatureEngine             │     │  具体计算器：                        │
│  - FactorEngine              │     │  - MaFeature, RsiFeature            │
│                             │     │  - ValuePeFactor, MomentumFactor       │
└─────────────────────────────┘     └─────────────────────────────────────┘
```

### 6.2 Port 层服务依赖关系

| 服务 | 依赖 | 被依赖 |
|------|------|--------|
| **SourceService** | TushareSource, MetadataQueryService | IngestionService |
| **IngestionService** | SourceService, Writer, ReconciliationService | - |
| **DataService** | QueryService, Core Engine | IngestionService, ReconciliationService, StrategyService |
| **Writer** | Store | IngestionService, ReconciliationService |
| **ReconciliationService** | DataService | IngestionService |

---

## 七、组件职责边界

### 7.1 DataHub 层

| 组件 | 职责 | 特点 |
|------|------|------|
| **TushareSource** | API 调用 + 转换为标准格式 | ✅ 纯净，无内部依赖 |
| **BarsStore** | Parquet 文件读写 | ✅ 纯数据访问 |
| **MarketQueryService** | 编排 Store | ✅ 只接收 sid，无同层依赖 |
| **MetadataQueryService** | Identity 解析、证券信息 | ✅ 可被其他域调用 |

### 7.2 Core Engine 层

| 组件 | 职责 | 特点 |
|------|------|------|
| **FeatureEngine** | 特征计算编排 | 无状态 |
| **FactorEngine** | 因子计算编排 | 无状态 |
| **MaFeature** | MA 特征计算 | 无状态 |
| **ValuePeFactor** | PE 价值因子计算 | 无状态 |

### 7.3 Port 层

| 组件 | 职责 | 特点 |
|------|------|------|
| **SourceService** | 编排 Source + Enrichment | 处理 Identity 解析 |
| **IngestionService** | 数据摄入流程编排 | 调用 SourceService + Writer |
| **DataService** | 数据查询和编排 | 调用 QueryService + Core Engine |
| **Writer** | 统一写入入口 | 调用 DataHub Store |
| **ReconciliationService** | 质量对账 | 调用 DataService |

---

## 八、存储配置

### 8.1 极简配置设计（v3.0）

**设计原则**：
- **单 DATAROOT**：所有数据路径从 DATAROOT 自动生成
- **单 SQLite 库**：所有元数据表存储在单一 SQLite 文件中
- **Parquet 分区**：时序数据按年分区存储

### 8.2 配置文件

#### **config/development/filestore.env**

```bash
# ========== 唯一配置项 ==========
DATAROOT=data_root

# ========== 其他路径自动生成 ==========
# SQLite: {DATAROOT}/metadata/metadata.sqlite（所有表）
# Parquet: {DATAROOT}/{domain}/{subdomain}/{table}
```

### 8.3 SQLite 库文件结构（单库多表）

**文件路径**：`{DATAROOT}/metadata/metadata.sqlite`

| 表名 | 域 | 说明 | 支持PIT |
|------|---|------|--------|
| `securities` | Metadata | 股票主数据 | - |
| `etf_basic` | Metadata | ETF 主数据 | - |
| `index_basic` | Metadata | 指数主数据 | - |
| `index_constituent` | Metadata | 指数成分股 | ✅ |
| `etf_constituent` | Metadata | ETF 成分股 | ✅ |
| `industry_basic` | Metadata | 申万行业主数据 | ✅ |
| `industry_mapping` | Metadata | 股票-行业映射 | ✅ |
| `trading_calendar` | Metadata | 交易日历 | - |
| `trading_session` | Metadata | 交易时段 | - |
| `identity_mapping` | Metadata | Identity 映射 | ✅ |
| `universe` | Metadata | 标的池定义 | - |
| `universe_constituent` | Metadata | 标的池成分股 | ✅ |
| `macro_metadata` | Macro | 宏观指标元数据 | - |

**说明**：
- 所有元数据表存储在单一 SQLite 文件中
- 读多写少场景，单库简化管理
- 支持 PIT 的表使用 `effective_from/effective_to` 字段

### 8.4 Parquet 数据目录结构

```
{DATAROOT}/
├── market/
│   ├── stock/bars/daily/{year}.parquet
│   ├── stock/status/{year}.parquet
│   ├── stock/adj/{year}.parquet
│   ├── etf/bars/daily/{year}.parquet
│   ├── etf/status/{year}.parquet
│   ├── etf/nav/{year}.parquet
│   ├── etf/adj/{year}.parquet
│   └── index/bars/daily/{year}.parquet
├── capital/
│   ├── flow/market/{year}.parquet
│   ├── flow/industry/{year}.parquet
│   ├── flow/stock/{year}.parquet
│   ├── margin/detail/{year}.parquet
│   ├── margin/summary/{year}.parquet
│   ├── top_board/{year}.parquet
│   ├── limit/{year}.parquet
│   └── chip/{year}.parquet
├── fundamental/
│   ├── financial/balance_sheet/{year}.parquet
│   ├── financial/income_statement/{year}.parquet
│   ├── financial/cash_flow/{year}.parquet
│   ├── indicator/{year}.parquet
│   ├── forecast/{year}.parquet
│   ├── holding/fund/{year}.parquet
│   ├── holding/inst/{year}.parquet
│   ├── shareholder/{year}.parquet
│   └── dividend/{year}.parquet
├── macro/
│   └── indicators/{year}.parquet
├── features/
│   ├── technical/price/{year}.parquet
│   ├── technical/volume/{year}.parquet
│   └── fundamental/{year}.parquet
└── factors/
    ├── narrow/style/{year}.parquet
    └── wide/style/{year}.parquet
```

### 8.5 路径配置实现

```python
# packages/foundation/src/ditto_foundation/config/paths.py
from pathlib import Path

class DataPaths:
    """数据路径配置类"""

    def __init__(self, dataroot: Path | str):
        self.dataroot = Path(dataroot)

    # SQLite 路径（单库）
    @property
    def metadata_db(self) -> Path:
        """唯一的元数据 SQLite 库"""
        return self.dataroot / "metadata" / "metadata.sqlite"

    # Parquet 路径（按域生成）
    def market_stock_bars(self) -> Path:
        return self.dataroot / "market" / "stock" / "bars" / "daily"

    def capital_flow_market(self) -> Path:
        return self.dataroot / "capital" / "flow" / "market"

    def fundamental_balance_sheet(self) -> Path:
        return self.dataroot / "fundamental" / "financial" / "balance_sheet"

    # ... 其他路径按需生成
```

### 8.3 SID 分配策略

| 资产类别 | SID 范围 | 主数据表 |
|---------|---------|----------|
| 股票（STOCK） | 1,000,000 - 1,999,999 | securities |
| ETF（ETF） | 2,000,000 - 2,999,999 | etf_basic |
| 指数（INDEX） | 3,000,000 - 3,999,999 | index_basic |
| 期货（FUTURE） | 4,000,000 - 4,999,999 | （预留） |
| 债券（BOND） | 5,000,000 - 5,999,999 | （预留） |

**设计原则**：
- 每个资产类别使用独立的 SID 段，避免冲突
- 通过 sid 前缀快速识别资产类别
- 为未来扩展预留空间

---

## 九、实施路线图（v3.0）

### 9.1 阶段 1：基础层重构（P0）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 BaseStore 接口 | 定义统一的存储接口 | P0 |
| 实现 ParquetStore | 支持分区读写 | P0 |
| 实现 SQLiteStore | 支持单库多表 | P0 |
| 简化配置系统 | 只需 DATAROOT，自动生成路径 | P0 |
| 迁移现有 Accessor 到 Store | 去除 Accessor 层 | P0 |

### 9.2 阶段 2：Metadata 域与 Market 域（P0）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 metadata.sqlite 单库多表 | 所有元数据表合并 | P0 |
| 实现 industry_basic | 申万行业主数据 | P0 |
| 实现 industry_mapping | 股票-行业映射（支持 PIT） | P0 |
| 实现 trading_calendar | 交易日历 | P0 |
| 实现 trading_session | 交易时段 | P0 |
| 实现 MarketQueryService | Market 域统一入口 | P0 |
| 实现 MetadataQueryService | Metadata 域统一入口（含 IDResolver） | P0 |

### 9.3 阶段 3：Capital 域（新增）（P1）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| **资金流向数据** | | |
| 实现 market_flow | 市场级别北向/南向资金 | P1 |
| 实现 industry_flow | 行业级别资金分布 | P1 |
| 实现 stock_flow | 个股级别资金明细 | P1 |
| **融资融券数据** | | |
| 实现 margin_detail | 融资融券明细 | P1 |
| 实现 margin_summary | 融资融券市场汇总 | P1 |
| **其他资金数据** | | |
| 实现 top_board | 龙虎榜数据 | P1 |
| 实现 limit_board | 打板数据 | P2 |
| 实现 chip_distribution | 筹码分布 | P2 |
| **服务层** | | |
| 实现 CapitalQueryService | Capital 域统一入口 | P1 |

### 9.4 阶段 4：Fundamental 域（扩展）（P1）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| **财务报表** | | |
| 实现 balance_sheet | 资产负债表（支持 PIT） | P1 |
| 实现 income_statement | 利润表（支持 PIT） | P1 |
| 实现 cash_flow | 现金流量表（支持 PIT） | P1 |
| **财务指标** | | |
| 实现 financial_indicator | PE、PB、ROE 等指标 | P1 |
| **业绩预告** | | |
| 实现 forecast | 业绩预告（支持 PIT） | P1 |
| **持仓数据** | | |
| 实现 fund_holding | 公募基金持仓（季度前十大） | P1 |
| 实现 inst_holding | 其他机构持仓 | P2 |
| 实现 shareholder | 大股东持股 | P2 |
| **分红送转** | | |
| 实现 dividend | 分红送转数据 | P2 |
| **服务层** | | |
| 实现 FundamentalQueryService | Fundamental 域统一入口 | P1 |

### 9.5 阶段 5：指数与成分股数据（P0）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 index_basic 表 | 指数主数据 | P0 |
| 实现 index_daily 数据集 | 指数日线行情 | P0 |
| 实现 index_constituent 表 | 指数成分股（支持 PIT） | P0 |
| 实现 etf_constituent 表 | ETF 成分股（支持 PIT） | P0 |
| 实现 etf_adj_factor 数据集 | ETF 复权因子 | P0 |

### 9.6 阶段 6：Macro 域与 PIT 查询（P1）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 macro_indicators 数据集 | 宏观指标窄表（支持 PIT） | P1 |
| 实现 macro_metadata 表 | 指标元数据（单库） | P1 |
| 实现 MacroQueryService | Macro 域查询服务 | P1 |
| 实现 PIT 查询逻辑 | 支持初值/修订值/最终值查询 | P1 |

### 9.7 阶段 7：Core Engine（P1）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 FeatureEngine | 特征计算编排 | P1 |
| 实现具体特征计算器 | MA、RSI、MACD 等 | P1 |
| 实现 FactorEngine | 因子计算编排 | P1 |
| 实现具体因子计算器 | 价值、动量等 | P1 |
| 实现因子后处理 | 去极值、标准化、中性化 | P1 |

### 9.8 阶段 8：Features/Factors 存储（P1）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 PriceFeaturesStore | 窄表 + 宽表 | P1 |
| 实现 StyleFactorsStore | 窄表 + 宽表 | P1 |
| 实现宽表生成策略 | 定期 Pivot | P1 |

### 9.9 阶段 9：Port 层重构（P0）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现 SourceService | 编排 Source + Enrichment | P0 |
| 实现 IngestionService | 重构摄入流程 | P0 |
| 实现 DataService | 数据查询和编排 | P0 |
| 实现 Writer | 统一写入入口 | P0 |
| 实现 ReconciliationService | 质量对账 | P2 |

### 9.10 阶段 10：质量增强（P2）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 实现质量隔离区 | QuarantineStore | P2 |
| 实现黄金数据集 | 版本冻结 | P2 |
| 实现跨源对账 | Tushare vs TDX | P2 |

---

## 十、关键设计决策总结（v3.0）

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **数据域划分** | Market、Capital、Fundamental、Metadata、Macro、Features、Factors | 按数据性质划分，职责清晰 |
| **SQLite 库文件** | 单库多表（metadata.sqlite） | 读多写少，简化配置 |
| **配置复杂度** | 只需 DATAROOT，路径自动生成 | 简化运维，减少出错 |
| **域名选择** | Metadata 域（非 Reference） | 更直观，与业界一致 |
| **Fundamental 域** | 合并财务数据 + 公司行为 | 符合学术定义 |
| **Capital 域** | 资金流向 + 融资融券 + 龙虎榜 + 打板 + 筹码 | 聚焦交易行为数据 |
| **行业分类** | 申万（SW）标准 | 国内量化业界通用 |
| **交易日历** | 独立实现 | 重要元数据，支持多市场 |
| **Accessor 层** | 完全去除 | 职责与 QueryService 重叠 |
| **同层依赖** | 禁止 | DataHub 域级服务完全独立 |
| **Enrichment 位置** | Port 层 | DataHub 保持纯净 |
| **Identity 解析** | Port 层 SourceService | DataHub 不依赖其他域服务 |
| **symbol 存储** | 冗余存储到 stock_daily | 查询便利、调试友好 |
| **状态数据** | 单独存储 stock_status/etf_status | 职责清晰、稀疏存储 |
| **ETF 主数据** | 独立 etf_basic 表 | 与 securities 分离，职责清晰 |
| **ETF 状态数据** | etf_status 表，与 stock_status 对齐 | 共同字段统一，独有字段保留 |
| **ETF 净值数据** | 独立 etf_nav 表（Parquet） | 时序数据，按年分区 |
| **ETF 复权因子** | 独立存储 etf_adj_factor | 与股票复权逻辑不同 |
| **指数数据结构** | 与 stock_daily 对齐 | 跨资产类型统一处理 |
| **指数主数据** | 独立 index_basic 表 | 指数有特有字段（基点、分类、加权方式） |
| **成分股数据组织** | universe/etf_constituent/index_constituent 分离 | 职责清晰，数据来源区分 |
| **universe 职责** | 只用于用户自定义标的池 | 与官方成分股数据分离 |
| **宏观数据 PIT** | 支持 PIT 查询 | 宏观数据存在修正（初值/修订值/最终值） |
| **财务数据 PIT** | 支持 PIT 查询 | 财务报表可能追溯调整 |
| **行业映射 PIT** | 支持 PIT 查询 | 股票行业归属会变化 |
| **SID 分配** | 分段分配（股票1xxx、ETF 2xxx、指数3xxx） | 避免冲突，快速识别资产类别 |
| **特征/因子存储** | 窄表为主，宽表为辅 | 灵活性 vs 性能的平衡 |
| **async 支持** | 暂不引入 | 同步实现更简单 |

---

## 十一、附录：代码示例

### A.1 Store 实现

```python
# packages/datahub/src/ditto_datahub/stores/base_store.py
class BaseStore(ABC):
    """Store 基类"""

    @abstractmethod
    def get_data(self, filters, columns, **kwargs): pass

    @abstractmethod
    def write_data(self, data, mode="append"): pass
```

### A.2 SourceService 实现

```python
# packages/port/src/ditto_port/services/source_service.py
class SourceService:
    """数据源服务"""

    def __init__(self, tushare_source, metadata_service):
        self.tushare_source = tushare_source
        self.metadata_service = metadata_service

    def fetch_daily_bars(self, trade_date, source="tushare"):
        # 1. 获取标准格式
        data = self.tushare_source.fetch_daily_bars(trade_date)

        # 2. 增强（Identity 解析）
        data = self._enrich_with_identity(data, source)

        # 3. 添加 symbol
        data = self._enrich_with_symbol(data)

        return data
```

### A.3 IngestionService 实现

```python
# packages/port/src/ditto_port/services/ingestion_service.py
class IngestionService:
    """数据摄入服务"""

    def ingest_daily_bars(self, trade_date, source_name="tushare"):
        # 1. 获取增强后的数据
        data = self.source_service.fetch_daily_bars(trade_date, source_name)

        # 2. 写入
        self.writer.write_bars(data)

        # 3. 对账
        self.reconciliation_service.reconcile_bars(trade_date)
```

---

**文档版本**: v3.1
**创建日期**: 2026-01-26
**最后更新**: 2026-01-26
**状态**: 设计草案

**相关文档**:
- [2026-01-24-datahub-architecture-design.md](./2026-01-24-datahub-architecture-design.md)
- [2026-01-24-datahub-domain-architecture-design.md](./2026-01-24-datahub-domain-architecture-design.md)
- [2026-01-24-datahub-store-layer-design.md](./2026-01-24-datahub-store-layer-design.md)
- [2026-01-23-dataset-field-mapping.md](../plans/2026-01-23-dataset-field-mapping.md)

---

## 完整数据域清单（最终版 v3.0）

```
packages/datahub/src/ditto_datahub/domains/
├── market/                      # Market 域：基础市场数据
│   ├── stock/                   # 股票
│   ├── etf/                     # ETF
│   ├── index/                   # 指数
│   └── market_query_service.py
│
├── capital/                     # Capital 域：资金与交易行为（新增）
│   ├── flow/                    # 资金流向
│   ├── margin/                  # 融资融券
│   ├── top_board/               # 龙虎榜
│   ├── limit/                   # 打板数据
│   ├── chip/                    # 筹码分布
│   └── capital_query_service.py
│
├── fundamental/                 # Fundamental 域：财务与公司行为（扩展）
│   ├── financial/               # 财务报表
│   ├── indicator/               # 财务指标
│   ├── forecast/                # 业绩预告/快报
│   ├── holding/                 # 持仓数据
│   ├── dividend/                # 分红送转
│   └── fundamental_query_service.py
│
├── metadata/                    # Metadata 域：元数据（单 SQLite 库）
│   ├── security/                # 证券主数据
│   ├── industry/                # 行业分类（新增）
│   ├── index/                   # 指数主数据 + 成分股
│   ├── etf/                     # ETF 主数据 + 成分股
│   ├── identity/                # Identity 映射
│   ├── universe/                # 用户自定义标的池
│   ├── calendar/                # 交易日历（新增）
│   └── metadata_query_service.py
│
├── features/                    # Features 域：特征数据
│   └── features_query_service.py
│
├── factors/                     # Factors 域：因子数据
│   └── factors_query_service.py
│
└── macro/                       # Macro 域：宏观数据
    ├── indicator/
    └── macro_query_service.py
```

---

## 附录 A：Capital 域数据集字段规格（新增）

### A.1 market_flow（市场级别资金流）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| trade_date | date | 交易日期 | - | ✗ |
| flow_type | string | 资金类型 | - | ✗ |
| net_amount | float64 | 净流入额 | 亿元 | ✓ |
| buy_amount | float64 | 买入额 | 亿元 | ✓ |
| sell_amount | float64 | 卖出额 | 亿元 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**flow_type 枚举值**：`north_bound`（北向）、`south_bound`（南向）

**配置**：
- 存储路径：`{DATAROOT}/capital/flow/market/{year}.parquet`
- 分区策略：按年
- 键列：`(trade_date, flow_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `moneyflow_hsgt`（沪深港通资金流向） |
| **Tushare doc_id** | 47 |
| **积分要求** | 2000积分（基础），5000积分（高频） |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| trade_date | trade_date | 直接映射 | 交易日期 |
| flow_type | - | 枚举映射 | 根据不同字段生成记录 |
| net_amount | - | 计算字段 | 根据 flow_type 选择不同字段 |
| buy_amount | - | 计算字段 | - |
| sell_amount | - | 计算字段 | - |
| source | - | 固定值 | "tushare" |

**flow_type 枚举映射规则**：

| flow_type 值 | net_amount 来源 | buy_amount 来源 | sell_amount 来源 |
|-------------|----------------|----------------|----------------|
| north_bound | hgt | - | - |
| south_bound | sgt | - | - |
| ggt_ss | ggt_ss | - | - |
| ggt_sz | ggt_sz | - | - |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| trade_date | str | 交易日期 | YYYYMMDD |
| ggt_ss | float | 港股通（沪）净流入 | 万元 |
| ggt_sz | float | 港股通（深）净流入 | 万元 |
| hgt | float | 沪股通净流入 | 万元 |
| sgt | float | 深股通净流入 | 万元 |
| north_money | float | 北向资金净流入 | 万元 |
| south_money | float | 南向资金净流入 | 万元 |

**接口调用参数**：

```python
tushare.moneyflow_hsgt(
    trade_date="20240101",  # 交易日期
)
```

**数据转换逻辑**：

```python
# 单条 Tushare 记录扩展为多条设计记录
raw_data = {
    "trade_date": "20240101",
    "ggt_ss": 10000,
    "ggt_sz": 5000,
    "hgt": 20000,
    "sgt": 15000,
}

# 转换后
records = [
    {"trade_date": "2024-01-01", "flow_type": "ggt_ss", "net_amount": 10000},
    {"trade_date": "2024-01-01", "flow_type": "ggt_sz", "net_amount": 5000},
    {"trade_date": "2024-01-01", "flow_type": "hgt", "net_amount": 20000},
    {"trade_date": "2024-01-01", "flow_type": "sgt", "net_amount": 15000},
]
```

### A.2 industry_flow（行业级别资金流）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| trade_date | date | 交易日期 | - | ✗ |
| industry_code | string | 申万行业代码 | - | ✗ |
| industry_name | string | 申万行业名称 | - | ✗ |
| industry_level | int32 | 行业级别 | - | ✗ |
| net_amount | float64 | 净流入额 | 万元 | ✗ |
| main_net_amount | float64 | 主力净流入额 | 万元 | ✓ |
| retail_net_amount | float64 | 散户净流入额 | 万元 | ✓ |
| stock_count | int32 | 成分股数量 | 个 | ✗ |
| up_count | int32 | 上涨股票数 | 个 | ✓ |
| down_count | int32 | 下跌股票数 | 个 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/flow/industry/{year}.parquet`
- 分区策略：按年
- 键列：`(trade_date, industry_code, industry_level, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **数据来源** | 从 `stock_flow` 按 `industry_mapping` 聚合 |
| **基础接口** | `moneyflow` (doc_id=24) + `index_member_all` (doc_id=335) |
| **积分要求** | 2000 + 2000 = 4000积分 |
| **数据可用性** | ✅ 完全可用（聚合生成） |

**聚合逻辑**：

```python
import polars as pl

def aggregate_industry_flow(
    stock_flow_df: pl.DataFrame,
    industry_mapping_df: pl.DataFrame,
    trade_date: str,
    level: int = 1
) -> pl.DataFrame:
    """
    从个股资金流聚合行业资金流

    参数:
        stock_flow_df: 个股资金流数据 (从 stock_flow 表)
        industry_mapping_df: 行业成分股映射 (从 industry_mapping 表)
        trade_date: 交易日期
        level: 行业级别 (1=一级行业, 2=二级行业, 3=三级行业)
    """
    # 1. 获取指定日期的行业成分股
    level_col = f"industry_code_l{level}"
    components = industry_mapping_df.filter(
        (pl.col("effective_from") <= trade_date) &
        ((pl.col("effective_to").is_null()) | (pl.col("effective_to") > trade_date))
    ).select([
        "sid",
        pl.col(level_col).alias("industry_code")
    ])

    # 2. 关联个股资金流
    joined = stock_flow_df.filter(
        pl.col("trade_date") == trade_date
    ).join(
        components,
        on="sid",
        how="inner"
    )

    # 3. 按行业聚合
    result = joined.group_by("industry_code").agg([
        pl.col("net_amount").sum(),
        pl.col("main_net_amount").sum(),
        pl.col("retail_net_amount").sum(),
        pl.len().alias("stock_count"),
        (pl.col("net_amount") > 0).sum().alias("up_count"),
        (pl.col("net_amount") < 0).sum().alias("down_count"),
        pl.first("source"),
    ])

    # 4. 添加行业名称和元数据
    result = result.with_columns([
        pl.lit(trade_date).str.strptime(pl.Date, "%Y%m%d").alias("trade_date"),
        pl.lit(level).alias("industry_level"),
    ])

    return result
```

**字段说明**：

| 设计字段 | 聚合方式 | 说明 |
|---------|---------|------|
| trade_date | - | 从 stock_flow 继承 |
| industry_code | - | 从 industry_mapping 的 L1/L2/L3 字段获取 |
| industry_name | - | 从 industry_basic 关联获取 |
| industry_level | - | 1（一级）、2（二级）、3（三级） |
| net_amount | SUM() | 个股 net_amount 的行业总和 |
| main_net_amount | SUM() | 个股 main_net_amount 的行业总和 |
| retail_net_amount | SUM() | 个股 retail_net_amount 的行业总和 |
| stock_count | COUNT() | 行业内有资金流数据的股票数量 |
| up_count | COUNT(net_amount > 0) | 净流入为正的股票数量 |
| down_count | COUNT(net_amount < 0) | 净流入为负的股票数量 |
| source | FIRST() | 继承 stock_flow 的 source |

**实现步骤**：

1. **获取个股资金流数据**：
   ```python
   # 从 stock_flow 表获取指定日期的个股资金流
   df_stock = load_stock_flow(trade_date="20240101")
   ```

2. **获取行业成分股映射**：
   ```python
   # 从 industry_mapping 表获取申万行业成分股
   # 使用 PIT 查询获取指定日期的有效映射
   df_mapping = load_industry_mapping(
       trade_date="20240101",
       level=1  # 一级行业
   )
   ```

3. **关联并聚合**：
   ```python
   # 按 sid 关联，然后按 industry_code 聚合
   df_industry = df_stock.join(df_mapping, on="sid")\
                        .group_by("industry_code")\
                        .agg(...)
   ```

4. **添加行业名称**：
   ```python
   # 从 industry_basic 表关联行业名称
   df_industry = df_industry.join(
       load_industry_basic(),
       on="industry_code"
   )
   ```

**存储策略**：

```python
# 分别存储不同级别的行业资金流
for level in [1, 2, 3]:
    df = aggregate_industry_flow(
        stock_flow_df,
        industry_mapping_df,
        trade_date,
        level=level
    )
    # 存储到对应路径
    save_to_parquet(
        df,
        f"{DATAROOT}/capital/flow/industry/l{level}/{year}.parquet"
    )
```

**注意事项**：
- 使用申万行业分类（SW2021 或 SW2014），与 industry_basic、industry_mapping 保持一致
- 支持多级行业（L1/L2/L3），通过参数控制
- 需要使用 PIT 查询获取指定日期的有效行业成分股
- stock_count 反映的是**有资金流数据**的成分股数量，而非行业全部成分股
- 如需获取全部成分股数量，需单独统计 industry_mapping 表

### A.3 stock_flow（个股级别资金流）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| symbol | string | 证券代码（冗余存储） | - | ✗ |
| trade_date | date | 交易日期 | - | ✗ |
| flow_type | string | 资金类型 | - | ✗ |
| net_amount | float64 | 净流入额 | 万元 | ✓ |
| main_net_amount | float64 | 主力净流入额 | 万元 | ✓ |
| retail_net_amount | float64 | 散户净流入额 | 万元 | ✓ |
| large_order_ratio | float64 | 大单成交占比 | 小数 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/flow/stock/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, flow_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `moneyflow`（个股资金流向） |
| **Tushare doc_id** | 24 |
| **积分要求** | 2000积分（基础），5000积分（高频） |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| symbol | ts_code | 格式转换 | 600000.SH → 600000 |
| trade_date | trade_date | 直接映射 | 交易日期 |
| flow_type | - | 固定值 | "individual_flow" |
| net_amount | net_mf_vol | 直接映射 | 净流入额（万元） |
| main_net_amount | net_amt_main | 直接映射 | 主力净流入（万元） |
| retail_net_amount | net_amt_retail | 直接映射 | 散户净流入（万元） |
| large_order_ratio | - | 计算字段 | (超大单+大单)/总成交量 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| trade_date | str | 交易日期 | YYYYMMDD |
| net_mf_vol | float | 净流入额 | 万元 |
| net_pct_main | float | 主力净流入占比 | 小数 |
| net_amt_main | float | 主力净流入额 | 万元 |
| net_amt_xl | float | 超大单净流入 | 万元 |
| net_amt_l | float | 大单净流入 | 万元 |
| net_amt_m | float | 中单净流入 | 万元 |
| net_amt_s | float | 小单净流入 | 万元 |
| net_amt_retail | float | 散户净流入 | 万元 |

**接口调用参数**：

```python
tushare.moneyflow(
    ts_code="600000.SH",      # 股票代码
    trade_date="20240101",    # 交易日期
)
```

**数据转换逻辑**：

```python
# large_order_ratio 计算
large_order_ratio = (net_amt_xl + net_amt_l) / net_mf_vol if net_mf_vol != 0 else 0
```

**注意事项**：
- 需要通过 identity_mapping 将 ts_code 转换为 sid
- symbol 字段存储去除交易所后缀的代码（如 600000）
- 数据按个股调用，批量获取需要循环调用

### A.4 margin_detail（融资融券明细）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| symbol | string | 证券代码（冗余存储） | - | ✗ |
| trade_date | date | 交易日期 | - | ✗ |
| fin_buy_amount | float64 | 融资买入额 | 元 | ✓ |
| fin_repay_amount | float64 | 融资偿还额 | 元 | ✓ |
| fin_balance | float64 | 融资余额 | 元 | ✗ |
| sec_sell_amount | float64 | 融券卖出量 | 股 | ✓ |
| sec_buy_amount | float64 | 融券买入量 | 股 | ✓ |
| sec_balance | float64 | 融券余量 | 股 | ✗ |
| sec_balance_value | float64 | 融券余额 | 元 | ✓ |
| margin_balance | float64 | 融资融券余额 | 元 | ✗ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/margin/detail/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `mtsk`（融资融券明细） |
| **Tushare doc_id** | 30 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| symbol | ts_code | 格式转换 | 600000.SH → 600000 |
| trade_date | trade_date | 直接映射 | 交易日期 |
| fin_buy_amount | fin_buy_amount | 直接映射 | 融资买入额（元） |
| fin_repay_amount | fin_repay_amount | 直接映射 | 融资偿还额（元） |
| fin_balance | fin_balance | 直接映射 | 融资余额（元） |
| sec_sell_amount | sec_sell_amount | 直接映射 | 融券卖出量（股） |
| sec_buy_amount | sec_buy_amount | 直接映射 | 融券买入量（股） |
| sec_balance | sec_balance | 直接映射 | 融券余量（股） |
| sec_balance_value | sec_balance_value | 直接映射 | 融券余额（元） |
| margin_balance | - | 计算字段 | fin_balance + sec_balance_value |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| trade_date | str | 交易日期 | YYYYMMDD |
| fin_buy_amount | float | 融资买入额 | 元 |
| fin_repay_amount | float | 融资偿还额 | 元 |
| fin_balance | float | 融资余额 | 元 |
| sec_sell_amount | float | 融券卖出量 | 股 |
| sec_buy_amount | float | 融券买入量 | 股 |
| sec_balance | float | 融券余量 | 股 |
| sec_balance_value | float | 融券余额 | 元 |

**接口调用参数**：

```python
tushare.mtsk(
    ts_code="600000.SH",      # 股票代码
    trade_date="20240101",    # 交易日期
)
```

**注意事项**：
- 需要通过 identity_mapping 将 ts_code 转换为 sid
- margin_balance 为计算字段，需要自行计算
- 数据按个股调用，批量获取需要循环调用

### A.5 margin_summary（融资融券市场汇总）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| trade_date | date | 交易日期 | - | ✗ |
| fin_buy_amount | float64 | 市场融资买入额 | 元 | ✓ |
| fin_balance | float64 | 市场融资余额 | 元 | ✗ |
| sec_sell_amount | float64 | 市场融券卖出量 | 股 | ✓ |
| sec_balance | float64 | 市场融券余量 | 股 | ✗ |
| margin_balance | float64 | 市场融资融券余额 | 元 | ✗ |
| fin_margin_stock_count | int32 | 融资融券标的数量 | 只 | ✗ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/margin/summary/{year}.parquet`
- 分区策略：按年
- 键列：`(trade_date, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `mtsk_sec`（融资融券汇总） |
| **Tushare doc_id** | 31 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| trade_date | trade_date | 直接映射 | 交易日期 |
| fin_buy_amount | fin_buy_amount | 直接映射 | 市场融资买入额（元） |
| fin_balance | fin_balance | 直接映射 | 市场融资余额（元） |
| sec_sell_amount | sec_sell_amount | 直接映射 | 市场融券卖出量（股） |
| sec_balance | sec_balance | 直接映射 | 市场融券余量（股） |
| margin_balance | - | 计算字段 | fin_balance + sec_balance_value |
| fin_margin_stock_count | - | 计算字段 | 统计当日有融资融券的股票数量 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| trade_date | str | 交易日期 | YYYYMMDD |
| fin_buy_amount | float | 市场融资买入额 | 元 |
| fin_balance | float | 市场融资余额 | 元 |
| sec_sell_amount | float | 市场融券卖出量 | 股 |
| sec_balance | float | 市场融券余量 | 股 |
| sec_balance_value | float | 市场融券余额 | 元 |

**接口调用参数**：

```python
tushare.mtsk_sec(
    trade_date="20240101",    # 交易日期
)
```

**注意事项**：
- fin_margin_stock_count 需要从 margin_detail 聚合统计
- margin_balance 为计算字段，需要自行计算

### A.6 top_board（龙虎榜）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| symbol | string | 证券代码（冗余存储） | ✗ |
| trade_date | date | 交易日期 | ✗ |
| reason | string | 上榜原因 | ✗ |
| direction | string | 买卖方向 | ✓ |
| buy_amount | float64 | 买入金额 | 元 | ✓ |
| sell_amount | float64 | 卖出金额 | 元 | ✓ |
| net_amount | float64 | 净买卖金额 | 元 | ✓ |
| buy_seats | string | 买入席位 | ✓ |
| sell_seats | string | 卖出席位 | ✓ |
| source | string | 数据源标识 | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/top_board/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, reason, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `top_list`（龙虎榜每日明细）+ `top_inst`（龙虎榜机构明细） |
| **Tushare doc_id** | 106（top_list）、107（top_inst） |
| **积分要求** | 2000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段（top_list） | 数据转换 | 说明 |
|---------|---------------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| symbol | ts_code | 格式转换 | 600000.SH → 600000 |
| trade_date | trade_date | 直接映射 | 交易日期 |
| reason | reason | 直接映射 | 上榜原因 |
| direction | - | 计算字段 | 根据 buy/sell 计算 |
| buy_amount | l_buy | 直接映射 | 买入额（元） |
| sell_amount | l_sell | 直接映射 | 卖出额（元） |
| net_amount | net_amount | 直接映射 | 净买卖金额（元） |
| buy_seats | exalter（top_inst） | 拼接字段 | side=0 的营业部名称（用 \| 拼接） |
| sell_seats | exalter（top_inst） | 拼接字段 | side=1 的营业部名称（用 \| 拼接） |
| source | - | 固定值 | "tushare" |

**top_list 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| trade_date | str | 交易日期 | YYYYMMDD |
| name | str | 股票名称 | - |
| close | float | 收盘价 | 元 |
| pct_change | float | 涨跌幅 | 小数 |
| turnover_rate | float | 换手率 | 小数 |
| amount | float | 总成交额 | 元 |
| l_sell | float | 龙虎榜卖出额 | 元 |
| l_buy | float | 龙虎榜买入额 | 元 |
| l_amount | float | 龙虎榜成交额 | 元 |
| net_amount | float | 龙虎榜净买入额 | 元 |
| net_rate | float | 龙虎榜净买额占比 | 小数 |
| amount_rate | float | 龙虎榜成交额占比 | 小数 |
| float_values | float | 当日流通市值 | 元 |
| reason | str | 上榜理由 | - |

**top_inst 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| trade_date | str | 交易日期 | YYYYMMDD |
| ts_code | str | TS代码 | - |
| exalter | str | 营业部名称 | - |
| side | str | 买卖类型（0：买入，1：卖出） | - |
| buy | float | 买入额（元） | 元 |
| buy_rate | float | 买入占总成交比例 | 小数 |
| sell | float | 卖出额（元） | 元 |
| sell_rate | float | 卖出占总成交比例 | 小数 |
| net_buy | float | 净成交额（元） | 元 |
| reason | str | 上榜理由 | - |

**接口调用参数**：

```python
# 龙虎榜每日明细
tushare.top_list(
    trade_date="20240101",    # 交易日期
    ts_code="600000.SH",      # 股票代码（可选）
)

# 龙虎榜机构明细
tushare.top_inst(
    trade_date="20240101",    # 交易日期
    ts_code="600000.SH",      # 股票代码（可选）
)
```

**数据转换逻辑**：

```python
# 方向计算
direction = "买入" if l_buy > l_sell else "卖出"

# 席位拼接（从 top_inst 接口）
buy_seats = "|".join([r["exalter"] for r in inst_records if r["side"] == "0"])
sell_seats = "|".join([r["exalter"] for r in inst_records if r["side"] == "1"])
```

**注意事项**：
- 需要同时调用 `top_list` 和 `top_inst` 两个接口
- `top_list` 提供买卖金额汇总
- `top_inst` 提供机构席位明细
- 需要通过 identity_mapping 将 ts_code 转换为 sid

### A.7 limit_board（打板数据）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| symbol | string | 证券代码（冗余存储） | ✗ |
| trade_date | date | 交易日期 | ✗ |
| limit_type | string | 涨跌停类型 | ✗ |
| limit_time | string | 封板时间 | ✓ |
| open_times | int32 | 打开次数 | ✓ |
| limit_order_amount | float64 | 封单额 | 元 | ✓ |
| break_order_amount | float64 | 炸单额 | 元 | ✓ |
| last_limit_price | float64 | 最后封板价 | 元 | ✓ |
| source | string | 数据源标识 | ✗ |

**limit_type 枚举值**：`limit_up`（涨停）、`limit_down`（跌停）

**配置**：
- 存储路径：`{DATAROOT}/capital/limit/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, limit_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `limit_list_d`（涨跌停列表）+ `limit_step`（连板天梯） |
| **Tushare doc_id** | 298（limit_list_d）、356（limit_step） |
| **积分要求** | 5000积分（limit_list_d），8000积分（limit_step） |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| symbol | ts_code | 格式转换 | 600000.SH → 600000 |
| trade_date | trade_date | 直接映射 | 交易日期 |
| limit_type | limit | 枚举映射 | U→limit_up, D→limit_down, Z→limit_up（炸板） |
| limit_time | first_time | 直接映射 | 首次封板时间 |
| open_times | open_times | 直接映射 | 炸板次数（跌停为开板次数） |
| limit_order_amount | fd_amount | 直接映射 | 封单金额（元） |
| break_order_amount | limit_amount | 直接映射 | 炸板成交金额（元，仅炸板有） |
| last_limit_price | close | 直接映射 | 收盘价（封板价） |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

**limit_list_d 接口（主要数据源）**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| trade_date | str | 交易日期 | YYYYMMDD |
| ts_code | str | 股票代码 | - |
| name | str | 股票名称 | - |
| close | float | 收盘价 | 元 |
| pct_chg | float | 涨跌幅 | % |
| amount | float | 成交额 | 元 |
| limit_amount | float | 板上成交金额 | 元（仅炸板） |
| fd_amount | float | 封单金额 | 元 |
| float_mv | float | 流通市值 | 元 |
| total_mv | float | 总市值 | 元 |
| turnover_ratio | float | 换手率 | % |
| first_time | str | 首次封板时间 | HH:MM:SS |
| last_time | str | 最后封板时间 | HH:MM:SS |
| open_times | int | 炸板次数 | 次 |
| up_stat | str | 涨停统计 | N/T |
| limit_times | int | 连板数 | 天 |
| limit | str | D跌停U涨停Z炸板 | - |
| industry | str | 所属行业 | - |

**limit_step 接口（连板数据补充）**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| name | str | 股票名称 | - |
| trade_date | str | 交易日期 | YYYYMMDD |
| nums | str | 连板次数 | 天 |

**Tushare 接口调用**：

```python
import tushare as ts

pro = ts.pro_api("your_token")

# 涨停板数据
df = pro.limit_list_d(
    trade_date="20240101",
    limit_type="U",  # U涨停 D跌停 Z炸板
    fields="ts_code,trade_date,name,close,pct_chg,amount,fd_amount,first_time,last_time,open_times,limit_times,limit"
)

# 跌停板数据
df = pro.limit_list_d(trade_date="20240101", limit_type="D")

# 炸板数据
df = pro.limit_list_d(trade_date="20240101", limit_type="Z")

# 连板天梯数据
df = pro.limit_step(trade_date="20240101")

# 按日期范围获取
df = pro.limit_list_d(
    start_date="20240101",
    end_date="20240131"
)
```

**数据转换示例**：

```python
import polars as pl

def transform_limit_data(df: pl.DataFrame) -> pl.DataFrame:
    """转换 Tushare limit_list_d 数据为设计格式"""
    return df.select(
        sid=pl.col("ts_code").map_elements(resolve_sid, return_dtype=pl.Int32),
        symbol=pl.col("ts_code").str.replace(r"\.\w+$", ""),
        trade_date=pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d"),
        limit_type=pl.when(pl.col("limit") == "U")
            .then(pl.lit("limit_up"))
            .when(pl.col("limit") == "D")
            .then(pl.lit("limit_down"))
            .otherwise(pl.lit("limit_up")),  # Z 炸板归类为涨停
        limit_time=pl.col("first_time"),
        open_times=pl.col("open_times"),
        limit_order_amount=pl.col("fd_amount"),
        break_order_amount=pl.coalesce(pl.col("limit_amount"), 0.0),
        last_limit_price=pl.col("close"),
        source=pl.lit("tushare")
    )
```

**注意事项**：
- 需要同时调用 `limit_list_d` 和 `limit_step` 两个接口
- `limit_list_d` 提供涨跌停和炸板的基本数据
- `limit_step` 提供连板天梯数据，可用于补充 `limit_times` 字段
- `limit_type` 字段：U（涨停）、D（跌停）、Z（炸板）
- 数据从 2020 年开始，不提供 ST 股票的统计
- 5000积分每分钟可请求200次，8000积分以上每分钟500次（每天不限制）

### A.8 chip_distribution（筹码分布）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| symbol | string | 证券代码（冗余存储） | ✗ |
| trade_date | date | 交易日期 | ✗ |
| price_range | string | 价格区间 | ✗ |
| chip_ratio | float64 | 筹码比例 | 小数 | ✗ |
| concentration_ratio | float64 | 集中度 | 小数 | ✓ |
| source | string | 数据源标识 | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/capital/chip/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, price_range, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `cyq_chips`（筹码分布） |
| **Tushare doc_id** | 294 |
| **积分要求** | 5000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| symbol | ts_code | 格式转换 | 600000.SH → 600000 |
| trade_date | trade_date | 直接映射 | 交易日期 |
| price_range | - | 计算字段 | 根据价格区间划分 |
| chip_ratio | ratio | 直接映射 | 筹码比例（小数） |
| concentration_ratio | - | 计算字段 | 计算集中度指标 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| trade_date | str | 交易日期 | YYYYMMDD |
| price | float | 价格 | 元 |
| ratio | float | 筹码比例 | 小数 |
| amount | float | 筹码量 | 股 |

**接口调用参数**：

```python
tushare.cyq_chips(
    ts_code="600000.SH",      # 股票代码
    trade_date="20240101",    # 交易日期
)
```

**数据转换逻辑**：

```python
# price_range 生成逻辑（示例）
# 将连续价格划分为离散区间
price_ranges = []
for i in range(0, 100, 5):  # 每5%一个区间
    price_ranges.append(f"{i}-{i+5}%")

# concentration_ratio 计算逻辑（示例）
# 可以使用赫芬达尔指数或其他集中度指标
concentration_ratio = sum([r**2 for r in ratios])
```

**注意事项**：
- 需要通过 identity_mapping 将 ts_code 转换为 sid
- price_range 需要根据价格区间自定义划分规则
- concentration_ratio 可以使用多种计算方式（如赫芬达尔指数）

---

## 附录 B：Fundamental 域数据集字段规格（新增）

### B.1 balance_sheet（资产负债表）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| report_date | date | 报告期 | - | ✗ |
| report_type | string | 报告类型 | - | ✗ |
| publish_date | date | 发布日期 | - | ✗ |
| total_assets | float64 | 总资产 | 元 | ✓ |
| total_liabilities | float64 | 总负债 | 元 | ✓ |
| total_equity | float64 | 股东权益 | 元 | ✓ |
| current_assets | float64 | 流动资产 | 元 | ✓ |
| current_liabilities | float64 | 流动负债 | 元 | ✓ |
| fixed_assets | float64 | 固定资产 | 元 | ✓ |
| intangible_assets | float64 | 无形资产 | 元 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**report_type 枚举值**：`Q1`（一季报）、`Q2`（中报）、`Q3`（三季报）、`Q4`（年报）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/financial/balance_sheet/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, report_date, report_type, source)`
- **支持 PIT 查询**（通过 publish_date）

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `balancesheet`（资产负债表） |
| **Tushare doc_id** | 6 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| report_date | end_date | 直接映射 | 报告期 |
| report_type | - | 根据 report_date 推断 | Q1/Q2/Q3/Q4 |
| publish_date | - | 使用 `fina_indicator` 接口获取 | 需要额外接口获取发布日期 |
| total_assets | total_assets | 直接映射 | 总资产（元） |
| total_liabilities | total_hldr_eqy_exc_min_int | 直接映射 | 总负债（元） |
| total_equity | total_equity | 直接映射 | 股东权益（元） |
| current_assets | total_current_assets | 直接映射 | 流动资产（元） |
| current_liabilities | total_current_liab | 直接映射 | 流动负债（元） |
| fixed_assets | fix_assets | 直接映射 | 固定资产（元） |
| intangible_assets | intangible_assets | 直接映射 | 无形资产（元） |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**（部分主要字段）：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| f_ann_date | str | 实际公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| report_type | str | 报告类型 | - |
| comp_type | str | 公司类型 | - |
| basic_eps | float | 基本每股收益 | - |
| total_assets | float | 资产总计 | 元 |
| total_hldr_eqy_exc_min_int | float | 负债合计 | 元 |
| total_equity | float | 股东权益合计 | 元 |
| total_current_assets | float | 流动资产合计 | 元 |
| total_current_liab | float | 流动负债合计 | 元 |
| fix_assets | float | 固定资产 | 元 |
| intangible_assets | float | 无形资产 | 元 |

**接口调用参数**：

```python
tushare.balancesheet(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)
```

**注意事项**：
- publish_date 需要从 `fina_indicator` 接口获取
- report_type 需要根据 end_date 推断（0331=Q1, 0630=Q2, 0930=Q3, 1231=Q4）
- 需要通过 identity_mapping 将 ts_code 转换为 sid

### B.2 income_statement（利润表）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| report_date | date | 报告期 | - | ✗ |
| report_type | string | 报告类型 | - | ✗ |
| publish_date | date | 发布日期 | - | ✗ |
| total_revenue | float64 | 营业总收入 | 元 | ✓ |
| operating_revenue | float64 | 营业收入 | 元 | ✓ |
| operating_cost | float64 | 营业成本 | 元 | ✓ |
| net_profit | float64 | 净利润 | 元 | ✓ |
| net_profit_parent | float64 | 归母净利润 | 元 | ✓ |
| operating_profit | float64 | 营业利润 | 元 | ✓ |
| total_profit | float64 | 利润总额 | 元 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/fundamental/financial/income_statement/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, report_date, report_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `income`（利润表） |
| **Tushare doc_id** | 5 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| report_date | end_date | 直接映射 | 报告期 |
| report_type | - | 根据 end_date 推断 | Q1/Q2/Q3/Q4 |
| publish_date | - | 使用 `fina_indicator` 接口获取 | 需要额外接口获取 |
| total_revenue | total_revenue | 直接映射 | 营业总收入（元） |
| operating_revenue | revenue | 直接映射 | 营业收入（元） |
| operating_cost | total_operating_cost | 直接映射 | 营业成本（元） |
| net_profit | net_profit | 直接映射 | 净利润（元） |
| net_profit_parent | np_parent_company_owners | 直接映射 | 归母净利润（元） |
| operating_profit | operate_profit | 直接映射 | 营业利润（元） |
| total_profit | total_profit | 直接映射 | 利润总额（元） |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**（部分主要字段）：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| f_ann_date | str | 实际公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| report_type | str | 报告类型 | - |
| total_revenue | float | 营业总收入 | 元 |
| revenue | float | 营业收入 | 元 |
| total_operating_cost | float | 营业总成本 | 元 |
| operate_profit | float | 营业利润 | 元 |
| total_profit | float | 利润总额 | 元 |
| net_profit | float | 净利润 | 元 |
| np_parent_company_owners | float | 归母所有者净利润 | 元 |

**接口调用参数**：

```python
tushare.income(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)
```

**注意事项**：
- publish_date 需要从 `fina_indicator` 接口获取
- report_type 需要根据 end_date 推断
- 需要通过 identity_mapping 将 ts_code 转换为 sid

### B.3 cash_flow（现金流量表）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| report_date | date | 报告期 | - | ✗ |
| report_type | string | 报告类型 | - | ✗ |
| publish_date | date | 发布日期 | - | ✗ |
| operating_cash_flow | float64 | 经营活动现金流 | 元 | ✓ |
| investing_cash_flow | float64 | 投资活动现金流 | 元 | ✓ |
| financing_cash_flow | float64 | 筹资活动现金流 | 元 | ✓ |
| net_cash_flow | float64 | 现金及现金等价物净增加 | 元 | ✓ |
| source | string | 数据源标识 | - | ✗ |

**配置**：
- 存储路径：`{DATAROOT}/fundamental/financial/cash_flow/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, report_date, report_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `cashflow`（现金流量表） |
| **Tushare doc_id** | 7 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| report_date | end_date | 直接映射 | 报告期 |
| report_type | - | 根据 end_date 推断 | Q1/Q2/Q3/Q4 |
| publish_date | - | 使用 `fina_indicator` 接口获取 | 需要额外接口获取 |
| operating_cash_flow | cash_flows_from_operating_activities | 直接映射 | 经营活动现金流（元） |
| investing_cash_flow | cash_flows_from_investing_activities | 直接映射 | 投资活动现金流（元） |
| financing_cash_flow | cash_flows_from_financing_activities | 直接映射 | 筹资活动现金流（元） |
| net_cash_flow | net_increase_in_cash_and_equivalents | 直接映射 | 现金及现金等价物净增加（元） |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**（部分主要字段）：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| f_ann_date | str | 实际公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| cash_flows_from_operating_activities | float | 经营活动现金流 | 元 |
| cash_flows_from_investing_activities | float | 投资活动现金流 | 元 |
| cash_flows_from_financing_activities | float | 筹资活动现金流 | 元 |
| net_increase_in_cash_and_equivalents | float | 现金及现金等价物净增加 | 元 |

**接口调用参数**：

```python
tushare.cashflow(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)
```

**注意事项**：
- publish_date 需要从 `fina_indicator` 接口获取
- report_type 需要根据 end_date 推断
- 需要通过 identity_mapping 将 ts_code 转换为 sid

### B.4 financial_indicator（财务指标）

| 列名 | 类型 | 描述 | 单位 | 可空 |
|------|------|------|------|------|
| sid | int32 | 证券内部标识符 | - | ✗ |
| trade_date | date | 交易日期 | - | ✗ |
| report_date | date | 报告期 | - | ✗ |
| indicator_type | string | 指标类型 | - | ✗ |
| pe_ttm | float64 | 市盈率TTM | - | ✓ |
| pb | float64 | 市净率 | - | ✓ |
| ps_ttm | float64 | 市销率TTM | - | ✓ |
| roe | float64 | 净资产收益率 | 小数 | ✓ |
| roa | float64 | 总资产收益率 | 小数 | ✓ |
| gross_margin | float64 | 毛利率 | 小数 | ✓ |
| net_margin | float64 | 净利率 | 小数 | ✓ |
| debt_to_asset | float64 | 资产负债率 | 小数 | ✓ |
| current_ratio | float64 | 流动比率 | - | ✓ |
| quick_ratio | float64 | 速动比率 | - | ✓ |
| source | string | 数据源标识 | - | ✗ |

**indicator_type 枚举值**：`latest`（最新）、`ttm`（滚动12个月）、`annualized`（年化）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/indicator/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, trade_date, report_date, indicator_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `fina_indicator`（财务指标） |
| **Tushare doc_id** | 10 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| trade_date | end_date | 直接映射 | 使用 end_date 作为 trade_date |
| report_date | end_date | 直接映射 | 报告期 |
| indicator_type | - | 固定值 | "latest" |
| pe_ttm | pe | 直接映射 | 市盈率TTM |
| pb | pb | 直接映射 | 市净率 |
| ps_ttm | ps | 直接映射 | 市销率TTM |
| roe | roe | 直接映射 | 净资产收益率（小数） |
| roa | roa | 直接映射 | 总资产收益率（小数） |
| gross_margin | grossprofit_margin | 直接映射 | 毛利率（小数） |
| net_margin | netprofit_margin | 直接映射 | 净利率（小数） |
| debt_to_asset | debt_to_assets | 直接映射 | 资产负债率（小数） |
| current_ratio | current_ratio | 直接映射 | 流动比率 |
| quick_ratio | quick_ratio | 直接映射 | 速动比率 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**（部分主要字段）：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| pe | float | 市盈率 | - |
| pe_ttm | float | 市盈率TTM | - |
| pb | float | 市净率 | - |
| ps | float | 市销率 | - |
| ps_ttm | float | 市销率TTM | - |
| dv_ratio | float | 股息率 | 小数 |
| roe | float | 净资产收益率 | 小数 |
| roa | float | 总资产收益率 | 小数 |
| grossprofit_margin | float | 毛利率 | 小数 |
| netprofit_margin | float | 销售净利率 | 小数 |
| debt_to_assets | float | 资产负债率 | 小数 |
| current_ratio | float | 流动比率 | - |
| quick_ratio | float | 速动比率 | - |

**接口调用参数**：

```python
tushare.fina_indicator(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)
```

**注意事项**：
- trade_date 使用 end_date，表示该指标对应的报告期
- 如需 TTM 数据，使用 `pe_ttm`, `ps_ttm` 字段
- 需要通过 identity_mapping 将 ts_code 转换为 sid

### B.5 forecast（业绩预告）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| report_date | date | 报告期 | ✗ |
| report_type | string | 报告类型 | ✗ |
| publish_date | date | 发布日期 | ✗ |
| forecast_type | string | 预告类型 | ✗ |
| profit_lower | float64 | 预告净利润下限 | 元 | ✓ |
| profit_upper | float64 | 预告净利润上限 | 元 | ✓ |
| profit_change_lower | float64 | 预告净利润变动下限 | 小数 | ✓ |
| profit_change_upper | float64 | 预告净利润变动上限 | 小数 | ✓ |
| reason | string | 业绩变动原因 | ✓ |
| source | string | 数据源标识 | ✗ |

**forecast_type 枚举值**：`pre_disclose`（预披露）、`forecast`（业绩预告）、`express`（业绩快报）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/forecast/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, report_date, report_type, publish_date, source)`
- **支持 PIT 查询**

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `forecast`（业绩预告）+ `express`（业绩快报） |
| **Tushare doc_id** | 23（forecast）、24（express） |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| report_date | end_date | 直接映射 | 报告期 |
| report_type | - | 根据 end_date 推断 | Q1/Q2/Q3/Q4 |
| publish_date | ann_date | 直接映射 | 发布日期 |
| forecast_type | - | 根据接口决定 | forecast/express |
| profit_lower | p_change_min | 计算字段 | 根据 p_change_min 计算 |
| profit_upper | p_change_max | 计算字段 | 根据 p_change_max 计算 |
| profit_change_lower | p_change_min | 直接映射 | 预告净利润变动下限（小数） |
| profit_change_upper | p_change_max | 直接映射 | 预告净利润变动上限（小数） |
| reason | reason_describe | 直接映射 | 业绩变动原因 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

**forecast 接口：**

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| type | str | 业绩预告类型 | - |
| p_change_min | float | 预告净利润变动下限 | 小数 |
| p_change_max | float | 预告净利润变动上限 | 小数 |
| net_profit_min | float | 预告净利润下限 | 元 |
| net_profit_max | float | 预告净利润上限 | 元 |
| reason_describe | str | 业绩变动原因 | - |

**express 接口：**

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| revenue | float | 营业收入 | 元 |
| operate_profit | float | 营业利润 | 元 |
| total_profit | float | 利润总额 | 元 |
| net_profit | float | 净利润 | 元 |
| total_assets | float | 总资产 | 元 |

**接口调用参数**：

```python
# 业绩预告
tushare.forecast(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)

# 业绩快报
tushare.express(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期（可选）
)
```

**注意事项**：
- 需要同时调用 `forecast` 和 `express` 接口
- forecast_type 根据调用的接口决定
- profit_lower/upper 需要根据 p_change_min/max 计算

### B.6 fund_holding（公募基金持仓）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符（股票） | ✗ |
| fund_id | string | 基金代码 | ✗ |
| fund_name | string | 基金名称 | ✓ |
| fund_type | string | 基金类型 | ✓ |
| report_date | date | 报告期 | ✗ |
| publish_date | date | 发布日期 | ✗ |
| holding_shares | float64 | 持有股数 | 股 | ✗ |
| holding_value | float64 | 持有市值 | 元 | ✗ |
| holding_rank | int32 | 持仓排名 | - | ✓ |
| total_asset_ratio | float64 | 占基金净值比 | 小数 | ✓ |
| source | string | 数据源标识 | ✗ |

**fund_type 枚举值**：`stock`（股票型）、`mixed`（混合型）、`bond`（债券型）、`index`（指数型）、`qdii`（QDII）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/holding/fund/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, fund_id, report_date, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `fund_portfolio`（基金投资组合） |
| **Tushare doc_id** | 21 |
| **积分要求** | 4000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| fund_id | ts_code | 直接映射 | 基金代码 |
| fund_name | - | 使用 `fund_basic` 接口获取 | 需要额外接口获取 |
| fund_type | - | 使用 `fund_basic` 接口获取 | 需要额外接口获取 |
| report_date | end_date | 直接映射 | 报告期 |
| publish_date | updated_date | 直接映射 | 发布日期 |
| holding_shares | amount | 直接映射 | 持有股数（股） |
| holding_value | - | 计算字段 | holding_shares * close_price |
| holding_rank | - | 计算字段 | 按持有市值排序 |
| total_asset_ratio | - | 计算字段 | holding_value / total_fund_asset |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 基金代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| symbol | str | 股票代码 | - |
| amount | float | 持有股数 | 股 |
| updated_date | str | 更新日期 | YYYYMMDD |

**接口调用参数**：

```python
tushare.fund_portfolio(
    ts_code="000001.OF",      # 基金代码
    period="20240331",        # 报告期
)
```

**注意事项**：
- 需要通过 identity_mapping 将 symbol（股票代码）转换为 sid
- fund_name 和 fund_type 需要从 `fund_basic` 接口获取
- holding_value 和 total_asset_ratio 需要计算

### B.7 inst_holding（其他机构持仓）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符（股票） | ✗ |
| inst_id | string | 机构代码 | ✗ |
| inst_name | string | 机构名称 | ✓ |
| inst_type | string | 机构类型 | ✗ |
| report_date | date | 报告期 | ✗ |
| publish_date | date | 发布日期 | ✗ |
| holding_shares | float64 | 持有股数 | 股 | ✗ |
| holding_shares_ratio | float64 | 持股比例 | 小数 | ✗ |
| holding_rank | int32 | 持仓排名 | - | ✓ |
| source | string | 数据源标识 | ✗ |

**inst_type 枚举值**：`social_security`（社保基金）、`insurance`（保险资金）、`qfii`（QFII）、`trust`（信托）、`securities`（券商）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/holding/inst/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, inst_id, report_date, inst_type, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | Tushare 不提供完整接口，需使用付费数据源 |
| **Tushare doc_id** | - |
| **积分要求** | - |
| **数据可用性** | ⚠️ Tushare 部分可用，建议使用 Wind/Choice |

**Tushare 部分接口**：

| 机构类型 | 接口名称 | doc_id | 积分要求 | 说明 |
|---------|---------|--------|---------|------|
| QFII | `qfii_name_change` | 86 | 3000 | QFII 名称变更历史 |
| 保险公司 | - | - | - | Tushare 不提供 |

**替代数据源**：

| 数据源 | 说明 | 备注 |
|--------|------|------|
| **Wind** | 提供完整机构持仓数据 | 付费 |
| **Choice** | 提供完整机构持仓数据 | 付费 |
| **上市公司年报** | 从年报手工提取 | 仅限前十大股东 |

**建议方案**：
- 优先使用 Wind/Choice 获取机构持仓数据
- 如预算有限，可以从上市公司年报中手工提取前十大股东中的机构信息

### B.8 shareholder（大股东持股）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| shareholder_name | string | 股东名称 | ✗ |
| shareholder_type | string | 股东类型 | ✗ |
| report_date | date | 报告期 | ✗ |
| publish_date | date | 发布日期 | ✗ |
| holding_shares | float64 | 持有股数 | 股 | ✗ |
| holding_ratio | float64 | 持股比例 | 小数 | ✗ |
| holding_rank | int32 | 股东排名 | - | ✗ |
| is_restricted | boolean | 是否限售股 | ✓ |
| source | string | 数据源标识 | ✗ |

**shareholder_type 枚举值**：`individual`（自然人）、`corporate`（法人）、`state`（国有）、`qfii`（境外）

**配置**：
- 存储路径：`{DATAROOT}/fundamental/shareholder/{year}.parquet`
- 分区策略：按年
- 键列：`(sid, shareholder_name, report_date, source)`
- **支持 PIT 查询**

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `top10_holders`（前十大股东） |
| **Tushare doc_id** | 83 |
| **积分要求** | 3000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| shareholder_name | holder_name | 直接映射 | 股东名称 |
| shareholder_type | - | 根据名称推断 | 根据名称推断类型 |
| report_date | end_date | 直接映射 | 报告期 |
| publish_date | ann_date | 直接映射 | 发布日期 |
| holding_shares | hold_amount | 直接映射 | 持有股数（股） |
| holding_ratio | hold_ratio | 直接映射 | 持股比例（小数） |
| holding_rank | holder_rank | 直接映射 | 股东排名 |
| is_restricted | - | 根据其他字段推断 | 需要额外信息 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 | 单位 |
|-------------|------|------|------|
| ts_code | str | 股票代码 | - |
| ann_date | str | 公告日期 | YYYYMMDD |
| end_date | str | 报告期 | YYYYMMDD |
| holder_name | str | 股东名称 | - |
| holder_amount | float | 持有股数 | 股 |
| hold_ratio | float | 持股比例 | 小数 |
| holder_rank | int | 股东排名 | - |

**接口调用参数**：

```python
tushare.top10_holders(
    ts_code="600000.SH",      # 股票代码
    period="20240331",        # 报告期
)
```

**注意事项**：
- 需要通过 identity_mapping 将 ts_code 转换为 sid
- shareholder_type 需要根据股东名称推断（如包含"基金"、"信托"等）
- is_restricted 需要额外信息，Tushare 不直接提供

---

## 附录 C：Metadata 域新增数据集字段规格

### C.1 industry_basic（申万行业主数据）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| industry_code | string | 申万行业代码 | ✗ |
| industry_name | string | 申万行业名称 | ✗ |
| industry_level | int32 | 行业级别 | ✗ |
| parent_code | string | 父级行业代码 | ✓ |
| is_active | boolean | 是否活跃 | ✗ |
| effective_from | date | 生效开始日期 | ✗ |
| effective_to | date | 生效结束日期 | ✓ |

**industry_level 枚举值**：`1`（一级行业，31个）、`2`（二级行业，134个）、`3`（三级行业，349个）

**配置**：
- SQLite 表：`industry_basic`（在 metadata.sqlite 中）
- **支持 PIT 查询**（申万行业定期调整）

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `index_classify`（申万行业分类） |
| **Tushare doc_id** | 181 |
| **积分要求** | 2000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| industry_code | index_code | 直接映射 | 申万行业代码 |
| industry_name | industry_name | 直接映射 | 申万行业名称 |
| industry_level | - | 根据 level 推断 | L1→1, L2→2, L3→3 |
| parent_code | parent_code | 直接映射 | 父级行业代码（一级为"0"） |
| is_active | - | 根据 is_pub 推断 | is_pub='1' |
| effective_from | - | 使用当前日期 | 初始化时使用当前日期 |
| effective_to | - | NULL | 当前有效 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 |
|-------------|------|------|
| index_code | str | 指数代码 |
| industry_name | str | 行业名称 |
| parent_code | str | 父级代码（一级为0） |
| level | str | 行业层级（L1/L2/L3） |
| industry_code | str | 行业代码 |
| is_pub | str | 是否发布了指数（1是，0否） |
| src | str | 行业分类（SW申万） |

**接口调用参数**：

```python
# 获取申万一级行业列表
tushare.index_classify(
    level="L1",             # 行业分级
    src="SW2021",           # 分类标准（SW2014或SW2021）
)

# 获取申万二级行业列表
tushare.index_classify(
    level="L2",
    src="SW2021",
)

# 获取申万三级行业列表
tushare.index_classify(
    level="L3",
    src="SW2021",
)
```

**注意事项**：
- 提供申万2014版本（28个一级、104个二级、227个三级）和2021版本（31个一级、134个二级、346个三级）
- 建议使用 SW2021 版本
- 行业代码格式：801010.SI（一级行业）、850111.SI（三级行业）
- parent_code 为 "0" 表示一级行业

### C.2 industry_mapping（股票-申万行业映射）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| sid | int32 | 证券内部标识符 | ✗ |
| industry_code_l1 | string | 申万一级行业代码 | ✗ |
| industry_code_l2 | string | 申万二级行业代码 | ✓ |
| industry_code_l3 | string | 申万三级行业代码 | ✓ |
| effective_from | date | 生效开始日期 | ✗ |
| effective_to | date | 生效结束日期 | ✓ |
| change_reason | string | 变更原因 | ✓ |
| source | string | 数据源标识 | ✗ |

**配置**：
- SQLite 表：`industry_mapping`（在 metadata.sqlite 中）
- **支持 PIT 查询**（股票行业变更历史）
- **键列**：`(sid, effective_from, source)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `index_member_all`（申万行业成分构成分级） |
| **Tushare doc_id** | 335 |
| **积分要求** | 2000积分 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| sid | - | Identity 解析 | 通过 ts_code 解析 |
| industry_code_l1 | l1_code | 直接映射 | 申万一级行业代码 |
| industry_code_l2 | l2_code | 直接映射 | 申万二级行业代码 |
| industry_code_l3 | l3_code | 直接映射 | 申万三级行业代码 |
| effective_from | in_date | 直接映射 | 纳入日期 |
| effective_to | out_date | 直接映射 | 剔除日期（NULL表示当前有效） |
| change_reason | - | 不可用 | Tushare 不提供 |
| source | - | 固定值 | "tushare" |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 |
|-------------|------|------|
| l1_code | str | 一级行业代码 |
| l1_name | str | 一级行业名称 |
| l2_code | str | 二级行业代码 |
| l2_name | str | 二级行业名称 |
| l3_code | str | 三级行业代码 |
| l3_name | str | 三级行业名称 |
| ts_code | str | 成分股票代码 |
| name | str | 成分股票名称 |
| in_date | str | 纳入日期 |
| out_date | str | 剔除日期 |
| is_new | str | 是否最新（Y是，N否） |

**接口调用参数**：

```python
# 获取某个分类的所有成分股
tushare.index_member_all(
    l1_code="801010.SI",     # 一级行业代码（可选）
    l2_code="801016.SI",     # 二级行业代码（可选）
    l3_code="850111.SI",     # 三级行业代码（可选）
)

# 获取某个股票所属行业
tushare.index_member_all(
    ts_code="000001.SZ",     # 股票代码
    is_new="Y",              # 是否最新（默认为"Y是"）
)
```

**注意事项**：
- 需要通过 identity_mapping 将 ts_code 转换为 sid
- 可以按行业代码或股票代码查询
- is_new="Y" 只返回最新成分，is_new="N" 返回历史成分
- out_date 为 NULL 表示当前仍在该行业中
- change_reason 字段 Tushare 不提供，可以设为固定值或 NULL

### C.3 trading_calendar（交易日历）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| trade_date | date | 交易日期 | ✗ |
| market | string | 市场代码 | ✗ |
| is_trading | boolean | 是否交易日 | ✗ |
| is_half_day | boolean | 是否半日交易 | ✓ |
| holiday_name | string | 节假日名称 | ✓ |
| reason | string | 非交易日原因 | ✓ |

**market 枚举值**：`SSE`（上交所）、`SZSE`（深交所）、`HKEX`（港交所）、`NYSE`（纽交所）、`NASDAQ`（纳斯达克）

**配置**：
- SQLite 表：`trading_calendar`（在 metadata.sqlite 中）
- **键列**：`(trade_date, market)`

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | `trade_cal`（交易日历） |
| **Tushare doc_id** | 17 |
| **积分要求** | 免费接口 |
| **数据可用性** | ✅ 完全可用 |

**字段映射**：

| 设计字段 | Tushare 字段 | 数据转换 | 说明 |
|---------|-------------|---------|------|
| trade_date | cal_date | 直接映射 | 交易日期 |
| market | exchange | 枚举映射 | 交易所映射 |
| is_trading | is_open | 直接映射 | 是否交易日（1=是，0=否） |
| is_half_day | - | 不可用 | Tushare 不提供 |
| holiday_name | - | 不可用 | Tushare 不提供 |
| reason | - | 不可用 | Tushare 不提供 |

**market 枚举映射**：

| Tushare exchange | 设计 market |
|-----------------|-------------|
| SSE | SSE |
| SZSE | SZSE |

**Tushare 接口返回字段**：

| Tushare 字段 | 类型 | 说明 |
|-------------|------|------|
| cal_date | str | 日历日期 |
| is_open | int | 是否开盘（1=是，0=否） |
| exchange | str | 交易所（SSE/SZSE） |

**接口调用参数**：

```python
tushare.trade_cal(
    exchange="SSE",         # 交易所
    start_date="20240101",  # 开始日期
    end_date="20241231",    # 结束日期
)
```

**注意事项**：
- Tushare 只提供上交所（SSE）和深交所（SZSE）的交易日历
- 不提供半日交易标识
- 不提供节假日名称和原因
- **扩展**：is_half_day、holiday_name、reason 需要从其他数据源获取或手工维护

### C.4 trading_session（交易时段）

| 列名 | 类型 | 描述 | 可空 |
|------|------|------|------|
| market | string | 市场代码 | ✗ |
| session_type | string | 时段类型 | ✗ |
| session_name | string | 时段名称 | ✗ |
| start_time | string | 开始时间 | ✗ |
| end_time | string | 结束时间 | ✗ |
| is_active | boolean | 是否启用 | ✗ |

**session_type 枚举值**：`morning`（上午）、`afternoon`（下午）、`continuous`（连续交易）

**配置**：
- SQLite 表：`trading_session`（在 metadata.sqlite 中）

**数据源接口映射**：

| 项目 | 内容 |
|------|------|
| **接口名称** | Tushare 不提供，需使用配置数据 |
| **Tushare doc_id** | - |
| **积分要求** | - |
| **数据可用性** | ⚠️ Tushare 不可用，需使用配置数据 |

**数据来源**：

交易时段是静态配置数据，不需要从 API 获取，建议直接配置。

**建议配置**：

```python
# 上交所（SSE）和深交所（SZSE）交易时段
TRADING_SESSIONS = [
    {
        "market": "SSE",
        "session_type": "morning",
        "session_name": "上午交易时段",
        "start_time": "09:30:00",
        "end_time": "11:30:00",
        "is_active": True,
    },
    {
        "market": "SSE",
        "session_type": "afternoon",
        "session_name": "下午交易时段",
        "start_time": "13:00:00",
        "end_time": "15:00:00",
        "is_active": True,
    },
    {
        "market": "SZSE",
        "session_type": "morning",
        "session_name": "上午交易时段",
        "start_time": "09:30:00",
        "end_time": "11:30:00",
        "is_active": True,
    },
    {
        "market": "SZSE",
        "session_type": "afternoon",
        "session_name": "下午交易时段",
        "start_time": "13:00:00",
        "end_time": "15:00:00",
        "is_active": True,
    },
]
```

**注意事项**：
- 交易时段是静态数据，建议在代码中硬编码配置
- 如需支持港股、美股等市场，需要额外配置
- 半日交易时段需要特殊处理

---

## 数据源接口映射总结

### Tushare 可用性统计

| 数据域 | 数据集数量 | 完全可用 | 部分可用 | 需要替代源 |
|--------|----------|---------|---------|-----------|
| Market | 3 | 3 | 0 | 0 |
| Capital | 8 | 8 | 0 | 0 |
| Fundamental | 8 | 7 | 0 | 1（inst_holding） |
| Metadata | 4 | 4 | 0 | 0 |
| **合计** | **23** | **22** | **0** | **1** |

**修正说明**：
- top_board 数据集：使用 `top_list` + `top_inst` 接口，完全可用 ✅
- limit_board：使用 `limit_list_d` + `limit_step` 接口，完全可用 ✅
- industry_flow：改为从 `stock_flow` 按 `industry_mapping` 聚合生成，使用申万行业分类 ✅
- industry_basic：使用 `index_classify` 接口，完全可用 ✅
- industry_mapping：使用 `index_member_all` 接口，完全可用 ✅
- inst_holding：Tushare 不提供，仍需使用 Wind/Choice

### 需要替代数据源的数据集

| 数据集 | 替代数据源 | 优先级 | 说明 |
|--------|----------|--------|------|
| inst_holding | Wind/Choice | P2 | Tushare 不提供完整机构持仓数据 |

### Tushare 接口积分汇总

| 积分要求 | 数据集数量 | 主要数据集 |
|---------|----------|----------|
| 免费接口 | 1 | trade_cal |
| 2000积分 | 16 | market_flow, stock_flow, top_board, limit_board, industry_basic, industry_mapping 等 |
| 3000积分 | 7 | margin_detail, forecast, dividend 等 |
| 4000积分 | 1 | fund_holding |
| 5000积分 | 2 | chip_distribution, limit_board（limit_list_d） |
| 8000积分 | 1 | limit_board（limit_step 可选） |

**说明**：
- `industry_flow` 通过聚合 `stock_flow` 生成，无需额外积分
- `industry_mapping` 中的 `index_member_all` 接口同时用于 industry_flow 聚合

### 实施建议

**P0（必须实现）**：
- 使用 Tushare 实现所有直接可用的数据集（21个）
- 实现 stock_flow → industry_flow 的聚合逻辑

**P1（优先实现）**：
- 实现交易日历的基础功能
- 使用 `index_classify` 和 `index_member_all` 实现完整的申万行业分类
- 实现行业资金流的聚合计算

**P2（可选实现）**：
- 使用 `limit_step` 接口增强打板数据的连板分析（需要8000积分）
- 使用 Wind/Choice 实现机构持仓数据

### 关键接口清单

| 数据集 | Tushare 接口 | doc_id | 积分 | 说明 |
|--------|-------------|-------|------|------|
| market_flow | moneyflow_hsgt | 47 | 2000 | 沪深港通资金流 |
| stock_flow | moneyflow | 24 | 2000 | 个股资金流 |
| industry_flow | 聚合生成 | - | - | 从 stock_flow + industry_mapping 聚合 |
| margin_detail | mtsk | 30 | 3000 | 融资融券明细 |
| margin_summary | mtsk_sec | 31 | 3000 | 融资融券汇总 |
| top_board | top_list + top_inst | 106 + 107 | 2000 | 龙虎榜数据 |
| limit_board | limit_list_d (+ limit_step) | 298 (+ 356) | 5000 (+ 8000) | 打板数据 |
| chip_distribution | cyq_chips | 294 | 5000 | 筹码分布 |
| industry_basic | index_classify | 181 | 2000 | 申万行业分类 |
| industry_mapping | index_member_all | 335 | 2000 | 申万行业成分股 |
| trading_calendar | trade_cal | 17 | 免费 | 交易日历 |
