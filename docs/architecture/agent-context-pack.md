# Ditto Agent Context Pack

## Fast Architecture Model

`apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel`.
`platform` is horizontal technical foundation.

Data, features, strategy, portfolio, risk, execution, backtest are **peer capability planes**.
Analysis is research-only, not imported by production packages.
`.importlinter` layer ordering is a tooling limitation, not a semantic ranking.

## Placement Rules

| Need | Place |
|---|---|
| HTTP/CLI/job DTO | `apps` |
| Use case orchestration | `application.processes`, `application.commands`, `application.queries` |
| Data source/storage/quality/catalog | `data` |
| Expression/factor/evaluation/materialization | `features` |
| Strategy definition, signal, alpha pipeline | `strategy` |
| Portfolio, accounting, rebalancing | `portfolio` |
| Pre/post-trade risk, constraints | `risk` |
| Orders, fills, broker gateway, audit | `execution` |
| Backtest runtime, simulation, performance | `backtest` |
| Research dataset control-plane | `analysis` |
| Shared stable value object | `kernel` |
| Business-agnostic config/observability/db utilities | `platform` |

Reports, diagnostics, experiments, and screeners are reserved/future analysis
namespaces, not current runtime APIs.

## Test Placement

Unit tests live beside the owning package under `tests/unit`.
Cross-package behavior goes to the highest package that owns the user-facing workflow.
E2E belongs in `packages/apps/tests/e2e`.

## Naming Rules

Known acronyms stay uppercase in class names: ETF, FX, API, SQL, DQ, PIT, HTTP.
Do not create new `Manager`, `Helper`, or `Utils` names without a specific owned resource or domain noun.

## Before Editing

Run `rg` for nearby patterns and import direction.
When changing imports, run `pixi run -e dev arch-check`.

## Tracing

`@traced` lives in `kernel.tracing`. Default is no-op. Install handler via `install_trace_handler()`.
Composition root (`apps.registry`) wires OTel bridge at startup.

## T0 Acceptance Gate

All must pass before merge:

```
python scripts/architecture/check_architecture_smells.py   # 0 issues
pixi run -e dev lint-imports                                # 34 kept, 0 broken
pixi run -e dev type                                        # 0 errors, 0 warnings
pixi run -e dev test --fast                                 # all pass
pixi run -e dev arch-check                                  # passes
```
