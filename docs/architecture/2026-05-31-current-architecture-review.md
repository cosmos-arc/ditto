# 2026-05-31 Current Architecture Review

> Status: baseline review plus Batch A remediation and Batch B paper-state ownership / reconciliation executor workflow / derived-run determinism fixes
> Branch reviewed: `dev/architecture-remediation-batch2-6`
> Latest local commit reviewed: `037ea690 refactor: V2 架构整改 Batch 2-6 — 全模块治理`
> Latest worktree reviewed: includes uncommitted Batch A remediation plus Batch B paper runtime account-ownership, reconciliation repair-planning / workflow-persistence / executor hardening, and derived latest-run determinism fix through 2026-05-31

## Executive Summary

Ditto 当前已经具备明显高于普通早期量化系统的工程骨架：12 包边界清晰，`src` layout、pixi、Python 3.13、polars-only、strict type checking、Import Linter、架构 smell check、CQRS 编排层和能力包拆分都已经落地。整体设计方向与 Clean Architecture 的依赖向内原则一致：业务规则和能力包基本不依赖外层入口或具体框架。

当前主要问题不在“有没有架构”，而在“架构是否已经被完整产品能力验证”。最新源码更接近 **A 股 ETF 日频数据/研究/回测平台的强骨架**，还不是 QuantConnect LEAN 或 NautilusTrader 那种 backtest / paper / live 一体化、跨市场、生产交易级平台。

当前评分：**85 / 100**。Baseline 评分为 **82 / 100**；Batch A 修复、coverage hardening、最终 branch coverage gate 达标，以及 Batch B 对 paper runtime 账户状态所有权、reconciliation repair workflow/executor 和 derived latest-run 稳定性的收敛后，系统真实度、集成稳定性和测试可信度继续提升。评分仍保持克制，因为 live broker conformance、DataCatalog/lineage 主干化、PIT fail-closed 和跨市场能力仍是主要差距。

| 维度 | 评分 | 判断 |
|---|---:|---|
| 模块边界与依赖方向 | 90 | 37 个 Import Linter 契约全通过，整体依赖图健康。 |
| 可读性与一致性 | 82 | 包定位清楚；Data/Application/Features 仍有大类、大函数和 registry 型复杂度。 |
| 可扩展性 | 80 | Protocol/DTO/DI 方向正确；DataCatalog、lineage、runtime 统一状态仍未成为真实主干。 |
| 测试与质量门禁 | 82 | `check` 和全量 coverage/integration 已通过；branch coverage 从 76.60% 提升到当前 80.22%，达到项目约定。 |
| 产品架构成熟度 | 73 | A 股 ETF 日频链路较强，paper runtime 账户状态所有权已收敛；live、多市场、intraday、生产 reconciler 等仍缺。 |
| 代码优雅度 | 82 | 纯领域包很干净；编排层和数据层仍有“路线表 + 适配器堆叠”的阶段性痕迹。 |

## Evidence

### Static Shape

- Production source: about 106k LOC across 934 package source files; Import Linter analyzed 923 files.
- Tests: about 173k LOC.
- Source files by package: data 289, features 120, application 119, apps 114, strategy 58, platform 61, execution 57, backtest 40, portfolio 21, risk 19, analysis 21, kernel 15.
- Import graph matches intended diamond/layer model; no direct application imports of concrete data storage/source internals were found.

### Verification

`pixi run -e dev check` passed:

- Ruff lint: passed.
- Ruff format: 1679 files unchanged.
- basedpyright: 0 errors, 0 warnings.
- Fast tests: 7591 passed, 25 skipped.
- Import Linter: 37 contracts kept; 923 files and 2756 dependencies analyzed.
- Architecture smell check: passed.

Baseline extra full coverage/integration run did not pass:

- Command: `pixi run -e dev test --cov-xml`
- Result: 39 failed, 8039 passed, 126 skipped.
- Generated coverage: line 95.28%, branch 76.28%.
- Main failures:
  - Backtest snapshot NAV expectations now contradict actual mark-to-market results.
  - Strategy integration fixtures construct `BacktestBrokerage` without the newly required `order_book`.
  - One application E2E smoke test expects `ValueError`, while command layer raises `AppCommandError`.

Batch A remediation verification now passes:

- Fixed strategy alpha integration fixture drift by wiring `BacktestBrokerage` with an `OrderBook`.
- Fixed account valuation semantics so NAV is `cash.total + market_value`, and backtest brokerage marks open positions to market on each processed bar.
- Aligned application E2E invalid-strategy expectation with the command layer's typed `AppCommandError`.
- `pixi run -e dev check`: passed; 7467 passed, 25 skipped; basedpyright 0 errors; 37 Import Linter contracts kept.
- `pixi run -e dev test --cov-xml`: passed; 8081 passed, 126 skipped; total coverage 94.15%; coverage XML line-rate 95.48%, branch-rate 76.60%.

Batch A coverage hardening progress:

- Added behavior tests for `MacroService` query/write paths: missing required columns, empty writes, metadata upsert, optional metadata conversion, code/ID resolution, metadata enrichment and no-metadata fallback.
- Added behavior tests for minimal materialization DQ summary construction: empty output, missing keys, null/duplicate keys, NaN values, all-null values, non-float values and null streak calculation.
- Added publication facade safety-gate tests for active slot resolution, omitted candidate/baseline versions, missing baseline records, stage string coercion, materialized-run requirement, complete-manifest requirement, active shadow slot with baseline, shadow compare prerequisite, publish-ready gate, and rollback/deprecate invalid states.
- `pixi run -e dev check`: passed; 7490 passed, 25 skipped; basedpyright 0 errors; 37 Import Linter contracts kept.
- `pixi run -e dev test --cov-xml`: passed; 8104 passed, 126 skipped; total coverage 94.34%; coverage XML line-rate 95.60%, branch-rate 77.62%.

Latest instrument metadata hardening pass:

- Found and fixed a real `InstrumentReader` cache truthiness bug: an explicitly configured but empty `DataCache` was treated as falsey, so first lookup skipped cache reads/writes. Cache guards now check `is not None`.
- Found and fixed a real `find_securities_with_extensions()` behavior gap: extension tables were joined but extension columns were not selected, contradicting the reader contract. Stock/ETF/index extension fields are now selected and merged by the existing extension path.
- Added behavior tests for instrument metadata PIT/source resolution, empty batch lookup, ticker-map caching, negative lookup caching, extension merge behavior, extension-table query behavior, no-row dataframe shape, and `_build_in_clause()` chunking.
- Targeted local coverage for `data/src/ditto_data/storage/metadata/instrument/instrument_reader.py`: 100.00% line and branch coverage.
- `pixi run -e dev check`: passed; Ruff lint passed; Ruff format reformatted 2 files; basedpyright 0 errors; 7490 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
- `pixi run -e dev test --cov-xml`: passed; 8118 passed, 126 skipped; total coverage 94.47%; coverage XML line-rate 95.69%, branch-rate 78.17%.

Latest CLI fundamental hardening pass:

- Found and fixed a product/API parity gap: the API and facade supported optional PIT `as_of_date` for `corporate-actions`, but the CLI had no `--as-of-date` option and could not pass PIT date to identifier resolution or corporate-action query.
- Added `query fundamental corporate-actions --as-of-date` and now forwards the date to both metadata identifier resolution and `FundamentalQueryFacade.list_corporate_actions(...)`.
- Added CLI behavior tests for financial report routing, invalid report type, unresolved identifiers, empty results, JSON/table output, dividend table fallback, corporate-action PIT forwarding and unversioned query behavior.
- Targeted local coverage for `packages/apps/src/ditto_apps/cli/commands/query/fundamental.py`: line-rate 98.06%, branch-rate 96.88%.
- `pixi run -e dev check`: passed; Ruff lint passed; Ruff format reformatted 1 file; basedpyright 0 errors; 7506 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
- `pixi run -e dev test --cov-xml`: passed; 8134 passed, 126 skipped; total coverage 94.59%; coverage XML line-rate 95.79%, branch-rate 78.64%.

Latest Tushare fundamental hardening pass:

- Added behavior tests for Tushare fundamental delegate/source/adapter layers covering financial statements, dividends, corporate actions, valuation, margin and pledge query modes.
- Covered date-batch vs ticker mode, mutual-exclusion validation, required query-mode validation, statement-date range validation, optional dividend ranges, PIT column stamping, transformer mapping and optional parameter filtering.
- Removed unreachable blank-ticker guards in `_fundamental.py` and `fundamental_source.py` after tests proved the shared `_resolve_identifier()` path already enforces them.
- Targeted local coverage:
  - `ditto_data.sources.tushare._fundamental`: 100.00% line and branch coverage.
  - `ditto_data.sources.tushare.fundamental_source`: 100.00% line and branch coverage.
  - `ditto_data.sources.tushare.adapters.fundamental`: 100.00% line and branch coverage.

Latest CalendarReader and cache determinism hardening pass:

- Found and fixed a real `CalendarReader` cache truthiness bug: an explicitly configured but empty `DataCache` was treated as falsey, so `reload()` and first `get_range()` skipped cache invalidation/population. Cache guards now check `is not None`.
- Added behavior tests for non-trading boundary offsets, safe offset errors, empty cache usage, reload invalidation, empty calendars, defensive missing-cache rows, quarter-end detection and empty period-end results.
- Targeted local coverage for `data/src/ditto_data/storage/metadata/calendar/calendar_reader.py`: 100.00% line and branch coverage.
- Stabilized `DataCache` TTL tests by replacing wall-clock `sleep(0.1)` with the existing deterministic `time_source` seam; this removed a full-suite flaky failure under parallel load.

Latest golden-dataset hardening pass:

- Added behavior tests for `TickerSpec` source/standard ticker formatting, internal-to-source exchange mapping, mixed string/object ticker parsing, invalid object tolerance, explicit `ticker_specs` precedence, disabled options, ticker lookup and asset-type source filtering.
- Targeted local coverage for `data/src/ditto_data/quality/golden.py`: 97.78% with branch gaps reduced from 20 missed branches to 2 partial branches.

Final Batch A verification:

- `pixi run -e dev check`: passed; Ruff lint passed; Ruff format unchanged; basedpyright 0 errors; 7580 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
- `pixi run -e dev test --cov-xml`: passed; 8208 passed, 126 skipped; total coverage 94.91%; coverage XML line-rate 96.01%, branch-rate 80.22%.
- Current highest production branch hotspots from `coverage.xml`: `data.sources.tushare.adapters.stock` (20 missed branches), `application.builders.template_builders` (20), index constituent writer (20), strategy-run SQLite store (19), SQL engine (17), technical quality checker (16), metadata instrument service (16), macro indicator reader (16), CLI macro query (16), CLI capital query (16).

This means the default fast gate, broader integration/coverage run and project-level branch coverage standard are now green. The remaining coverage work should shift from gate-chasing to risk-ranked hardening of high-value production hotspots.

Latest Batch B paper-runtime ownership pass:

- Resolved the paper runtime account ownership decision in favor of gateway-owned state, matching the existing `BrokerGateway.get_account()` contract and live-broker mental model.
- `PaperTradingRuntime` now only submits orders to the gateway and delegates account snapshots to `gateway.get_account()`; it no longer consumes `query_fills()` to apply the same fills to a second `Account`.
- Added a regression/conformance test proving runtime account state is the gateway account state and a mock-gateway test proving runtime does not call `query_fills()` for local re-accounting.
- Verification:
  - `pixi run -e dev pytest packages/application/tests/unit/process/execution/test_paper_trading_process_unit.py -q --no-cov`: passed; 12 passed.
  - `pixi run -e dev pytest packages/execution/tests/unit/broker/test_paper_gateway_unit.py packages/execution/tests/unit/broker/gateways/test_paper_conformance_unit.py packages/execution/tests/unit/broker/test_gateway_conformance_unit.py -q --no-cov`: passed; 72 passed.
  - `pixi run -e dev check`: passed; Ruff lint passed; Ruff format unchanged; basedpyright 0 errors; 7581 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
  - `pixi run -e dev test --cov-xml`: passed; 8209 passed, 126 skipped; total coverage 94.91%; coverage XML line-rate 96.01%, branch-rate 80.21%.

Latest Batch B reconciliation repair-planning pass:

- Added a side-effect-free `plan_repair()` layer that converts `ReconciliationReport.diffs` into typed repair actions without mutating orders, fills, account state or journals.
- Defined repair action semantics for missing fills, extra broker fills, quantity/price mismatches and order-status mismatches. Mutating actions are marked `requires_manual_review=True`; broker refresh is read-only and does not require manual review.
- Updated the reconciliation ADR and maturity manifest to distinguish pure repair planning, persisted workflow state, and future mutating repair execution work.
- Verification:
  - `pixi run -e dev pytest packages/execution/tests/unit/test_reconciliation_unit.py packages/execution/tests/unit/test_reconciliation_repair_unit.py -q --no-cov`: passed; 28 passed.
  - `pixi run -e dev basedpyright packages/execution/src/ditto_execution/reconciliation packages/execution/tests/unit/test_reconciliation_repair_unit.py`: passed; 0 errors, 0 warnings, 0 notes.
  - `pixi run -e dev pytest packages/execution/tests/unit -q --no-cov`: passed; 560 passed.
  - `pixi run -e dev check`: passed; Ruff lint passed; Ruff format 1675 files unchanged; basedpyright 0 errors; 7585 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
  - `pixi run -e dev test --cov-xml`: passed; 8213 passed, 126 skipped; total coverage 94.91%; coverage XML line-rate 96.01%, branch-rate 80.23%.

Latest Batch B reconciliation workflow persistence pass:

- Added `SQLiteRepairWorkflowStore` for persisted repair action review/execution state, using deterministic action IDs of the form `report_id:index`.
- Added `RepairActionStatus` and `RepairActionRecord` so repair actions can move through `ready`, `pending_review`, `approved`, `rejected`, and `executed` states without mutating orders, fills, account state or journals.
- Preserved safety semantics: read-only broker refresh actions can be ready immediately; write-like actions require approval before execution can be recorded; rejected actions cannot execute.
- Wired the repair workflow DDL into the execution storage provider schema initialization.
- Verification:
  - `pixi run -e dev pytest packages/execution/tests/unit/test_reconciliation_workflow_store_unit.py -q --no-cov`: passed; 5 passed.
  - `pixi run -e dev pytest packages/execution/tests/unit/test_reconciliation_unit.py packages/execution/tests/unit/test_reconciliation_repair_unit.py packages/execution/tests/unit/test_reconciliation_workflow_store_unit.py -q --no-cov`: passed; 33 passed.
  - `pixi run -e dev basedpyright packages/execution/src/ditto_execution/reconciliation packages/execution/src/ditto_execution/storage/sqlite/reconciliation.py packages/execution/src/ditto_execution/di/storage.py packages/execution/tests/unit/test_reconciliation_workflow_store_unit.py`: passed; 0 errors, 0 warnings, 0 notes.
  - `pixi run -e dev pytest packages/execution/tests/unit -q --no-cov`: passed; 565 passed.

Latest Batch B repair executor orchestration pass:

- Added `RepairActionExecutor` as the executor orchestration layer for persisted repair workflow actions.
- Added `RepairExecutionResult`, `RepairActionHandler`, `RepairWorkflowStore`, `RepairExecutionAuditSink`, and `BrokerFillQueryPort` so action execution is explicit, typed and injectable rather than hidden inside reconciliation planning.
- Added `BrokerRefreshRepairHandler` for the only default built-in action: read-only broker fill refresh. Write-like actions still require approval and an explicitly registered handler.
- Safety semantics: `pending_review` / `rejected` actions are not dispatched; `ready` / `approved` actions can dispatch to a registered handler; successful results are written back through `SQLiteRepairWorkflowStore.mark_executed(...)`; optional audit sinks receive execution results.
- Verification:
  - `pixi run -e dev pytest packages/execution/tests/unit/test_reconciliation_executor_unit.py -q --no-cov`: passed; 3 passed.
  - `pixi run -e dev basedpyright packages/execution/src/ditto_execution/reconciliation packages/execution/tests/unit/test_reconciliation_executor_unit.py`: passed; 0 errors, 0 warnings, 0 notes.
  - `pixi run -e dev pytest packages/execution/tests/unit/test_reconciliation_unit.py packages/execution/tests/unit/test_reconciliation_repair_unit.py packages/execution/tests/unit/test_reconciliation_workflow_store_unit.py packages/execution/tests/unit/test_reconciliation_executor_unit.py -q --no-cov`: passed; 36 passed.
  - `pixi run -e dev check`: passed; Ruff lint passed; Ruff format 1681 files unchanged; basedpyright 0 errors; 7597 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
  - `pixi run -e dev test --cov-xml`: passed; 8225 passed, 126 skipped; total coverage 94.92%; coverage XML line-rate 96.02%, branch-rate 80.22%.

Latest derived latest-run determinism pass:

- Full coverage validation exposed a real non-determinism: two derived materialization runs can share the same `created_at`, and the previous `get_latest_run()` tie-breaker used random `run_id` ordering. In one full-suite order, this returned an older `scheduled` run instead of the later `cascade` repair run.
- `SQLiteDerivedCatalogReader.get_latest_run()` now uses SQLite persistence order as the tie-breaker when `created_at` ties, so random run IDs no longer decide runtime semantics.
- Added a storage regression test proving a later cascade run wins over an earlier scheduled run with the same timestamp.
- Verification:
  - `pixi run -e dev pytest packages/features/tests/unit/storage/sqlite/derived/test_catalog_reader_unit.py -q --no-cov`: passed; 1 passed.
  - `pixi run -e dev pytest packages/apps/tests/integration/flows/test_derived_materialization_query_repair_integration.py::TestDerivedMaterializationQueryRepairIntegration::test_materialize_query_and_repair_flow_share_one_artifact_chain -q --no-cov`: passed; 1 passed.
  - `pixi run -e dev basedpyright packages/features/src/ditto_features/storage/sqlite/derived/reader.py packages/features/tests/unit/storage/sqlite/derived/test_catalog_reader_unit.py`: passed; 0 errors, 0 warnings, 0 notes.
  - `pixi run -e dev check`: passed; Ruff lint passed; Ruff format 1679 files unchanged; basedpyright 0 errors; 7591 passed, 25 skipped; 37 Import Linter contracts kept; architecture smell check passed.
  - `pixi run -e dev test --cov-xml`: passed; 8225 passed, 126 skipped; total coverage 94.92%; coverage XML line-rate 96.02%, branch-rate 80.22%.

## Industry Baselines Used

- Clean Architecture: inner business rules must not know outer delivery/storage/framework mechanisms.
- PyPA `src` layout: helps avoid accidental local imports and better matches installed package behavior.
- Import Linter: explicit layers/forbidden/independence contracts are an appropriate Python guard for architecture boundaries.
- Polars best practice: lazy/expression-oriented computation is the right direction for large tabular workflows.
- Coverage.py branch coverage: line coverage alone is insufficient for decision-heavy trading logic.
- QuantConnect LEAN: mature reference for modular alpha / portfolio / risk / execution framework and same-code backtest/live discipline.
- NautilusTrader: mature reference for event-driven backtest/paper/live, adapters, matching engine, risk, execution and portfolio subsystems.
- OpenTelemetry: traces, metrics and logs should form one operational observability model.

References:

- https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- https://import-linter.readthedocs.io/
- https://docs.pola.rs/user-guide/lazy/
- https://coverage.readthedocs.io/en/latest/branch.html
- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- https://nautilustrader.io/docs/latest/
- https://opentelemetry.io/docs/concepts/

## Top Findings

### P2: Branch Coverage Gate Is Met, But Hotspots Remain

Batch A restored the broader integration run and moved `coverage.xml` branch-rate from 76.60% to 80.22%; after the Batch B paper-runtime, reconciliation repair workflow/executor and derived-run determinism fixes, the current XML branch-rate remains 80.22%, still satisfying the project rule of at least 80%. For a trading platform, branch coverage still matters beyond the gate because order state, PIT policy, settlement, rejection, reconciliation and failure recovery are decision-heavy surfaces.

Next hardening targets:

1. Prioritize branch tests for `data.sources.tushare.adapters.stock`, `application.builders.template_builders`, index constituent storage, strategy-run SQLite storage, SQL engine branches, metadata instrument service and remaining CLI query branches in capital/macro.
2. Treat skipped E2E lanes that need external sample data or services as explicit maturity gaps, not invisible test debt.
3. Add behavior tests around negative paths, unsupported policies and state recovery before broad refactors.
4. Keep coverage gains tied to behavior contracts rather than superficial execution.

### P2: Paper Runtime Ownership Is Fixed; Broker Conformance And Repair Execution Must Broaden

`PaperBrokerGateway` remains the owner of paper account state, and `PaperTradingRuntime` now delegates account snapshots to `BrokerGateway.get_account()` instead of applying gateway fills to a second `Account`. This removes the double-application/divergent-account path in the paper runtime.

Remaining work:

- Expand the broker conformance suite so future live adapters prove the same submit/cancel/reject/fill/account semantics.
- Add concrete mutating repair handlers that consume approved persisted actions and record broker/store effects through the executor.
- Make paper/live account views and order status transitions visible in one audit trail.

### P1: DataCatalog And Lineage Are Not Yet The Operational Source Of Truth

The project has `DataCatalog` contracts and an in-memory runtime, but ingestion routing still depends on a large `Dataset` enum and application registry table. This is reasonable as transitional scaffolding, but it limits multi-market, multi-source, versioned dataset extensibility.

Target direction:

- `Dataset` should become a stable identifier vocabulary, not an operational routing spine.
- Routing, source capabilities, schema version, storage location, freshness, PIT columns and maturity should move into catalog metadata.
- Lineage should be written by ingestion/materialization/backtest paths and queried by audit/reporting paths.

### P1: PIT Safety Is Not Yet Fail-Closed

PIT helpers warn and fall back to `trade_date` when `knowledge_date` is missing. This is useful during migration, but production data access should fail closed unless the caller explicitly chooses a research-only unsafe mode.

Target direction:

- Production `TimeContext` requires PIT-safe columns.
- Unsafe fallback requires a named policy and is visible in audit output.
- Backtest manifests record PIT policy and source snapshot versions.

### P2: Strategy Pipeline Contracts Are Still Stringly Typed

`DecisionFrame` is documented as a column convention between pipeline stages. The package is well isolated, but the stage boundary is still implicit.

Target direction:

- Introduce a small `DecisionFrameSchema` validator at pipeline stage boundaries.
- Make template maturity depend on schema checks and golden snapshots.
- Keep strategy independent from data/features by defining schema contracts inside strategy or kernel-level generic DTOs.

### P2: Code Shape Debt Is Concentrated, Not Systemic

Most packages are manageable, but several files/classes are doing too much:

- `default_dataset_registry()` is a large imperative route table.
- `DerivedCatalogService` and `TushareSource` each expose about 30 public methods.
- Some app/job flows and statistical helpers exceed comfortable function length.

This is not yet an architecture failure, but it is the next readability ceiling.

## Package Review

| Package | Score | What Works | Main Gaps | Next Move |
|---|---:|---|---|---|
| kernel | 8.2 | Thin shared Protocol/value spine; runtime/time/trading contracts are useful. | A-share semantics leak into common trading types; event payloads still partly untyped. | Split universal trading concepts from market-specific rule extensions. |
| platform | 8.6 | Business-agnostic infra; config/log/cache/storage foundations are mostly isolated. | Observability is present but not yet a full SLO/run-trace model. | Standardize traces/metrics/log correlation across jobs and API. |
| data | 7.8 | Strong storage/source breadth, PIT helpers, quality checks, polars discipline; instrument/calendar metadata readers and Tushare fundamental paths are now strongly branch-covered. | Largest package; Dataset enum/registry/catalog split; lineage incomplete; PIT fallback too permissive; Tushare stock/macro, SQL engine, quality checkers and index-constituent branches remain weak. | Make DataCatalog + lineage the operational source of truth. |
| features | 8.0 | Expression/materialization/publication safety is strong; good immutable contracts; latest-run lookup is now deterministic when repair runs share timestamps. | Dependency mapping is manual; composite keys and 1m grain still reserved; large catalog service. | Create durable dependency registry and schema/time contracts. |
| strategy | 8.2 | Package isolation is excellent; alpha pipeline/templates are readable; integration fixture drift is repaired. | DecisionFrame schema implicit; broader stock/sector templates are still experimental. | Add stage schema gates and keep golden integration snapshots current. |
| portfolio | 8.8 | Clean pure domain; account/view separation, immutable models and mark-to-market valuation are strong. | Product maturity still experimental; projections/stores/events incomplete. | Add state projection and event publication around core accounting. |
| risk | 8.4 | Narrow protocols; pure findings; no platform dependency. | Continuous risk gate, state recovery and typed audit payloads still product gaps. | Promote risk state snapshot/restore and audit schema. |
| execution | 8.3 | OMS FSM, order ticket, journal, reconciler, pure repair planner, persisted repair workflow state, repair executor orchestration and paper gateway foundations exist; paper runtime now uses gateway-owned account state. | Live adapters reserved; broker conformance is still paper-heavy; executor has only read-only broker refresh by default, with concrete mutating handlers still missing. | Broaden broker conformance suite and add approved mutating repair handlers before live adapter work. |
| backtest | 8.1 | Engine loop, StepChain, synchronizer, manifests and daily mark-to-market semantics are solid. | Delayed tail execution is not fully PIT exact; replay/recovery limited. | Lock valuation/settlement semantics with conformance snapshots. |
| analysis | 7.8 | Research control-plane is isolated from production packages. | Late-arrival SHIFT policy is reserved; research ports/policies need stronger product contract. | Make maturity/unsupported policies impossible to misuse. |
| application | 7.7 | CQRS direction and import boundaries are good; use cases compose capabilities cleanly; typed command errors are aligned in E2E; paper runtime no longer owns duplicate account state. | Orchestrators/registries are large; several reserved backends. | Thin orchestration by moving routing metadata into capability-owned catalogs. |
| apps | 7.8 | FastAPI/CLI/jobs composition root is clear; DI/lifecycle exists; fundamental CLI now matches API/facade PIT capability for corporate actions. | E2E fixture skips; maturity exposure incomplete; metrics exporter timeout appears in full run shutdown; capital/macro query branches remain weak. | Commit a synthetic golden lane and expose maturity in public API/docs. |

## Product Architecture Gap Against Mature Trading Platforms

### Present Strengths

- Clean modular spine for data, strategy, portfolio, risk, execution and backtest.
- Backtest and execution share enough vocabulary to converge.
- A-share ETF daily workflow has meaningful implementation and tests.
- Publication safety and quality concepts are more mature than many early quant systems.

### Missing Or Incomplete Compared With LEAN/NautilusTrader-Class Systems

- Same strategy code across backtest, paper and live is not yet proven.
- No production broker adapters.
- Paper/live account and order ownership semantics are not yet proven across live adapters.
- Durable event sourcing and replay are partial.
- Data lineage is contract-level/experimental rather than universal runtime fact.
- Global market calendars, multi-currency accounting, corporate actions, intraday/tick, and exchange microstructure are not production-ready.
- Reconciliation detects mismatches, produces pure repair plans, persists approval/execution state and has executor orchestration, but concrete mutating repair handlers are not yet implemented.
- Portfolio optimization, risk model governance, slippage/impact calibration and walk-forward optimization are still product gaps.
- Observability is not yet a full traces/metrics/logs/SLO operating model.

The honest product positioning should remain: **initial-focus A-share ETF daily research/backtest, experimental broader A-share/global data and strategy surfaces, reserved live trading**.

## Remediation Order

### Batch A: Restore System Truth

1. Completed: fixed full integration failures in `backtest`, `strategy`, and `application`.
2. Completed: re-ran `pixi run -e dev check`.
3. Completed: re-ran `pixi run -e dev test --cov-xml`.
4. Completed: branch coverage raised from 76.60% to 80.22% with data-service, materialization-DQ, publication safety-gate, instrument metadata, CLI fundamental, Tushare fundamental, CalendarReader and golden-dataset behavior tests.
5. Remaining: reduce reliance on skipped external-data E2E lanes and continue risk-ranked hardening of high-value branch hotspots.

### Batch B: Execution / Paper Runtime Ownership

1. Completed: chose gateway-owned account state for paper runtime.
2. Completed: added failing conformance/regression tests proving runtime uses gateway account state and does not locally re-apply gateway fills.
3. Completed: updated `PaperTradingRuntime` wiring to remove duplicate `Account` ownership.
4. Completed: verified runtime tests and paper gateway conformance tests.
5. Completed: added side-effect-free reconciliation repair planning semantics.
6. Completed: added persisted repair workflow state and approval gates.
7. Completed: added repair executor orchestration, handler dispatch and audit sink port.
8. Remaining: broaden broker conformance to future live adapters and add concrete mutating repair handlers.

### Batch C: DataCatalog / Lineage

1. Promote catalog metadata to own dataset routing/freshness/storage/schema/maturity.
2. Make ingestion and materialization write lineage records.
3. Reduce `Dataset` enum to stable IDs and compatibility helpers.
4. Add architecture tests that prevent new route metadata from re-entering enum properties.

### Batch D: PIT And Time Semantics

1. Make production PIT fallback fail closed.
2. Introduce explicit `UnsafeResearchTimePolicy`.
3. Record PIT policy in backtest/materialization manifests.
4. Add leakage regression tests.

### Batch E: Strategy / Feature Contracts

1. Add `DecisionFrameSchema`.
2. Validate each strategy stage boundary.
3. Promote template maturity only after schema + golden snapshot pass.
4. Replace manual materialization dependency parsing with durable dependency registry.

### Batch F: Product Maturity And Operations

1. Add a committed synthetic golden E2E lane.
2. Expose maturity status in API/docs.
3. Add OpenTelemetry-style run correlation for API/jobs/backtests/trades.
4. Expand broker/reconciler conformance before live adapter work.

## Review Governance

For each module remediation, use this loop:

1. Pick one package and one P1/P2 finding.
2. Write or identify a failing test that proves the problem.
3. Make the smallest architecture-aligned fix.
4. Run the narrow test.
5. Run `pixi run -e dev check`.
6. For cross-module/runtime changes, run `pixi run -e dev test --cov-xml`.
7. Update this report or a linked remediation plan with the result.

## Completion Criteria For This Review Program

The review program is complete only when:

- `pixi run -e dev check` passes.
- Full integration/coverage run passes with branch coverage >= 80%.
- Paper runtime has one account state owner and conformance tests prove it. (Met for `PaperTradingRuntime`; broader live broker conformance remains active remediation work.)
- Dataset routing and lineage are catalog-driven or have a documented accepted deviation.
- PIT unsafe fallback is impossible in production paths without an explicit policy.
- Strategy stage schemas catch malformed decision frames before execution.
- Capability maturity docs match exposed APIs and product claims.
- Each package score is re-reviewed after remediation.
