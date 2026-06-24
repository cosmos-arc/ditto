# Ditto System Positioning Assessment

> Date: 2026-06-24
> Scope: backend monorepo at `/home/chevy/projects/ditto`
> Method: source-level inspection, committed acceptance evidence, historical review reconciliation, and official industry benchmark references.

## Executive Summary

Ditto should remain a long-term full-stack personal quant platform, but its next usable boundary should be stated as a staged platform rather than a fully live-trading product. The current source tree shows a strong engineering and architecture foundation, a credible daily research/backtest/signals backend, and extensive execution/reconciliation primitives. The main strategic risk is target drift: large amounts of backend machinery exist before the daily user workflow is simple, real-data-proven, and AI/Agent-friendly.

## Current System Fact Base

### Repository Scale

Ditto is no longer a prototype-scale project. Current source inspection shows:

| Area | Python files | LOC |
|---|---:|---:|
| Production source | 999 | 135,100 |
| Tests | 800 | 212,559 |

The largest production packages are `data` (299 files / 35,409 LOC), `application` (152 / 31,810), `apps` (121 / 17,396), and `features` (122 / 16,129). Test weight is similarly concentrated in `application`, `data`, `apps`, `backtest`, `execution`, and `features`. This is a mature backend system with substantial governance and verification investment; its strategic question is no longer "is there enough code," but "which code forms a daily usable platform boundary."

### Architecture Frame

The active architecture model is the 12-package capability-plane structure documented in `CLAUDE.md` and `docs/architecture/agent-context-pack.md`:

```text
apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel
platform = horizontal technical foundation
```

`application` owns use-case orchestration. `apps` owns API/CLI/jobs and composition root wiring. `data`, `features`, `strategy`, `portfolio`, `risk`, `execution`, and `backtest` are peer capability planes rather than a simple vertical stack. `analysis` is research-only and production packages must not depend on it. This model is unusually explicit for a personal quant platform and is mechanically protected by import-linter and architecture smell checks.

### Current Acceptance Evidence

The committed `artifacts/acceptance/rc1-report.json` records a successful historical acceptance bundle generated on 2026-06-17. Its key evidence includes:

- `pixi run -e dev check` passed in the recorded artifact, including lint, format, type, fast tests, import-linter, and architecture smell checks.
- The targeted synthetic golden lane passed 8 tests across ETF golden, stock-selection golden, and stock-selection signal package E2E.
- A real-data E2E lane passed 2 FRED PIT-related tests.
- The embedded maturity-status output still showed many experimental or blocked datasets with missing catalog storage/schema/freshness evidence.

This means the artifact proves strong backend gates and synthetic/golden workflows, but it must not be treated as final proof that all launch datasets are production-admitted. Real-data production credibility remains stricter than "recorded acceptance passed."

### Assessment Principle

This report does not equate code volume with product readiness. A capability is treated as usable only when it has a coherent workflow, source evidence, validation evidence, and a clear stage boundary. Backend primitives, protocol seams, and governance machinery are valuable, but they are not automatically user-ready workflows.

## Five-Stage Maturity Assessment

### Recommended Product Positioning

Ditto should be positioned as a long-term, full-stack, A-share ETF-first personal quant platform, but the current usable product boundary should be narrower:

> A daily research and decision-support backend for A-share ETF strategies, with governed data ingestion, PIT-aware backtests, factor/strategy signal generation, manual execution tracking, deviation reporting, and paper/execution protocol foundations.

This means the present system is not yet a polished live-trading platform, not yet a fully automated multi-asset alpha factory, and not yet an AI-native quant operating system. It is strongest as a governed backend platform that can produce auditable daily research, backtest, and signal artifacts. The next product goal should be to turn that backend strength into a small number of complete daily workflows.

### Stage Summary

| Stage | Target Role | Current Rating | Usable Boundary | Main Gap |
|---|---|---|---|---|
| L0 | Platform kernel and engineering governance | Strong | Package boundaries, import rules, test gates, maturity rules, lineage/catalog governance | Complexity concentration and documentation density make the system hard to operate without a curated workflow |
| L1 | Research, data, features, backtest | Partial-ready | ETF daily data, ETF strategies, factor materialization, deterministic backtest/replay evidence | Stock/fundamental/macro data are still experimental; real-data launch evidence is incomplete |
| L2 | Portfolio decision and risk control | Partial | Signal package generation, target portfolio bridge, pre/post checks, basic manual decision loop | Optimizer, portfolio analytics, risk dashboards, attribution, and decision UX are not yet product-complete |
| L3 | Paper trading and broker-simulated operations | Experimental-partial | OMS FSM, PaperBrokerGateway, broker-event recording, reconciliation/repair primitives, manual fill/deviation loop | Daily paper account lifecycle, continuous risk, scheduler, user-facing account state, and operational polish are incomplete |
| L4 | Live trading and autonomous operations | Reserved/experimental | Protocol seams, descriptors, conformance fixtures, recording gateway | No real broker adapter, no live credentials/runtime, no product UI in this repo, no AI/Agent operating layer |

### L0: Backend Platform Kernel

L0 is the most mature layer. The architecture is explicit, well-tested, and unusually disciplined for a personal quant codebase. The 12-package model keeps `apps`, `application`, capability packages, `platform`, and `kernel` separated, and the maturity manifest defines guardrails for experimental versus initial-focus behavior. Source evidence includes the architecture contract in `CLAUDE.md`, the capability-plane reference in `docs/architecture/agent-context-pack.md`, the maturity rules in `docs/architecture/capability-maturity.md`, and import-linter/architecture-smell gates recorded in the RC1 acceptance artifact.

The main L0 issue is not lack of engineering quality. It is cognitive load. The backend has accumulated enough governance, DTOs, lineage, source fallback, repair, and maturity machinery that a user cannot infer the practical daily workflow from code structure alone. For the next stage, L0 should serve L1-L3 workflows, not continue expanding as an end in itself.

### L1: Research, Data, Features, and Backtest

L1 is the first layer that can become genuinely useful soon. The strongest current boundary is A-share ETF daily research and backtest. `docs/architecture/capability-maturity.md` marks A-share ETF daily data/research/backtest, feature/factor materialization, ETF strategy templates, and the backtest engine as `initial-focus`. The backtest stack has deterministic replay, checkpoint/resume, PIT policy propagation, source-snapshot propagation, and artifact evidence.

The stock/fundamental/macro side is promising but should remain experimental until launch datasets are promoted with real evidence. The system already has stricter safeguards than many hobby quant stacks: catalog-backed maturity gates fail closed unless callers explicitly set `allow_experimental_data` or a persisted promotion override exists. The newer fundamental bridge is important because it closes a previous class of factor-readiness gap: `packages/application/src/ditto_application/processes/execution/fundamental_snapshot.py` builds a PIT-aware snapshot with `roe`, `net_margin`, and `eps`, and `packages/application/src/ditto_application/processes/execution/factor_bridge.py` injects that snapshot into current-day rows using `knowledge_date`, then derives `pe_ratio` from close and EPS. This is the right architectural direction because backtest orchestration receives a closure instead of importing PIT query policy directly.

The remaining L1 gap is real-data completeness. `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py` shows a token-gated Tushare E2E path for metadata, market bars, valuation metrics, universe creation, signal publication, and experimental-data opt-in. That proves the direction, but it does not yet prove all launch datasets, promotion evidence, repeatable daily refresh, and failure-handling needed for a product boundary. L1 should therefore target "ETF production-ready plus stock-selection research beta", not "full A-share quant research platform" yet.

### L2: Portfolio Decision and Risk Control

L2 is present but not product-complete. The strategy layer can emit target portfolios and signal packages, and the application layer has bridges such as canonical target IDs and strict identity mapping. `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py` proves a valuable end-to-end loop: manual signal -> fill -> position -> deviation. That is the embryo of a daily trader workflow.

The gap is that a top personal quant system needs portfolio decisioning, not only signal production. The maturity manifest still marks portfolio accounting/rebalancing and risk checks as experimental. Pre/post checks exist, but continuous risk, typed audit payloads, and state recovery are incomplete. The next L2 boundary should be: "Given today's approved signals and current account state, produce a target portfolio, explain the sizing/risk tradeoffs, and show what changed from the previous day." Until that exists, Ditto remains a research backend with execution primitives rather than an integrated decision platform.

### L3: Paper Trading and Operational Loop

L3 has substantial low-level machinery but only partial daily workflow readiness. The execution package has an `initial-focus` OMS FSM with seven states, order book/ticket concepts, and dual client/broker IDs. `PaperBrokerGateway` is experimental but broad: submit/fill/cancel/reject/partial-fill behavior, broker event recording, broker-order ID query, reconciliation links, repair actions, retry semantics, and SQLite-backed claim guards are all represented in the maturity manifest.

This is strong backend infrastructure. The product gap is the missing operating loop. A daily user should be able to run paper mode, inspect account state, review open orders/fills/reconciliation, apply or reject repair actions, and compare actual versus target weights. Today, those pieces exist as backend contracts, fixtures, and tests, but not as a compact workflow with scheduler, status page/API narrative, and "what should I do next" guidance. L3 should be promoted only after daily paper-run ergonomics are proven.

### L4: Live Trading and Autonomous Operation

L4 should stay explicitly out of the current usable boundary. The maturity manifest says live trading adapters are `reserved`, and the backend scope explicitly excludes real broker adapter implementation and product UI. That is a good constraint. It prevents protocol work from being mistaken for live-trading readiness.

For a long-term full-stack platform, L4 will eventually require broker-specific adapters, credential isolation, kill switches, continuous risk gates, reconciliation against broker truth, outage recovery, audit trails, and operator controls. For an AI/Agent-native platform, it will also require agent-safe tool contracts, permissioned action scopes, explainable recommendations, dry-run/approval gates, memory over runs, and benchmarked research automation. Current Ditto has many of the ingredients for audited backend actions, but not yet the AI/Agent layer itself.
