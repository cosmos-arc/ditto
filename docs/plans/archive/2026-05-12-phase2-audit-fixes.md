# Phase 2 OMS Lite 审计修复计划

## 概述
- Sprint: B10 | Phase: 2 审计修复
- 创建: 2026-05-12
- 基线: Phase 2 OMS Lite 源码审计发现的 7 项问题
- 分支: `remediation/cross-module-b1-b7`（当前分支）

## 问题清单

| ID | 问题 | 严重度 | 类型 |
|----|------|--------|------|
| F1 | FSM `_fill_transition` 零数量成交未防御 | BUG | 代码缺陷 |
| F2 | `OrderTicket.with_fill()` 缺少 quantity > 0 校验 | BUG | 代码缺陷 |
| F3 | `OrderEvent.timestamp` 硬编码 `datetime(2026, 1, 1)` 默认值 | RISK | 潜在风险 |
| F4 | `account.py:256` 的 `type: ignore[assignment]` | STYLE | 规约违反 |
| F5 | `execution/CLAUDE.md` Known Gaps 过时 | DOC | 文档债务 |
| F6 | `portfolio/CLAUDE.md` 引用已删除的 `order_book.py` | DOC | 文档债务 |
| F7 | Phase 2 计划文档 T8-T11 未勾选 | DOC | 文档不同步 |

## 技术方案

### F1+F2: FSM 防御性校验
- 在 `_fill_transition()` 入口加 `fill_qty <= 0` 防御 → `OrderStateError`
- 在 `OrderTicket.with_fill()` 入口加 `quantity <= 0` 校验 → `ValueError`
- 两层防御：FSM 是纯函数层的断言，with_fill 是 API 层的校验

### F3: 时间戳默认值
- 改为 `datetime.now(tz=UTC)` — 生成真实时间戳
- 测试中已有调用方显式传入 timestamp（BacktestBrokerage 等），不受影响
- OrderBook.submit/cancel 内部创建的事件同样受益于真实默认值

### F4: type: ignore 消除
- 重构 `_apply_position_updates` 参数类型：`Position | None` → 独立的 upsert/remove 类型
- 或直接在 upsert 分支解构时做 assertion
- 最小改动方案：upsert 分支解构后加 assert pos is not None，消除 type: ignore

### F5-F7: 文档同步
- execution CLAUDE.md：更新 orders/ 目录描述 + Known Gaps + 测试位置
- portfolio CLAUDE.md：移除 order_book.py 行 + 更新测试位置
- Phase 2 计划文档：勾选 T8-T11

---

## 任务清单

### Wave 1: 代码修复

- [x] F1+F2: FSM + with_fill 防御性校验 `[M]`
  - 验收:
    - `transition(SUBMITTED, FILL, fill_qty=0)` → `OrderStateError`
    - `transition(SUBMITTED, FILL, fill_qty=-1)` → `OrderStateError`
    - `ticket.with_fill(quantity=0, ...)` → `ValueError`
    - `ticket.with_fill(quantity=-1, ...)` → `ValueError`
    - 现有测试全部通过（无回归）
  - 文件:
    - `packages/execution/src/ditto_execution/orders/fsm.py` — `_fill_transition` 加防御
    - `packages/execution/src/ditto_execution/orders/ticket.py` — `with_fill` 加校验
    - `packages/execution/tests/unit/orders/test_fsm_unit.py` — 新增 2 个参数化用例
    - `packages/execution/tests/unit/orders/test_ticket_unit.py` — 新增 2 个测试
  - 依赖: 无

- [x] F3: 时间戳默认值修正 `[S]`
  - 验收:
    - `OrderEvent` 不传 timestamp → 得到当前 UTC 时间（非 2026-01-01）
    - OrderBook.submit/cancel 创建的事件使用真实时间戳
    - 现有显式传 timestamp 的测试不受影响
  - 文件:
    - `packages/execution/src/ditto_execution/orders/event.py` — 改 default_factory
    - `packages/execution/src/ditto_execution/orders/book.py` — submit/cancel 移除硬编码
  - 依赖: 无

- [x] F4: account.py type: ignore 消除 `[S]`
  - 验收:
    - `account.py` 零 `type: ignore`（grep 验证）
    - basedpyright strict 通过
  - 文件:
    - `packages/portfolio/src/ditto_portfolio/accounting/account.py` — `_apply_position_updates` 类型收窄
  - 依赖: 无

### Wave 2: 文档同步

- [x] F5: execution CLAUDE.md 更新 `[S]`
  - 验收: orders/ 目录描述反映实际文件；Known Gaps 中 OMS Lite 标记为已实现
  - 文件:
    - `packages/execution/CLAUDE.md` — 3 处修改（目录 + Known Gaps + 测试位置）
  - 依赖: 无

- [x] F6: portfolio CLAUDE.md 更新 `[S]`
  - 验收: 移除 `order_book.py` 引用；account.py 描述更新；测试列表移除 test_order_book_unit.py
  - 文件:
    - `packages/portfolio/CLAUDE.md` — 3 处修改
  - 依赖: 无

- [x] F7: Phase 2 计划文档勾选 `[S]`
  - 验收: T8-T11 标记为 `[x]`
  - 文件:
    - `docs/plans/2026-05-11-phase2-oms-lite-plan.md` — 勾选 4 个任务
  - 依赖: 无

### Wave 3: 验证

- [x] F8: 全量验证 `[S]`
  - 验收: `pixi run -e dev check` 通过；`pixi run -e dev arch-check` 通过
  - 依赖: F1-F7 全部完成

---

## 依赖图

```
F1+F2 (FSM+ticket) ──┐
F3 (timestamp) ───────┤
F4 (type ignore) ─────┼──→ F8 (验证)
F5 (exec CLAUDE.md) ──┤
F6 (port CLAUDE.md) ──┤
F7 (plan checkboxes) ─┘
```

所有 F1-F7 可并行执行，F8 串行收尾。

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| F3 改 timestamp 默认值可能影响未显式传 timestamp 的测试 | 中 | 先 grep 找出所有依赖默认值的测试，逐一修正 |
| F4 type 收窄可能需要调整 `_calculate_new_position` 返回类型 | 低 | 用 assert 最小改动 |
