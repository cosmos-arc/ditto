---
last_synced: 2026-06-04
---

# Application Agent 指南

## 定位

应用编排层 — CQRS 模式组织 Use Case，协调 capability packages（领域计算）与 Data（数据服务）。

## 核心模块

| 模块 | 职责 |
|------|------|
| queries/ | 只读查询（metadata/market/capital/fundamental/macro/backtest/strategy/trade） |
| commands/ | Command DTO + Handler（ingestion/quality/strategy/trade/universe） |
| processes/ | Process Manager（ingestion/materialization/execution/quality） |
| builders/ | 运行时装配（runtime_builder/slice_builder/service_factory） |
| providers*.py | DI Provider（6 个：Command/MarketQuery/StrategyQuery/PortfolioQuery/Process/Builder） |

## 依赖规则

### 允许

- application → kernel/data/strategy/portfolio/risk/execution/backtest/features/platform ✅

### 禁止

- application → apps ❌
- queries → processes/commands/builders ❌
- commands → queries/builders ❌

## 关键约束

- 纯编排层，不包含核心业务逻辑
- CQRS 互斥规则由 importlinter R8 合约强制
- queries 禁止写入，commands 禁止读取，processes 可双向
- 禁止直接使用 platform.config（配置加载走 apps）

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
