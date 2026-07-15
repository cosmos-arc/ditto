# Execution Review Report

> Date: 2026-05-08
> Scope: `packages/execution`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Execution 是交易执行平面，当前代码已经把“执行域语言”和“回测模拟实现”分开：`ditto_execution.brokerage.Brokerage` 是 backtest/live loop 面向的运行时端口，`ditto_execution.broker.contracts.BrokerGateway` 是券商适配器端口，真实回测撮合实现留在 `ditto_backtest.brokerage.BacktestBrokerage`。

硬性依赖边界没有发现违规：生产代码只依赖 `kernel`、`portfolio`、`platform` 和 execution 自身，没有依赖 data/features/strategy/backtest/analysis/application/apps。

真正的缺口在 OMS 成熟度。Execution 已有 planner、brokerage/gateway Protocol、审计、人工交易 CRUD、OrderStore/FillStore/Reconciliation 占位契约，但还没有一条可恢复、可对账、可幂等的订单状态链。

## 2. 源码证据

### 2.1 规模

| Metric | Evidence |
|---|---:|
| Python source files | 35 |
| Test files | 23 |
| Source LOC | 2,981 |
| Largest files | `planner.py` 530, `trade_builder.py` 426, `audit/execution_audit_service.py` 297 |
| Public root API | `ditto_execution.__all__ = []` |
| Key protocols | `Brokerage`, `BrokerGateway`, `ExecutionPlanner`, `TradeBuilder`, `OrderStore`, `FillStore`, `OrderRouter`, `FillReceiver`, `TradeAuditor` |

### 2.2 Runtime and adapter seams

| Area | Evidence |
|---|---|
| Runtime brokerage port | `brokerage.py` exposes `connect/get_account/place_order/cancel_order/process_pending` plus `ProcessInput(step_time, trade_date, bars)`. |
| Broker adapter port | `broker/contracts.py` exposes `BrokerGateway.connect/get_account/submit_order/cancel_order/query_fills`. |
| Broker implementations | `broker/gateways/__init__.py` is explicitly a placeholder; no gateway implementation exists under execution. |
| Backtest implementation | `ditto_backtest.brokerage.BacktestBrokerage` owns simulated order state, fill processing, T+1 freeze/thaw, and account mutation. |
| Event publication | Backtest steps publish execution-owned `OrderSubmitted` and `OrderFilled` dataclasses through kernel `EventBus`. |

### 2.3 Orders, fills, storage, audit

| Area | Evidence |
|---|---|
| Order lifecycle model | `Order`, `OrderTicket`, `OrderStatus`, and `OrderBook` live in portfolio accounting, not execution. |
| Execution order store | `orders/store.py` defines `OrderRecord(order_id, strategy_id, trade_date, instrument_id, side, quantity, status)` and `OrderStore` Protocol only. |
| Missing OMS identity | No source hits for `ClientOrderId`, `BrokerOrderId`, `OrderJournal`, `OrderState`, or idempotency key types. |
| Fill persistence | `execution_fills` stores `fill_id`, `intent_id`, strategy/date/instrument/direction/qty/price/fee/slippage; it does not link broker fill id or broker order id. |
| Intent persistence | `trade_intents` stores trading intent status with optimistic status update guard. |
| Position persistence | `actual_positions` stores actual position snapshots via `PositionRecord`; ownership with portfolio needs later review. |
| Audit | `ExecutionAuditService` writes risk scan, pre-trade decision, and trade-fill payloads to `execution_audit`. |
| Reconciliation | `ReconciliationReport` is a count summary dataclass; no reconciliation service, store, diff model, or gateway snapshot comparison exists. |

### 2.4 Tests and guards

| Guard | Evidence |
|---|---|
| Broker responsibility split | `test_broker_protocol_semantics_unit.py` asserts `BrokerGateway` and `Brokerage` have non-overlapping responsibilities. |
| Placeholder contracts | `test_execution_placeholder_contracts_unit.py` proves `OrderStore`, `FillStore`, and `ReconciliationReport` are minimal actionable placeholders. |
| Audit persistence | Audit tests cover schema creation, inserts, queries, serialization, and trade fill logs. |
| Trade storage | Trade service tests cover SQLite schema, idempotent fill lookup, status transition guards, and SQL allowlists. |
| Import boundary | `pixi run -e dev arch-check` remains the authoritative architecture boundary check. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| EXEC-P1-01 | P1 | Execution has `OrderStore` Protocol and `OrderRecord`, but no `ClientOrderId`, `BrokerOrderId`, `OrderJournal`, or execution-owned durable state machine; portfolio owns `OrderTicket/OrderStatus`. | Paper/live order recovery cannot prove what was submitted, acknowledged, partially filled, canceled, rejected, or replayed after crash. | Define OMS Lite in execution: identity types, state transition table, append-only journal, idempotency keys, and narrow portfolio/risk views. |
| EXEC-P1-02 | P1 | `BrokerGateway` is a Protocol and `broker/gateways` is placeholder-only; the only concrete brokerage implementation is backtest-owned simulation. | Adapter seam is documented but not executable; paper/live cannot be smoke-tested without inventing behavior in application/apps. | Add a deterministic paper/mock `BrokerGateway` or gateway harness in execution, while keeping full simulation brokerage in backtest. |
| EXEC-P1-03 | P1 | `ReconciliationReport` only stores expected/actual/unmatched counts and is only covered by placeholder tests. | Broker/account truth cannot be compared with local orders/fills/positions; operational drift and crash recovery are invisible. | Introduce reconciliation records, store, and service that compare journal/orders/fills/positions with gateway snapshots and emit audit evidence. |
| EXEC-P1-04 | P1 | `execution_fills`, `trade_intents`, `actual_positions`, and `execution_audit` are useful CRUD/audit paths, but none tie broker order id, client id, fill id, journal sequence, and reconciliation result together. | Manual execution records and audit logs may look complete while live/paper order truth is still split across unrelated tables. | Make OMS journal the spine, then let fill storage, audit payloads, and reconciliation reference journal/client/broker ids. |
| EXEC-P2-01 | P2 | `planner.py` is 530 lines and mixes target diff, pending-aware planning, market prechecks, lot rounding, T+1 handling, cost estimates, and order id generation. | Planner behavior is hard to review by concern; adding new venues/rules will increase regression risk. | Split later by concern: target diff, market/rule precheck, quantity rounding, cost estimate, and id policy. |
| EXEC-P2-02 | P2 | A-share rule behavior appears in execution planner/reality/rules and backtest default rules while kernel still contains shared trading defaults. | Reference-market semantics remain scattered and may drift between execution, backtest, risk, and kernel. | Coordinate with `KERNEL-P1-03`: move venue/reference decisions toward a reference provider before adding new market semantics. |

No P0 finding was confirmed in this pass. Because paper/live trading is still marked reserved or experimental, the missing OMS pieces are not current production outages, but they are hard blockers before claiming paper/live readiness.

## 4. 目标设计

Execution should own the OMS Lite language and adapter truth, not the backtest simulation engine.

Keep:

- `Brokerage` as the runtime-facing port consumed by backtest/live loops.
- `BrokerGateway` as the adapter-facing port for concrete broker systems.
- Execution-owned typed order events, with kernel `EventBus` staying a transport.
- SQLite audit/trade storage as useful local persistence paths.

Add or tighten:

- `ClientOrderId`, `BrokerOrderId`, `ExecutionOrderId` if needed, and explicit idempotency keys.
- `OrderJournalEntry` with monotonic sequence, state transition, source, broker refs, and timestamps.
- A state transition table owned by execution and projected into portfolio/accounting views.
- `ReconciliationRecord` and `ReconciliationService` that can compare local journal/fills/positions with broker snapshots.
- A deterministic gateway harness that proves submit/query/cancel/fill semantics without using the backtest brokerage as a hidden live substitute.

Constrain:

- Portfolio may keep accounting `OrderTicket` if it remains an account/order-book view, but execution must own the operational order truth.
- Backtest may reuse execution ports/events, but simulated matching and settlement stay in backtest.
- Application/apps should wire concrete gateway/brokerage implementations, not define their own order lifecycle rules.

## 5. TDD 整改计划

1. OMS identity and journal:
   - RED: add tests proving a submitted order creates a durable journal entry with client id, strategy/run context, and initial state.
   - GREEN: add minimal identity value objects, `OrderJournalEntry`, and an in-memory or SQLite-backed journal port.
   - REFACTOR: project journal state into existing `OrderRecord` or replace `OrderRecord` with a fuller OMS record.

2. Gateway harness:
   - RED: add contract tests for `BrokerGateway.submit_order/query_fills/cancel_order` with broker id mapping and idempotent submit.
   - GREEN: implement the smallest deterministic paper/mock gateway under `execution.broker.gateways`.
   - REFACTOR: wire the gateway to OMS journal through an adapter, not directly to portfolio account state.

3. Reconciliation:
   - RED: add tests for unmatched local order, unmatched broker fill, quantity mismatch, and terminal-state mismatch.
   - GREEN: add `ReconciliationRecord`, store, and service comparing journal/fill/position projections with gateway snapshots.
   - REFACTOR: persist reconciliation results and link them from audit payloads.

4. Planner decomposition:
   - RED: preserve current planner behavior with focused tests for target diff, lock, suspended/limit, T+1, and 100+1 rounding.
   - GREEN: extract pure helpers by concern without changing order output.
   - REFACTOR: move market reference/rule lookup behind the future reference provider.

## 6. 验收命令

For this review artifact:

```bash
awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-execution-review.md
```

For execution remediation work:

```bash
pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/execution/tests
pixi run -e dev arch-check
pixi run -e dev check
```

## 7. 延后项与原因

| Item | Reason | Reopen Condition |
|---|---|---|
| Moving `OrderTicket/OrderStatus` out of portfolio now | Portfolio review must decide whether these are accounting views or operational order truth before moving code. | Portfolio review starts or OMS journal implementation requires ownership change. |
| Implementing live broker adapters | Live trading is reserved; adding adapters before OMS/reconciliation would create false readiness. | OMS Lite, paper gateway, reconciliation, and recovery tests exist. |
| Splitting planner immediately | Current review is finding ownership/risk; planner behavior has many existing tests and should be decomposed under TDD. | First new venue/rule requirement or OMS remediation touches planner id/state behavior. |
