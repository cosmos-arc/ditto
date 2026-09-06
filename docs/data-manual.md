# Ditto 数据集手册

**版本：v2.0**

**最后更新：2026-03-04**

---

## 目录

1. [概述](#1-概述)
2. [数据供应商](#2-数据供应商)
3. [市场数据域](#3-市场数据域)
4. [元数据域](#4-元数据域)
5. [资本数据域](#5-资本数据域)
6. [基本面数据域](#6-基本面数据域)
7. [宏观数据域](#7-宏观数据域)
8. [存储架构](#8-存储架构)
9. [PIT 数据处理](#9-pit-数据处理)
10. [数据访问规范](#10-数据访问规范)

---

## 1. 概述

### 1.1 数据架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据流向                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      │
│  │  数据供应商       │      │  Sources 层     │      │  Store 层        │      │
│  │                 │      │                 │      │                 │      │
│  │  • Tushare      │ ───▶ │  • Adapter      │ ───▶ │  • Reader       │      │
│  │  • AkShare      │      │  • Transformer  │      │  • Writer       │      │
│  │  • 通达信        │      │  • ColumnMapping│      │                 │      │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘      │
│                                    │                   │                     │
│                                    ▼                   ▼                     │
│                           ┌─────────────────────────────────┐               │
│                           │        Service 层               │               │
│                           │  MetadataService, MarketService │               │
│                           └─────────────────────────────────┘               │
│                                                                              │
│                              数据域划分                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Market │ Metadata │ Capital │ Fundamental │ Macro │ Features │ Factors│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据域概览

| 数据域 | 说明 | 主要数据集 | 服务类 |
|--------|------|-----------|--------|
| **Market** | 市场行情数据 | stock_daily, etf_daily, index_daily, adj_factor, stock_status | `MarketService` |
| **Metadata** | 证券元数据 | instrument, calendar, industry, index_weight, universe_constituent | `MetadataService` |
| **Capital** | 资本数据 | margin_trading, pledge_ratio, valuation_metrics, index_composition | `CapitalService` |
| **Fundamental** | 基本面数据 | balance_sheet, income_statement, cash_flow, dividend, forecast | `FundamentalService` |
| **Macro** | 宏观经济数据 | macro_indicators | `MacroService` |
| **Features** | 技术特征 | technical_indicators | `FeatureService` |
| **Factors** | 因子数据 | style_factors | `FactorService` |

### 1.3 关键概念

| 概念 | 说明 |
|------|------|
| **source_ticker** | 数据源原始代码（如 `000001.SZ`） |
| **instrument_id** | 系统内部标准化 ID（Int64） |
| **knowledge_date** | 数据可知日期（PIT 安全） |
| **effective_from/to** | PIT 版本有效期 |
| **trade_date** | 交易日期 |
| **report_date** | 财报报告期 |

---

## 2. 数据供应商

### 2.1 Tushare Pro（主数据源）

| 配置项 | 值 |
|--------|-----|
| API 地址 | `http://api.tushare.pro` |
| 认证方式 | Token（通过 keyring 管理） |
| 请求超时 | 30 秒 |
| 重试次数 | 3 次 |
| 限流策略 | `free`（免费版）/ `paid`（付费版） |

**主要 API 接口**：

| 接口 | API Name | 数据类型 |
|------|----------|----------|
| 股票列表 | `stock_basic` | 元数据 |
| 交易日历 | `trade_cal` | 元数据 |
| 股票日线 | `daily` | 行情 |
| 复权因子 | `adj_factor` | 行情 |
| 涨跌停价 | `stk_limit` | 行情 |
| ETF 日线 | `fund_daily` | 行情 |
| 指数日线 | `index_daily` | 行情 |
| 估值指标 | `daily_basic` | 估值 |
| 股息分红 | `dividend` | 公司行为 |
| 融资融券 | `margin` | 公司行为 |
| 股权质押 | `pledge_stat` | 公司行为 |
| 资产负债表 | `balancesheet` | 财务 |
| 利润表 | `income` | 财务 |
| 现金流量表 | `cashflow` | 财务 |

**适配器位置**：`packages/data/src/ditto_data/sources/tushare/adapters/`

### 2.2 FRED（美国宏观数据）

| 配置项 | 值 |
|--------|-----|
| API 地址 | `https://api.stlouisfed.org/fred/` |
| 认证方式 | API Key（通过 keyring 管理） |
| 数据类型 | 美国宏观经济指标（GDP、CPI、M2、利率等） |

**配置方式**：

```bash
# 设置 FRED API Key
uv run --no-sync python -c "
import keyring
keyring.set_password('fred', 'api_key', 'YOUR_API_KEY')
"
```

### 2.3 通达信（质量对账）

| 配置项 | 值 |
|--------|-----|
| 数据路径 | `/opt/tdx/vipdoc`（Linux）/ `D:\new_tdx\vipdoc`（Windows） |
| 文件格式 | `.day` 二进制文件 |
| 用途 | 仅用于数据质量对账，不参与主数据摄入 |

### 2.4 AkShare（降级备选）

当 Tushare 不可用时，可手动触发 AkShare 作为降级数据源。

---

## 3. 市场数据域

### 3.1 股票日线行情 (stock_daily)

#### 3.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `daily` |
| **请求参数** | `trade_date`（YYYYMMDD 格式） |
| **适配器** | `StockTushareAdapter` |

#### 3.1.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | 数据源代码 |
| `open` | Float64 | 开盘价 |
| `high` | Float64 | 最高价 |
| `low` | Float64 | 最低价 |
| `close` | Float64 | 收盘价 |
| `pre_close` | Float64 | 昨收价 |
| `volume` | Float64 | 成交量 |
| `amount` | Float64 | 成交额 |
| `pct_change` | Float64 | 涨跌幅（%） |
| `turnover` | Float64 | 换手率（计算列） |
| `is_suspended` | Boolean | 是否停牌 |
| `is_limit_up` | Boolean | 是否涨停 |
| `is_limit_down` | Boolean | 是否跌停 |
| `is_st` | Boolean | 是否 ST |
| `up_limit` | Float64 | 涨停价 |
| `down_limit` | Float64 | 跌停价 |

**存储路径**：`market/stock/bars/daily/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

**Reader/Writer**：`BarsReader` / `BarsWriter`

---

### 3.2 ETF 日线行情 (etf_daily)

#### 3.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `fund_daily` |
| **适配器** | `ETFTushareAdapter` |

#### 3.2.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | ETF 代码 |
| `open` | Float64 | 开盘价 |
| `high` | Float64 | 最高价 |
| `low` | Float64 | 最低价 |
| `close` | Float64 | 收盘价 |
| `pre_close` | Float64 | 昨收价 |
| `volume` | Float64 | 成交量 |
| `amount` | Float64 | 成交额 |
| `pct_change` | Float64 | 涨跌幅 |

**存储路径**：`market/etf/bars/daily/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

---

### 3.3 指数日线行情 (index_daily)

#### 3.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_daily` |
| **适配器** | `IndexTushareAdapter` |

#### 3.3.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | 指数代码（如 `000300.SH`） |
| `open` | Float64 | 开盘价 |
| `high` | Float64 | 最高价 |
| `low` | Float64 | 最低价 |
| `close` | Float64 | 收盘价 |
| `pre_close` | Float64 | 昨收价 |
| `change` | Float64 | 涨跌额 |
| `pct_change` | Float64 | 涨跌幅 |
| `volume` | Float64 | 成交量 |
| `amount` | Float64 | 成交额 |

**存储路径**：`market/index/bars/daily/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

---

### 3.4 复权因子 (adj_factor)

#### 3.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `adj_factor` |

#### 3.4.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | 股票代码 |
| `adj_factor` | Float64 | 复权因子 |
| `knowledge_date` | Date | 数据可知日期 |

**存储路径**：`market/stock/adj/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

---

### 3.5 股票状态 (stock_status)

#### 3.5.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `trade_status` / `stk_status` |

#### 3.5.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `is_suspended` | Boolean | 是否停牌 |
| `suspend_timing` | Utf8 | 停牌时段 |
| `is_st` | Boolean | 是否 ST |
| `st_type` | Utf8 | ST 类型 |
| `list_status` | Utf8 | 上市状态 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | 股票代码 |

**存储路径**：`market/stock/status/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

---

## 4. 元数据域

### 4.1 证券主数据 (instrument)

#### 4.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `stock_basic` / `fund_basic` / `index_basic` |
| **请求参数** | `list_status=L`（上市状态） |

#### 4.1.2 数据模型

```python
@dataclass(frozen=True)
class InstrumentRegistration:
    source_ticker: str      # 源代码（如 "600000.SH"）
    ticker: str             # 裸代码（如 "600000"）
    name: str               # 证券名称
    exchange: str           # 交易所代码（SSE/SZSE/BSE）
    asset_class: str        # 资产类别（stock/etf/index）
    list_date: str          # 上市日期
    source: str = "tushare"
    board: str | None = None
    extension: InstrumentExtension | None = None
```

**扩展信息**：

| 扩展类型 | 字段 |
|---------|------|
| `StockExtension` | `list_status`, `industry_id` |
| `ETFExtension` | `fund_type`, `fund_manager`, `establish_date`, `tracking_index` |
| `IndexExtension` | `base_date`, `base_point`, `num_constituents` |

**存储**：SQLite（`metadata/metadata.sqlite`）

**主键**：`(instrument_id)`

---

### 4.2 交易日历 (calendar)

#### 4.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `trade_cal` |
| **请求参数** | `exchange=SSE`, `start_date`, `end_date` |
| **适配器** | `CalendarTushareAdapter` |

#### 4.2.2 数据模型

```python
@dataclass(frozen=True)
class CalendarDay:
    trade_date: str
    is_open: bool
    prev_trade_date: str | None
    next_trade_date: str | None
    week_of_year: int | None
    month: int | None
    quarter: int | None
    year: int | None
    is_week_end: bool
    is_month_end: bool
    is_quarter_end: bool
```

**存储路径**：`metadata/calendar/`

---

### 4.3 行业分类 (industry)

#### 4.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_classify`（申万行业） |
| **适配器** | `IndustryTushareAdapter` |

#### 4.3.2 数据模型

```python
@dataclass(frozen=True)
class IndustryBasic:
    industry_id: str
    industry_name: str
    industry_level: str  # 一级/二级行业
    parent_id: str | None = None
    is_active: bool = True

@dataclass(frozen=True)
class IndustryMapping:
    instrument_id: int
    industry_id: str
    source: str = "sw"  # 申万
    effective_from: str | None = None
    effective_to: str | None = None
```

**主键**：`(instrument_id, industry_id, effective_from)`

---

### 4.4 指数权重 (index_weight)

#### 4.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_weight` |

#### 4.4.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `index_instrument_id` | Int64 | 指数内部 ID |
| `constituent_instrument_id` | Int64 | 成分股内部 ID |
| `trade_date` | Date | 交易日期 |
| `weight` | Float64 | 权重 |
| `source` | Utf8 | 数据源 |
| `index_code` | Utf8 | 指数代码 |
| `con_code` | Utf8 | 成分股代码 |

**存储路径**：`metadata/index/weight/{year}.parquet`

**主键**：`(index_instrument_id, constituent_instrument_id, trade_date)`

---

### 4.5 股票池成分 (universe_constituent)

#### 4.5.1 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `universe_id` | Utf8 | 股票池 ID |
| `instrument_id` | Int64 | 成分股内部 ID |
| `source` | Utf8 | 数据源 |
| `source_ticker` | Utf8 | 成分股代码 |
| `effective_from` | Date | 生效开始日期 |
| `effective_to` | Date | 生效结束日期 |
| `weight` | Float64 | 权重 |

**存储路径**：`metadata/universe/constituent/`

**主键**：`(universe_id, instrument_id, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

---

## 5. 资本数据域

### 5.1 融资融券 (margin_trading)

#### 5.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `margin` |

#### 5.1.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `margin_buy_balance` | Float64 | 融资余额 |
| `short_sell_balance` | Float64 | 融券余额 |
| `margin_buy_volume` | Float64 | 融资买入量 |
| `short_sell_volume` | Float64 | 融券卖出量 |

**存储路径**：`capital/margin/`

**主键**：`(instrument_id, trade_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

---

### 5.2 估值指标 (valuation_metrics)

#### 5.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `daily_basic` |

#### 5.2.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `pe_ratio` | Float64 | 市盈率 |
| `pb_ratio` | Float64 | 市净率 |
| `ps_ratio` | Float64 | 市销率 |
| `dividend_yield` | Float64 | 股息率 |
| `market_cap` | Float64 | 总市值 |

**存储路径**：`capital/valuation/`

**主键**：`(instrument_id, trade_date, effective_from)`

---

### 5.3 股权质押 (pledge_ratio)

#### 5.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `pledge_stat` |

#### 5.3.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `report_date` | Date | 报告日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `pledge_ratio` | Float64 | 质押比例 |
| `pledge_shares` | Float64 | 质押股数 |
| `total_shares` | Float64 | 总股本 |

**存储路径**：`capital/pledge/`

---

## 6. 基本面数据域

### 6.1 资产负债表 (balance_sheet)

#### 6.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `balancesheet` |

#### 6.1.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期（公告日） |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `total_assets` | Float64 | 总资产 |
| `total_liabilities` | Float64 | 总负债 |
| `net_assets` | Float64 | 净资产 |
| `current_assets` | Float64 | 流动资产 |
| `current_liabilities` | Float64 | 流动负债 |

**存储路径**：`fundamental/financial/balance_sheet/`

**主键**：`(instrument_id, report_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

---

### 6.2 利润表 (income_statement)

#### 6.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `income` |

#### 6.2.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `revenue` | Float64 | 营业收入 |
| `operating_profit` | Float64 | 营业利润 |
| `net_profit` | Float64 | 净利润 |
| `eps` | Float64 | 每股收益 |

**存储路径**：`fundamental/financial/income_statement/`

**主键**：`(instrument_id, report_date, effective_from)`

---

### 6.3 现金流量表 (cash_flow)

#### 6.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `cashflow` |

#### 6.3.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `operating_cash_flow` | Float64 | 经营活动现金流 |
| `investing_cash_flow` | Float64 | 投资活动现金流 |
| `financing_cash_flow` | Float64 | 筹资活动现金流 |
| `net_cash_flow` | Float64 | 现金净增加额 |

**存储路径**：`fundamental/financial/cash_flow/`

**主键**：`(instrument_id, report_date, effective_from)`

---

### 6.4 股息分红 (dividend)

#### 6.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `dividend` |

#### 6.4.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 股票 ID |
| `ex_dividend_date` | Date | 除权除息日 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `dividend_per_share` | Float64 | 每股股息 |
| `dividend_yield` | Float64 | 股息率 |

**存储路径**：`fundamental/corporate/dividend/`

**主键**：`(instrument_id, ex_dividend_date, effective_from)`

---

## 7. 宏观数据域

### 7.1 宏观指标 (macro_indicators)

#### 7.1.1 数据源

| 数据源 | 覆盖范围 | 说明 |
|--------|---------|------|
| Tushare | 中国宏观经济 | Shibor、LPR、社融、M2 等 |
| FRED | 美国宏观经济 | GDP、CPI、PPI、就业数据等 |

#### 7.1.2 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `indicator_code` | String | 指标代码 |
| `indicator_name` | String | 指标名称 |
| `category` | String | 指标分类 |
| `frequency` | String | 频率（daily/monthly/quarterly） |
| `need_pit` | Boolean | 是否需要 PIT 处理 |
| `date` | Date | 日期 |
| `value` | Float64 | 指标值 |
| `knowledge_date` | Date | 数据可知日期 |
| `source` | String | 数据来源 |
| `unit` | String | 单位 |
| `description` | String | 描述 |

**存储路径**：`macro/indicators/`

**主键**：`(indicator_code, date, knowledge_date)`

---

## 8. 存储架构

### 8.1 存储格式

| 数据类型 | 存储格式 | 说明 |
|----------|----------|------|
| 时序数据 | Parquet | 按年分区，列式存储 |
| 元数据 | SQLite | 关系型数据，支持事务 |
| 临时数据 | 内存/临时文件 | 处理中间结果 |

### 8.2 目录结构

```
data_root/
├── market/                    # 市场数据
│   ├── stock/
│   │   ├── bars/daily/       # 股票日线
│   │   │   ├── 2020.parquet
│   │   │   ├── 2021.parquet
│   │   │   └── ...
│   │   ├── adj/              # 复权因子
│   │   └── status/           # 股票状态
│   ├── etf/
│   │   ├── bars/daily/       # ETF 日线
│   │   ├── adj/              # ETF 复权因子
│   │   ├── status/           # ETF 状态
│   │   └── nav/              # ETF 净值
│   └── index/
│       ├── bars/daily/       # 指数日线
│       └── constituent/      # 指数成分股
├── metadata/                  # 元数据
│   ├── calendar/             # 交易日历
│   ├── instrument/           # 证券主数据（SQLite）
│   ├── index/
│   │   └── weight/           # 指数权重
│   └── universe/
│       └── constituent/      # 股票池成分
├── capital/                   # 资本数据
│   ├── margin/               # 融资融券
│   ├── valuation/            # 估值指标
│   ├── pledge/               # 股权质押
│   ├── index_composition/    # 指数成分
│   ├── flow/                 # 资金流
│   ├── top_board/            # 龙虎榜
│   ├── limit_board/          # 涨跌停
│   └── chip/                 # 筹码分布
├── fundamental/               # 基本面数据
│   ├── financial/            # 财务数据
│   │   ├── balance_sheet/
│   │   ├── income_statement/
│   │   └── cash_flow/
│   ├── indicator/            # 财务指标
│   ├── forecast/             # 业绩预告
│   ├── holding/              # 持股数据
│   └── corporate/            # 公司行为
│       └── dividend/         # 分红
├── macro/                     # 宏观数据
│   └── indicators/           # 宏观指标
├── features/                  # 特征数据
│   └── technical/            # 技术特征
│       ├── price/            # 价格特征
│       ├── indicators_narrow/ # 技术指标窄表
│       └── indicators_wide/  # 技术指标宽表
├── factors/                   # 因子数据
│   ├── narrow/style/         # 窄风格因子
│   ├── wide/style/           # 宽风格因子
│   ├── factors_narrow/       # 因子窄表
│   └── factors_wide/         # 因子宽表
├── runtime/                   # 运行时数据
│   ├── quality/              # 质量记录
│   │   ├── quarantine/       # 隔离数据
│   │   └── comparison/       # 对账记录
│   └── ingestion/            # 摄入日志
├── db/                        # 数据库
│   └── ditto.duckdb          # DuckDB 文件
├── metadata/
│   └── metadata.sqlite       # SQLite 元数据库
├── logs/                      # 日志
├── backups/                   # 备份
└── temp/                      # 临时文件
```

### 8.3 CQRS 架构

DataHub Store 层采用 CQRS（Command Query Responsibility Segregation）模式：

| 组件 | 职责 | 方法 | 特点 |
|------|------|------|------|
| **Reader** | 数据查询 | `read()`, `count()`, `get_*()` | 无副作用，可并发 |
| **Writer** | 数据写入 | `write()`, `delete()` | 有副作用，需并发控制 |
| **Service** | 业务逻辑 | 封装业务操作 | 协调 Reader/Writer |

**文件命名约定**：
- 查询类：`*_reader.py`（如 `bars_reader.py`）
- 写入类：`*_writer.py`（如 `bars_writer.py`）
- 服务类：`*_service.py`（如 `market_service.py`）

### 8.4 分区策略

| 数据类型 | 分区键 | 分区粒度 |
|----------|--------|----------|
| 日线行情 | `trade_date` | 按年 |
| 复权因子 | `trade_date` | 按年 |
| 财务报表 | `report_date` | 按年 |
| 元数据 | - | 单文件（SQLite） |

---

## 9. PIT 数据处理

### 9.1 PIT 概念

**Point-in-Time（PIT）数据**确保回测时只使用当时可知的数据，避免未来函数（look-ahead bias）。

### 9.2 PIT 实现

| 字段 | 说明 |
|------|------|
| `knowledge_date` | 数据可知日期（公告日/披露日） |
| `effective_from` | 该版本数据生效开始日期 |
| `effective_to` | 该版本数据生效结束日期（NULL 表示当前版本） |

### 9.3 PIT 查询条件

```python
# 查询 as_of_date 时的数据
condition = """
    effective_from <= as_of_date
    AND (effective_to IS NULL OR effective_to > as_of_date)
"""
```

### 9.4 PIT 数据类型

| 数据类型 | knowledge_date 规则 | PIT 处理 |
|----------|---------------------|----------|
| 日线行情 | `trade_date + 1` | 版本控制 |
| 复权因子 | `trade_date` | 版本控制 |
| 财务报表 | `ann_date`（公告日） | 版本控制 |
| 估值指标 | `trade_date + 1` | 版本控制 |
| 公司行为 | `announcement_date` | 无版本控制 |
| 宏观指标 | 数据发布日 | 版本控制 |

---

## 10. 数据访问规范

### 10.1 访问层级规则

| 访问类型 | ✅ 允许 | ❌ 禁止 | 说明 |
|---------|--------|--------|------|
| **通过 Service** | `MetadataService`, `MarketService` 等 | - | **推荐方式**，通过 DI 容器注入 |
| **直接导入 Sources** | `from ditto_data.sources.*` | - | Sources 可直接访问 |
| **直接访问 Reader/Writer** | - | `from ditto_data.storage.*` | **禁止**直接访问 |

### 10.2 正确示例

```python
# ✅ 推荐：通过 DI 容器注入 Domain Service
from dishka import Container
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.market_service import MarketService

container = Container()
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 使用 Service
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")
bars = market_service.query(query)

# ❌ 禁止：直接访问 Reader/Writer
from ditto_data.storage.metadata import InstrumentReader  # ❌
reader = InstrumentReader(...)  # ❌
```

### 10.3 服务层清单

| 服务类 | 职责 | 位置 |
|--------|------|------|
| `MetadataService` | 元数据管理 | `services/metadata_service.py` |
| `MarketService` | 市场数据 | `services/market_service.py` |
| `CapitalService` | 资本数据 | `services/capital_service.py` |
| `FundamentalService` | 基本面数据 | `services/fundamental_service.py` |
| `MacroService` | 宏观数据 | `services/macro_service.py` |
| `FeatureService` | 特征数据 | `services/feature_service.py` |
| `FactorService` | 因子数据 | `services/factor_service.py` |

---

## 附录

### A. 数据域与适配器映射

| 数据域 | 适配器类 | 文件路径 |
|--------|----------|----------|
| Market - Stock | `StockTushareAdapter` | `sources/tushare/adapters/stock.py` |
| Market - ETF | `ETFTushareAdapter` | `sources/tushare/adapters/etf.py` |
| Market - Index | `IndexTushareAdapter` | `sources/tushare/adapters/index.py` |
| Metadata - Calendar | `CalendarTushareAdapter` | `sources/tushare/adapters/calendar.py` |
| Metadata - Industry | `IndustryTushareAdapter` | `sources/tushare/adapters/industry.py` |
| Capital | `CapitalTushareAdapter` | `sources/tushare/adapters/capital.py` |
| Fundamental | `FundamentalTushareAdapter` | `sources/tushare/adapters/fundamental.py` |
| Macro | `MacroTushareAdapter` | `sources/tushare/adapters/macro.py` |
| FX | `FXTushareAdapter` | `sources/tushare/adapters/fx.py` |
| Metal | `MetalTushareAdapter` | `sources/tushare/adapters/metal.py` |
| Bond Yield | `BondYieldTushareAdapter` | `sources/tushare/adapters/bond_yield.py` |

### B. 枚举类型

**交易所 (Exchange)**:

> **注**：此处的 `SSE`/`SZSE` 等为文档层面的交易所简称，与 kernel 的 `InstrumentId` 前缀（`XSHE`/`XSHG`）属不同抽象层级。

| 值 | 说明 |
|----|------|
| `SSE` | 上海证券交易所 |
| `SZSE` | 深圳证券交易所 |
| `BSE` | 北京证券交易所 |
| `CFFEX` | 中国金融期货交易所 |
| `SHFE` | 上海期货交易所 |
| `DCE` | 大连商品交易所 |
| `CZCE` | 郑州商品交易所 |

**证券类型 (AssetClass)**:
| 值 | 说明 |
|----|------|
| `stock` | 股票 |
| `etf` | ETF 基金 |
| `index` | 指数 |
| `bond` | 债券 |
| `future` | 期货 |

### C. 关键文件路径

| 功能 | 路径 |
|------|------|
| Store Schema | `packages/data/src/ditto_data/storage/schemas/` |
| 数据模型 | `packages/data/src/ditto_data/models/` |
| Tushare 适配器 | `packages/data/src/ditto_data/sources/tushare/adapters/` |
| 列映射定义 | `packages/data/src/ditto_data/sources/tushare/processors/mappings/` |
| Domain Service | `packages/data/src/ditto_data/services/` |

### D. 相关文档

- [配置系统手册](/docs/configuration.md)
- [运维手册](/docs/ops-manual.md)
- [DataHub 架构规范](/packages/data/AGENTS.md)
