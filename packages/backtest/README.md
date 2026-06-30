# Ditto Backtest

**版本**: v0.1.0 | **日期**: 2026-06-04 | **状态**: 稳定

## 概要

回测引擎 — EngineLoop 日历步进，Step chain 编排，绩效统计。

## 核心子域

| 子域 | 职责 |
|------|------|
| engine | EngineLoop 主循环，日历步进调度 |
| steps | Step chain — 策略/风控/执行/审计步骤编排 |
| simulation | 模拟模型 — brokerage/fill/slippage/settlement |
| audit | 审计子系统，回测过程追踪 |
| statistics | 绩效统计指标计算 |

## 相关文档

- [CLAUDE.md](CLAUDE.md) — 详细架构规则与导入约束
