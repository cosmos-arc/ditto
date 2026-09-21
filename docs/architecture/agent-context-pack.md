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

## Research Dataset Boundary

- `research_dataset_build_flow` → `ResearchDatasetBuildProcess.build` resolves
  specs, spine and PIT inputs → analysis `ResearchArtifactService` publishes
  immutable content → `ResearchCatalogService` commits the completed snapshot.
- `ResearchDatasetQuery.get_snapshot/load_build_report` reads exact catalog
  identities and existing reports; it cannot build or export. Existing snapshot
  paths and hashes are retained without rewriting.
- Same inputs and content reuse the published identity, including creation time.
  A failed catalog commit is retried against those files; a conflicting immutable
  file is rejected. Partial publication has no completed catalog entry.
- `ditto research export-dataset --snapshot-id <id> --format csv|sqlite --path
  exports/data.csv` resolves a saved snapshot via `ResearchDatasetQuery`, then
  invokes `ResearchDatasetExport`. It verifies the catalog identity, manifest,
  data checksum and source-bound local research permissions before publication.
- Each resolved input freezes its own source snapshot IDs at build time. Export
  requires complete per-input bindings and an exact union matching the snapshot
  source set; later upstream metadata cannot retroactively authorize old inputs.
- Export targets stay within the research artifact root. The analysis artifact
  service reserves a `<target>.manifest.json` sidecar with source identity,
  ordered schema, row count and checksum, then publishes the complete data file
  without replacement. Read both files and verify the checksum; a sidecar alone
  is an interrupted export, recoverable by repeating the same request.
- SQLite export uses an analysis-owned temporary database and transaction, quoted
  identifiers and bound values. Empty data retains its schema. Temporal/decimal
  values use lossless text and their original types remain in the sidecar; NaN
  is rejected because SQLite would silently turn it into NULL.
- Same-content retries reuse files; target or provenance conflicts require a new
  target. Export is personal local research only and grants no redistribution
  rights. Missing source/license evidence fails closed; no rebuild or latest
  input lookup occurs during export.

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

## 验证入口

按[测试指南](../engineering/testing.md)选择 Task 验证范围；PR 的绿色结果只证明
当前提交所选中的检查，完整证明由 main、merge queue、定期 CI 和发布要求承载。
具体选择与聚合见[Harness 验证分工](../engineering/agent-harness.md#本地与-ci-的验证分工)。

研究导出对增量制品保守绑定该版本所有物化 run 的来源集合，不按 mtime 只选最新批次；任一 run 缺少来源证据则拒绝导出。当前没有分区级完整 lineage，完整覆盖旧分区后仍可能要求旧来源许可；需缩小许可范围时先补充分区 lineage，再收窄来源集合。SQLite 将 UInt64/Int128 与时间、decimal 按文本无损保存，manifest 保留原始 Polars schema。
