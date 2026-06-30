# Ditto Execution

**版本**: v0.1.0 | **日期**: 2026-06-04 | **状态**: 稳定

## 概要

交易执行 — 订单管理（OMS Lite）、券商网关抽象、执行现实模拟（费用/滑点/交收）、审计与对账。

## 核心子域

| 子域 | 职责 |
|------|------|
| orders | OMS Lite — FSM 状态机、Journal、双 ID 追踪 |
| fills | 成交处理与匹配 |
| broker | 券商网关 Protocol + PaperGateway 实现 |
| reality | 费用/滑点模型，执行现实模拟 |
| audit | 执行审计日志 |
| storage | SQLite 持久化存储 |
| reconciliation | 对账与差异检测 |

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 详细架构规则与导入约束
