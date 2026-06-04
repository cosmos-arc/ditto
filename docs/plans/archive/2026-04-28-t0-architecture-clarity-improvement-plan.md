# T0 Architecture Clarity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Raise Ditto's architecture clarity, naming precision, boundary enforceability, and agent understandability before any Order/live/platformization work.

**Architecture:** This plan treats architecture clarity as an executable product surface. It aligns the documented diamond model with import-linter, moves contracts to the layer that owns them, tightens CQRS semantics, makes ambiguous names explicit, and adds lightweight machine checks where documentation alone is too weak.

**Tech Stack:** Python 3.13, pixi, ruff, basedpyright, import-linter, pytest, polars, dishka, loguru/OpenTelemetry.

---

## Scope

This is the **A route: architecture clarity first**. It intentionally does not implement Order, live trading, DataCatalog, DataPortal, plugin discovery, OMS, or web workspace. Those are downstream discussions after this plan reduces ambiguity in the current system.

Primary inputs:

- `docs/architecture/boundaries-and-abstraction-standards.md`
- `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`
- `docs/reviews/audit/2026-04-28-t0-gap-analysis-and-design.md`
- `.importlinter`
- Package-level `CLAUDE.md` files

External baselines:

- Clean Architecture dependency rule: source dependencies point inward.
  <https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html>
- Python Protocols / structural subtyping: use Protocol when behavior is structural.
  <https://peps.python.org/pep-0544/>
- Python plugin discovery: consumer defines the interface; plugins provide implementations.
  <https://packaging.python.org/en/latest/specifications/entry-points/>
- pluggy hookspec/hookimpl model for later pluginization, not this phase.
  <https://pluggy.readthedocs.io/en/stable/>
- OpenTelemetry tracing: instrument important operations, not every helper.
  <https://opentelemetry.io/docs/languages/python/>

## Non-Goals

- No `Order` aggregate or OrderGateway.
- No backtest/live unified TradingLoop.
- No DataCatalog replacement for `Dataset` yet; this plan only prepares naming and boundary ground.
- No dynamic plugin discovery.
- No broad public API compatibility shim unless needed to keep one task bite-sized.

## T0 Exit Criteria

- `pixi run -e dev arch-check` passes.
- `pixi run -e dev type` passes for source.
- Targeted package tests pass for modified packages.
- Architecture docs and executable contracts describe the same dependency model.
- `analytics.expression` no longer imports `analytics.materialization`.
- Storage CQRS guard tests prevent Readers from owning write/DDL behavior and Writers from exposing query behavior in targeted metadata stores.
- Engine domain exceptions are centralized in `ditto_engine.exceptions`.
- Agent-facing guidance includes test placement, config placement, DI placement, public API rules, acronym policy, and helper/utils rules.

## Risk Controls

- Use TDD for every behavior-changing task.
- Prefer leaf-module imports over new re-export chains.
- Keep commits small: one task, one commit.
- Run `pixi run -e dev arch-check` after every boundary/import change.
- Do not mix style-only renames with semantic moves unless the task explicitly says so.

---

### Task 1: Freeze Metrics And Scorecard

**Files:**
- Create: `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`
- Modify: `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`

**Step 1: Capture fresh baseline commands**

Run:

```bash
find packages interfaces -path '*/src/*' -name '*.py' -print | wc -l
find packages interfaces -path '*/src/*' -name '*.py' -print0 | xargs -0 wc -l | tail -1
for p in packages/analytics packages/app packages/data packages/engine packages/infra packages/kernel interfaces; do
  printf '%-20s traced=' "$p"
  rg -n '@traced' "$p/src" -g '*.py' | wc -l | tr -d '\n'
  printf ' protocols='
  rg -n 'class .*\(Protocol\)|class .*Protocol\)' "$p/src" -g '*.py' | wc -l | tr -d '\n'
  printf ' exceptException='
  rg -n 'except Exception' "$p/src" -g '*.py' | wc -l
done
```

Expected: values near the current read-only baseline: 733 source files, 97,447 source lines, Data 42,138 lines, engine/analytics/interfaces `@traced=0`.

**Step 2: Write the scorecard**

Create a short scorecard with these sections:

```markdown
# T0 Architecture Clarity Scorecard

## Baseline

| Metric | Value | Command |
|---|---:|---|
| Source files | ... | `find ...` |
| Source lines | ... | `wc -l` |
| Data source lines | 42138 | package line count |
| analytics.expression -> materialization imports | 2 | `rg materialization.contracts packages/analytics/src/ditto_analytics/expression` |

## T0 Gates

| Gate | Current | Target |
|---|---|---|
| Docs/import-linter model alignment | mismatch | aligned |
| Expression boundary | reversed dependency | clean |
| CQRS storage method purity | partial | guarded |
| Engine exception taxonomy | root + scattered StateTransitionError | centralized |
| Agent context pack | scattered docs | one fast path |
```

**Step 3: Link it from the evaluation report**

Add a one-line pointer in the comprehensive evaluation report near the execution summary:

```markdown
> T0 architecture clarity execution metrics are tracked in
> `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`.
```

**Step 4: Verify**

Run:

```bash
git diff --check docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md
```

Expected: no whitespace errors.

**Step 5: Commit**

```bash
git add docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md
git commit -m "docs: add T0 architecture clarity scorecard"
```

---

### Task 2: Align Diamond Model With Import-Linter

**Files:**
- Modify: `.importlinter`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`
- Modify: `CLAUDE.md`

**Step 1: Write a failing documentation consistency check manually**

Before editing, run:

```bash
rg -n "Interfaces → App → Engine → Data → Infra|engine→data 排序|diamond|并列核心平面" .importlinter CLAUDE.md docs/architecture/boundaries-and-abstraction-standards.md
```

Expected: `.importlinter` still describes a linear `Interfaces -> App -> Engine -> Data -> Infra` stack, while boundaries uses the diamond model.

**Step 2: Update `.importlinter` comments only**

Do not weaken contracts. Replace the misleading layered comment with:

```ini
# Technical ordering for import-linter's `layers` contract.
# This is not the domain architecture model.
#
# Domain architecture is a diamond:
#   interfaces -> app -> {data, analytics, engine} -> kernel
#   infra is horizontal foundation.
#
# import-linter `layers` needs a sequence, so this contract only guards
# broad top-to-bottom imports. Parallel-plane isolation is enforced by
# the explicit forbidden contracts below.
```

**Step 3: Update `CLAUDE.md` architecture summary**

In the architecture principles section, add a short paragraph after the dependency rules:

```markdown
架构心智模型以 diamond 为准：`data`、`analytics`、`engine` 是并列核心平面；
`.importlinter` 中的 layers 顺序是工具表达限制，不代表业务层级高低。
平面互斥由 explicit forbidden contracts 固化。
```

**Step 4: Update boundaries document**

In Section 3 or Section 10, add:

```markdown
机器门禁解释原则：当 `.importlinter` 的 layers 表达与 diamond 图看似冲突时，
以 diamond 作为架构语义，以 explicit forbidden contracts 作为平面隔离依据。
```

**Step 5: Verify**

Run:

```bash
pixi run -e dev arch-check
rg -n "diamond|并列核心平面|Technical ordering" .importlinter CLAUDE.md docs/architecture/boundaries-and-abstraction-standards.md
```

Expected: import-linter still passes; docs and comments now tell the same story.

**Step 6: Commit**

```bash
git add .importlinter CLAUDE.md docs/architecture/boundaries-and-abstraction-standards.md
git commit -m "docs: align architecture model with import contracts"
```

---

### Task 3: Move Expression Contracts To Expression Layer

**Files:**
- Create: `packages/analytics/src/ditto_analytics/expression/contracts.py`
- Modify: `packages/analytics/src/ditto_analytics/expression/analyzer.py`
- Modify: `packages/analytics/src/ditto_analytics/expression/compiler.py`
- Modify: `packages/analytics/src/ditto_analytics/expression/__init__.py`
- Modify: `packages/analytics/src/ditto_analytics/materialization/contracts.py`
- Modify imports in `packages/app/src`, `packages/data/src`, and tests that reference `ditto_analytics.materialization.contracts` for expression-owned types.
- Modify: `.importlinter`

**Step 1: Write the failing boundary check**

Add this contract to `.importlinter` temporarily before code changes:

```ini
[importlinter:contract:analytics-expression-no-materialization]
name = Analytics expression must not import materialization
type = forbidden
source_modules =
    ditto_analytics.expression.**
forbidden_modules =
    ditto_analytics.materialization.**
```

Run:

```bash
pixi run -e dev arch-check
```

Expected: FAIL due to `expression/analyzer.py` and `expression/compiler.py` importing `materialization.contracts`.

**Step 2: Create expression contracts**

Create `packages/analytics/src/ditto_analytics/expression/contracts.py`:

```python
"""Expression-layer compile contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

__all__ = [
    "Analysis",
    "AnalysisWarning",
    "CompiledDerivedExpression",
    "CompileIdentity",
]


@dataclass(frozen=True)
class AnalysisWarning:
    """Lightweight compile-time warning produced during expression analysis."""

    message: str
    error_code: str


@dataclass(frozen=True)
class Analysis:
    """Semantic analysis metadata extracted from a derived expression."""

    dependencies: tuple[str, ...]
    operator_names: tuple[str, ...]
    lookback: int
    requires_full_day: bool
    scope: str
    output_schema: tuple[str, ...] = ("value",)
    warnings: tuple[AnalysisWarning, ...] = ()


@dataclass(frozen=True)
class CompileIdentity:
    """Stable compile identity for cache keys and artifact metadata."""

    compile_input_hash: str
    operator_fingerprint: str
    compiler_fingerprint: str
    cache_key: str
    engine_codegen_version: str
    analysis_version: str
    polars_version: str
    expr_serialization_format: str
    operator_versions: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    global_compile_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledDerivedExpression:
    """Compiled expression plus semantic metadata."""

    derived_id: str
    version: int
    expr: pl.Expr
    analysis: Analysis
    compile_identity: CompileIdentity
```

**Step 3: Update expression imports**

Change:

```python
from ditto_analytics.materialization.contracts import Analysis, AnalysisWarning
```

to:

```python
from ditto_analytics.expression.contracts import Analysis, AnalysisWarning
```

Change compiler imports similarly for `Analysis`, `CompiledDerivedExpression`, and `CompileIdentity`.

**Step 4: Update materialization contracts**

Remove the moved dataclass definitions from `materialization/contracts.py`; import them instead:

```python
from ditto_analytics.expression.contracts import (
    Analysis,
    AnalysisWarning,
    CompiledDerivedExpression,
    CompileIdentity,
)
```

Keep them in `__all__` only for one commit if this keeps the refactor small. Then update internal imports to the expression path in the next step so the re-export becomes removable.

**Step 5: Update callers**

Use:

```bash
rg -n "Analysis|AnalysisWarning|CompileIdentity|CompiledDerivedExpression|materialization\.contracts" packages interfaces -g '*.py'
```

For expression-owned types, import from `ditto_analytics.expression.contracts`.
For materialization-owned request/result/plan/event types, keep `ditto_analytics.materialization.contracts`.

**Step 6: Verify**

Run:

```bash
pixi run -e dev arch-check
pixi run -e dev pytest packages/analytics/tests packages/app/tests/unit/process/materialization packages/app/tests/unit/process/execution/test_factor_bridge_unit.py packages/data/tests/unit/services/derived/test_artifact_persistence_service_unit.py -q
pixi run -e dev type
```

Expected: arch-check passes; targeted tests pass; type check passes.

**Step 7: Commit**

```bash
git add .importlinter packages/analytics packages/app packages/data
git commit -m "refactor: move expression contracts to expression layer"
```

---

### Task 4: Enforce Storage CQRS Method Purity

**Files:**
- Create: `packages/data/tests/unit/architecture/test_storage_cqrs_contracts_unit.py`
- Modify: `packages/data/src/ditto_data/storage/metadata/strategy_spec_store.py`
- Modify: `packages/data/src/ditto_data/storage/metadata/fee_schedule_reader.py`
- Modify: `packages/data/src/ditto_data/storage/metadata/fee_schedule_writer.py`
- Modify: `packages/data/src/ditto_data/storage/metadata/trading_rule_reader.py`
- Modify: `packages/data/src/ditto_data/storage/metadata/trading_rule_writer.py`
- Modify tests under `packages/data/tests/unit/storage/metadata/` or nearest existing metadata storage tests.

**Step 1: Write failing architecture tests**

Create the guard test:

```python
"""Architecture tests for storage CQRS method ownership."""

from __future__ import annotations

import inspect

from ditto_data.storage.metadata.fee_schedule_reader import SQLiteFeeScheduleReader
from ditto_data.storage.metadata.fee_schedule_writer import SQLiteFeeScheduleWriter
from ditto_data.storage.metadata.strategy_spec_store import (
    SQLiteStrategySpecReader,
    SQLiteStrategySpecWriter,
)
from ditto_data.storage.metadata.trading_rule_reader import SQLiteTradingRuleReader
from ditto_data.storage.metadata.trading_rule_writer import SQLiteTradingRuleWriter

_WRITER_METHOD_PREFIXES = ("write", "save", "delete", "update", "load", "init_schema")
_READER_METHOD_PREFIXES = ("get", "list", "read", "count")


def _public_methods(cls: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_metadata_readers_do_not_expose_write_or_schema_methods() -> None:
    for cls in (SQLiteStrategySpecReader, SQLiteFeeScheduleReader, SQLiteTradingRuleReader):
        methods = _public_methods(cls)
        forbidden = {
            name
            for name in methods
            if name == "init_schema" or name.startswith(("write", "save", "delete", "update", "load"))
        }
        assert forbidden == set()


def test_metadata_writers_do_not_expose_query_methods() -> None:
    for cls in (SQLiteStrategySpecWriter, SQLiteFeeScheduleWriter, SQLiteTradingRuleWriter):
        methods = _public_methods(cls)
        forbidden = {
            name
            for name in methods
            if name.startswith(_READER_METHOD_PREFIXES)
        }
        assert forbidden == set()
```

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/architecture/test_storage_cqrs_contracts_unit.py -q
```

Expected: FAIL because readers expose `init_schema()` / `load()` and writers expose `get_records()`.

**Step 2: Move reader DDL behavior out of readers**

For `SQLiteStrategySpecReader`, remove `init_schema()`. Make initialization call `SQLiteStrategySpecWriter.init_schema()` where schema setup is currently required.

For `SQLiteFeeScheduleReader` and `SQLiteTradingRuleReader`, remove `init_schema()` and `load()`.

**Step 3: Move writer query behavior out of writers**

Move `SQLiteFeeScheduleWriter.get_records()` to `SQLiteFeeScheduleReader.list_all()` or `get_records()`. Prefer `list_all()` if no caller depends on `get_records()`.

Move `SQLiteTradingRuleWriter.get_records()` to `SQLiteTradingRuleReader.list_all()` or `get_records()`.

If a test needs to inspect persisted rows, instantiate the reader in the test instead of asking the writer to query.

**Step 4: Update callers**

Use:

```bash
rg -n "SQLite.*Reader\\(|\\.init_schema\\(|\\.load\\(|\\.get_records\\(" packages/data packages/app interfaces -g '*.py'
```

Update only the affected metadata stores. Do not attempt a repo-wide CQRS cleanup in this task.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/architecture/test_storage_cqrs_contracts_unit.py packages/data/tests/unit/storage packages/data/tests/integration/storage -q
pixi run -e dev type
```

Expected: new architecture guard passes; storage tests pass; type check passes.

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/storage/metadata packages/data/tests
git commit -m "refactor: enforce metadata storage CQRS purity"
```

---

### Task 5: Normalize Python Abstractions And Engine Exceptions

**Files:**
- Modify: `packages/data/src/ditto_data/storage/base/partition_strategy.py`
- Modify: `packages/data/tests/unit/storage/base/test_partition_strategy.py`
- Modify: `packages/engine/src/ditto_engine/exceptions.py`
- Modify: `packages/engine/src/ditto_engine/accounting/order_book.py`
- Modify: `packages/engine/src/ditto_engine/accounting/__init__.py`
- Modify tests importing `StateTransitionError`

**Step 1: Update PartitionStrategy tests first**

Replace the ABC instantiation test with structural Protocol behavior:

```python
from typing import Protocol

from ditto_data.storage.base import PartitionStrategy, YearlyPartition


def test_yearly_partition_satisfies_partition_strategy() -> None:
    strategy: PartitionStrategy = YearlyPartition()
    assert strategy.get_filename("2024") == "2024.parquet"
```

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/storage/base/test_partition_strategy.py -q
```

Expected: FAIL until `PartitionStrategy` becomes Protocol and tests are updated.

**Step 2: Convert PartitionStrategy to Protocol**

Use:

```python
from typing import Protocol


class PartitionStrategy(Protocol):
    """Partition strategy protocol for Parquet file organization."""

    def get_partition_key(self, date_str: str) -> str: ...

    def get_filename(self, partition_key: str) -> str: ...

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]: ...
```

`YearlyPartition` does not need to inherit from `PartitionStrategy`.

**Step 3: Centralize Engine exceptions**

In `packages/engine/src/ditto_engine/exceptions.py`, add:

```python
class StateTransitionError(EngineError):
    """Invalid domain state transition."""


class InvalidOrderError(EngineError):
    """Invalid order or execution request."""


class BacktestConfigError(EngineError):
    """Invalid backtest configuration."""


class DataIntegrityError(EngineError):
    """Invalid or unsafe input data for engine execution."""


class PortfolioConstraintError(EngineError):
    """Portfolio or risk constraint violation."""
```

Update `__all__` accordingly.

Move `StateTransitionError` out of `accounting/order_book.py`; import it from `ditto_engine.exceptions`. Update tests to import `StateTransitionError` from `ditto_engine.exceptions` unless they are explicitly testing the accounting public API.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/storage/base/test_partition_strategy.py packages/engine/tests/unit packages/engine/tests/integration/backtest/test_backtest_invariants.py packages/kernel/tests/unit/test_exceptions.py -q
pixi run -e dev type
```

Expected: tests pass; no type regressions.

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/storage/base packages/data/tests/unit/storage/base packages/engine packages/kernel/tests
git commit -m "refactor: clarify protocols and engine exceptions"
```

---

### Task 6: Resolve Ambiguous Naming Semantics

**Files:**
- Modify: `packages/data/src/ditto_data/sources/normalization.py`
- Modify: `packages/data/tests/unit/sources/test_normalization_unit.py`
- Modify: `packages/data/src/ditto_data/services/strategy/strategy_run_service.py`
- Modify: `packages/data/src/ditto_data/services/strategy/__init__.py`
- Modify callers importing data-layer `StrategyRunService`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`

**Step 1: Correct acronym policy in docs**

Add to the naming dictionary:

```markdown
Known domain acronyms stay uppercase in class names: `ETF`, `FX`, `API`,
`SQL`, `DQ`, `PIT`, `HTTP`. Module paths remain lowercase (`etf`, `fx`).
Do not rename public classes to `Etf` or `Fx`; that loses acronym signal.
```

This deliberately corrects the earlier candidate recommendation that suggested `Etf` / `Fx`.

**Step 2: Rename data source normalization Exchange**

The data source enum is not the same semantic object as `ditto_kernel.instrument.Exchange`.
Rename it to `SourceExchangeCode`:

```python
class SourceExchangeCode(StrEnum):
    """Source-facing exchange code used during data normalization."""

    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"
    CFFEX = "CFFEX"
    SHFE = "SHFE"
    DCE = "DCE"
    CZCE = "CZCE"
```

Update `NormalizationConfig.exchange_map` to:

```python
exchange_map: dict[str, SourceExchangeCode] = field(
    default_factory=lambda: {
        "SH": SourceExchangeCode.SSE,
        "SZ": SourceExchangeCode.SZSE,
        "BJ": SourceExchangeCode.BSE,
    }
)
```

Update tests to assert `SourceExchangeCode.SSE == "SSE"`.

**Step 3: Rename data-layer StrategyRunService**

Rename `StrategyRunService` in `ditto_data.services.strategy.strategy_run_service` to `StrategyRunLifecycleStore`.

Reason: the class coordinates persisted run lifecycle state through reader/writer protocols. The app-layer `StrategyRunService` remains the business process service.

Update:

```python
__all__ = [
    "StrategyRunLifecycleStore",
    "StrategyRunReaderProtocol",
    "StrategyRunWriterProtocol",
]


class StrategyRunLifecycleStore:
    """Persistent strategy run lifecycle store."""
```

Then update imports:

```bash
rg -n "ditto_data\.services\.strategy\.strategy_run_service import|StrategyRunService" packages interfaces -g '*.py'
```

Only change references that point to the data-layer class. Leave app-layer `ditto_app.process.execution.strategy_run_process.StrategyRunService` unchanged.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/sources packages/data/tests/unit/services/strategy interfaces/tests/registry packages/app/tests/unit/query/test_run_unit.py packages/app/tests/unit/query/test_lineage_unit.py -q
pixi run -e dev type
```

Expected: source normalization and run lifecycle tests pass; type check passes.

**Step 5: Commit**

```bash
git add packages/data interfaces packages/app docs/architecture/boundaries-and-abstraction-standards.md
git commit -m "refactor: clarify exchange and run lifecycle names"
```

---

### Task 7: Make Config Path And Logging Semantics Explicit

**Files:**
- Modify: `packages/data/src/ditto_data/config/data_source_validation.py`
- Modify: `packages/infra/src/ditto_infra/foundation/config/providers/config_validation.py`
- Modify: `packages/infra/src/ditto_infra/foundation/config/initializer.py`
- Modify: `packages/infra/src/ditto_infra/foundation/observability/_lifecycle.py`
- Modify: `packages/data/src/ditto_data/quality/config.py`
- Modify: `packages/data/tests/unit/config/test_data_source_validation_provider_unit.py`
- Add tests for `DQSettings.get_rules_paths()`

**Step 1: Add DQSettings path tests**

Create or extend a unit test to assert relative paths are resolved from an explicit root:

```python
from pathlib import Path

from ditto_data.quality.config import DQSettings


def test_dq_settings_resolves_relative_paths_from_config_root(tmp_path: Path) -> None:
    rules = tmp_path / "config" / "testing" / "dq_rules"
    rules.mkdir(parents=True)
    expected = rules / "stock_daily.yml"
    expected.write_text("rules: []\n", encoding="utf-8")

    settings = DQSettings(environment="testing", config_root=tmp_path)

    assert settings.get_rules_paths("stock_daily") == [expected]
```

Expected: FAIL until `config_root` exists.

**Step 2: Add `config_root` to DQSettings**

Use:

```python
config_root: Path = Field(default_factory=lambda: Path.cwd())

@property
def rules_path(self) -> Path:
    path = Path(self.rules_dir)
    if path.is_absolute():
        return path
    return self.config_root / path
```

For environment-specific rules:

```python
env_rules = self.config_root / "config" / self.environment / "dq_rules" / f"{dataset}.yml"
```

**Step 3: Replace f-string logging with structured logging**

Change:

```python
logger.error(f"Data source validation failed: {message}")
```

to:

```python
logger.error(
    "Data source validation failed",
    event="data_source_validation_failed",
    message=message,
)
```

Apply the same structured pattern to the infra config validation and initializer f-string logs.

**Step 4: Verify**

Run:

```bash
rg -n "logger\.(debug|info|warning|error|critical)\(f" packages interfaces -g '*.py'
pixi run -e dev pytest packages/data/tests/unit/config packages/infra/tests/unit/config -q
pixi run -e dev type
```

Expected: grep returns no source f-string logger calls; tests and type check pass.

**Step 5: Commit**

```bash
git add packages/data/src/ditto_data/config packages/data/src/ditto_data/quality packages/data/tests/unit/config packages/infra
git commit -m "fix: make config paths and logging explicit"
```

---

### Task 8: Split Materialization Helpers By Responsibility

**Files:**
- Create: `packages/app/src/ditto_app/process/materialization/minimal_dq.py`
- Create: `packages/app/src/ditto_app/process/materialization/manifest_builder.py`
- Create: `packages/app/src/ditto_app/process/materialization/dependency_refs.py`
- Modify: `packages/app/src/ditto_app/process/materialization/helpers.py`
- Modify callers and tests under `packages/app/tests/unit/process/materialization/`

**Step 1: Characterize current behavior**

Run:

```bash
pixi run -e dev pytest packages/app/tests/unit/process/materialization/test_materialization_unit.py packages/app/tests/unit/process/materialization/test_manifest_builder_unit.py -q
```

Expected: pass before refactor.

**Step 2: Move DQ summary functions**

Move these from `helpers.py` to `minimal_dq.py`:

- `build_minimal_dq_record`
- `_build_minimal_dq_summary`
- `_count_null_primary_keys`
- `_count_duplicate_primary_keys`
- `_count_nan_values`
- `_count_computable_values`
- `_compute_value_statistics`
- `_compute_value_jump_rate`
- `_compute_max_consecutive_nulls`
- `_max_consecutive_true`

Export only public functions:

```python
__all__ = ["build_minimal_dq_record"]
```

If tests need private helpers, test through public records or move the specific helper test to the new module with a clearer public function.

**Step 3: Move manifest functions**

Move these to `manifest_builder.py`:

- `build_manifest_record`
- `_build_manifest`
- `_manifest_payload`
- `_compile_flags_dict`
- `_manifest_hash`
- `resolve_shadow_baseline`

**Step 4: Move dependency reference functions**

Move these to `dependency_refs.py`:

- `dependency_refs`
- `_market_dependency_ref`
- `_etf_dependency_ref`

Keep `helpers.py` as a temporary import shim for one commit only if needed:

```python
from ditto_app.process.materialization.dependency_refs import dependency_refs
from ditto_app.process.materialization.manifest_builder import (
    build_manifest_record,
    resolve_shadow_baseline,
)
from ditto_app.process.materialization.minimal_dq import build_minimal_dq_record

__all__ = [
    "build_manifest_record",
    "build_minimal_dq_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]
```

Then update internal imports to the leaf modules and delete the shim in a follow-up if no imports remain.

**Step 5: Verify**

Run:

```bash
rg -n "process\.materialization\.helpers" packages interfaces -g '*.py'
pixi run -e dev pytest packages/app/tests/unit/process/materialization -q
pixi run -e dev type
```

Expected: no production imports from `helpers.py`; materialization tests pass.

**Step 6: Commit**

```bash
git add packages/app/src/ditto_app/process/materialization packages/app/tests/unit/process/materialization
git commit -m "refactor: split materialization helpers by responsibility"
```

---

### Task 9: Split Factor Analysis Metrics Into Cohesive Modules

**Files:**
- Create: `packages/analytics/src/ditto_analytics/evaluation/metrics/orthogonalization.py`
- Create: `packages/analytics/src/ditto_analytics/evaluation/metrics/fama_macbeth.py`
- Create: `packages/analytics/src/ditto_analytics/evaluation/metrics/exposure.py`
- Create: `packages/analytics/src/ditto_analytics/evaluation/metrics/attribution.py`
- Modify: `packages/analytics/src/ditto_analytics/evaluation/metrics/factor_analysis.py`
- Modify related tests under `packages/analytics/tests/unit/evaluation/`

**Step 1: Characterize current metrics**

Run:

```bash
pixi run -e dev pytest packages/analytics/tests/unit/evaluation -q
```

Expected: pass before refactor.

**Step 2: Move by public API**

Move:

- `orthogonalize` and private orthogonalization helpers to `orthogonalization.py`.
- `fama_macbeth` and private Fama-MacBeth helpers to `fama_macbeth.py`.
- `factor_exposure` and exposure helpers to `exposure.py`.
- `performance_attribution` and attribution helpers to `attribution.py`.

Keep `factor_analysis.py` as a thin compatibility aggregator for one commit:

```python
"""Factor analysis public API."""

from ditto_analytics.evaluation.metrics.attribution import performance_attribution
from ditto_analytics.evaluation.metrics.exposure import factor_exposure
from ditto_analytics.evaluation.metrics.fama_macbeth import fama_macbeth
from ditto_analytics.evaluation.metrics.orthogonalization import orthogonalize

__all__ = [
    "factor_exposure",
    "fama_macbeth",
    "orthogonalize",
    "performance_attribution",
]
```

**Step 3: Update tests only if needed**

Prefer keeping public imports stable unless tests need private helper imports. Move private helper tests to module-level tests only when those helpers remain meaningful.

**Step 4: Verify**

Run:

```bash
wc -l packages/analytics/src/ditto_analytics/evaluation/metrics/factor_analysis.py
pixi run -e dev pytest packages/analytics/tests/unit/evaluation -q
pixi run -e dev type
```

Expected: `factor_analysis.py` is under 80 lines; tests and type check pass.

**Step 5: Commit**

```bash
git add packages/analytics/src/ditto_analytics/evaluation/metrics packages/analytics/tests/unit/evaluation
git commit -m "refactor: split factor analysis metrics"
```

---

### Task 10: Add Targeted Observability To Core Entry Points

**Files:**
- Modify selected files in:
  - `packages/engine/src/ditto_engine/backtest/engine.py`
  - `packages/engine/src/ditto_engine/alpha/pipeline.py`
  - `packages/engine/src/ditto_engine/execution/planner.py`
  - `packages/analytics/src/ditto_analytics/expression/compiler.py`
  - `packages/analytics/src/ditto_analytics/evaluation/evaluator.py`
- Add or update tests only where decorators affect behavior.

**Step 1: Identify public entry points**

Run:

```bash
rg -n "^class |^def " packages/engine/src/ditto_engine/backtest/engine.py packages/engine/src/ditto_engine/alpha/pipeline.py packages/engine/src/ditto_engine/execution/planner.py packages/analytics/src/ditto_analytics/expression/compiler.py packages/analytics/src/ditto_analytics/evaluation/evaluator.py
```

**Step 2: Add `@traced` to entry points only**

Use existing infra decorator:

```python
from ditto_infra.foundation import traced


@traced("engine.backtest.run")
def run(...):
    ...
```

Naming convention:

- `engine.backtest.run`
- `engine.alpha.pipeline.process`
- `engine.execution.plan`
- `analytics.expression.compile`
- `analytics.evaluation.evaluate`

Do not decorate private math helpers or high-frequency inner loops unless profiling proves a need.

**Step 3: Verify**

Run:

```bash
for p in packages/analytics packages/engine; do
  printf '%-20s traced=' "$p"
  rg -n '@traced' "$p/src" -g '*.py' | wc -l
done
pixi run -e dev pytest packages/engine/tests/unit packages/analytics/tests/unit -q
pixi run -e dev type
```

Expected: engine and analytics each have non-zero traced entry points; tests and type check pass.

**Step 4: Commit**

```bash
git add packages/engine packages/analytics
git commit -m "chore: trace core engine and analytics entry points"
```

---

### Task 11: Add Agent Context Pack And Placement Rules

**Files:**
- Create: `docs/architecture/agent-context-pack.md`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`
- Modify: `CLAUDE.md`
- Modify package-level `CLAUDE.md` files only if they conflict with the pack.

**Step 1: Create the context pack**

Create `docs/architecture/agent-context-pack.md`:

```markdown
# Ditto Agent Context Pack

## Fast Architecture Model

`interfaces -> app -> {data, analytics, engine} -> kernel`.
`infra` is horizontal foundation.

## Placement Rules

| Need | Place |
|---|---|
| HTTP/CLI/job DTO | `interfaces` |
| Use case orchestration | `app.process`, `app.command`, `app.query` |
| Data source/storage/quality/catalog | `data` |
| Expression/factor/evaluation/research | `analytics` |
| Strategy, portfolio, risk, execution, backtest runtime | `engine` |
| Shared stable value object | `kernel` |
| Business-agnostic config/observability/db utilities | `infra` |

## Test Placement

Unit tests live beside the owning package under `tests/unit`.
Cross-package behavior goes to the highest package that owns the user-facing workflow.
E2E belongs in `interfaces/tests/e2e`.

## Naming Rules

Known acronyms stay uppercase in class names: ETF, FX, API, SQL, DQ, PIT, HTTP.
Do not create new `Manager`, `Helper`, or `Utils` names without a specific owned resource or domain noun.

## Before Editing

Run `rg` for nearby patterns and import direction.
When changing imports, run `pixi run -e dev arch-check`.
```

**Step 2: Link it from main docs**

Add links in `CLAUDE.md` and `boundaries-and-abstraction-standards.md`.

**Step 3: Verify**

Run:

```bash
rg -n "agent-context-pack|Agent Context Pack" CLAUDE.md docs/architecture
git diff --check docs/architecture/agent-context-pack.md CLAUDE.md docs/architecture/boundaries-and-abstraction-standards.md
```

Expected: links exist; no whitespace errors.

**Step 4: Commit**

```bash
git add docs/architecture/agent-context-pack.md CLAUDE.md docs/architecture/boundaries-and-abstraction-standards.md
git commit -m "docs: add agent architecture context pack"
```

---

### Task 12: Add Lightweight Architecture Smell Checks

**Files:**
- Create: `scripts/architecture/check_architecture_smells.py`
- Modify: `pyproject.toml` or pixi task config if architecture scripts are already wired elsewhere.
- Add tests for the script if there is an existing scripts test pattern.

**Step 1: Implement a read-only checker**

Create a script that checks only stable, low-noise smells:

```python
"""Read-only architecture smell checks for Ditto."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOTS = [
    ROOT / "packages",
    ROOT / "interfaces",
]

FORBIDDEN_SOURCE_LOG_PATTERNS = (
    "logger.debug(f",
    "logger.info(f",
    "logger.warning(f",
    "logger.error(f",
    "logger.critical(f",
)


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for root in SRC_ROOTS:
        files.extend(root.glob("**/src/**/*.py"))
    return sorted(files)


def main() -> int:
    errors: list[str] = []
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_SOURCE_LOG_PATTERNS:
            if pattern in text:
                errors.append(f"{path.relative_to(ROOT)}: contains {pattern!r}")
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Do not add broad naming checks yet; they will be noisy. The first check should enforce only things already agreed and already cleaned up.

**Step 2: Wire into an architecture command**

If pixi has a suitable task section, add a task such as:

```toml
arch-smells = "python scripts/architecture/check_architecture_smells.py"
```

If task wiring is centralized elsewhere, use the existing pattern.

**Step 3: Verify**

Run:

```bash
python scripts/architecture/check_architecture_smells.py
pixi run -e dev arch-check
```

Expected: smell checker exits 0 after Task 7; arch-check passes.

**Step 4: Commit**

```bash
git add scripts/architecture/check_architecture_smells.py pyproject.toml
git commit -m "chore: add architecture smell checker"
```

---

### Task 13: Final Documentation Convergence

**Files:**
- Modify: `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`
- Modify: `docs/reviews/audit/2026-04-28-t0-gap-analysis-and-design.md`
- Modify: `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`

**Step 1: Update the evaluation report**

Mark resolved or revised findings:

- F01: resolved by diamond/import-linter explanation.
- F07: resolved by expression contracts move and import-linter contract.
- F05: partially resolved for metadata stores, with guard coverage.
- F06: revise recommendation to uppercase known acronyms, not `Etf`/`Fx`.
- F08: resolved for exception taxonomy baseline.
- F09: improved from zero traced entry points in engine/analytics to targeted coverage.

**Step 2: Update T0 gap plan**

In the T0 gap analysis, add a note that Order/live/DataCatalog remain blocked on architecture clarity completion. Make P1-P6 explicitly downstream of this plan.

**Step 3: Update scorecard**

Record final command results:

```bash
pixi run -e dev arch-check
pixi run -e dev type
pixi run -e dev pytest packages/analytics/tests packages/data/tests/unit packages/engine/tests/unit packages/app/tests/unit/process/materialization -q
```

**Step 4: Verify full fast check**

Run:

```bash
pixi run -e dev check
```

Expected: lint, format, type, and fast tests pass.

**Step 5: Commit**

```bash
git add docs/reviews/audit docs/architecture
git commit -m "docs: close T0 architecture clarity plan"
```

---

## Suggested Execution Order

1. Task 1: Freeze Metrics And Scorecard
2. Task 2: Align Diamond Model With Import-Linter
3. Task 3: Move Expression Contracts To Expression Layer
4. Task 7: Make Config Path And Logging Semantics Explicit
5. Task 5: Normalize Python Abstractions And Engine Exceptions
6. Task 4: Enforce Storage CQRS Method Purity
7. Task 6: Resolve Ambiguous Naming Semantics
8. Task 8: Split Materialization Helpers By Responsibility
9. Task 9: Split Factor Analysis Metrics Into Cohesive Modules
10. Task 10: Add Targeted Observability To Core Entry Points
11. Task 11: Add Agent Context Pack And Placement Rules
12. Task 12: Add Lightweight Architecture Smell Checks
13. Task 13: Final Documentation Convergence

This order fixes dependency-direction and documentation truth first, then tackles code semantics, then improves understandability and observability.

## Post-Plan Decision Gate

Only after Task 13 passes `pixi run -e dev check`, reopen the capability boundary discussion in this order:

1. Order and execution lifecycle.
2. Backtest/live parity.
3. DataCatalog and DataPortal.
4. Plugin discovery and platformization.
