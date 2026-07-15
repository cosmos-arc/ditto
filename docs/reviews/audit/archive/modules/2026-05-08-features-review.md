# Features Review Report

> Date: 2026-05-08
> Scope: `packages/features`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Features owns expression, factors, materialization, evaluation, artifact storage/query, and publication safety. Production code follows the package rule: it depends on kernel/platform, not data/strategy/portfolio/risk/execution/backtest/analysis/application/apps.

The package is comparatively mature: expression compilation, materialization contracts, derived catalog runtime records, artifact readers/writers, publication safety, and tests exist. The main gaps are time/input provenance semantics and public service surface clarity.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 105 Python source files, 33 test files, about 14,625 source LOC. |
| Largest files | `expression/codegen.py` 749, `evaluation/evaluator.py` 746, `ic.py` 622, `derived_catalog_service.py` 577, `derived/writer.py` 513. |
| Runtime records | `DerivedRun` and `DerivedRunRecord` carry `source_snapshot_id`; invalidation events carry `source_dataset` and `source_snapshot_id`. |
| Publication safety | `CompatibilityManifest` requires engine/codegen/operator/calendar/time semantics fields; application builder writes `time_semantics_version="time-v1"`. |
| PIT reads | Factor/derived readers expose `as_of`/`as_of_date` filters using local effective-time columns. |
| Services surface | `services` includes derived catalog/query/artifact/gc/shadow slot/publication safety record concerns. |
| SQL/noqa | A small number of sqlite/parquet readers/writers use controlled dynamic placeholders/table names. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| FEAT-P1-01 | P1 | Artifacts record `source_snapshot_id` and manifest `time_semantics_version`, but do not yet use DataCatalog asset refs or shared `TimeContext`. | Feature artifacts may be reproducible locally but not uniformly traceable across data/backtest/research. | Link derived inputs/outputs to DataCatalog/Lineage once runtime store exists; align query cutoff with `TimeContext`. |
| FEAT-P1-02 | P1 | `time_semantics_version="time-v1"` is hard-coded in application manifest builder and local readers use `as_of`/effective-time conventions. | Time semantics can drift between materialization, artifact read, research build, and runtime query. | Define time semantics in ADR and make manifest builder consume a versioned shared constant/config. |
| FEAT-P1-03 | P1 | Expression/operator tests cover PIT-oriented behavior, but there is no standard leak-test template spanning shift/rolling/join/publication cutoff. | Future operators or joins may accidentally introduce lookahead. | Add a reusable PIT leak test harness for expressions and artifact publication reads. |
| FEAT-P2-01 | P2 | Codegen/evaluator/IC/materialization service files are large and multi-concern. | New expression/operator work is harder to review. | Split emitters/evaluator sections after behavior is pinned with golden tests. |
| FEAT-P2-02 | P2 | `features.services` is a broad public-looking namespace with many unrelated orchestration/storage concerns. | Consumers may import internals directly and widen the public surface. | Add a features public API table or subpackage service namespaces by concern. |

No P0 finding was confirmed. The package should remain initial-focus, with provenance/time semantics treated as the key hardening area.

## 4. TDD 整改计划

1. Provenance:
   - RED: materialize a derived artifact and assert catalog asset refs and lineage inputs/outputs are recorded.
   - GREEN: add adapter to DataCatalog/Lineage when the data runtime store lands.
   - REFACTOR: replace raw `source_dataset` strings where catalog refs are available.

2. Time semantics:
   - RED: one test proving manifest, artifact read, and research build agree on cutoff semantics.
   - GREEN: centralize `time-v1` and pass a shared context.
   - REFACTOR: document migration to `time-v2` before changing behavior.

3. Public surface:
   - RED: add architecture test for allowed features service imports.
   - GREEN: expose only stable facades from `ditto_features.services`.
   - REFACTOR: move low-level stores/readers to explicit leaf imports.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-features-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/features/tests && pixi run -e dev arch-check && pixi run -e dev check`.
