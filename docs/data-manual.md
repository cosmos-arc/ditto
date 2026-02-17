# Ditto 数据集手册

**版本：v1.0**

**最后更新：2026-02-17**

---

## 目录

1. [概述](#1-概述)
2. [数据供应商](#2-数据供应商)
3. [市场数据域](#3-市场数据域)
4. [元数据域](#4-元数据域)
5. [资本数据域](#5-资本数据域)
6. [公司行为域](#6-公司行为域)
7. [衍生品数据域](#7-衍生品数据域)
8. [宏观数据域](#8-宏观数据域)
9. [存储架构](#9-存储架构)
10. [PIT 数据处理](#10-pit-数据处理)

---

## 1. 概述

### 1.1 数据架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据流向                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      │
│  │  数据供应商       │      │  适配器层        │      │  存储层          │      │
│  │                 │      │                 │      │                 │      │
│  │  • Tushare      │ ───▶ │  • Adapter      │ ───▶ │  • Parquet      │      │
│  │  • 通达信        │      │  • Transformer  │      │  • SQLite       │      │
│  │  • AkShare      │      │  • ColumnMapping│      │                 │      │
│  └─────────────────┘      └─────────────────┘      └─────────────────┘      │
│                                                                              │
│                              数据域划分                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Market │ Metadata │ Capital │ Corp Actions │ Derivatives │ Macro   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据域概览

| 数据域 | 说明 | 主要数据集 |
|--------|------|-----------|
| **Market** | 市场行情数据 | stock_daily, etf_daily, index_daily, adj_factor, stock_status |
| **Metadata** | 证券元数据 | instrument, calendar, industry, index_member, universe |
| **Capital** | 资本与财务数据 | balance_sheet, income_statement, cash_flow, valuation_metrics |
| **Corp Actions** | 公司行为 | dividend, corporate_actions, margin_trading, pledge_ratio |
| **Derivatives** | 衍生品数据 | futures_position, index_composition |
| **Macro** | 宏观经济数据 | macro_indicators |

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
| 限流策略 | `paid`（付费版） |

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
| 估值指标 | `pe_daily` | 估值 |
| 股息分红 | `dividend` | 公司行为 |
| 融资融券 | `margin` | 公司行为 |
| 股权质押 | `pledge_stat` | 公司行为 |
| 资产负债表 | `balancesheet` | 财务 |
| 利润表 | `income` | 财务 |
| 现金流量表 | `cashflow` | 财务 |

### 2.2 通达信（质量对账）

| 配置项 | 值 |
|--------|-----|
| 数据路径 | `/opt/tdx/vipdoc` |
| 文件格式 | `.day` 二进制文件 |
| 用途 | 仅用于数据质量对账，不参与主数据摄入 |

### 2.3 AkShare（降级备选）

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
| **返回字段** | `ts_code, trade_date, open, high, low, close, pre_close, vol, amount, pct_chg` |

#### 3.1.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | 数据源代码（如 `000001.SZ`） |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期（= trade_date + 1） |
| `open` | Float64 | 开盘价 |
| `high` | Float64 | 最高价 |
| `low` | Float64 | 最低价 |
| `close` | Float64 | 收盘价 |
| `pre_close` | Float64 | 昨收价 |
| `volume` | Float64 | 成交量（手） |
| `amount` | Float64 | 成交额（千元） |
| `pct_change` | Float64 | 涨跌幅（%） |

**主键**：`(source_ticker, trade_date)`

#### 3.1.3 存储数据 Schema

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
| `pct_change` | Float64 | 涨跌幅 |
| `turnover` | Float64 | 换手率（计算列） |
| `is_suspended` | Boolean | 是否停牌 |
| `is_limit_up` | Boolean | 是否涨停 |
| `is_limit_down` | Boolean | 是否跌停 |
| `is_st` | Boolean | 是否 ST |
| `up_limit` | Float64 | 涨停价 |
| `down_limit` | Float64 | 跌停价 |

**存储路径**：`market/stock/bars/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

#### 3.1.4 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `ts_code` | `source_ticker` | 直接映射 |
| `vol` | `volume` | 直接映射 |
| `pct_chg` | `pct_change` | 直接映射 |
| `trade_date` | `trade_date` | `%Y%m%d` → Date |
| - | `knowledge_date` | `trade_date + 1 day` |
| - | `instrument_id` | 通过 instrument 映射表转换 |

---

### 3.2 ETF 日线行情 (etf_daily)

#### 3.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `fund_daily` |
| **请求参数** | `trade_date`（YYYYMMDD 格式） |

#### 3.2.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | ETF 代码（如 `510300.SH`） |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `open` | Float64 | 开盘价 |
| `high` | Float64 | 最高价 |
| `low` | Float64 | 最低价 |
| `close` | Float64 | 收盘价 |
| `pre_close` | Float64 | 昨收价 |
| `volume` | Float64 | 成交量 |
| `amount` | Float64 | 成交额 |
| `pct_change` | Float64 | 涨跌幅 |

**主键**：`(source_ticker, trade_date)`

#### 3.2.3 存储数据 Schema

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

**存储路径**：`market/etf/bars/{year}.parquet`

**主键**：`(instrument_id, trade_date)`

---

### 3.3 指数日线行情 (index_daily)

#### 3.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_daily` |

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

**存储路径**：`market/index/bars/{year}.parquet`

---

### 3.4 复权因子 (adj_factor)

#### 3.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `adj_factor` |

#### 3.4.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | 股票代码 |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期（= trade_date） |
| `adj_factor` | Float64 | 复权因子 |

**主键**：`(source_ticker, trade_date)`

#### 3.4.3 存储数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | Int64 | 系统内部 ID |
| `trade_date` | Date | 交易日期 |
| `source` | Utf8 | 数据源标识 |
| `source_ticker` | Utf8 | 股票代码 |
| `adj_factor` | Float64 | 复权因子 |
| `knowledge_date` | Date | 数据可知日期 |

**存储路径**：`market/stock/adj/{year}.parquet`

---

### 3.5 股票状态 (stock_status)

#### 3.5.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `trade_status` / `stk_status` |

#### 3.5.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | 股票代码 |
| `trade_date` | Date | 交易日期 |
| `is_suspended` | Boolean | 是否停牌 |
| `suspend_timing` | String | 停牌时段 |
| `is_st` | Boolean | 是否 ST |
| `st_type` | String | ST 类型 |
| `list_status` | String | 上市状态 |

**主键**：无（允许重复，同一股票同一天多条状态记录）

#### 3.5.3 存储数据 Schema

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

---

### 3.6 涨跌停价 (stock_limit)

#### 3.6.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `stk_limit` |

#### 3.6.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | 股票代码 |
| `trade_date` | Date | 交易日期 |
| `up_limit` | Float64 | 涨停价 |
| `down_limit` | Float64 | 跌停价 |

**主键**：`(source_ticker, trade_date)`

---

### 3.7 基金复权因子 (fund_adj)

#### 3.7.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `fund_adj` |

#### 3.7.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `source_ticker` | String | 基金代码 |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `adj_factor` | Float64 | 复权因子 |

**主键**：`(source_ticker, trade_date)`

---

## 4. 元数据域

### 4.1 证券主数据 (instrument)

#### 4.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `stock_basic` / `fund_basic` / `index_basic` |
| **请求参数** | `list_status=L`（上市状态） |

#### 4.1.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 系统内部 ID |
| `source_ticker` | String | 数据源代码 |
| `name` | String | 证券名称 |
| `exchange` | String | 交易所（SSE/SZSE/BSE） |
| `list_date` | Date | 上市日期 |
| `delist_date` | Date | 退市日期 |
| `instrument_type` | String | 证券类型（stock/etf/index） |

**主键**：`(instrument_id)`

#### 4.1.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `ts_code` | `source_ticker` | 直接映射 |
| - | `ticker` | `source_ticker.split('.')[0]` |
| - | `exchange` | `SH → SSE`, `SZ → SZSE` |

---

### 4.2 交易日历 (calendar)

#### 4.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `trade_cal` |
| **请求参数** | `exchange=SSE`, `start_date`, `end_date` |

#### 4.2.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `trade_date` | Date | 日期 |
| `is_open` | Boolean | 是否开市 |

**存储路径**：`metadata/calendar/`

---

### 4.3 行业分类 (industry)

#### 4.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_classify`（申万行业） |

#### 4.3.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `industry_name` | String | 行业名称 |
| `industry_level` | Int32 | 行业级别（1=一级，2=二级） |
| `industry_date` | Date | 行业分类日期 |
| `knowledge_date` | Date | 数据可知日期 |

**主键**：`(instrument_id, industry_date)`

---

### 4.4 指数成分股 (index_member)

#### 4.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_weight` |

#### 4.4.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `index_id` | String | 指数 ID |
| `instrument_id` | String | 成分股 ID |
| `weight` | Float64 | 权重 |
| `effective_from` | Date | 生效开始日期 |
| `effective_to` | Date | 生效结束日期（NULL 表示当前有效） |

**主键**：`(index_id, instrument_id, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

---

### 4.5 指数权重 (index_weight)

#### 4.5.1 存储数据 Schema

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

### 4.6 股票池成分 (universe_constituent)

#### 4.6.1 存储数据 Schema

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

---

## 5. 资本数据域

### 5.1 资产负债表 (balance_sheet)

#### 5.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `balancesheet` |

#### 5.1.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期（公告日） |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `total_assets` | Float64 | 总资产 |
| `total_liabilities` | Float64 | 总负债 |
| `net_assets` | Float64 | 净资产 |
| `current_assets` | Float64 | 流动资产 |
| `current_liabilities` | Float64 | 流动负债 |

**主键**：`(instrument_id, report_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 5.1.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `ts_code` | `instrument_id` | 直接映射 |
| `total_liab` | `total_liabilities` | 直接映射 |
| `end_date` | `report_date` | 直接映射 |
| `ann_date` | `knowledge_date` | 直接映射 |
| `total_hldr_eqy_exc_min_int` | `net_assets` | 直接映射 |
| `total_cur_assets` | `current_assets` | 直接映射 |
| `total_cur_liab` | `current_liabilities` | 直接映射 |

---

### 5.2 利润表 (income_statement)

#### 5.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `income` |

#### 5.2.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `revenue` | Float64 | 营业收入 |
| `operating_profit` | Float64 | 营业利润 |
| `net_profit` | Float64 | 净利润 |
| `eps` | Float64 | 每股收益 |

**主键**：`(instrument_id, report_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 5.2.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `total_operating_revenue` | `revenue` | 直接映射 |
| `basic_eps` | `eps` | 直接映射 |

---

### 5.3 现金流量表 (cash_flow)

#### 5.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `cashflow` |

#### 5.3.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `report_date` | Date | 报告期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `operating_cash_flow` | Float64 | 经营活动现金流 |
| `investing_cash_flow` | Float64 | 投资活动现金流 |
| `financing_cash_flow` | Float64 | 筹资活动现金流 |
| `net_cash_flow` | Float64 | 现金净增加额 |

**主键**：`(instrument_id, report_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 5.3.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `n_cashflow_act` | `operating_cash_flow` | 直接映射 |
| `n_cash_flows_inv_act` | `investing_cash_flow` | 直接映射 |
| `n_cash_flows_fnc_act` | `financing_cash_flow` | 直接映射 |
| - | `net_cash_flow` | 计算列（三者之和） |

---

### 5.4 估值指标 (valuation_metrics)

#### 5.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `pe_daily` |

#### 5.4.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期（= trade_date + 1） |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `pe_ratio` | Float64 | 市盈率 |
| `pb_ratio` | Float64 | 市净率 |
| `ps_ratio` | Float64 | 市销率 |
| `dividend_yield` | Float64 | 股息率 |
| `market_cap` | Float64 | 总市值 |

**主键**：`(instrument_id, trade_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 5.4.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `pe` | `pe_ratio` | 直接映射 |
| `pb` | `pb_ratio` | 直接映射 |
| `ps` | `ps_ratio` | 直接映射 |
| `total_mv` | `market_cap` | 直接映射 |
| - | `knowledge_date` | `trade_date + 1 day` |
| - | `effective_from` | `= knowledge_date` |
| - | `effective_to` | `NULL` |

---

## 6. 公司行为域

### 6.1 股息分红 (dividend)

#### 6.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `dividend` |

#### 6.1.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `ex_dividend_date` | Date | 除权除息日 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `dividend_per_share` | Float64 | 每股股息 |
| `dividend_yield` | Float64 | 股息率 |

**主键**：`(instrument_id, ex_dividend_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 6.1.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `ex_date` | `ex_dividend_date` | 直接映射 |
| `dividend` | `dividend_per_share` | 直接映射 |

---

### 6.2 融资融券 (margin_trading)

#### 6.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `margin` |

#### 6.2.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `margin_buy_balance` | Float64 | 融资余额 |
| `short_sell_balance` | Float64 | 融券余额 |
| `margin_buy_volume` | Float64 | 融资买入量 |
| `short_sell_volume` | Float64 | 融券卖出量 |

**主键**：`(instrument_id, trade_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 6.2.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `rz_balance` | `margin_buy_balance` | 直接映射 |
| `rz_vol` | `margin_buy_volume` | 直接映射 |
| `rq_balance` | `short_sell_balance` | 直接映射 |
| `rq_vol` | `short_sell_volume` | 直接映射 |

---

### 6.3 股权质押 (pledge_ratio)

#### 6.3.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `pledge_stat` |

#### 6.3.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `report_date` | Date | 报告日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `pledge_ratio` | Float64 | 质押比例 |
| `pledge_shares` | Float64 | 质押股数 |
| `total_shares` | Float64 | 总股本 |

**主键**：`(instrument_id, report_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 6.3.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `pledge_count` | `pledge_shares` | 直接映射 |
| `total_share` | `total_shares` | 直接映射 |

---

### 6.4 公司行为 (corporate_actions)

#### 6.4.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `b_stock_act` |

#### 6.4.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 股票 ID |
| `action_type` | String | 行为类型 |
| `announcement_date` | Date | 公告日期 |
| `effective_date` | Date | 生效日期 |
| `description` | String | 描述 |

**主键**：`(instrument_id, action_type, announcement_date)`

**PIT 列**：无（非 PIT 数据）

#### 6.4.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `ba_type` | `action_type` | 直接映射 |
| `ann_date` | `announcement_date` | 直接映射 |
| `act_date` | `effective_date` | 直接映射 |
| `name` | `description` | 直接映射 |

---

## 7. 衍生品数据域

### 7.1 期货持仓 (futures_position)

#### 7.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | 期货相关接口 |

#### 7.1.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `instrument_id` | String | 合约 ID |
| `trade_date` | Date | 交易日期 |
| `knowledge_date` | Date | 数据可知日期 |
| `effective_from` | Date | 版本生效开始日期 |
| `effective_to` | Date | 版本生效结束日期 |
| `open_interest` | Float64 | 持仓量 |
| `settlement_price` | Float64 | 结算价 |
| `volume` | Float64 | 成交量 |
| `turnover` | Float64 | 成交额 |

**主键**：`(instrument_id, trade_date, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 7.1.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `oi` | `open_interest` | 直接映射 |
| `settlement` | `settlement_price` | 直接映射 |
| `vol` | `volume` | 直接映射 |
| - | `turnover` | 直接映射 |

---

### 7.2 指数成分股 (index_composition)

#### 7.2.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | `index_weight` |

#### 7.2.2 源数据 Schema

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `index_id` | String | 指数 ID |
| `instrument_id` | String | 成分股 ID |
| `weight` | Float64 | 权重 |
| `effective_from` | Date | 生效开始日期 |
| `effective_to` | Date | 生效结束日期 |

**主键**：`(index_id, instrument_id, effective_from)`

**PIT 列**：`(effective_from, effective_to)`

#### 7.2.3 转换逻辑

| 源字段 | 目标字段 | 转换规则 |
|--------|----------|----------|
| `in_date` | `effective_from` | 直接映射 |
| - | `effective_to` | 初始为 NULL |

---

## 8. 宏观数据域

### 8.1 宏观指标 (macro_indicators)

#### 8.1.1 供应商接口

| 项目 | 值 |
|------|-----|
| **供应商** | Tushare |
| **API Name** | 各类宏观接口（如 `shibor`） |

#### 8.1.2 源数据 Schema

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

**主键**：`(indicator_code, date, knowledge_date)`

**PIT 列**：`(knowledge_date,)`

---

## 9. 存储架构

### 9.1 存储格式

| 数据类型 | 存储格式 | 说明 |
|----------|----------|------|
| 时序数据 | Parquet | 按年分区，列式存储 |
| 元数据 | SQLite | 关系型数据，支持事务 |
| 临时数据 | 内存/临时文件 | 处理中间结果 |

### 9.2 目录结构

```
data_root/
├── market/                    # 市场数据
│   ├── stock/
│   │   ├── bars/             # 股票日线
│   │   │   ├── 2020.parquet
│   │   │   ├── 2021.parquet
│   │   │   └── ...
│   │   ├── adj/              # 复权因子
│   │   └── status/           # 股票状态
│   ├── etf/
│   │   └── bars/             # ETF 日线
│   └── index/
│       └── bars/             # 指数日线
├── metadata/                  # 元数据
│   ├── calendar/             # 交易日历
│   ├── instrument/           # 证券主数据
│   ├── index/
│   │   └── weight/           # 指数权重
│   └── universe/
│       └── constituent/      # 股票池成分
├── capital/                   # 资本数据
│   ├── balance_sheet/
│   ├── income_statement/
│   ├── cash_flow/
│   └── valuation_metrics/
├── corporate_actions/         # 公司行为
│   ├── dividend/
│   ├── margin_trading/
│   └── pledge_ratio/
├── derivatives/               # 衍生品
│   ├── futures_position/
│   └── index_composition/
├── macro/                     # 宏观数据
│   └── indicators/
└── meta.db                    # SQLite 元数据库
```

### 9.3 分区策略

| 数据类型 | 分区键 | 分区粒度 |
|----------|--------|----------|
| 日线行情 | `trade_date` | 按年 |
| 复权因子 | `trade_date` | 按年 |
| 财务报表 | `report_date` | 按年 |
| 元数据 | - | 单文件 |

---

## 10. PIT 数据处理

### 10.1 PIT 概念

**Point-in-Time（PIT）数据**确保回测时只使用当时可知的数据，避免未来函数（look-ahead bias）。

### 10.2 PIT 实现

| 字段 | 说明 |
|------|------|
| `knowledge_date` | 数据可知日期（公告日/披露日） |
| `effective_from` | 该版本数据生效开始日期 |
| `effective_to` | 该版本数据生效结束日期（NULL 表示当前版本） |

### 10.3 PIT 查询条件

```python
# 查询 as_of_date 时的数据
condition = """
    effective_from <= as_of_date
    AND (effective_to IS NULL OR effective_to > as_of_date)
"""
```

### 10.4 PIT 数据类型

| 数据类型 | knowledge_date 规则 | PIT 处理 |
|----------|---------------------|----------|
| 日线行情 | `trade_date + 1` | 版本控制 |
| 复权因子 | `trade_date` | 版本控制 |
| 财务报表 | `ann_date`（公告日） | 版本控制 |
| 估值指标 | `trade_date + 1` | 版本控制 |
| 公司行为 | `announcement_date` | 无版本控制 |
| 宏观指标 | 数据发布日 | 版本控制 |

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

### B. 枚举类型

**交易所 (Exchange)**:
| 值 | 说明 |
|----|------|
| `SSE` | 上海证券交易所 |
| `SZSE` | 深圳证券交易所 |
| `BSE` | 北京证券交易所 |
| `CFFEX` | 中国金融期货交易所 |
| `SHFE` | 上海期货交易所 |
| `DCE` | 大连商品交易所 |
| `CZCE` | 郑州商品交易所 |

**证券类型 (InstrumentType)**:
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
| 源数据 Schema | `packages/datahub/src/ditto_datahub/sources/schemas/` |
| 存储数据 Schema | `packages/datahub/src/ditto_datahub/stores/schemas/` |
| 列映射定义 | `packages/datahub/src/ditto_datahub/sources/tushare/processors/mappings/` |
| 数据转换器 | `packages/datahub/src/ditto_datahub/sources/tushare/processors/transformer.py` |
| Tushare 适配器 | `packages/datahub/src/ditto_datahub/sources/tushare/adapters/` |
