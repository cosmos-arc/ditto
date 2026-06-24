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
