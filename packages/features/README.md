# Ditto Features

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.1.0 | **日期**: 2026-06-04 | **状态**: 稳定

## 概要

因子与表达式计算 — Pratt Parser DSL、因子库（15 类）、物化编排、因子评估（IC/Fama-MacBeth）。

## 核心子域

| 子域 | 职责 |
|------|------|
| expression | Expression DSL — lexer/parser/AST/codegen/compiler |
| factors | 因子库（15 类因子定义） |
| materialization | 物化计划与缓存管理 |
| evaluation | 评估指标 — IC/ICIR/Fama-MacBeth/归因分析 |
| services | 衍生数据服务与发布安全 |
| storage | 存储适配层 |

## 相关文档

- [AGENTS.md](AGENTS.md) — 详细架构规则与导入约束
