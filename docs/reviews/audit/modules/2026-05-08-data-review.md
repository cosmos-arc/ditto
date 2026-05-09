# Data Review Report

> Date: 2026-05-08
> Scope: `packages/data`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Data is the data platform: ingestion, providers, source adapters, storage, quality, PIT helpers, runtime SQL, DataCatalog/Lineage contracts, and domain services. The package is intentionally broad, and its boundary rule allows kernel/platform but forbids upward production-layer dependencies.

The review confirms meaningful implementation depth, especially market/fundamental/capital/macro services and storage. The biggest architectural gap is that the new governance language (`DataCatalog`, `Lineage`) is still contract-only, while the older `Dataset` enum and application config remain the real routing spine.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 270 Python source files, 191 test files, about 30,690 source LOC. |
| Largest files | `tushare_source.py` 777, `market_service.py` 752, `capital.py` adapter 725, `instrument.py` metadata service 698, `instrument_reader.py` 674, `sqlite_store.py` 623, `errors.py` 606. |
| Dataset spine | `models/common.py` defines `Dataset` with stock, ETF, index, fundamental, capital, macro, FX, commodity, corporate action, and index weight entries. |
| Catalog/lineage | `catalog/contracts.py` and `lineage/contracts.py` define product-neutral Protocols and dataclasses; only unit tests and architecture tests consume them today. |
| PIT terms | `knowledge_date`, `as_of_date`, `effective_from/to`, and `availability_time` appear across ingestion, storage, runtime SQL, services, features, application, and apps. |
| Consumer leakage | Backtest and application consume `ditto_data.provider.DataProvider` and `BarQuery` directly. |
| SQL/noqa | Several storage/runtime helpers use interpolated table/where strings with local allowlist comments. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| DATA-P1-01 | P1 | `DataCatalogReader/Writer` and `DataLineageRecorder/Reader` are contract-only; no runtime store/integration path exists. | Governance vocabulary can be mistaken for active lineage/catalog enforcement. | Either implement a minimal runtime store or mark DataCatalog runtime experimental with explicit reopen criteria. |
| DATA-P1-02 | P1 | `Dataset` enum and `application.config.INGESTION_SPECS` remain the real dataset router across data/apps/application. | Adding new markets/datasets requires enum/config edits in multiple places and delays DataCatalog migration. | Define a Dataset budget and migration path: enum for current fixed ingestion, catalog for extensible assets. |
| DATA-P1-03 | P1 | `DataProvider` is data-owned but consumed by backtest/application runtime builders. | Consumers bind to a data-layer interface rather than consumer-owned ports. | Add backtest/application-owned portal ports and adapt data providers at composition boundary. |
| DATA-P1-04 | P1 | Trading calendars, reference metadata, status histories, and rule-like PIT reference data live inside data storage/services while kernel/execution/backtest also hold market-rule defaults. | Reference-domain semantics can scatter across data/kernel/execution/backtest. | Split “data storage” from “market reference provider” decisions in ADR before adding new venue rules. |
| DATA-P2-01 | P2 | Several source/service/storage files exceed 600 LOC. | New dataset families will increase review and regression cost. | Decompose source adapters and service routers after Dataset/DataCatalog direction is fixed. |
| DATA-P2-02 | P2 | SQL interpolation has many local `S608` allowlist comments in base stores and runtime SQL helpers. | Safety depends on many small local conventions. | Maintain a SQL/noqa budget and move identifier validation into shared helpers. |

No P0 finding was confirmed. Data is functional but its governance/control-plane maturity should be described as experimental until catalog/lineage are runtime-backed.

## 4. TDD 整改计划

1. Catalog runtime:
   - RED: add tests proving a written catalog asset can be listed, queried, and linked to lineage.
   - GREEN: add minimal SQLite/file-backed catalog and lineage store.
   - REFACTOR: emit catalog refs from ingestion/materialization/backtest manifests.

2. Dataset budget:
   - RED: add architecture test counting new `Dataset` enum additions or requiring maturity labels.
   - GREEN: document enum vs catalog responsibilities.
   - REFACTOR: move extensible assets toward DataCatalog.

3. Consumer-owned ports:
   - RED: prove backtest core can run against a `HistoricalDataPortal` Protocol without importing data provider types.
   - GREEN: add adapter in application/apps composition.
   - REFACTOR: repeat for research/materialization portals where needed.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-data-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/data/tests && pixi run -e dev arch-check && pixi run -e dev check`.

