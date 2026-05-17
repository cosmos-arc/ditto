# Code Review 修复计划

## 概述
- Sprint: PR #64 审查修复 | Phase: 审查问题修复
- 创建: 2026-05-12

## 技术方案

11 个审查问题按依赖关系分 4 批修复。核心策略：

1. **类型修复先行** — 无依赖风险，纯机械改动
2. **FSM 清理** — 消除死代码，简化状态机
3. **跨包边界修复** — Risk/Execution 依赖解耦（最复杂）
4. **文档与防御性修复** — docstring/占位值/防御性检查

### 依赖图

```
T1 类型修复 (独立)
T2-T5 FSM/状态清理 (依赖 T1 的类型修正)
T6 Risk-Execution 解耦 (独立，最复杂)
T7-T11 文档/防御修复 (依赖 T6 解耦结果)
```

---

## 任务清单

### Batch 1: 类型修复 (独立，无依赖)

- [x] T1: 修复 `OrderSubmitted`/`OrderFilled` 类型不匹配 `[S]`
  - 验收: `OrderSubmitted.quantity: int`, `OrderFilled.filled_quantity: int`; basedpyright 通过
  - 文件: `packages/execution/src/ditto_execution/events.py`
  - 改动: `quantity: float` → `quantity: int` (line 27); `filled_quantity: float` → `filled_quantity: int` (line 37)
  - 测试: 确认 `test_order_events_unit.py` 类型推断正确

### Batch 2: FSM 与状态清理 (依赖 T1)

- [x] T2: 清理 FSM `_fill_transition` 死代码路径 `[S]`
  - 验收: 移除 line 75-78 不可达的 TRANSITIONS fallback; TRANSITIONS 表移除 FILL 条目; 所有现有测试通过
  - 文件: `packages/execution/src/ditto_execution/orders/fsm.py`
  - 改动:
    - 移除 `(SUBMITTED, FILL)` 和 `(PARTIALLY_FILLED, FILL)` 条目从 TRANSITIONS 表 (lines 14, 18)
    - 简化 `_fill_transition`: `if fill_qty > 0 and leaves_qty > 0` → `if leaves_qty > 0`; `leaves_qty <= 0` 时 raise `OrderStateError`
    - 添加注释: "FILL transitions handled by _fill_transition(), not TRANSITIONS table"
  - 测试: `packages/execution/tests/unit/orders/test_fsm_unit.py`

- [x] T3: 消除 `_apply_fill` 双重状态计算 `[M]`
  - 验收: `OrderEvent.status` 由 FSM 结果驱动，不独立计算; 事件日志与 ticket 状态一致
  - 文件: `packages/backtest/src/ditto_backtest/brokerage.py` (lines 349-374)
  - 改动:
    - `_apply_fill` 先调用 `ticket.with_fill()` 获取 `updated_ticket`
    - 从 `updated_ticket.status` 构建 `OrderEvent`（而非手动计算）
    - 注意：`with_fill` 内部已记录 event 到 `order_events`，需确认 journal 是否重复
  - 测试: `packages/backtest/tests/unit/test_brokerage_unit.py` + 验证 event.status == ticket.status

- [x] T4: PlanningStep 传递 `order_book` 到 planner `[S]`
  - 验收: `PlanningStep.execute()` 传递 `order_book=ctx.order_book`; planner 可见 pending orders
  - 文件: `packages/backtest/src/ditto_backtest/steps/planning.py` (line 65-72)
  - 改动: 在 `self._planner.plan(...)` 调用中添加 `order_book=ctx.order_book`
  - 测试: `packages/backtest/tests/unit/test_planning_step.py`

- [x] T5: 移除 `OrderExpired` 孤儿事件 `[S]`
  - 验收: 删除 `OrderExpired` 类定义; 移除 `EventName.ORDER_EXPIRED`; 清理 `__all__`; 所有测试通过
  - 文件:
    - `packages/execution/src/ditto_execution/events.py` (删除 class + __all__ 条目)
    - `packages/kernel/src/ditto_kernel/events.py` (移除 `ORDER_EXPIRED` 常量)
  - 测试: 确认无消费者引用 `OrderExpired`

### Batch 3: Risk-Execution 边界解耦 (最复杂)

- [x] T6: 解耦 Risk 对 Execution 的依赖 — 提取 Protocol `[L]`
  - 验收: `ditto_risk` 不再直接依赖 `ditto_execution`; importlinter `ignore_imports` 可移除; 所有 risk 测试通过
  - 技术方案:
    1. 在 `ditto_risk/contracts.py` 定义两个 Protocol:
       - `PreTradeOrder` — 暴露 `instrument_id`, `quantity`, `direction`, `order_type`, `price`, `order_id` (只读属性)
       - `PreTradeTicket` — 暴露 `order: PreTradeOrder`, `status`, `leaves_quantity`, `filled_quantity` (只读属性)
    2. 更新 `ditto_risk/constraints/context.py`:
       - `PreTradeContext.pending_tickets: tuple[PreTradeTicket, ...]`
       - `estimate_order_cost(order: PreTradeOrder)` 和 `with_order_accepted(order: PreTradeOrder)`
    3. 更新 `ditto_risk/constraints/checks.py`:
       - 所有 `Order` 类型替换为 `PreTradeOrder`
    4. 更新 `ditto_risk/exposure/checks.py`:
       - `Order` → `PreTradeOrder`
    5. 移除 `packages/risk/pyproject.toml` 的 `ditto-execution` 依赖
    6. 移除 `.importlinter` 中 risk-boundary 的 `ignore_imports`
    7. 运行 `arch-check` 确认边界合规
  - 文件:
    - `packages/risk/src/ditto_risk/contracts.py` (新增 Protocol)
    - `packages/risk/src/ditto_risk/constraints/context.py`
    - `packages/risk/src/ditto_risk/constraints/checks.py`
    - `packages/risk/src/ditto_risk/exposure/checks.py`
    - `packages/risk/pyproject.toml`
    - `.importlinter`
  - 测试:
    - 更新 `test_risk_import_boundary_unit.py` 确认无 execution 依赖
    - 确认所有 `packages/risk/tests/unit/` 通过
    - 确认 `arch-check` 36/36 contracts

### Batch 4: 文档与防御性修复 (依赖 T1, T6)

- [x] T7: 修复 `PositionChanged` docstring 与类型 `[S]`
  - 验收: docstring 反映实际发布行为; `instrument_id` 使用 `InstrumentId` 类型
  - 文件: `packages/portfolio/src/ditto_portfolio/events.py`
  - 改动:
    - docstring: `"reserved — 当前未在生产流程中发布"` → `"持仓变更事件 — Account.apply_fill 通过 event_bus 发布"`
    - `instrument_id: int` → `instrument_id: InstrumentId`; 添加 import
    - `quantity_change: float` → `quantity_change: int`; `new_quantity: float` → `new_quantity: int` (持仓数量为整数)
  - 测试: `packages/portfolio/tests/unit/test_position_events_unit.py`

- [x] T8: 修复 `OrderBookReadOnly.__init__` 不可变性保证 `[S]`
  - 验收: 构造函数创建 dict 副本; docstring 准确描述不可变性
  - 文件: `packages/execution/src/ditto_execution/orders/book.py` (lines 16-20)
  - 改动: `self._tickets = dict(tickets)` (浅拷贝); docstring 更新
  - 测试: `packages/execution/tests/unit/orders/test_book_unit.py`

- [x] T9: 修复 `OrderBook.cancel()` 终态防御 `[S]`
  - 验收: cancel 前检查 `is_terminal`; 终态返回而非抛异常
  - 文件: `packages/execution/src/ditto_execution/orders/book.py` (lines 63-75)
  - 改动: 在构造 event 前添加 `if ticket.status.is_terminal: return` (或 raise 更明确的错误)
  - 测试: `packages/execution/tests/unit/orders/test_book_unit.py`

- [x] T10: 修复 `PositionChanged` 在 portfolio CLAUDE.md 的状态描述 `[S]`
  - 验收: PORT-P1-03 从 "reserved" 更新为 "active"
  - 文件: `packages/portfolio/CLAUDE.md`
  - 改动: 更新 PORT-P1-03 表格行的描述

- [x] T11: 替换 `_make_filled` 中硬编码 `datetime(2026, 1, 1)` `[S]`
  - 验收: 使用 `datetime.min` 作为 sentinel; 添加注释说明 Brokerage 会覆盖
  - 文件: `packages/backtest/src/ditto_backtest/simulation/fill.py` (line 234)
  - 改动: `datetime(2026, 1, 1)` → `datetime.min`; 添加注释
  - 测试: `packages/backtest/tests/unit/` 相关 fill model 测试

---

## 执行顺序

```
Batch 1 (T1) → 独立，先做
  ↓
Batch 2 (T2 → T3 → T4 → T5) → FSM/状态清理，顺序执行
  ↓
Batch 3 (T6) → 最复杂，独立执行
  ↓
Batch 4 (T7 → T8 → T9 → T10 → T11) → 收尾

全程: pixi run -e dev check 验证
```

## 风险评估

| 任务 | 风险 | 缓解 |
|------|------|------|
| T6 (Risk 解耦) | Protocol 结构性变更可能影响 PreTradeStep 调用方 | execution.Order 已满足 Protocol duck-typing; 确认 `@runtime_checkable` |
| T3 (双重状态) | with_fill 内部已追加 event，修改需防重复 | 仔细阅读 ticket.py with_fill 确认 event 是否已存储 |
| T1 (类型修复) | `float` → `int` 可能影响 JSON 序列化 | DomainEvent 是 frozen dataclass，不影响 |

## 复杂度汇总

| 等级 | 数量 | 任务 |
|------|------|------|
| S | 8 | T1, T2, T4, T5, T7, T8, T9, T10, T11 |
| M | 1 | T3 |
| L | 1 | T6 |
| **总计** | **11 任务** | **预估 ~300 行改动** |
