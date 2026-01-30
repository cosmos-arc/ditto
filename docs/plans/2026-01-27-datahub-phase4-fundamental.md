# DataHub Fundamental 域重构实施计划

> **注意:** 本阶段不在三域重构范围内。
>
> **三域重构范围:** Metadata、Market、Capital 三个域。
>
> **最新实施计划:** 参见 [2026-01-29-datahub-three-domain-refactor-implementation.md](./2026-01-29-datahub-three-domain-refactor-implementation.md)
>
> **说明:** Fundamental 域的财务报表、财务指标等功能已纳入新的 Capital 域。本计划文档保留用于参考，未来实施时需要根据最新架构调整。

---

## 原始计划（保留用于参考）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 实现完整的 Fundamental 域，支持财务报表、财务指标、业绩预告、持仓数据等

**架构:**
- 创建 `domains/fundamental/` 目录
- 按数据类型组织：financial、indicator、forecast、holding、dividend
- 实现 FundamentalQueryService 作为域级统一入口

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Phase 0 - 基础层重构, Phase 1 - Metadata 域重构

---

## 目录结构

```
packages/datahub/src/ditto_datahub/domains/fundamental/
├── __init__.py
├── financial/
│   ├── balance_sheet_store.py
│   ├── income_statement_store.py
│   └── cash_flow_store.py
├── indicator/financial_indicator_store.py
├── forecast/
│   ├── forecast_store.py
│   └── express_store.py
├── holding/
│   ├── fund_holding_store.py
│   ├── inst_holding_store.py
│   └── shareholder_store.py
├── dividend/dividend_store.py
└── fundamental_query_service.py
```

---

## 任务清单

### 任务 1: 创建 Fundamental 域目录结构

### 任务 2: 实现 Financial 子域

**2.1 实现 BalanceSheetStore**
- 数据集: balance_sheet (资产负债表)
- 接口: Tushare balancesheet
- 存储: Parquet
- 支持 PIT 查询

**2.2 实现 IncomeStatementStore**
- 数据集: income_statement (利润表)
- 接口: Tushare income
- 存储: Parquet
- 支持 PIT 查询

**2.3 实现 CashFlowStore**
- 数据集: cash_flow (现金流量表)
- 接口: Tushare cashflow
- 存储: Parquet
- 支持 PIT 查询

### 任务 3: 实现 FinancialIndicatorStore

- 数据集: financial_indicator (PE、PB、ROE 等)
- 接口: Tushare fina_indicator
- 存储: Parquet

### 任务 4: 实现 Forecast 子域

**4.1 实现 ForecastStore**
- 数据集: forecast (业绩预告)
- 接口: Tushare forecast
- 存储: Parquet
- 支持 PIT 查询

**4.2 实现 ExpressStore**
- 数据集: express (业绩快报)
- 接口: Tushare express
- 存储: Parquet

### 任务 5: 实现 Holding 子域

**5.1 实现 FundHoldingStore**
- 数据集: fund_holding (公募基金持仓)
- 接口: 需要确定数据源
- 存储: Parquet

**5.2 实现 InstHoldingStore**
- 数据集: inst_holding (机构持仓)
- 接口: 需要确定数据源
- 存储: Parquet

**5.3 实现 ShareholderStore**
- 数据集: shareholder (大股东持股)
- 接口: 需要确定数据源
- 存储: Parquet

### 任务 6: 实现 DividendStore

- 数据集: dividend (分红送转)
- 接口: 需要确定数据源
- 存储: Parquet

### 任务 7: 实现 FundamentalQueryService

### 任务 8: 更新 DataHub 集成

### 任务 9: 清理和文档更新

### 任务 10: 创建 Git Tag

---

## 验收标准

- [ ] domains/fundamental/ 目录结构完整
- [ ] 三大财务报表 Store 实现完整
- [ ] 财务指标 Store 实现完整
- [ ] 业绩预告 Store 实现完整
- [ ] 持仓数据 Store 实现 (P1)
- [ ] FundamentalQueryService 实现所有查询接口
- [ ] 测试覆盖率 ≥ 80%
- [ ] 所有代码检查通过

---

## 预计时间

**总计: 约 12-15 个工作日**

- Financial 子域: 4 天
- Indicator + Forecast: 3 天
- Holding + Dividend: 3 天
- QueryService + 集成: 2 天
- 测试 + 文档: 2-3 天
