# Ditto Module Review Ledger

> Date: 2026-05-08
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`
> Scope: global baseline plus 12 package reviews.

## Status Legend

| Status | Meaning |
|---|---|
| pending | Review has not started. |
| in_progress | Evidence collection or report writing is active. |
| reviewed | Review report exists; findings are confirmed but not remediated. |
| accepted | Finding is confirmed and has a target direction. |
| fixed | Finding has an implementation, tests, and verification. |
| deferred | Finding is intentionally delayed with a reopening condition. |
| rejected | Evidence showed the suspected issue is not a problem. |

## Module Progress

| Module | Wave | Review Status | P0 | P1 | P2 | Current Artifact | Notes |
|---|---|---:|---:|---:|---:|---|---|
| kernel | W1 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-kernel-review.md` | First module review completed after W0 baseline. |
| execution | W1 | reviewed | 0 | 4 | 2 | `docs/reviews/audit/modules/2026-05-08-execution-review.md` | OMS Lite, gateway, and reconciliation gaps confirmed. |
| portfolio | W1 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-portfolio-review.md` | State projection and reserved portfolio surfaces confirmed. |
| risk | W1 | reviewed | 0 | 3 | 1 | `docs/reviews/audit/modules/2026-05-08-risk-review.md` | Continuous risk gate and state snapshot gaps confirmed. |
| backtest | W1 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-backtest-review.md` | Backtest/paper seam and replay state gaps confirmed. |
| data | W2 | reviewed | 0 | 4 | 2 | `docs/reviews/audit/modules/2026-05-08-data-review.md` | DataCatalog runtime, Dataset budget, and consumer port findings confirmed. |
| features | W2/W3 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-features-review.md` | Provenance/time semantics and services surface findings confirmed. |
| strategy | W3 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-strategy-review.md` | Stage schema, context recovery, and template maturity findings confirmed. |
| application | W3 | reviewed | 0 | 4 | 2 | `docs/reviews/audit/modules/2026-05-08-application-review.md` | Composition root and fact ownership risks confirmed. |
| apps | W4 | reviewed | 0 | 3 | 2 | `docs/reviews/audit/modules/2026-05-08-apps-review.md` | Golden E2E and maturity-aware API gaps confirmed. |
| analysis | W3 | reviewed | 0 | 3 | 1 | `docs/reviews/audit/modules/2026-05-08-analysis-review.md` | Research port ownership and reserved namespace policy findings confirmed. |
| platform | W0-W4 | reviewed | 0 | 1 | 3 | `docs/reviews/audit/modules/2026-05-08-platform-review.md` | SQL helper and infrastructure surface findings confirmed. |

## Findings

| ID | Module | Severity | Status | Evidence | Risk | Target Direction |
|---|---|---|---|---|---|---|
| KERNEL-P1-01 | kernel | P1 | accepted | `ditto_kernel.events.DomainEvent` uses `event_type: str` and `payload: dict[str, Any]`; production publishes backtest events by string. | Event replay, audit, and cross-runtime contracts remain fragile. | Keep the bus thin, but introduce typed event ownership and an event-name catalog before OMS/runtime work. |
| KERNEL-P1-02 | kernel | P1 | accepted | `Clock` exposes only `now/today/advance_to`; `TimeContext` has no source hit while `knowledge_date`, `as_of_date`, `effective_from/to`, and `availability_time` are scattered across packages. | PIT and runtime time semantics depend on local conventions. | Add a minimal shared `TimeContext` decision in the runtime ADR, then implement only when two consumers are ready. |
| KERNEL-P1-03 | kernel | P1 | accepted | `trading.py` contains A-share defaults and `default_price_limit_pct`; consumers are execution/backtest/risk/application/apps. | Kernel may grow into market-reference business logic. | Freeze current DTOs as a bridge and move rule semantics toward `market_reference` / reference provider. |
| KERNEL-P2-01 | kernel | P2 | accepted | Root `__all__` has 30 entries, exactly at the documented limit, and mixes clocks/events/trading constants with core value types. | Public API drift becomes hard to review; stable vs candidate API is not explicit. | Add a kernel public API table and keep lower-frequency symbols leaf-only. |
| KERNEL-P2-02 | kernel | P2 | accepted | `Derived*` exceptions live in kernel for data/features sharing but are not part of the package type table in `packages/kernel/CLAUDE.md`. | Kernel domain error ownership is underspecified. | Document them as a shared derived boundary or plan a later port-specific migration. |
| EXEC-P1-01 | execution | P1 | accepted | Execution has `OrderStore` and `OrderRecord`, but no `ClientOrderId`, `BrokerOrderId`, `OrderJournal`, or execution-owned durable state machine; portfolio owns `OrderTicket/OrderStatus`. | Paper/live order recovery cannot prove submitted, acknowledged, filled, canceled, rejected, or replayed state. | Define OMS Lite in execution: identity types, state transition table, append-only journal, idempotency keys, and narrow portfolio/risk views. |
| EXEC-P1-02 | execution | P1 | accepted | `BrokerGateway` is Protocol-only and `broker/gateways` is placeholder-only; concrete simulated brokerage lives in backtest. | Adapter seam is documented but not executable for paper/live smoke tests. | Add a deterministic paper/mock `BrokerGateway` or gateway harness in execution while keeping full simulation brokerage in backtest. |
| EXEC-P1-03 | execution | P1 | accepted | `ReconciliationReport` is only a count summary dataclass with placeholder tests; no reconciliation service/store/diff model exists. | Broker/account truth cannot be compared with local orders/fills/positions. | Add reconciliation records, store, and service comparing journal/fills/positions with gateway snapshots and writing audit evidence. |
| EXEC-P1-04 | execution | P1 | accepted | Trade CRUD and audit tables do not tie broker order id, client id, fill id, journal sequence, and reconciliation result together. | Manual records and audit logs may appear complete while operational order truth is split across unrelated tables. | Make OMS journal the spine referenced by fill storage, audit payloads, and reconciliation. |
| EXEC-P2-01 | execution | P2 | accepted | `planner.py` is 530 lines and mixes target diff, market prechecks, lot rounding, T+1 handling, cost estimates, and order id generation. | Planner behavior is hard to review by concern; new venues/rules will increase regression risk. | Split planner by concern under focused behavior-preserving tests. |
| EXEC-P2-02 | execution | P2 | accepted | A-share rule behavior appears in execution planner/reality/rules and backtest default rules while kernel contains shared trading defaults. | Reference-market semantics may drift across execution, backtest, risk, and kernel. | Coordinate with `KERNEL-P1-03` and move venue/reference decisions toward a reference provider. |
| PORT-P1-01 | portfolio | P1 | accepted | `Account` applies fills in memory, but no portfolio-owned snapshot/journal restore contract exists. | Portfolio/accounting state cannot be independently reconstructed after crash/replay. | Define portfolio state projection/snapshot over execution journal/fills. |
| PORT-P1-02 | portfolio | P1 | accepted | `positions`, `holdings`, and `target_portfolios` are DTO/Protocol-only surfaces. | Package names imply richer runtime state management than exists. | Mark as experimental/reserved or implement a minimal store/projection. |
| PORT-P1-03 | portfolio | P1 | accepted | `PositionChanged` is reserved and not emitted by `Account.apply_fill`. | Event stream cannot prove position transitions. | Publish typed events or keep the event explicitly reserved. |
| PORT-P2-01 | portfolio | P2 | accepted | Position/target names overlap across portfolio, strategy, execution, and application. | Ownership ambiguity during wiring and docs work. | Add glossary/public API table with qualified names. |
| PORT-P2-02 | portfolio | P2 | accepted | Portfolio owns order-book/accounting order objects while execution owns operational OMS direction. | Portfolio views may be mistaken for broker lifecycle truth. | Keep portfolio orders as accounting views and project execution OMS state narrowly. |
| RISK-P1-01 | risk | P1 | accepted | Pre/post checks exist, but shared continuous `RiskGate` runtime contract does not. | Paper runtime can bypass or duplicate risk sequencing. | Define a first-class risk gate/decision event contract for backtest and paper. |
| RISK-P1-02 | risk | P1 | accepted | `MaxDrawdownRule` and strategy locks/cooldowns are stateful without snapshot/restore. | Restart/replay can change risk actions and lock behavior. | Add risk-state snapshot and replay tests. |
| RISK-P1-03 | risk | P1 | accepted | `RiskGuardTriggered` still carries generic `details: dict[str, Any]`. | Risk event/audit schemas may drift. | Introduce typed risk decision/audit payloads. |
| RISK-P2-01 | risk | P2 | accepted | Risk action, backtest risk scan record, and execution audit mapping are split. | Cross-runtime audit comparison is harder. | Publish one stable risk record catalog. |
| BACKTEST-P1-01 | backtest | P1 | accepted | Engine step chain is backtest-owned and in-memory. | Paper runtime may copy/diverge from backtest order/risk/fill sequence. | Extract/document shared backtest/paper lifecycle seam. |
| BACKTEST-P1-02 | backtest | P1 | accepted | `ProviderBackedDataFeed` directly consumes data-owned `DataProvider`/`BarQuery`. | Backtest core depends on data-layer provider language. | Add backtest-owned historical data portal and adapt data providers at boundary. |
| BACKTEST-P1-03 | backtest | P1 | accepted | Replay compares manifest/NAV but not OMS journal, risk state, account restore, or fill idempotency. | Deterministic NAV can hide state recovery defects. | Extend replay proof after OMS/risk snapshot work. |
| BACKTEST-P2-01 | backtest | P2 | accepted | `statistics.py`, `engine.py`, `manifest.py`, `brokerage.py`, and `data_feed.py` are large mixed-concern files. | Runtime/reporting changes cost more to audit. | Decompose by runtime, simulation, manifest, and reporting under tests. |
| BACKTEST-P2-02 | backtest | P2 | accepted | Manifest `RunMode` includes live-like vocabulary while live is reserved. | Artifacts can imply live readiness. | Tie mode language to maturity manifest. |
| PLAT-P1-01 | platform | P1 | accepted | `SQLiteClient.count(table, where)` interpolates table/where strings with caller-validation comment. | Shared helper can become a SQL injection footgun. | Add identifier validation or constrained query builder. |
| PLAT-P2-01 | platform | P2 | accepted | `ParquetStore` is 768 lines across path/read/write/merge/metadata/checksum concerns. | Storage behavior is harder to audit. | Split read/write/metadata/path helpers. |
| PLAT-P2-02 | platform | P2 | accepted | Platform storage docs/examples use dataset/instrument terminology. | Domain semantics may leak into platform. | Reword to collection/key language; keep market examples in data docs. |
| PLAT-P2-03 | platform | P2 | accepted | Runtime correlation/journal ids are not first-class observability guidance yet. | Logs/audit can lack common join keys. | Add correlation guidance after OMS identity is chosen. |
| DATA-P1-01 | data | P1 | accepted | DataCatalog and Lineage are contract-only with unit tests, no runtime store/integration. | Governance vocabulary can be mistaken for active enforcement. | Implement minimal runtime store or mark runtime experimental. |
| DATA-P1-02 | data | P1 | accepted | `Dataset` enum and application `INGESTION_SPECS` remain the real routing spine. | New datasets require enum/config edits and may bypass maturity checks. | Define Dataset budget and catalog migration path. |
| DATA-P1-03 | data | P1 | accepted | Data-owned `DataProvider` is consumed by backtest/application runtime builders. | Consumer runtime contracts are owned by data. | Add consumer-owned data portal ports and adapters. |
| DATA-P1-04 | data | P1 | accepted | Reference metadata/calendars/status histories live in data while market-rule defaults live elsewhere. | Reference-domain semantics can scatter. | Decide market reference provider ownership in ADR. |
| DATA-P2-01 | data | P2 | accepted | Multiple source/service/storage files exceed 600 LOC. | New dataset families increase review cost. | Decompose after Dataset/DataCatalog direction is fixed. |
| DATA-P2-02 | data | P2 | accepted | Many local SQL `S608` allowlist comments remain in storage/runtime helpers. | SQL safety depends on local convention. | Maintain SQL/noqa budget and shared identifier validation. |
| FEAT-P1-01 | features | P1 | accepted | Derived artifacts record snapshot ids/time version but do not use DataCatalog refs or `TimeContext`. | Provenance is not uniform across data/backtest/research. | Link artifacts to DataCatalog/Lineage and shared time context. |
| FEAT-P1-02 | features | P1 | accepted | `time_semantics_version="time-v1"` is hard-coded in application manifest builder. | Time semantics can drift across materialization/read/research. | Centralize versioned time semantics. |
| FEAT-P1-03 | features | P1 | accepted | No reusable PIT leak template spans shift/rolling/join/publication cutoff. | Future operators or joins can introduce lookahead. | Add reusable PIT leak test harness. |
| FEAT-P2-01 | features | P2 | accepted | `codegen.py`, `evaluator.py`, `ic.py`, and catalog service files are large. | Expression/evaluation changes are harder to audit. | Split emitters/evaluator sections under golden tests. |
| FEAT-P2-02 | features | P2 | accepted | `features.services` is broad and public-looking. | Consumers can import internals and widen public surface. | Add public API table or service subpackage namespaces. |
| STRAT-P1-01 | strategy | P1 | accepted | `DecisionStage` lacks machine-readable `requires/produces`; schema checks are local. | Pipeline changes can break downstream stages silently. | Add stage metadata and contract tests. |
| STRAT-P1-02 | strategy | P1 | accepted | `StrategyContext` stores locks/cooldowns/positions without snapshot/restore. | Backtest replay or paper restart can diverge. | Add context snapshot or move locks into runtime risk state. |
| STRAT-P1-03 | strategy | P1 | accepted | ETF and broader stock/sector templates share package surface despite different maturity. | Non-focus templates may be overclaimed. | Mark template maturity explicitly. |
| STRAT-P2-01 | strategy | P2 | accepted | Strategy `TargetPortfolio` overlaps with portfolio target naming. | Ownership ambiguity in APIs/docs. | Qualify names in glossary/public API table. |
| STRAT-P2-02 | strategy | P2 | accepted | Large template/stage files combine config, logic, and builders. | New templates become harder to review. | Split by config/stages/builder after tests. |
| APP-P1-01 | application | P1 | accepted | Providers/builders import many concrete capability/data/source/store types. | Application becomes a hidden composition root. | Move adapter selection to apps registry or app-owned ports. |
| APP-P1-02 | application | P1 | accepted | Backtest runtime builder constructs simulation, data adapter, account, risk, planner, and defaults. | Runtime semantics become builder behavior. | Extract runtime factory contract aligned to backtest/paper seam. |
| APP-P1-03 | application | P1 | accepted | `INGESTION_SPECS` duplicates dataset routing and maturity facts. | Data/application/apps facts can diverge. | Make Dataset/DataCatalog/maturity source of truth explicit. |
| APP-P1-04 | application | P1 | accepted | `queries/research.py` directly depends on analysis, data, and features services. | Research path is not isolated behind app-owned ports. | Add research ports or record narrow ADR allowance. |
| APP-P2-01 | application | P2 | accepted | Multiple orchestration/build files exceed 500 LOC. | Use-case and wiring logic are harder to review. | Split coordinators/builders by concern under tests. |
| APP-P2-02 | application | P2 | accepted | DTO names overlap with capability packages. | Read models can be confused with domain models. | Add public DTO naming table. |
| ANALYSIS-P1-01 | analysis | P1 | accepted | Runtime research facade lives in application and directly imports analysis services/domain. | Analysis ports are less reusable/guardable. | Add app-owned research ports or move neutral facade contract. |
| ANALYSIS-P1-02 | analysis | P1 | accepted | `SHIFT_TO_NEXT_SNAPSHOT` warns and returns unchanged. | Named policy can look implemented while doing nothing. | Mark unsupported/reserved or implement shift semantics. |
| ANALYSIS-P1-03 | analysis | P1 | accepted | Research v1 validates `cn_stock`, `1d`, and derived-only inputs. | Global research capability can be overclaimed. | Keep broader research products experimental/reserved. |
| ANALYSIS-P2-01 | analysis | P2 | accepted | Reserved namespace guard paths/phrases are hard-coded in script. | New reserved namespace can bypass guard if script is not updated. | Use maturity/public API manifest as single source. |
| APPS-P1-01 | apps | P1 | accepted | E2E tests skip when TDX samples/PIT snapshots are missing; full check currently has 25 skips. | CI can pass without core E2E proof. | Add committed synthetic golden E2E lane. |
| APPS-P1-02 | apps | P1 | accepted | API/CLI surface covers broad domains while maturity varies. | Users can infer production readiness from endpoint presence. | Add maturity-aware docs/route/help metadata. |
| APPS-P1-03 | apps | P1 | accepted | Registry/config owns broad composition and derived data-root facts. | Composition root can accumulate business facts. | Keep registry as composition-only and source facts from manifests/configs. |
| APPS-P2-01 | apps | P2 | accepted | Large route/job files mix request parsing, facade calls, response shaping, and status mapping. | Thin-boundary compliance is harder to audit. | Split route/job concerns after snapshots exist. |
| APPS-P2-02 | apps | P2 | accepted | One DQ host-composition allowance exists in `jobs/context.py`. | Narrow exception can expand by copy/paste. | Keep exact allowance with owner/reason for any expansion. |

## Cross-Module Topics

| Topic | Current Status | Owning Wave | Reopen Condition |
|---|---|---|---|
| Runtime event/command/lifecycle | open | W1 | Kernel, execution, portfolio, risk, and backtest reviews all have accepted findings; reopen before runtime implementation work. |
| TimeContext/PIT | open | W1/W2 | Kernel, data, features, backtest, application, and analysis reviews all found local time/PIT terms; reopen before adding another PIT path or publication cutoff. |
| OMS Lite | open | W1 | Execution owns identity/journal/reconciliation; portfolio/backtest/replay depend on it; reopen before paper/mock gateway or order recovery work. |
| Reference domain | open | W1/W2 | Kernel, execution, data, and backtest reviews found scattered market-rule/reference semantics; reopen before new venue/rule behavior. |
| DataCatalog runtime | open | W2 | Contracts exist but no runtime store/integration; reopen before adding new dataset families or provenance claims. |
| Consumer-owned ports | open | W2/W3 | DataProvider and research services are consumed directly by backtest/application; reopen before runtime builder or research facade changes. |
| Composition root | open | W3/W4 | Application is a second composition hotspot; apps registry is the intended host composition root. Reopen before provider/concrete wiring changes. |
| Public API and naming | open | W3 | Target/position/signal/research names overlap across packages; reopen before public API expansion. |
| Maturity manifest | open | W0/W3/W4 | All module reviews now feed maturity labels; reopen before advertising non-A-share, live/paper, or analysis reserved capabilities. |
| SQL/noqa budget | open | W0-W4 | Platform/data/features reviews confirmed dynamic SQL allowances; reopen before adding new SQL helpers or suppressions. |
| E2E/golden data | open | W4 | Apps review confirmed fixture skips; reopen before claiming end-to-end runtime readiness. |
