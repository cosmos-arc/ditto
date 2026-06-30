---
last_synced: 2026-06-04
---

# Features Agent 指南

## 定位

因子、表达式、衍生数据与发布安全能力平面 — 表达式语言、因子定义、物化计划、因子评估。

## 核心模块

| 模块 | 职责 |
|------|------|
| expression/ | 表达式语言（lexer/parser/AST/compiler/codegen） |
| factors/ | 因子定义（spec/primitives/category implementations） |
| materialization/ | 物化计划（依赖推导/计划编排） |
| evaluation/ | 因子评估（IC/Fama-MacBeth/暴露分析/归因） |
| services/ | 衍生数据服务（catalog/persistence/concurrent materialization/GC） |
| storage/ | Feature-owned 存储适配 |

## 依赖规则

### 允许

- features → kernel ✅
- features → platform ✅

### 禁止

- features → strategy/portfolio/risk/execution/backtest/analysis/application/apps ❌

## 关键约束

- expression 不依赖 materialization（单向依赖）
- 因子定义依赖表达式和 spec，不依赖上层编排
- 纯计算层，feature-owned 运行时/存储适配通过 contracts/Protocols 交互
- 不直接依赖 data（数据由 application 编排注入）

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
