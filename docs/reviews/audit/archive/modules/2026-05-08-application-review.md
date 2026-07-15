# Application Review Report

> Date: 2026-05-08
> Scope: `packages/application`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Application is the CQRS orchestration layer. It is allowed to depend on all capability packages, data, and platform foundation/services, while apps remains above it. Import-linter R8 rules guard query/command/process/builder coupling.

The layer is doing a lot of valuable composition. The main architectural risk is that it is also becoming a second composition root: providers/builders/processes directly import many concrete stores, services, sources, backtest simulation classes, feature services, and analysis research services.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 104 Python source files, 107 test files, about 18,315 source LOC. |
| Largest files | `ingestion/coordinator.py` 764, `runtime_builder.py` 626, `config.py` 614, `queries/research.py` 595, `data_writer.py` 594, `materialization/orchestrator.py` 585, `backtest_process.py` 571, `providers.py` 563. |
| Provider fan-in | `providers.py` imports data services/sources/stores, execution audit/trade service, features services/stores, strategy stores, and app processes/builders. |
| Runtime builder | `service_factory.py` constructs `BacktestBrokerage`, `ProviderBackedDataFeed`, `AShareFeeModel`, portfolio account, risk checks, and strategy pipeline/runtime. |
| Dataset routing | `application.config.INGESTION_SPECS` mirrors data `Dataset` enum with task names, dependencies, schedules, critical fields, and availability times. |
| Research dependency | `queries/research.py` directly imports analysis research services/domain, data metadata service, and features artifact reader. |
| Ports | Some app-owned ports exist, e.g. `processes/execution/ports.py`, but they do not cover data/backtest/research runtime seams broadly. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| APP-P1-01 | P1 | Application providers/builders import concrete capability/data/source/store types extensively. | Application can become a hidden composition root instead of pure use-case orchestration. | Move concrete infrastructure selection to apps registry or wrap with narrower app-owned ports. |
| APP-P1-02 | P1 | `BacktestRuntimeBuilder` constructs backtest simulation, data provider adapter, portfolio account, risk checks, execution planner, and fee/slippage defaults in one place. | Runtime mode semantics become app-builder behavior rather than reviewed package contracts. | Extract a backtest/paper runtime factory contract and make application orchestrate ports, not define lifecycle defaults. |
| APP-P1-03 | P1 | `INGESTION_SPECS` duplicates dataset routing facts from data `Dataset`, including broad multi-market families. | Dataset/maturity facts can diverge between data, application, and apps. | Make DataCatalog/Dataset budget the source of truth, or mark application config as fixed current ingestion config. |
| APP-P1-04 | P1 | `queries/research.py` directly depends on analysis domain/services plus data/features services. | Research path is correct by intent but not yet isolated behind application-owned research ports. | Add research reader/builder ports or document this as a narrow ADR allowance with owner/reopen condition. |
| APP-P2-01 | P2 | Multiple orchestration files exceed 500 LOC. | Use-case logic and wiring become harder to review. | Split coordinators/builders by command/query/runtime concern after behavior tests. |
| APP-P2-02 | P2 | Position, trade, signal, dataset, and research DTO names overlap with capability packages. | API readers may confuse app read models with domain models. | Add public DTO naming table and qualify cross-package model names. |

No P0 finding was confirmed. The allowed dependency direction is intact; the issue is composition responsibility and fact ownership.

## 4. TDD 整改计划

1. Composition boundary:
   - RED: add smell tests limiting new direct concrete imports outside approved providers/builders.
   - GREEN: add application-owned ports for data portal, research catalog/artifacts, and runtime brokerage/data seams.
   - REFACTOR: move concrete adapter selection toward apps registry.

2. Runtime factory:
   - RED: assert backtest runtime uses an agreed lifecycle contract rather than builder-only defaults.
   - GREEN: extract runtime factory DTO/port.
   - REFACTOR: align with backtest/paper seam and execution OMS decisions.

3. Dataset source of truth:
   - RED: add test that every application ingestion spec maps to a maturity/Dataset entry.
   - GREEN: document enum/config responsibilities.
   - REFACTOR: move extensible assets to DataCatalog.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-application-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/application/tests && pixi run -e dev arch-check && pixi run -e dev check`.
