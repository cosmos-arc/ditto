# Platform Review Report

> Date: 2026-05-08
> Scope: `packages/platform`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Platform is shared infrastructure: config, cache, logging/observability, DB/storage primitives, notification services, and other business-agnostic foundation pieces. The package is intentionally thin on domain language and may depend on kernel only for shared error/trace semantics.

The hard boundary is mostly healthy. The review found no broad domain dependency leak, but did find two infrastructure risks: SQL identifier validation is still caller-by-convention in one shared client, and generic storage docs/examples use data/domain vocabulary enough that future contributors may copy domain semantics into platform.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 51 Python source files, 41 test files, about 5,661 source LOC. |
| Largest files | `storage/parquet_store.py` 768, `observability/metrics.py` 534, `config/paths.py` 520, `cache/core.py` 326, `db/sqlite_pool.py` 301. |
| SQL/noqa | `foundation/storage/sqlite_client.py` builds `SELECT COUNT(*) FROM {table}` and optional `WHERE {where}` with comment that caller validates. |
| Storage vocabulary | `ParquetStore` documents `data_root/dataset/YYYY.parquet`, `instrument_column`, and examples like daily market datasets. |
| Observability | Metrics registry and notification services are generic; capability metric imports happen at apps registry composition. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| PLAT-P1-01 | P1 | `SQLiteClient.count(table, where)` interpolates table and where strings; safety is documented as caller responsibility. | Platform provides a reusable footgun: one unvalidated caller can turn a shared helper into SQL injection risk. | Add identifier validation/value object or a constrained query builder for table and where clauses. |
| PLAT-P2-01 | P2 | `ParquetStore` is 768 lines and covers path layout, lazy scan, merge/dedup, write, metadata, delete, count, and checksum. | It is hard to audit storage behavior by concern. | Split read, write, metadata/checksum, and path-layout helpers while preserving API. |
| PLAT-P2-02 | P2 | Generic platform storage docs/examples use dataset/instrument terminology. | Domain terms can drift into platform as business semantics. | Reword platform API/docs toward `namespace`, `collection`, and `key_column`; keep market examples in data docs. |
| PLAT-P2-03 | P2 | Observability is generic, but runtime correlation/journal IDs are not a first-class cross-runtime contract yet. | Execution/risk/backtest audit paths may log useful data without stable correlation keys. | Add correlation-id guidance after OMS Lite chooses journal/run/order identity names. |

No P0 finding was confirmed. The package remains infrastructure-owned; the SQL helper is the only P1.

## 4. TDD 整改计划

1. SQL identifier safety:
   - RED: add tests rejecting table names and where fragments outside a validated budget.
   - GREEN: add identifier validation or replace `where: str` with a safe small expression object.
   - REFACTOR: remove caller-validated comments where validation becomes local.

2. Storage split:
   - RED: preserve current read/write/delete/checksum behavior with focused tests.
   - GREEN: extract helpers by concern.
   - REFACTOR: update docs to avoid data-domain terminology in platform.

3. Correlation guidance:
   - RED: add architecture test/docs assertion for required correlation fields once OMS ids exist.
   - GREEN: add generic logging context helper or doc.
   - REFACTOR: project execution/risk/backtest audit through the same field names.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-platform-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/platform/tests && pixi run -e dev arch-check && pixi run -e dev check`.
