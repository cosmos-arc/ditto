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
