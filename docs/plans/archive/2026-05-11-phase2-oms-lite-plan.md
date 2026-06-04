# Phase 2: OMS Lite 实施计划

## 概述
- Sprint: B10 | Phase: 2 - OMS Lite
- 创建: 2026-05-11
- 基线: `docs/plans/2026-05-10-deferred-items-design.md` §Phase 2 + Phase 3 降级项
- 分支: `remediation/phase2-oms-lite`

## 技术方案

### 核心变更
1. Order 生命周期管理从 portfolio 迁移至 execution（FSM + Journal + 双 ID）
2. Account 与 OrderBook 解耦（Account 只接受 FillEvent 更新现金/持仓）
3. TradeDataPort ISP 拆分（10 方法 → 3 窄 Port）

### 关键架构约束
- `ditto_portfolio` 禁止依赖 `ditto_execution`（单向：execution → portfolio）
- 因此 Account/AccountView 不能引用 execution 的 OrderBook/OrderTicket
- AccountView 的 `order_book: OrderBookReadOnly` 和 `pending_buy_value: float` 字段需移除
- StepContext（backtest 包）新增 `order_book` 引用，PreTradeStep 从 StepContext 获取 pending orders

### 影响范围
| 包 | 新增文件 | 修改文件 | 删除文件 |
|---|---------|---------|---------|
| execution | 9 (orders/) | 6 (planner, brokerage, contracts, events, target_diff, trade_builder) | 1 (orders/store.py) |
| portfolio | 0 | 3 (account.py, account/__init__.py, contracts.py) | 0 |
| backtest | 0 | 4 (brokerage.py, steps/pre_trade.py, steps/types.py, engine_steps.py) | 0 |
| kernel | 0 | 1 (events.py EventName enum) | 1 (strategy.py DecisionFrame) |
| application | 0 | 7 (providers, queries, commands referencing TradeDataPort) | 0 |

---

## 任务清单

### Wave 1: 新类型定义（execution only，零现有代码改动） ✅ 已完成

- [x] T1: Order ID + Status + Trigger 类型定义 `[S]`
  - 验收: 类型定义通过 basedpyright strict；FSM 转换表覆盖全部合法路径
  - 文件:
    - `packages/execution/src/ditto_execution/orders/ids.py` — ClientOrderId, BrokerOrderId 值对象
    - `packages/execution/src/ditto_execution/orders/status.py` — OrderStatus(StrEnum), 7 状态 + is_terminal
    - `packages/execution/src/ditto_execution/orders/trigger.py` — OrderTrigger(StrEnum), 5 触发器
  - 测试: `packages/execution/tests/unit/orders/test_ids_unit.py`
    - ClientOrderId.generate() 生成 "ditto-" 前缀 UUID
    - BrokerOrderId 值对象不变性
    - OrderStatus.is_terminal 正确性
  - 依赖: 无

- [x] T2: FSM 转换表 + transition() 函数 `[M]`
  - 验收: 全部合法转换通过；非法转换抛出 OrderStateError；FILL 路径正确区分 FILLED/PARTIALLY_FILLED
  - 文件:
    - `packages/execution/src/ditto_execution/orders/fsm.py` — TRANSITIONS 表 + _TRIGGER_TARGET + transition()
  - 测试: `packages/execution/tests/unit/orders/test_fsm_unit.py`
    - 全部合法 (status, trigger) 组合 → 正确目标状态
    - 非法组合 → OrderStateError
    - FILL + fill_qty == leaves_qty → FILLED
    - FILL + fill_qty < leaves_qty → PARTIALLY_FILLED
    - FILL + current=PARTIALLY_FILLED → 正确处理
    - 参数化: 全部非法转换（terminal 状态 + 各 trigger）
  - 依赖: T1

- [x] T3: Order 模型 + OrderEvent + Journal Protocol `[M]`
  - 验收: Order 使用 ClientOrderId；OrderEvent 含 trigger 字段；Journal Protocol 可实例化内存实现
  - 文件:
    - `packages/execution/src/ditto_execution/orders/model.py` — Order(frozen dataclass), OrderType, OrderDirection
    - `packages/execution/src/ditto_execution/orders/event.py` — OrderEvent(frozen, 含 trigger)
    - `packages/execution/src/ditto_execution/orders/journal.py` — OrderEventJournal Protocol + InMemoryOrderEventJournal
  - 测试: `packages/execution/tests/unit/orders/test_journal_unit.py`
    - InMemoryOrderEventJournal.append() + events_for() + all_events()
    - events_for(unknown_id) → 空 tuple
    - OrderEvent frozen 不变性
  - 依赖: T1

- [x] T4: OrderTicket（集成 FSM）`[M]`
  - 验收: with_fill/with_cancel/with_reject/with_invalid 内部调用 transition()；leaves_quantity 正确；order_events 自动追加
  - 文件:
    - `packages/execution/src/ditto_execution/orders/ticket.py` — OrderTicket(frozen dataclass)
  - 测试: `packages/execution/tests/unit/orders/test_ticket_unit.py`
    - with_fill() → FILLED（完全成交）或 PARTIALLY_FILLED（部分成交）
    - with_cancel() → CANCELED + OrderEvent 追加
    - with_reject() → REJECTED
    - with_invalid() → INVALID
    - terminal 状态 with_cancel → OrderStateError
    - terminal 状态 with_invalid → OrderStateError
    - leaves_quantity 计算：order.quantity - filled_quantity
    - average_fill_price 多次成交累积计算
  - 依赖: T2, T3

- [x] T5: OrderBook + OrderBookReadOnly `[M]`
  - 验收: OrderBook 使用 Journal 追踪事件；readonly_view() 返回只读快照
  - 文件:
    - `packages/execution/src/ditto_execution/orders/book.py` — OrderBook(mutable) + OrderBookReadOnly(readonly)
  - 测试: `packages/execution/tests/unit/orders/test_book_unit.py`
    - submit() → ticket 状态 SUBMITTED
    - update() → ticket 替换
    - cancel() → ticket 状态 CANCELED + journal 事件
    - get_pending() → 只返回非 terminal ticket
    - readonly_view() → OrderBookReadOnly 快照
    - cancel(unknown_id) → KeyError
    - cancel(terminal ticket) → OrderStateError
  - 依赖: T4

- [x] T6: Domain Event 扩展 `[S]`
  - 验收: OrderRejected/OrderExpired 正确继承 DomainEvent；EventName enum 新增 2 值
  - 文件:
    - `packages/execution/src/ditto_execution/events.py` — 新增 OrderRejected, OrderExpired
    - `packages/kernel/src/ditto_kernel/events.py` — EventName 新增 ORDER_REJECTED, ORDER_EXPIRED
  - 测试: `packages/execution/tests/unit/test_events_unit.py`（已有文件追加测试）
    - OrderRejected 字段验证
    - OrderExpired 字段验证
    - event_type 自动设置正确
  - 依赖: 无

- [x] T7: execution/orders/ barrel 导出 `[S]`
  - 验收: __init__.py 导出全部公开类型；arch-check 通过
  - 文件:
    - `packages/execution/src/ditto_execution/orders/__init__.py` — __all__ 导出
  - 测试: `packages/execution/tests/unit/orders/test_orders_exports_unit.py`
    - 验证全部公开类型可从 orders 包导入
  - 依赖: T1-T5

### Wave 2: Account 解耦 + 跨包适配

- [x] T8: Account 与 OrderBook 解耦 `[L]`
  - 验收: Account 不再持有 order_book 字段；AccountView 移除 order_book 和 pending_buy_value；现有 portfolio 测试全通过
  - 文件:
    - `packages/portfolio/src/ditto_portfolio/accounting/account.py` — 移除 order_book 字段，重构 get_view()
    - `packages/portfolio/src/ditto_portfolio/accounting/order_book.py` — OrderBookReadOnly 保留（仅 AccountView 引用检查）
    - `packages/portfolio/src/ditto_portfolio/contracts.py` — AccountView 接口更新
    - `packages/portfolio/src/ditto_portfolio/accounting/buying_power.py` — 适配新 AccountView
  - 关键变更:
    - Account.__init__() 移除 order_book 参数
    - AccountView 移除 order_book 和 pending_buy_value 字段
    - Account._calc_pending_buy_value() 删除
    - Account.get_view() 签名简化（无 order_book 参数）
    - CashAccountBuyingPower 适配（pending_buy_value 改为外部计算或移除）
  - 测试: `packages/portfolio/tests/unit/accounting/test_account_unit.py`（已有文件更新）
    - Account 构造不持有 order_book
    - AccountView 无 order_book 字段
    - apply_fill() 功能不变
    - thaw_position() 功能不变
  - 依赖: T5（需 execution OrderBook 可用）
  - 风险: HIGH — AccountView 是 7+ 文件消费的接口；需逐个适配

- [x] T9: BacktestBrokerage 适配新 OMS `[L]`
  - 验收: BacktestBrokerage 使用 execution 的 OrderBook；回测集成测试通过；功能不变
  - 文件:
    - `packages/backtest/src/ditto_backtest/brokerage.py` — 持有 execution OrderBook，account 不再被访问 order_book
    - `packages/backtest/src/ditto_backtest/steps/types.py` — StepContext 新增 order_book 字段
    - `packages/backtest/src/ditto_backtest/steps/pre_trade.py` — 从 StepContext 获取 pending_orders（不再从 AccountView）
    - `packages/backtest/src/ditto_backtest/engine_steps.py` — StepDeps 新增 order_book 依赖
  - 关键变更:
    - BacktestBrokerage 持有 `self._order_book: OrderBook`（来自 execution）
    - place_order() → self._order_book.submit(ticket)
    - cancel_order() → self._order_book.cancel(order_id)
    - process_pending() → self._order_book.get_pending()
    - _apply_fill() → self._order_book.update(ticket) + self._account.apply_fill()
    - StepContext 新增 `order_book: OrderBookReadOnly | None`
    - PreTradeStep 使用 ctx.order_book.get_pending() 而非 ctx.account_view.order_book.get_pending()
    - pending_buy_value 改为从 order_book 直接计算
  - 测试: `packages/backtest/tests/unit/test_brokerage_unit.py`（已有文件大幅更新）
    - place_order 使用 execution OrderBook
    - process_pending 正确遍历 pending tickets
    - _apply_fill 同时更新 OrderBook 和 Account
    - cancel_order 正确取消
  - 依赖: T5, T8

- [x] T10: execution 包导入迁移 `[M]`
  - 验收: execution 内部所有 `from ditto_portfolio.accounting import Order/OrderTicket/OrderBook/...` 替换为 execution 包内导入；basedpyright 通过
  - 文件（6 个 production 文件 + 对应测试）:
    - `packages/execution/src/ditto_execution/planner.py` — Order, OrderBook, OrderTicket, OrderStatus, FillEvent, AccountView, CashBook, Position
    - `packages/execution/src/ditto_execution/_planner_types.py` — Order
    - `packages/execution/src/ditto_execution/cost_estimate.py` — Order
    - `packages/execution/src/ditto_execution/brokerage.py` — AccountView, FillEvent, Order, OrderTicket
    - `packages/execution/src/ditto_execution/target_diff.py` — AccountView, Order, OrderBookReadOnly
    - `packages/execution/src/ditto_execution/trade_builder.py` — AccountView, FillEvent
    - `packages/execution/src/ditto_execution/broker/contracts.py` — AccountView, FillEvent, Order, OrderTicket
    - `packages/execution/src/ditto_execution/reality/fee.py` — Order
    - `packages/execution/src/ditto_execution/fills/outcomes.py` — FillEvent
  - 变更规则:
    - `Order`, `OrderTicket`, `OrderStatus`, `OrderEvent`, `OrderBook`, `OrderBookReadOnly` → `from ditto_execution.orders.xxx import`
    - `AccountView`, `FillEvent`, `CashBook`, `Position`, `CashAccountBuyingPower` → 保留 `from ditto_portfolio.accounting import`（这些类型仍在 portfolio）
  - 测试: `pixi run -e dev type`（类型检查验证）
  - 依赖: T5

- [x] T11: risk + backtest + application 导入更新 `[M]`
  - 验收: 全部跨包 Order 引用更新；arch-check 通过
  - 文件:
    - `packages/risk/src/ditto_risk/constraints/checks.py` — Order
    - `packages/risk/src/ditto_risk/exposure/checks.py` — Order
    - `packages/risk/src/ditto_risk/constraints/context.py` — AccountView, Order, OrderBookReadOnly, OrderTicket
    - `packages/backtest/src/ditto_backtest/brokerage.py` — 已在 T9 处理
    - `packages/backtest/src/ditto_backtest/steps/pre_trade.py` — 已在 T9 处理
    - `packages/application/src/ditto_application/builders/service_factory.py` — Account, OrderBook（构造时使用 execution 的）
    - `packages/application/src/ditto_application/processes/execution/fee_override.py` — Order
  - 测试: `pixi run -e dev type` + `pixi run -e dev arch-check`
  - 依赖: T10

### Wave 3: ISP 优化 + 清理

- [x] T12: TradeDataPort ISP 拆分 `[M]`
  - 验收: TradeDataPort 替换为 3 个窄 Port；7 个消费者更新；arch-check 通过
  - 文件:
    - `packages/execution/src/ditto_execution/contracts.py` — TradeDataPort → IntentDataPort + FillDataPort + PositionDataPort
    - `packages/execution/src/ditto_execution/di/storage.py` — 适配新 Port（3 个窄 Port 供应商 + TradeService 内部实例）
    - `packages/application/src/ditto_application/providers_portfolio.py` — 适配
    - `packages/application/src/ditto_application/providers_command.py` — 适配
    - `packages/application/src/ditto_application/queries/portfolio_actual.py` — 适配（fill_port + position_port）
    - `packages/application/src/ditto_application/queries/trade.py` — 适配（intent_port）
    - `packages/application/src/ditto_application/queries/signal.py` — 适配（intent_port）
    - `packages/application/src/ditto_application/commands/trade.py` — 适配（intent_port + fill_port + position_port）
  - 策略: TradeDataPort 直接删除，所有消费者一次性迁移到 3 个窄 Port
  - 测试: `packages/execution/tests/unit/test_trade_data_ports_unit.py`
    - 3 个窄 Port 的方法签名正确（22 tests）
    - TradeService 结构兼容性验证
  - 依赖: T11

- [x] T13: 清理 portfolio 旧类型 + 迁移测试文件 `[M]`
  - 验收: portfolio 的 order_book.py 整文件删除；11 个测试文件迁移到 execution Order；全量测试通过
  - 文件:
    - `packages/portfolio/src/ditto_portfolio/accounting/order_book.py` — 已删除（6 个 OMS 类型全部迁移到 execution/orders/）
    - `packages/portfolio/src/ditto_portfolio/accounting/__init__.py` — 移除 OMS re-export
    - `packages/portfolio/tests/unit/accounting/test_order_book_unit.py` — 已删除
    - 11 个测试文件迁移 Order/OrderTicket/OrderStatus 引用到 execution 包
  - 测试: `pixi run -e dev test`（6527 passed）
  - 依赖: T12

- [x] T14: B9-K.6 kernel DecisionFrame 删除 `[S]` — 跳过（不适用）
  - kernel/strategy.py 不存在 DecisionFrame；strategy 包的 DecisionFrame 是活跃类型别名，不可删除

- [x] T15: B9-EX.4 DiffContext 引入 `[S]` — 跳过（已完成）
  - DiffContext frozen dataclass 已存在；compute_diff 签名已收束为 2 参数

### Wave 4: 验证

- [x] T16: 全量验证 `[S]`
  - 验收: `pixi run -e dev check` 通过；`pixi run -e dev arch-check` 通过；6527 测试通过，36/36 契约保持
  - 文件: 无新文件
  - 依赖: T13-T15

---

## 依赖图

```
T1 ─→ T2 ─→ T4 ─→ T5 ─→ T7
 │                  │
 └─→ T3 ────────────┘
                      │
                      ├──→ T8 ──→ T9
                      │            │
T6 (独立)             │            │
                      ├──→ T10 ──→ T11 ──→ T12 ──→ T13 ──→ T16
                      │                                │
T14 (独立) ───────────────────────────────────────────→ T16
T15 ────────────────────────────→ T16
```

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| AccountView 接口变更影响 7+ 文件 | 高 | T8 先改 portfolio 测试通过，再改消费者 |
| OrderBook 解耦后 pending_buy_value 计算位置变化 | 中 | 提取为独立函数，PreTradeStep 调用 |
| TradeDataPort facade 过渡期双重导入 | 低 | 标注 deprecated，下个版本删除 |
| 回测功能回归 | 高 | T9 后运行全量回测集成测试 |

## 执行顺序建议

1. **Wave 1 并行**: T1→T2→T3→T4→T5→T7 可串行完成，T6/T14 可并行
2. **Wave 2 串行**: T8→T9→T10→T11 严格按序
3. **Wave 3 并行**: T12/T13/T15 可部分并行
4. **Wave 4**: T16 最终验证
