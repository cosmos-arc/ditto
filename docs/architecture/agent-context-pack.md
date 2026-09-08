# Ditto Agent Context Pack

## Fast Architecture Model

Agent 路径为 `apps -> agent -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel`；非 Agent 入口仍可由 `apps -> application` 直接调用。
`platform` is horizontal technical foundation.

Data, features, strategy, portfolio, risk, execution, backtest are **peer capability planes**.
Analysis is research-only, not imported by production packages.
`.importlinter` layer ordering is a tooling limitation, not a semantic ranking.

## Placement Rules

| Need | Place |
|---|---|
| HTTP/CLI/job DTO | `apps` |
| Governed model runtime, tools, approval, Agent store, replay/eval | `agent` |
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

## Portfolio Comparison Boundary

| Responsibility | Owner / Provider | Direct Consumers | Contract |
|---|---|---|---|
| Same-valuation normalization, pairwise drift, target constraints | `portfolio` / deterministic services | `application` | `PortfolioValuationInput`, `PortfolioDriftView` |
| Exposure, stress, and constraint findings | `risk` / deterministic scenario service | `application` | `PortfolioScenarioInput`, `ScenarioPreview` |
| Signal Package + Paper/Manual ledger + Paper execution + retained PIT price join | `application.queries` / `LivePortfolioComparisonSource` | application queries | `PortfolioComparisonSourcePort` |
| Three-column aggregation and no-write preview | `application.queries` | `apps`, `agent` | `PortfolioComparisonView`, `PortfolioScenarioPreviewView` |
| HTTP projection and physical dependency injection | `apps/backend` / FastAPI and `apps.registry` | Web (`apps/web`) | OpenAPI `/api/v1/portfolio/*` |
| Grounded explanation only | `agent` tools over application leaf contracts | Agent runtime | sealed comparison/scenario evidence, `PortfolioDiagnostic` |

The comparison fails closed unless all three portfolios share `as_of`, valuation
snapshot, provider snapshot set, and CNY currency. The Signal Package checksum
selects Model targets; Paper and Manual are rebuilt from separate append-only
ledgers. Agent schemas expose portfolio/session identities and user scenario
constraints, but never temporal cutoffs, provider snapshot IDs, target weights,
apply commands, or ledger writes. `.importlinter`, `arch-check`, PIT future
sentinels, no-side-effect tests, and the static OpenAPI snapshot enforce this
boundary.

## Test Placement

Unit tests live beside the owning package under `tests/unit`.
Cross-package behavior goes to the highest package that owns the user-facing workflow.
E2E belongs in `apps/backend/tests/e2e`.

## Naming Rules

Known acronyms stay uppercase in class names: ETF, FX, API, SQL, DQ, PIT, HTTP.
Do not create new `Manager`, `Helper`, or `Utils` names without a specific owned resource or domain noun.

## Before Editing

Run `rg` for nearby patterns and import direction.
When changing imports, run `task arch-check`.

## Tracing

`@traced` lives in `kernel.tracing`. Default is no-op. Install handler via `install_trace_handler()`.
Composition root (`apps.registry`) wires OTel bridge and physical Agent adapters at startup.

## T0 Acceptance Gate

All must pass before merge:

```
python scripts/architecture/check_architecture_smells.py   # 0 issues
task lint-imports --                                # all pass
task type --                                        # 0 errors, 0 warnings
task test -- --fast                                 # all pass
task arch-check --                                  # passes
```
