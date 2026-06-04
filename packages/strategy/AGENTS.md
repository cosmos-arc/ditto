---
last_synced: 2026-06-04
---

# Strategy Agent 指南

## 定位

策略定义与信号生成能力包 — Alpha Pipeline（Pipeline + Stage）、策略模板、信号契约、策略规格。

## 核心模块

| 模块 | 职责 |
|------|------|
| alpha/ | Alpha pipeline（builtins/templates/pipeline/protocols/specs） |
| signals/ | 信号契约（SignalStore Protocol + 信号模型） |
| storage/sqlite/ | 策略持久化（spec/run/artifact） |
| runs/ | 策略运行模型 |
| di/ | 依赖注入 |

## 依赖规则

### 允许

- strategy → kernel ✅
- strategy → platform ✅（SQLite / 日志 / 追踪）

### 禁止

- strategy → data/features/portfolio/risk/execution/backtest ❌
- strategy → application/apps/analysis ❌

## 关键约束

- 市场数据通过 StrategyInputBundle 由 application/backtest 注入，不直接依赖 data
- 信号存储通过 SignalStore Protocol 注入，不持有具体实现
- DecisionFrame 通过列名约定流转数据（instrument_id/signal/score/weight）
- 策略只产出信号和规格，组合/风控/执行由编排层负责

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
