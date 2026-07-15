# Portfolio Review Report

> Date: 2026-05-08
> Scope: `packages/portfolio`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Portfolio 是纯组合/账户/调仓/会计领域包。当前生产代码符合包级规则：只依赖 `kernel`，不依赖 data/features/strategy/risk/execution/backtest/analysis/application/apps/platform。

当前实现最成熟的是账户会计和调仓约束：`Account`、`CashBook`、`PositionLot`、`OrderBook`、allocation/constraints/comparison 都有单元测试。较薄的是 positions/holdings/target_portfolios：它们现在主要是 DTO + Protocol，不是完整 runtime/store。

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 21 Python source files, 15 test files, about 1,717 source LOC. |
| Largest files | `order_book.py` 283, `account.py` 254, `constraints.py` 248, `allocation.py` 214, `comparison.py` 179. |
| Account state | `Account` owns cash, positions, and order book; `get_view()` returns read-only `AccountView`. |
| Fill accounting | `Account.apply_fill(fill, settle_date, on_frozen)` mutates cash/positions and delegates T+1 frozen handling through callback. |
| Portfolio read models | `positions`, `holdings`, and `target_portfolios` expose `PositionSnapshot`, `HoldingSnapshot`, `TargetPortfolio`, and reader/store Protocols only. |
| Events | `PositionChanged` exists but its docstring says it is reserved and not currently produced in the production flow. |
| Cross-package overlap | Execution/application also define actual position snapshots/records; strategy also defines a `TargetPortfolio`. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| PORT-P1-01 | P1 | `Account` can apply fills in memory, but there is no portfolio-owned snapshot/journal restore contract, and execution has no OMS journal yet. | Crash recovery or replay cannot independently reconstruct portfolio/accounting state from durable execution truth. | Define a portfolio state snapshot/projection contract that consumes execution journal/fill events once OMS Lite exists. |
| PORT-P1-02 | P1 | `positions`, `holdings`, and `target_portfolios` are currently DTO/Protocol surfaces without runtime/store implementation. | Docs and package names imply richer portfolio state management than currently exists. | Mark these surfaces experimental/reserved until one minimal runtime path exists, or implement the smallest store/projection. |
| PORT-P1-03 | P1 | `PositionChanged` is explicitly reserved and not emitted by `Account.apply_fill`. | Event stream cannot prove account position transitions; later audit/replay could assume events exist. | Either publish typed portfolio events from accounting transitions or keep the event reserved in maturity docs. |
| PORT-P2-01 | P2 | `PositionReader`, `PositionSnapshot`, `TargetPortfolio`, and actual-position names appear in portfolio, strategy, execution, and application. | Naming collisions make ownership hard for future agents and API consumers. | Add a glossary/public API table distinguishing accounting snapshot, strategy target, execution actual, and app DTO. |
| PORT-P2-02 | P2 | Portfolio owns `OrderTicket`, `OrderStatus`, and `OrderBook`, while execution review identified missing operational OMS ownership. | Portfolio order-book views may be mistaken for broker/order lifecycle truth. | Keep portfolio order objects as accounting views; let execution own operational order state and expose narrow projections. |

No P0 finding was confirmed. The package boundary is sound; the blocker is runtime maturity, not import hygiene.

## 4. TDD 整改计划

1. State projection:
   - RED: prove a stream of fills or journal entries can rebuild account cash and positions.
   - GREEN: add a minimal `PortfolioStateSnapshot` / projector port without depending on execution internals.
   - REFACTOR: wire execution OMS projection later through application/backtest.

2. Reserved surfaces:
   - RED: add tests or docs guard that positions/holdings/target portfolio stores are not advertised as production-ready.
   - GREEN: mark maturity explicitly or add one minimal SQLite/in-memory implementation.
   - REFACTOR: align names with strategy/execution/application DTOs.

3. Portfolio events:
   - RED: define expected `PositionChanged` emission from `apply_fill` or assert it remains reserved.
   - GREEN: implement typed event creation or remove runtime implication.
   - REFACTOR: connect to runtime event catalog after `KERNEL-P1-01`.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-portfolio-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/portfolio/tests && pixi run -e dev arch-check && pixi run -e dev check`.
