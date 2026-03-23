# Phase 2 Part 02: ExecutionPlanner 简化版

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 TargetPortfolio 转换为 Order 列表，实现 pending-aware diff 和 locked_instruments 检查

**Architecture:** ExecutionPlanner 是决策层（TargetPortfolio）到执行层（Order）的桥接组件。简化版不含 T+1/涨跌停/停牌/100+1，但包含 F2 (pending-aware diff) 和 S1 (planner lock)。

**Design Doc:** v3 §4.2 (ExecutionPlanner)

**Prerequisite:** Part 01 (Order) + Phase 0 accounting/ + Phase 1 portfolio/

---

## 简化边界

| 功能 | Phase 2 简化版 | Phase 3 完整版 |
|------|---------------|---------------|
| pending-aware diff (F2) | ✅ | ✅ |
| locked_instruments (S1) | ✅ | ✅ |
| all_instruments 合并 (R2) | ✅ | ✅ |
| T+1 冻结检查 | ❌ | ✅ |
| 涨跌停预检 | ❌ | ✅ |
| 停牌过滤 | ❌ | ✅ |
| 100+1 取整 | ❌ | ✅ |

## 任务清单

- [ ] Task 2.1: `ExecutionPlan` frozen dataclass `[S]`
  - 验收: plan_id, trade_date, orders(tuple[Order]), estimated_turnover, estimated_cost, blocked_orders(tuple[BlockedOrder])
  - 文件: `packages/core/src/ditto_core/execution/planner.py`

- [ ] Task 2.2: `BlockedOrder` frozen dataclass `[S]`
  - 验收: instrument_id, direction, intended_quantity, reason, severity("block"/"defer")
  - 文件: `packages/core/src/ditto_core/execution/planner.py`

- [ ] Task 2.3: `ExecutionPlanner` Protocol `[S]`
  - 验收: plan(target, account, slice, trade_date, rules, locked_instruments?) → ExecutionPlan
  - 文件: `packages/core/src/ditto_core/execution/planner.py`

- [ ] Task 2.4: `SimpleExecutionPlanner._compute_pending_delta()` `[M]`
  - 验收: 汇总 pending orders 的净数量变化（buy +, sell -）
  - 文件: `packages/core/src/ditto_core/execution/planner.py`
  - 测试:
    - 无 pending orders → 空 delta
    - 一个 pending buy(300) → delta[iid] = +300
    - 一个 pending sell(200) → delta[iid] = -200
    - mixed pending → 净量正确

- [ ] Task 2.5: `SimpleExecutionPlanner._compute_diff()` `[L]`
  - 验收:
    - target_qty > effective_qty + locked → BlockedOrder(reason="risk_locked")
    - target_qty > effective_qty → buy order
    - target_qty < effective_qty → sell order
    - target_qty == effective_qty → 无订单
    - 退出标的（当前有仓位但 target 无）→ 全部卖出
    - 空仓首次建仓 → 纯买入
  - 文件: `packages/core/src/ditto_core/execution/planner.py`

- [ ] Task 2.6: `SimpleExecutionPlanner.plan()` 完整编排 `[M]`
  - 验收: 合并 all_instruments → 获取 rules → 计算 diff → 构建 ExecutionPlan
  - 文件: `packages/core/src/ditto_core/execution/planner.py`
  - all_instruments = target.instrument_ids ∪ current positions ∪ pending order instruments (R2)

- [ ] Task 2.7: 包导出更新 `[S]`
  - 验收: execution/__init__.py 导出 ExecutionPlan, BlockedOrder, ExecutionPlanner, SimpleExecutionPlanner
  - 文件: `packages/core/src/ditto_core/execution/__init__.py`

- [ ] Task 2.8: 单元测试 `[M]`
  - 文件: `packages/core/tests/unit/execution/test_planner_unit.py`
  - 场景:
    - pending-aware: 有 pending sell 时不重复生成卖单 (F2)
    - planner lock: 锁定标的不生成买单 (S1)
    - exit instruments: 退出标的生成全部卖出 (R2)
    - empty to initial: 空仓首次建仓
    - no rebalance: target == current → 无订单
    - mixed: 部分调仓 + 退出 + 新增

---

## 文件清单

```
packages/core/src/ditto_core/execution/
├── __init__.py           # 更新导出
└── planner.py            # [新增] ExecutionPlanner / ExecutionPlan / BlockedOrder / SimpleExecutionPlanner

packages/core/tests/unit/execution/
└── test_planner_unit.py  # [新增]
```

## 质量门禁

```bash
pixi run -e dev check
```
