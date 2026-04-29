# Ditto Agent Context Pack

## Fast Architecture Model

`interfaces -> app -> {data, analytics, engine} -> kernel`.
`infra` is horizontal foundation.

Data, analytics, engine are **peer planes** (diamond model), not layers.
`.importlinter` layer ordering is a tooling limitation, not a semantic ranking.

## Placement Rules

| Need | Place |
|---|---|
| HTTP/CLI/job DTO | `interfaces` |
| Use case orchestration | `app.process`, `app.command`, `app.query` |
| Data source/storage/quality/catalog | `data` |
| Expression/factor/evaluation/research | `analytics` |
| Strategy, portfolio, risk, execution, backtest runtime | `engine` |
| Shared stable value object | `kernel` |
| Business-agnostic config/observability/db utilities | `infra` |

## Test Placement

Unit tests live beside the owning package under `tests/unit`.
Cross-package behavior goes to the highest package that owns the user-facing workflow.
E2E belongs in `interfaces/tests/e2e`.

## Naming Rules

Known acronyms stay uppercase in class names: ETF, FX, API, SQL, DQ, PIT, HTTP.
Do not create new `Manager`, `Helper`, or `Utils` names without a specific owned resource or domain noun.

## Before Editing

Run `rg` for nearby patterns and import direction.
When changing imports, run `pixi run -e dev arch-check`.

## Tracing

`@traced` lives in `kernel.tracing`. Default is no-op. Install handler via `install_trace_handler()`.
Composition root (interfaces) wires OTel bridge at startup.

## T0 Acceptance Gate

All must pass before merge:

```
python scripts/architecture/check_architecture_smells.py   # 0 issues
pixi run -e dev lint-imports                                # 34 kept, 0 broken
pixi run -e dev type                                        # 0 errors, 0 warnings
pixi run -e dev test --fast                                 # all pass
pixi run -e dev arch-check                                  # passes
```
