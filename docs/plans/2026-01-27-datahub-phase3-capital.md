# DataHub Capital 域重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 实现完整的 Capital 域，支持资金流向、融资融券、龙虎榜、打板、筹码分布等数据

**架构:**
- 创建 `domains/capital/` 目录
- 按数据类型组织：flow、margin、top_board、limit_board、chip
- 实现 CapitalQueryService 作为域级统一入口

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Phase 0 - 基础层重构, Phase 2 - Market 域重构

---

## 目录结构

```
packages/datahub/src/ditto_datahub/domains/capital/
├── __init__.py
├── flow/
│   ├── market_flow_store.py

│   ├── industry_flow_store.py
│   └── stock_flow_store.py
├── margin/
│   ├── margin_detail_store.py
│   └── margin_summary_store.py
├── top_board/top_board_store.py
├── limit_board/limit_board_store.py
├── chip/chip_distribution_store.py
└── capital_query_service.py
```

---

## 任务清单

### 任务 1: 创建 Capital 域目录结构

创建基本的域目录和 __init__.py 文件。

### 任务 2: 实现 Flow 子域

**2.1 实现 MarketFlowStore**
- 数据集: market_flow (市场级别北向/南向资金)
- 接口: Tushare moneyflow_hsgt
- 存储: Parquet

**2.2 实现 StockFlowStore**
- 数据集: stock_flow (个股资金明细)
- 接口: Tushare moneyflow
- 存储: Parquet

**2.3 实现 IndustryFlowStore**
- 数据集: industry_flow (行业资金分布)
- 生成逻辑: 从 StockFlowStore 按 industry_mapping 聚合
- 存储: Parquet

### 任务 3: 实现 Margin 子域

**3.1 实现 MarginDetailStore**
- 数据集: margin_detail (融资融券明细)
- 接口: Tushare mtsk
- 存储: Parquet

**3.2 实现 MarginSummaryStore**
- 数据集: margin_summary (市场汇总)
- 接口: Tushare mtsk_sec
- 存储: Parquet

### 任务 4: 实现 TopBoardStore

- 数据集: top_board (龙虎榜)
- 接口: Tushare top_list + top_inst
- 存储: Parquet

### 任务 5: 实现 LimitBoardStore

- 数据集: limit_board (打板数据)
- 接口: Tushare limit_list_d
- 存储: Parquet

### 任务 6: 实现 ChipDistributionStore

- 数据集: chip_distribution (筹码分布)
- 接口: Tushare cyq_chips
- 存储: Parquet

### 任务 7: 实现 CapitalQueryService

整合所有 Capital 子域的查询功能。

### 任务 8: 更新 DataHub 集成

### 任务 9: 清理和文档更新

### 任务 10: 创建 Git Tag

---

## 验收标准

- [ ] domains/capital/ 目录结构完整
- [ ] 所有 Flow Store 实现完整
- [ ] Margin 子域实现完整
- [ ] TopBoard/LimitBoard/Chip 实现完整
- [ ] CapitalQueryService 实现所有查询接口
- [ ] 测试覆盖率 ≥ 80%
- [ ] 所有代码检查通过

---

## 预计时间

**总计: 约 10-12 个工作日**

- Flow 子域: 3 天
- Margin 子域: 2 天
- TopBoard/LimitBoard/Chip: 2 天
- QueryService + 集成: 2 天
- 测试 + 文档: 1-2 天
