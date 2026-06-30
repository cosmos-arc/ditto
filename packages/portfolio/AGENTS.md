---
last_synced: 2026-06-04
---

# Portfolio Agent 指南

## 定位

组合构建与管理平面 — 会计系统（账户/持仓/现金/购买力/订单簿）、调仓逻辑（权重分配/约束检查）。

## 核心模块

| 模块 | 职责 |
|------|------|
| accounting/ | 会计系统（account/position/cash/buying_power/order_book/fills） |
| rebalancing/ | 调仓逻辑（allocation/constraints/comparison） |
| contracts.py | 组合领域契约 |
| events.py | 领域事件 |

## 依赖规则

### 允许

- portfolio → kernel ✅

### 禁止

- portfolio → data/features/strategy/risk/execution/backtest/analysis/application/apps ❌
- portfolio → platform ❌

## 关键约束

- 纯领域模型层，不依赖具体执行或风控实现
- 会计系统是投资组合的状态机，所有操作通过显式方法变更
- 调仓逻辑只做权重计算，不做交易决策

## 详细规范

参见 [CLAUDE.md](CLAUDE.md)。
