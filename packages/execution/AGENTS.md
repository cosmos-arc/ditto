---
last_synced: 2026-06-04
---

# Execution Agent 指南

## 定位

交易执行平面 — 订单管理（OMS）、券商网关抽象、执行现实模拟（费用/滑点/交收）、交易审计与对账。

## 核心模块

| 模块 | 职责 |
|------|------|
| broker/ | 券商网关抽象（BrokerGateway Protocol） |
| orders/ | 订单管理 |
| fills/ | 成交处理 |
| reality/ | A 股执行现实（费用/滑点/交收） |
| audit/ | 交易审计（不可篡改） |
| storage/sqlite/ | 交易数据持久化 |
| di/ | 依赖注入 Provider |

## 依赖规则

### 允许

- execution → kernel ✅
- execution → portfolio ✅
- execution → platform ✅（仅 foundation）

### 禁止

- execution → data/features/strategy/backtest/analysis/application/apps ❌

## 关键约束

- 不依赖回测或分析层
- Broker Gateway 是与外部券商的唯一接口
- 审计记录所有交易行为，不可篡改
- 执行现实模拟封装 A 股规则（T+1/涨跌停/费用）

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
