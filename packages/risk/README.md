# Ditto Risk

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.1.0 | **日期**: 2026-06-04 | **状态**: 稳定

## 概要

风险管理 — 盘前/盘后风控、约束检查、暴露度管理、回撤控制。

## 核心子域

| 子域 | 职责 |
|------|------|
| constraints | 预交易约束检查 |
| exposure | 暴露度分析与监控 |
| drawdown | 回撤规则与控制 |
| observability | 可观测性 — 风控指标与告警 |

## 相关文档

- [AGENTS.md](AGENTS.md) — 详细架构规则与导入约束
