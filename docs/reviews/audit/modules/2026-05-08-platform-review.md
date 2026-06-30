# Platform Review Report

> Date: 2026-05-08
> Scope: `packages/platform`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Platform is shared infrastructure: config, cache, logging/observability, DB/storage primitives, notification services, and other business-agnostic foundation pieces. The package is intentionally thin on domain language and may depend on kernel only for shared error/trace semantics.

The hard boundary is mostly healthy. The review found no broad domain dependency leak. As of 2026-06-08, the shared SQLite count helper validates table identifiers and constrains WHERE fragments locally, so the prior PLAT-P1-01 SQL helper risk is resolved. Remaining open concerns are P2 polish: generic storage docs/examples still use enough data/domain vocabulary that future contributors may copy domain semantics into platform, and larger storage/observability files remain harder to audit by concern.

2026-06-08 update: the previously observed SQLitePool `close_all()` multithread test determinism risk is remediated. The test now waits for explicit worker connection reports and releases workers with an Event, so it verifies live thread-local connection cleanup without relying on fast thread exit, thread-id reuse, or SQLite WAL initialization timing.

2026-06-08 update: `SQLiteClient.count(table, where, params)` now validates table identifiers and accepts only a small parameterized WHERE grammar: `identifier <operator> ?`, `identifier IS [NOT] NULL`, and `AND`-joined predicates. It rejects literals, OR tautologies, statement separators, comments, SQL keywords, and placeholder-count mismatches before SQLite execution.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 51 Python source files, 41 test files, about 5,661 source LOC. |
| Largest files | `storage/parquet_store.py` 768, `observability/metrics.py` 534, `config/paths.py` 520, `cache/core.py` 326, `db/sqlite_pool.py` 301. |
| SQL/noqa | `foundation/storage/sqlite_client.py` validates `count()` table identifiers and WHERE fragments before constructing `SELECT COUNT(*) FROM {table}`. |
| SQLitePool determinism | `test_sqlite_pool_multithread.py` now keeps worker connections live via explicit result reporting and Event release; targeted DB/storage tests pass under xdist. |
| Storage vocabulary | `ParquetStore` documents `data_root/dataset/YYYY.parquet`, `instrument_column`, and examples like daily market datasets. |
| Observability | Metrics registry and notification services are generic; capability metric imports happen at apps registry composition. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| PLAT-P1-01 | Resolved 2026-06-08 | `SQLiteClient.count(table, where, params)` validates table names and constrained parameterized WHERE fragments; tests cover table injection, literal WHERE fragments, OR tautologies, statement separators and placeholder mismatch. | Residual risk is deliberate narrowness: unsupported predicates must use a dedicated caller-owned query builder instead of raw `count(where=...)`. | Keep `count()` grammar small; add explicit helper APIs only when real callers need broader predicates. |
| PLAT-P2-01 | P2 | `ParquetStore` is 768 lines and covers path layout, lazy scan, merge/dedup, write, metadata, delete, count, and checksum. | It is hard to audit storage behavior by concern. | Split read, write, metadata/checksum, and path-layout helpers while preserving API. |
| PLAT-P2-02 | P2 | Generic platform storage docs/examples use dataset/instrument terminology. | Domain terms can drift into platform as business semantics. | Reword platform API/docs toward `namespace`, `collection`, and `key_column`; keep market examples in data docs. |
| PLAT-P2-03 | P2 | Observability is generic, but runtime correlation/journal IDs are not a first-class cross-runtime contract yet. | Execution/risk/backtest audit paths may log useful data without stable correlation keys. | Add correlation-id guidance after OMS Lite chooses journal/run/order identity names. |

No P0 finding was confirmed. The package remains infrastructure-owned; no open P1 remains in this module report after the SQL helper remediation.

## 4. TDD 整改计划

1. SQL identifier and WHERE fragment safety:
   - DONE: tests reject table names and where fragments outside the validated budget.
   - DONE: `SQLiteClient.count()` validates table identifiers and a small parameterized WHERE grammar locally.
   - DONE: caller-validated safety assumption is removed from the shared helper.

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
