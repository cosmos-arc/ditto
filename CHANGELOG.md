# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **BaseRuntimeKernel** in `ditto_kernel.runtime` — parameterized runtime lifecycle FSM base class with `RuntimeLifecycle` (8 stable + 7 transition states), `RuntimeSnapshot` (frozen state snapshot), `validate_transition()` pure function, and `TradingRuntimeKernel` Protocol.
- **BacktestRuntimeKernel** in `ditto_backtest.runtime` — inherits `BaseRuntimeKernel`, composes `SimulatedClock` + `SimpleEventBus`.
- **PaperRuntimeKernel** in `ditto_execution.broker.runtime` — inherits `BaseRuntimeKernel`, composes `RealtimeClock` + `SimpleEventBus`.
- `__all__` exports to multiple modules across kernel, backtest, execution, and application packages.
- `from __future__ import annotations` to `ditto_kernel.runtime` for forward-type compatibility.
- Missing `__init__` docstrings to several package `__init__.py` files.
- PIT observation comments in data layer deserialization helpers.
- **DataCatalog runtime** — `InMemoryCatalogStore` + `SqliteCatalogStore` with metadata tracking and promotion workflows.
- **DataLineage runtime** — `InMemoryLineageStore` + `SqliteLineageStore` for dataset dependency tracking.
- **Catalog promotion workflow** — evidence/assessment/override/revoke lifecycle for dataset certification.
- **PIT fail-closed policy** — `knowledge_date` defaults to today, preventing accidental look-ahead.
- **BrokerEventRecordingGateway** — decorator gateway that records broker events with structured taxonomy.
- **Reconciliation repair workflow** — plan/executor/store for automated trade reconciliation repair.
- **PaperRuntimeKernel** — paper-trading runtime kernel with `RealtimeClock` + `SimpleEventBus`.
- **BacktestCheckpoint** — checkpoint/resume API for long-running backtests.
- **KillSwitch** — type-safe kill switch with strict enum states.
- **CompositeDecisionStage** — score fusion and rank normalization for multi-signal strategy decisions.
- **Experience Memory (Markdown)** — markdown-based experience store for AI learning loops.
- **Hypothesis bridge points** — structured hypothesis-to-expression mapping in features layer.
- **Source health reporting** — health status tracking and summary API for data sources.
- **Maturity gates** — maturity-level validation across application query facades.
- **OpenAPI maturity annotations** — API endpoint maturity level documentation.
- **Expression codegen modularization** — split into cs/ts/scalar operator modules for maintainability.
- **IC computation/report split** — separated IC calculation from reporting in analysis layer.
- **Path resolver modularization** — decomposed path resolution into focused resolver modules.

### Changed

- **`data_store.py`** removed 22 backward-compat convenience properties; consumers must use `settings.paths.*` directly.
- Mutable global caches replaced with `functools.cache` across data and application layers.
- **`dataset_registry.py`** extracted domain sub-lists as module-level constants for clarity.
- **`ResearchDatasetFacade.build()`** split into smaller focused methods.
- **`records.py` `from_row()`** extracted JSON deserialization helpers for readability.
- Magic number literals replaced with named constants where identified.

### Fixed

- **`_xdg_paths.py`** dead code removal.
- **`paper.py`** nesting reduction for improved readability.
- Test filename typo corrected: `test_codege_helpers_unit.py` → `test_codegen_helpers_unit.py`.
