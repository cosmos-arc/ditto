# Capability Architecture 100 Point Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the capability package architecture from "import-clean and mostly complete" to a 100-point state where semantic ownership, machine guardrails, docs, and full verification all agree.

**Architecture:** Keep the accepted 12-package capability architecture. Do not add a new layer or another shared package. Move misplaced domain semantics to the package that owns them, keep `application` as orchestration, and keep `apps/registry` as the only composition root.

**Tech Stack:** Python 3.13, dishka DI, import-linter, custom architecture smell checks, basedpyright, ruff, pytest, Polars, SQLite storage adapters.

---

## 100 Point Definition

The remediation is complete only when all items below are true:

| Area | Points | Required Result |
|---|---:|---|
| Package dependency graph | 15 | `pixi run -e dev arch-check` passes with no import-linter or smell failures. |
| Semantic ownership | 25 | Data owns market facts/DQ/ingestion only; Features owns derived artifacts/publication safety/factors; Platform owns generic technology only. |
| Platform purity | 15 | No DQ, ticker, factor, portfolio, risk, strategy, or market-data defaults remain in `ditto_platform`. |
| Data/features split | 15 | No features/factors/derived-publication runtime storage remains in `ditto_data`. |
| Execution boundary quality | 10 | No `TYPE_CHECKING` or lazy `__getattr__` is used to hide storage cycles; broker protocols have a single documented ownership model. |
| Apps/application surface | 8 | Non-registry apps cannot import capability internals; registry bundles expose stable facades/contracts, not storage implementation details. |
| Capability skeleton honesty | 5 | Placeholder modules either become minimal Protocol/DTO contracts or are explicitly documented as out-of-scope without fake completion. |
| Documentation and AI rules | 4 | Active docs/comments no longer reference legacy `infra/interfaces/analytics/engine` as architecture names. |
| Full gate | 3 | `pixi run -e dev check` passes; `pixi run -e dev ci` is run or any remaining external blocker is documented. |

---

## Task 0: Add Semantic Ownership Guardrails First

**Files:**
- Modify: `scripts/architecture/check_architecture_smells.py`
- Create: `packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py`

**Step 1: Write failing tests**

Add tests that assert the smell checker rejects:

```python
def test_apps_capability_roots_include_all_domain_packages():
    from scripts.architecture.check_architecture_smells import (
        APPS_CAPABILITY_IMPORT_ROOTS,
    )

    assert {"ditto_portfolio", "ditto_risk"} <= APPS_CAPABILITY_IMPORT_ROOTS


def test_semantic_forbidden_terms_include_derived_feature_ownership():
    from scripts.architecture.check_architecture_smells import (
        DATA_FORBIDDEN_SEMANTIC_TERMS,
        PLATFORM_FORBIDDEN_DOMAIN_TERMS,
    )

    assert "features/" in DATA_FORBIDDEN_SEMANTIC_TERMS
    assert "factors/" in DATA_FORBIDDEN_SEMANTIC_TERMS
    assert "publication_safety" in DATA_FORBIDDEN_SEMANTIC_TERMS
    assert "instrument_id" in PLATFORM_FORBIDDEN_DOMAIN_TERMS
    assert "trade_date" in PLATFORM_FORBIDDEN_DOMAIN_TERMS
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py -q
```

Expected: fails because constants/checks do not exist or are incomplete.

**Step 3: Implement guard constants and checks**

In `scripts/architecture/check_architecture_smells.py`:

- Add `ditto_portfolio` and `ditto_risk` to `APPS_CAPABILITY_IMPORT_ROOTS`.
- Add `DATA_FORBIDDEN_SEMANTIC_TERMS` covering `"features/"`, `"factors/"`, `"publication_safety"`, `"publication_shadow"`, and import strings under `ditto_data.storage.runtime.publication_*`.
- Add `PLATFORM_FORBIDDEN_DOMAIN_TERMS` covering `"instrument_id"`, `"trade_date"`, `"factor_"`, `"portfolio_"`, `"risk."`, `"dq_"`, `"golden_dataset"`, and `"ticker"`.
- Add targeted scanners that skip tests, docs, migrations, and changelog archives.
- Keep exceptions explicit and tiny; do not broad-allow an entire file just to pass the check.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py -q
pixi run -e dev arch-check
```

Expected: new unit test passes; `arch-check` may now fail until later tasks remove the actual smells.

**Step 5: Commit**

```bash
git add scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture/test_capability_semantic_ownership_unit.py
git commit -m "test: guard capability semantic ownership"
```

---

## Task 1: Move Publication Safety Runtime Stores From Data To Features

**Files:**
- Move: `packages/data/src/ditto_data/storage/runtime/publication_safety/*`
- To: `packages/features/src/ditto_features/storage/runtime/publication_safety/*`
- Move tests: `packages/data/tests/unit/storage/runtime/publication_safety/*`
- To: `packages/features/tests/unit/storage/runtime/publication_safety/*`
- Modify imports in moved files from `ditto_data.storage.runtime.publication_safety` to `ditto_features.storage.runtime.publication_safety`
- Modify: `packages/features/pyproject.toml`

**Step 1: Write failing import-boundary test**

Create or extend `packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py`:

```python
from pathlib import Path


def test_data_runtime_storage_has_no_publication_safety_store():
    runtime_root = Path("packages/data/src/ditto_data/storage/runtime")
    assert not (runtime_root / "publication_safety").exists()
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py -q
```

Expected: fails because the directory still exists under data.

**Step 3: Move implementation and tests**

Use `git mv` for the files. Ensure the new package directories have `__init__.py`.

Update all source/test imports found by:

```bash
rg -n "ditto_data\.storage\.runtime\.publication_safety|storage/runtime/publication_safety" packages -g '*.py'
```

Expected source destinations:

- `packages/application/src/ditto_application/providers.py`
- `packages/application/tests/unit/process/materialization/test_publication_facade_unit.py`
- `packages/application/tests/unit/process/materialization/test_derived_materialization_orchestrator_unit.py`
- `packages/apps/tests/integration/flows/test_derived_publication_integration.py`

**Step 4: Verify moved store tests**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/storage/runtime/publication_safety -q
pixi run -e dev pytest packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py -q
```

Expected: all pass.

**Step 5: Commit**

```bash
git add packages/data packages/features packages/application packages/apps
git commit -m "refactor: move publication safety stores to features"
```

---

## Task 2: Move Publication Safety Record Service To Features

**Files:**
- Move: `packages/data/src/ditto_data/ingestion/publication_safety_record_service.py`
- To: `packages/features/src/ditto_features/services/publication_safety_record_service.py`
- Move: `packages/data/tests/unit/services/test_publication_safety_record_service.py`
- To: `packages/features/tests/unit/services/test_publication_safety_record_service.py`
- Modify: `packages/data/src/ditto_data/ingestion/__init__.py`
- Modify: `packages/application/src/ditto_application/providers.py`
- Modify: `packages/application/src/ditto_application/processes/materialization/orchestrator.py`
- Modify: `packages/application/src/ditto_application/processes/materialization/publication_facade.py`

**Step 1: Write failing test**

Extend `packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py`:

```python
def test_data_ingestion_has_no_derived_publication_service():
    path = Path("packages/data/src/ditto_data/ingestion/publication_safety_record_service.py")
    assert not path.exists()
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py -q
```

Expected: fails.

**Step 3: Move service and update imports**

Update imports from:

```python
from ditto_data.ingestion.publication_safety_record_service import ...
```

to:

```python
from ditto_features.services.publication_safety_record_service import ...
```

Remove the service from `ditto_data.ingestion.__all__`.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/services/test_publication_safety_record_service.py -q
pixi run -e dev pytest packages/application/tests/unit/process/materialization/test_publication_facade_unit.py -q
pixi run -e dev pytest packages/application/tests/unit/process/materialization/test_derived_materialization_orchestrator_unit.py -q
```

Expected: all pass.

**Step 5: Commit**

```bash
git add packages/data packages/features packages/application packages/apps
git commit -m "refactor: move publication safety service to features"
```

---

## Task 3: Move Derived Shadow Slot SQLite Storage To Features DI

**Files:**
- Move: `packages/data/src/ditto_data/storage/runtime/publication_shadow_sqlite/*`
- To: `packages/features/src/ditto_features/storage/runtime/publication_shadow_sqlite/*`
- Move tests: `packages/data/tests/unit/storage/runtime/publication_shadow_sqlite/*`
- To: `packages/features/tests/unit/storage/runtime/publication_shadow_sqlite/*`
- Modify: `packages/data/src/ditto_data/di/runtime.py`
- Modify: `packages/features/src/ditto_features/di/storage.py`
- Modify: `packages/application/src/ditto_application/providers.py`

**Step 1: Write failing ownership test**

Add:

```python
def test_data_runtime_storage_has_no_publication_shadow_sqlite():
    runtime_root = Path("packages/data/src/ditto_data/storage/runtime")
    assert not (runtime_root / "publication_shadow_sqlite").exists()
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/architecture/test_data_semantic_ownership_unit.py -q
```

Expected: fails.

**Step 3: Move storage adapter and provider ownership**

Move imports from data to features:

```python
from ditto_features.storage.runtime.publication_shadow_sqlite import (
    SQLiteDerivedShadowSlotReader,
    SQLiteDerivedShadowSlotWriter,
)
```

Register `DerivedShadowSlotService` and shadow slot reader/writer in `FeaturesStorageProvider`, because shadow slots are derived publication runtime state.

Remove shadow slot provider responsibility from `ditto_data.di.runtime`.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/storage/runtime/publication_shadow_sqlite -q
pixi run -e dev pytest packages/apps/tests/registry/test_runtime_provider_derived_catalog_unit.py -q
pixi run -e dev arch-check
```

Expected: tests pass; arch-check may still fail on remaining data/platform semantic checks.

**Step 5: Commit**

```bash
git add packages/data packages/features packages/application packages/apps
git commit -m "refactor: move derived shadow runtime storage to features"
```

---

## Task 4: Remove Feature And Factor Paths From DataStoreSettings

**Files:**
- Modify: `packages/data/src/ditto_data/config/data_store.py`
- Modify: `packages/data/tests/unit/config/test_data_store_settings_unit.py`
- Create: `packages/features/src/ditto_features/config/__init__.py`
- Create: `packages/features/src/ditto_features/config/artifact_store.py`
- Create: `packages/features/tests/unit/config/test_artifact_store_settings_unit.py`
- Modify callers discovered by `rg -n "features_technical_|factors_(narrow|wide)" packages -g '*.py'`

**Step 1: Write failing tests**

In data tests:

```python
def test_data_store_settings_does_not_own_feature_or_factor_paths():
    settings = DataStoreSettings()
    assert not hasattr(settings, "features_technical_price_path")
    assert not hasattr(settings, "factors_narrow_path")
    assert "features/technical/price" not in settings.all_directories()
    assert "factors/factors_narrow" not in settings.all_directories()
```

In features tests:

```python
from pathlib import Path

from ditto_features.config import FeatureArtifactStoreSettings


def test_feature_artifact_store_settings_owns_feature_and_factor_paths():
    settings = FeatureArtifactStoreSettings(data_root=Path("data"))

    assert settings.features_technical_price_path == Path("data/features/technical/price")
    assert settings.factors_narrow_path == Path("data/factors/factors_narrow")
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/config/test_data_store_settings_unit.py packages/features/tests/unit/config/test_artifact_store_settings_unit.py -q
```

Expected: fails until settings are split.

**Step 3: Implement split**

Create `FeatureArtifactStoreSettings` with only derived/feature/factor artifact paths. Keep `data_root` as an injected root so filesystem layout remains backward-compatible.

Remove feature/factor properties and directories from `DataStoreSettings`.

Do not move existing parquet artifact data paths on disk in this task; only move config ownership.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/config/test_data_store_settings_unit.py -q
pixi run -e dev pytest packages/features/tests/unit/config/test_artifact_store_settings_unit.py -q
pixi run -e dev arch-check
```

Expected: passes after callers use the features config.

**Step 5: Commit**

```bash
git add packages/data packages/features packages/application packages/apps
git commit -m "refactor: move feature artifact paths out of data config"
```

---

## Task 5: Purify Platform Project Root Helpers And Ticker Utilities

**Files:**
- Modify: `packages/platform/src/ditto_platform/foundation/config/project_root.py`
- Modify: `packages/platform/tests/unit/config/test_project_root_unit.py`
- Move: `packages/platform/src/ditto_platform/foundation/util/ticker_utils.py`
- To: `packages/data/src/ditto_data/utils/ticker_utils.py` or `packages/data/src/ditto_data/market/ticker_utils.py`
- Move test: `packages/platform/tests/unit/util/test_ticker_utils_unit.py`
- To: `packages/data/tests/unit/utils/test_ticker_utils_unit.py`
- Modify imports discovered by `rg -n "ticker_utils|get_standard_ticker|get_default_dq_rules_dir|get_default_golden_dataset_path" packages -g '*.py'`

**Step 1: Write failing tests**

Update platform tests to assert only generic root discovery remains:

```python
def test_project_root_module_exports_only_generic_helpers():
    import ditto_platform.foundation.config.project_root as project_root

    assert not hasattr(project_root, "get_default_dq_rules_dir")
    assert not hasattr(project_root, "get_default_golden_dataset_path")
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit/config/test_project_root_unit.py -q
```

Expected: fails.

**Step 3: Move domain helpers**

Move DQ/golden path helpers to data quality config, for example:

```text
packages/data/src/ditto_data/quality/config_paths.py
```

Move ticker utility to data. Update all imports.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit/config/test_project_root_unit.py packages/data/tests/unit/utils/test_ticker_utils_unit.py -q
pixi run -e dev arch-check
```

Expected: platform tests pass; arch-check still may fail until metrics/parquet are cleaned.

**Step 5: Commit**

```bash
git add packages/platform packages/data
git commit -m "refactor: move domain helpers out of platform"
```

---

## Task 6: Make Platform ParquetStore Generic

**Files:**
- Modify: `packages/platform/src/ditto_platform/foundation/storage/parquet_store.py`
- Create or modify: `packages/platform/tests/unit/storage/test_parquet_store_generic_unit.py`
- Modify data/features adapters that rely on default `instrument_id` and `trade_date`

**Step 1: Write failing tests**

Add tests that fail when platform hard-codes market columns:

```python
def test_parquet_store_requires_explicit_key_and_date_columns(tmp_path):
    store = ParquetStore(
        data_root=tmp_path,
        key_columns=("id", "date"),
        date_column="date",
    )

    assert store._get_key_columns() == ["id", "date"]
    assert store._get_date_column() == "date"
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit/storage/test_parquet_store_generic_unit.py -q
```

Expected: fails because constructor does not accept explicit key/date columns.

**Step 3: Implement generic constructor**

Change `ParquetStore.__init__` to accept:

```python
key_columns: tuple[str, ...] = ()
date_column: str | None = None
instrument_column: str | None = None
```

Rules:

- Generic platform code must not default to `instrument_id` or `trade_date`.
- Data/features adapters must pass those domain columns explicitly.
- `read(..., instrument_ids=...)` should either become a generic `filters` argument or be moved to data/features wrapper adapters. Prefer moving the domain-specific filter into wrappers.

**Step 4: Verify data/features adapters**

Run:

```bash
pixi run -e dev pytest packages/data/tests packages/features/tests -q
pixi run -e dev arch-check
```

Expected: data/features tests pass and platform no longer contains market column defaults.

**Step 5: Commit**

```bash
git add packages/platform packages/data packages/features
git commit -m "refactor: make platform parquet store domain neutral"
```

---

## Task 7: Move Domain Metric Catalogs Out Of Platform

**Files:**
- Modify: `packages/platform/src/ditto_platform/foundation/observability/metrics.py`
- Modify: `packages/platform/tests/unit/observability/test_metrics_registry_unit.py`
- Modify: `packages/platform/tests/integration/observability/test_metrics_integration.py`
- Create: `packages/data/src/ditto_data/observability/metrics.py`
- Create: `packages/features/src/ditto_features/observability/metrics.py`
- Create: `packages/portfolio/src/ditto_portfolio/observability/metrics.py`
- Create: `packages/risk/src/ditto_risk/observability/metrics.py`
- Create optional app-level registry wiring in `packages/apps/src/ditto_apps/registry/infra/observability.py`

**Step 1: Write failing platform purity test**

```python
def test_platform_metrics_are_technology_only():
    from ditto_platform.foundation.observability.metrics import METRIC_DEFINITIONS

    names = {item["instrument_name"] for item in METRIC_DEFINITIONS}
    assert not any(".factor." in name for name in names)
    assert not any(".portfolio." in name for name in names)
    assert not any(".risk." in name for name in names)
    assert not any(".dq." in name for name in names)
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit/observability/test_metrics_registry_unit.py -q
```

Expected: fails while platform owns domain metrics.

**Step 3: Split metric definitions**

Keep platform metrics for technology primitives only:

- API
- cache
- SQL
- JSON serialization
- scheduler if it is app infrastructure

Move domain metrics to the package that owns them:

- data: `ditto.data.*`, DQ, ingestion
- features: `ditto.factor.*`, derived materialization
- strategy: signal generation if strategy owns the signal semantic
- portfolio: portfolio value/drawdown
- risk: kill switch and risk checks

**Step 4: Wire registration at composition root**

The platform can expose a generic `register_metric_definitions(definitions)` function. `apps/registry` imports package-owned definitions and registers them.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit/observability packages/platform/tests/integration/observability -q
pixi run -e dev arch-check
```

Expected: platform is domain-neutral and metrics still initialize.

**Step 6: Commit**

```bash
git add packages/platform packages/data packages/features packages/portfolio packages/risk packages/apps
git commit -m "refactor: move domain metrics out of platform"
```

---

## Task 8: Remove Execution Storage Lazy Import Cycle

**Files:**
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/__init__.py`
- Modify: `packages/execution/src/ditto_execution/storage/deps.py`
- Modify: `packages/execution/src/ditto_execution/di/storage.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/service.py`
- Create: `packages/execution/tests/unit/storage/test_trade_package_imports_unit.py`

**Step 1: Write failing test**

```python
from pathlib import Path


def test_trade_package_has_no_lazy_service_cycle():
    source = Path(
        "packages/execution/src/ditto_execution/storage/sqlite/trade/__init__.py"
    ).read_text()

    assert "TYPE_CHECKING" not in source
    assert "__getattr__" not in source
    assert "import_module" not in source
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/storage/test_trade_package_imports_unit.py -q
```

Expected: fails.

**Step 3: Break cycle by importing leaf modules**

Change `packages/execution/src/ditto_execution/storage/deps.py` to import directly from:

```python
from ditto_execution.storage.sqlite.trade.fills import FillReader, FillWriter
from ditto_execution.storage.sqlite.trade.intents import IntentReader, IntentWriter
from ditto_execution.storage.sqlite.trade.positions import PositionReader, PositionWriter
```

Change `packages/execution/src/ditto_execution/di/storage.py` to import `TradeService` directly from:

```python
from ditto_execution.storage.sqlite.trade.service import TradeService
```

Then remove lazy export logic from `trade/__init__.py`.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/storage -q
pixi run -e dev arch-check
```

Expected: no cycle and no lazy import workaround.

**Step 5: Commit**

```bash
git add packages/execution
git commit -m "refactor: remove execution trade lazy import cycle"
```

---

## Task 9: Unify Execution Brokerage Protocol Semantics

**Files:**
- Modify: `packages/execution/src/ditto_execution/brokerage.py`
- Modify: `packages/execution/src/ditto_execution/broker/contracts.py`
- Modify imports discovered by `rg -n "BrokerGateway|Brokerage|submit_order|place_order|query_fills|process_pending" packages -g '*.py'`
- Create: `packages/execution/tests/unit/broker/test_broker_protocol_semantics_unit.py`

**Step 1: Choose the target model**

Recommended model:

- `BrokerGateway`: low-level live or simulated adapter port with `submit_order`, `cancel_order`, `get_account`, `query_fills`.
- `Brokerage`: higher-level execution runtime port that may wrap a gateway and owns `process_pending`.

This keeps live gateway semantics separate from simulation-time processing.

**Step 2: Write tests**

```python
def test_broker_protocols_have_non_overlapping_documented_responsibilities():
    from ditto_execution.broker.contracts import BrokerGateway
    from ditto_execution.brokerage import Brokerage

    assert hasattr(BrokerGateway, "submit_order")
    assert not hasattr(BrokerGateway, "process_pending")
    assert hasattr(Brokerage, "place_order")
    assert hasattr(Brokerage, "process_pending")
```

**Step 3: Verify failure or ambiguity**

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/broker/test_broker_protocol_semantics_unit.py -q
```

Expected: may pass structurally, but add docstring assertions if needed to force explicit semantics.

**Step 4: Implement semantic cleanup**

Add module-level docs explaining:

- `BrokerGateway` is an adapter-facing port.
- `Brokerage` is runtime-facing and used by backtest/live execution loops.
- The adapter from `Brokerage.place_order` to `BrokerGateway.submit_order` lives in execution/application wiring, not in backtest.

Rename only if current consumers are few enough. If renaming, do it in one focused commit.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/execution/tests packages/backtest/tests -q
pixi run -e dev arch-check
```

Expected: execution/backtest boundaries remain clean.

**Step 6: Commit**

```bash
git add packages/execution packages/backtest packages/application
git commit -m "refactor: clarify execution broker protocols"
```

---

## Task 10: Tighten Apps Registry Public Surface

**Files:**
- Modify: `packages/apps/src/ditto_apps/registry/contexts/bundle.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/strategy.py`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify tests under `packages/apps/tests/registry/`

**Step 1: Write failing guard**

Extend the architecture smell tests so non-registry apps still cannot import capability internals, and registry bundle dataclasses should not expose concrete storage classes in their public fields.

Example test:

```python
def test_strategy_bundle_does_not_expose_storage_implementation_types():
    from dataclasses import fields

    from ditto_apps.registry.contexts.bundle import StrategyBundle

    field_types = {str(field.type) for field in fields(StrategyBundle)}
    assert not any(".storage.sqlite." in value for value in field_types)
```

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/registry -q
```

Expected: fails if bundle exposes concrete strategy storage services.

**Step 3: Replace concrete field types with facades/protocols**

Prefer:

- `StrategyFacade`
- `RunLifecycleService`
- A strategy catalog Protocol exported from `ditto_strategy.contracts` if query access is required.

Do not expose `ditto_strategy.storage.sqlite.*` types from bundle dataclass annotations.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/registry packages/apps/tests/unit/architecture -q
pixi run -e dev arch-check
```

Expected: apps boundary remains strict.

**Step 5: Commit**

```bash
git add packages/apps packages/strategy scripts/architecture/check_architecture_smells.py
git commit -m "refactor: expose stable registry context contracts"
```

---

## Task 11: Convert Honest Placeholders Into Minimal Contracts

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/signals/models.py`
- Modify: `packages/strategy/src/ditto_strategy/signals/store.py`
- Modify: `packages/strategy/src/ditto_strategy/audit/__init__.py`
- Modify: `packages/portfolio/src/ditto_portfolio/holdings/__init__.py`
- Modify: `packages/portfolio/src/ditto_portfolio/positions/__init__.py`
- Modify: `packages/portfolio/src/ditto_portfolio/target_portfolios/__init__.py`
- Modify: `packages/execution/src/ditto_execution/orders/store.py`
- Modify: `packages/execution/src/ditto_execution/fills/store.py`
- Modify: `packages/execution/src/ditto_execution/reconciliation/__init__.py`
- Create focused tests in the corresponding package test directories.

**Step 1: Write failing tests**

Each placeholder should expose at least one meaningful Protocol or DTO. Example:

```python
def test_signal_store_contract_is_actionable():
    from ditto_strategy.signals.store import SignalStore

    assert hasattr(SignalStore, "save_signal")
    assert hasattr(SignalStore, "list_signals")
```

**Step 2: Verify failure**

Run focused tests for strategy, portfolio, and execution.

**Step 3: Add minimal contracts only**

Do not implement storage. Add just enough contracts to make module ownership real:

- `SignalRecord`, `SignalStore`
- `HoldingSnapshot`, `HoldingReader`
- `PositionSnapshot`, `PositionReader`
- `TargetPortfolio`, `TargetPortfolioStore`
- `OrderStore`, `FillStore`
- `ReconciliationReport`

Use dataclasses and Protocols; avoid new dependencies.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests packages/portfolio/tests packages/execution/tests -q
pixi run -e dev arch-check
```

Expected: contracts are import-clean and not fake implementations.

**Step 5: Commit**

```bash
git add packages/strategy packages/portfolio packages/execution
git commit -m "feat: define minimal capability contracts"
```

---

## Task 12: Clean Active Documentation And Source Terminology Drift

**Files:**
- Modify: `packages/apps/src/ditto_apps/registry/__init__.py`
- Modify: `packages/apps/src/ditto_apps/exceptions.py`
- Modify: `packages/application/src/ditto_application/commands/backtest.py`
- Modify: `packages/application/src/ditto_application/contracts.py`
- Modify: `packages/features/src/ditto_features/validation.py`
- Modify: `packages/kernel/src/ditto_kernel/tracing.py`
- Modify: `scripts/architecture/check_architecture_smells.py` if active-doc scanner needs tightening

**Step 1: Write failing stale-term test**

Extend existing architecture doc/rule tests to scan active source docstrings for legacy architectural names:

```python
STALE_SOURCE_ARCHITECTURE_TERMS = (
    "Interfaces 层",
    "interfaces/",
    "infra/",
    "analytics layer",
    "engine 层",
)
```

Allow generic terms like "execution engine" and persisted schema fields like `engine_version`.

**Step 2: Verify failure**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture -q
```

Expected: fails on known stale comments/docstrings.

**Step 3: Update terminology**

Replace legacy names with current architecture terms:

- `interfaces` -> `apps`
- `infra` -> `platform`
- `analytics layer` -> `features`
- old `engine layer` comments -> concrete package name

Do not rename telemetry operation names in this task unless they are clearly not part of backwards-compatible metric naming.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture -q
pixi run -e dev arch-check
```

Expected: no active stale architecture references.

**Step 5: Commit**

```bash
git add packages scripts/architecture/check_architecture_smells.py
git commit -m "docs: remove stale architecture terminology"
```

---

## Task 13: Final 100 Point Gate

**Files:**
- Modify only files required by verification failures.
- Create or update: `docs/reviews/2026-05-04-capability-architecture-100-point-review.md`

**Step 1: Run architecture gate**

```bash
pixi run -e dev arch-check
```

Expected:

```text
Contracts: 36 kept, 0 broken.
Architecture smell check passed.
```

If the number of contracts changes, document why.

**Step 2: Run normal developer gate**

```bash
pixi run -e dev check
```

Expected: ruff, format, type, fast tests, import-linter, and architecture smell checks pass.

**Step 3: Run CI gate**

```bash
pixi run -e dev ci
```

Expected: full lint, format-check, type-all, coverage tests, and arch-check pass.

**Step 4: Run targeted ownership searches**

```bash
rg -n "publication_safety|publication_shadow_sqlite|features/|factors/" packages/data/src -g '*.py'
rg -n "instrument_id|trade_date|factor_|portfolio_|risk\\.|dq_|golden_dataset|ticker" packages/platform/src -g '*.py'
rg -n "TYPE_CHECKING|__getattr__|import_module" packages/execution/src/ditto_execution/storage/sqlite/trade -g '*.py'
rg -n "ditto_data\\.storage\\.runtime\\.publication|ditto_data\\.ingestion\\.publication_safety" packages -g '*.py'
```

Expected: no matches except explicitly documented false positives.

**Step 5: Write final review**

Create `docs/reviews/2026-05-04-capability-architecture-100-point-review.md` with:

- final score table
- exact commands run and results
- remaining out-of-scope product capabilities, if any
- confirmation that semantic ownership and machine guardrails agree

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: complete capability architecture semantic cleanup"
```

---

## Execution Notes

- Use one task per commit. Do not batch platform, data/features, execution, and docs cleanup into one commit.
- Keep compatibility only where there is a real external migration need. Do not add cross-package re-export shims.
- When moving files, prefer `git mv` so review history stays understandable.
- If a move creates a dependency cycle, move the Protocol to the consumer-owned package instead of using `TYPE_CHECKING`.
- Run `pixi run -e dev arch-check` after every task that changes imports.
- The plan reaches 100 only after the final review document records actual command output.
