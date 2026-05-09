# Kernel Review Report

> Date: 2026-05-08
> Scope: `packages/kernel`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Kernel 是共享内核：零外部依赖、零 I/O、零业务流程，只放跨平面稳定值对象、枚举、Protocol 和薄实现。当前源码符合硬性导入边界：`pyproject.toml` 无运行时依赖，`test_kernel_import_boundary_unit.py` 检查 kernel 不导入其他 Ditto 包。

实际压力点不在硬依赖，而在“哪些概念值得继续放在 kernel”：event/time/trading/reference/derived errors 已成为跨包语言，但有些还只是薄 seam，有些已经带明显领域归属。

## 2. 源码证据

### 2.1 规模

| Metric | Evidence |
|---|---:|
| Python source files | 16 |
| Source LOC | 1,507 |
| Largest files | `publication_safety.py` 233, `trading.py` 190, `exceptions.py` 169, `strategy.py` 137 |
| Root public API | `__all__` has 30 entries |
| Protocols | `Clock`, `EventBus`, `MacroDataProvider`, `DecisionFrame`, `FeeModel`, `InstrumentRuleProvider` |

### 2.2 Cross-package consumption snapshot

| Symbol family | Consumer evidence |
|---|---|
| Event bus | `EventBus` in backtest steps; `SimpleEventBus` created in application backtest process; subscriptions mostly in tests. |
| Clock | `Clock` / `SimulatedClock` used by backtest and application integration paths; `RealtimeClock` has no non-kernel usage. |
| Trading/reference DTOs | `MarketSnapshot`, `InstrumentDefinition`, `TradingRuleSet`, `FeeSchedule`, `FeeModel`, `InstrumentRuleProvider` used by execution, backtest, risk, application tests, and apps models/tests. |
| Strategy derived contract | `DerivedSpec`, `DerivedRole`, `MaterializationProfile` used by features, data, application, apps, and strategy. |
| Research records | Used by analysis, application, apps, and data research storage/control-plane paths. |
| Publication safety records | Used by features, data, application, and apps publication/materialization paths. |

### 2.3 Boundary scan

`rg` found no runtime third-party import in kernel. Matches for `polars` and `parquet` are documentation/test string references, not imports. Kernel imports only standard library and same-package modules.

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| KERNEL-P1-01 | P1 | `events.py` defines `DomainEvent(event_type: str, payload: dict[str, Any])`; backtest publishes string events like `order_submitted`, `order_filled`, `risk_guard_triggered`. | Runtime replay/audit depends on string names and untyped payloads; schema drift will not be caught by type checks. | Keep `EventBus` as transport, but require domain-owned typed event records plus an event-name catalog before OMS/runtime work. |
| KERNEL-P1-02 | P1 | `clock.py` only exposes `now/today/advance_to`; no `TimeContext` symbol; PIT terms are scattered across data/features/backtest/apps. | PIT safety relies on local naming conventions rather than one runtime/query context. | Add `TimeContext` to runtime ADR as a candidate kernel value object; implement only after at least two consumers are ready. |
| KERNEL-P1-03 | P1 | `trading.py` contains A-share defaults and `default_price_limit_pct` lifecycle/board logic; consumers span execution/backtest/risk. | Kernel can become the market-reference rules package, violating “shared minimal language”. | Freeze current DTOs as transitional shared language; move market-specific rule semantics toward reference/market_reference provider. |
| KERNEL-P2-01 | P2 | Root `__all__` is exactly 30 entries and includes trading constants plus clocks/events. | The public API budget is at its limit; future symbols may be added without a stable/internal decision. | Maintain a kernel public API table and keep lower-frequency concepts leaf-module only. |
| KERNEL-P2-02 | P2 | `exceptions.py` owns `Derived*` exceptions used by data/features; package type table does not list them. | Derived-domain ownership is implicit; future agents may add more domain-specific errors to kernel. | Document `Derived*` as a deliberate shared derived boundary or migrate later to consumer-owned ports. |

No P0 finding was confirmed in this pass. The hard import boundary is guarded and currently passes the existing architecture gate.

## 4. 目标设计

Kernel should remain the transport and vocabulary floor, not the owner of runtime business behavior.

Keep:

- Base values with broad cross-package use: `InstrumentId`, `OrderSide`, `OrderType`, `DittoError`, selected common enums.
- Thin infrastructure Protocols/implementations: `Clock`, `EventBus`, `traced`.
- Shared derived/publication records that demonstrably bridge data/features/application, but document their ownership.

Move or constrain:

- Event payload schemas should be owned by execution/risk/portfolio/backtest/features, not by generic `dict[str, Any]`.
- A-share market rule calculation should move toward reference/market_reference once the target domain exists.
- `RealtimeClock` should either gain a real application/runtime consumer or remain leaf-only and not be treated as proven production runtime support.

## 5. TDD 整改计划

1. Event typing:
   - RED: add a test proving backtest published events use a documented event-name catalog.
   - GREEN: introduce the smallest catalog or typed adapter without changing bus dispatch semantics.
   - REFACTOR: move payload construction helpers into owning runtime/domain packages.

2. TimeContext:
   - RED: add one backtest/data or features test that requires a shared context for trade date and knowledge/as-of cutoff.
   - GREEN: add a minimal frozen value object only after consumer signatures are agreed.
   - REFACTOR: replace local date bundles gradually; do not bulk-rewrite PIT storage.

3. Trading/reference:
   - RED: add tests that demonstrate A-share rule logic is provided through an `InstrumentRuleProvider` / reference provider rather than hard-coded kernel defaults.
   - GREEN: move rule choice out of kernel while preserving DTO compatibility.
   - REFACTOR: document reference ownership and deprecate direct use of `default_price_limit_pct` outside the provider.

4. Public API:
   - RED: add architecture test for root `__all__` budget and stable public symbols.
   - GREEN: document stable/candidate/internal kernel symbols.
   - REFACTOR: move low-frequency imports to leaf modules.

## 6. 验收命令

For the review artifact:

```bash
awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-kernel-review.md
```

For kernel changes when implemented:

```bash
pixi run -e dev test packages/kernel/tests
pixi run -e dev arch-check
pixi run -e dev check
```

## 7. 延后项与原因

| Item | Reason | Reopen Condition |
|---|---|---|
| Implementing `TimeContext` immediately | Current review is deciding ownership; implementing before execution/backtest/data consumers agree would churn APIs. | Start of W1 runtime implementation or W2 DataCatalog/PIT work. |
| Moving `trading.py` now | Execution/backtest/risk currently depend on these DTOs; moving before reference domain design would create churn. | Execution review defines OMS/rules provider and Data review defines reference/catalog boundary. |
| Replacing `DomainEvent` now | Backtest event tests and application process use it as transport; typed events need event catalog first. | Execution/backtest runtime seam implementation. |
