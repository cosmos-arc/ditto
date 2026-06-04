# Capability Architecture Final Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完全收口 capability architecture quality remediation 的剩余缺口，使全量 `pixi run -e dev check` 通过，并让源码、门禁、文档和设计意图一致。

**Architecture:** 保持当前 12 包能力架构和更严格的最终依赖图。先修复测试门禁，再补 import-linter/architecture-smell 的 exact barrel 覆盖，随后清理 data 对 platform 的剩余 re-export、让领域错误层级进入真实边界，最后同步主动文档和最终验证。所有共享技术类型从 canonical owner 导入：纯领域共享放 `ditto_kernel`，技术基础类型放 `ditto_platform`，不再经 `ditto_data` 中转。

**Tech Stack:** Python 3.13, pixi, pytest/xdist, ruff, basedpyright, import-linter, custom architecture smell checker, setuptools editable packages.

---

## Current Evidence

Latest audit evidence:

- Branch: `architecture-refactor`.
- `pixi run -e dev arch-check`: pass, 36 contracts kept, 0 broken.
- `pixi run -e dev check`: fail during `pytest --fast`.
- Failure: `packages/risk/tests/unit/test_models_unit.py` conflicts with `packages/data/tests/unit/quality/test_models_unit.py` under pytest default import mode.
- `packages/apps/README.md` still contains active stale docs: `interfaces/`, `apps -> analytics`.
- `.importlinter` covers `ditto_data.models` exact for apps, but not all exact barrels.
- `data-storage-no-model-import` still misses exact `ditto_data.models`.
- `ditto_data.models.common` still re-exports `OnDuplicate` from platform.
- `ditto_data.storage.base` still re-exports platform storage types.
- Domain error classes exist, but most public boundary code still raises `ValueError` or generic `ExecutionError`.

## Required Final State

The work is complete only when all of these are true:

- `pixi run -e dev check` exits 0.
- `pixi run -e dev arch-check` exits 0 with 0 unmatched ignore warnings.
- No active source imports platform/kernel owned types through `ditto_data` re-export shims.
- No `ditto_data.storage.*` module imports exact `ditto_data.models`.
- Non-registry apps code does not import `ditto_data.models/services/errors/quality/config` direct or exact barrels.
- Public strategy/execution/features boundary failures use specific domain errors.
- Active package docs do not mention old package names or old layer names.
- The untracked remediation plan files are intentionally added or intentionally removed.

## Execution Rules

1. Use TDD: RED -> GREEN -> REFACTOR.
2. One task, one commit unless the task explicitly says split.
3. Do not weaken lint, type, import-linter, coverage, or architecture checks.
4. Do not add long-term compatibility re-export shims.
5. Before deleting an import path, run `rg` to locate all consumers.
6. Use `apply_patch` for manual edits.
7. Do not use `TYPE_CHECKING` to hide architecture violations.

---

## Task 0: Baseline and Worktree Hygiene

**Files:**
- Read: `git status --short`
- Read: `docs/plans/2026-05-04-capability-architecture-quality-remediation.md`
- Read: `docs/plans/2026-05-04-capability-architecture-final-completion-plan.md`

**Step 1: Confirm current branch and untracked files**

Run:

```bash
git branch --show-current
git status --short
```

Expected:

```text
architecture-refactor
?? docs/plans/2026-05-04-capability-architecture-quality-remediation.md
?? docs/plans/2026-05-04-capability-architecture-final-completion-plan.md
```

If there are unrelated user changes, do not revert them. Record them before continuing.

**Step 2: Decide plan-file ownership**

If both plan files should remain project history, add them in Task 7. If `2026-05-04-capability-architecture-quality-remediation.md` was only scratch, ask before deleting it.

**Step 3: Reproduce the failing gate**

Run:

```bash
pixi run -e dev check
```

Expected before Task 1:

```text
pytest --fast ... ERROR collecting packages/risk/tests/unit/test_models_unit.py
import file mismatch
```

**Step 4: Commit**

No commit for baseline unless plan files are intentionally committed now.

---

## Task 1: Fix Pytest Import Mode So Full Check Collects All Tests

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/test.py`
- Create: `packages/apps/tests/unit/architecture/test_pytest_import_mode_unit.py`

**Problem:**

`pyproject.toml` currently has `importmode = "importlib"`, but `pixi run -e dev check` still runs pytest with default prepend import mode. Duplicate basenames are common in this repo, so a new `packages/risk/tests/unit/test_models_unit.py` collides with `packages/data/tests/unit/quality/test_models_unit.py`.

**Step 1: RED - Add config guard**

Create `packages/apps/tests/unit/architecture/test_pytest_import_mode_unit.py`:

```python
"""Pytest collection must use importlib mode for duplicate test basenames."""

from pathlib import Path


def test_pytest_addopts_enforces_importlib_import_mode() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text


def test_test_wrapper_enforces_importlib_import_mode() -> None:
    text = Path("scripts/test.py").read_text(encoding="utf-8")
    assert '"--import-mode=importlib"' in text
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_pytest_import_mode_unit.py -q --no-cov
```

Expected: FAIL because neither guard exists yet.

**Step 2: GREEN - Make import mode explicit**

Modify `pyproject.toml`:

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["packages/*/tests"]
python_files = ["test_*.py"]
```

Remove the ineffective line:

```toml
importmode = "importlib"
```

Add import mode to `addopts`:

```toml
addopts = [
    "-ra",
    "-v",
    "--import-mode=importlib",
    "-n", "auto",
    "--dist", "loadfile",
    ...
]
```

Modify `scripts/test.py` base command:

```python
cmd = ["pytest", "-v", "--import-mode=importlib"]
```

**Step 3: Verify duplicate-basename reproduction**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/quality/test_models_unit.py packages/risk/tests/unit/test_models_unit.py -q --no-cov
```

Expected:

```text
12 passed
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_pytest_import_mode_unit.py -q --no-cov
```

Expected: PASS.

**Step 4: Verify the previously failing gate segment**

Run:

```bash
pixi run -e dev test --fast
```

Expected: all fast tests collect and run; no `import file mismatch`.

**Step 5: Commit**

```bash
git add pyproject.toml scripts/test.py packages/apps/tests/unit/architecture/test_pytest_import_mode_unit.py
git commit -m "test: enforce pytest importlib collection mode"
```

---

## Task 2: Close Data Storage Exact Barrel and OnDuplicate Re-Export Debt

**Files:**
- Modify: `.importlinter`
- Modify: `packages/data/src/ditto_data/models/common.py`
- Modify: `packages/data/src/ditto_data/models/__init__.py`
- Modify: `packages/data/src/ditto_data/storage/market/stock/status/status_writer.py`
- Modify: any additional `rg` consumers
- Modify: `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`
- Create: `packages/apps/tests/unit/architecture/test_data_storage_boundary_unit.py`

**Problem:**

`ditto_data.storage` is forbidden from importing `ditto_data.models.**`, but exact `ditto_data.models` still bypasses the contract. `status_writer.py` imports `OnDuplicate` from `ditto_data.models`, and `ditto_data.models.common` re-exports platform-owned `OnDuplicate`.

**Step 1: RED - Add exact data storage barrel test**

Create `packages/apps/tests/unit/architecture/test_data_storage_boundary_unit.py`:

```python
"""Data storage must not import data model barrels."""

from pathlib import Path


def test_data_storage_does_not_import_data_model_barrel() -> None:
    offenders: list[str] = []
    for path in Path("packages/data/src/ditto_data/storage").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "from ditto_data.models import" in text or "import ditto_data.models" in text:
            offenders.append(path.as_posix())
    assert offenders == [], "\n".join(offenders)
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_data_storage_boundary_unit.py -q --no-cov
```

Expected: FAIL with `packages/data/src/ditto_data/storage/market/stock/status/status_writer.py`.

**Step 2: RED - Extend canonical import guard**

Update `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`:

```python
FORBIDDEN_IMPORTS = (
    "from ditto_data.models.publication_safety import",
    "from ditto_data.models.storage import WriteResult",
    "from ditto_data.models.storage import WriteStoreResult",
    "from ditto_data.models import OnDuplicate",
    "from ditto_data.models.common import OnDuplicate",
    "from ditto_data.errors import Derived",
)
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q --no-cov
```

Expected: FAIL until OnDuplicate re-export consumers move.

**Step 3: Replace OnDuplicate imports**

Locate consumers:

```bash
rg -n "OnDuplicate" packages -g '*.py'
rg -n "from ditto_data.models import .*OnDuplicate|from ditto_data.models.common import OnDuplicate" packages -g '*.py'
```

Replace:

```python
from ditto_data.models import OnDuplicate
from ditto_data.models.common import OnDuplicate
```

with:

```python
from ditto_platform.foundation.storage.types import OnDuplicate
```

Required known change:

```python
# packages/data/src/ditto_data/storage/market/stock/status/status_writer.py
from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult
```

**Step 4: Remove the re-export from data models**

Modify `packages/data/src/ditto_data/models/common.py`:

- Remove the `from ditto_platform.foundation.storage.types import OnDuplicate` import.
- Remove `"OnDuplicate"` from `__all__`.
- Remove the "Store enum" comment.

Modify `packages/data/src/ditto_data/models/__init__.py`:

- Stop importing `OnDuplicate`.
- Remove `"OnDuplicate"` from `__all__`.

**Step 5: Tighten import-linter**

In `.importlinter`, update `data-storage-no-model-import`:

```ini
forbidden_modules =
    ditto_data.models.**
    ditto_data.models
```

Keep still-valid data-domain model exceptions:

```ini
ignore_imports =
    ditto_data.storage.** -> ditto_data.models.metadata
    ditto_data.storage.** -> ditto_data.models.macro
    ditto_data.storage.** -> ditto_data.models.ingestion
    ditto_data.storage.** -> ditto_data.models.common
```

Do not add an ignore for exact `ditto_data.models`.

**Step 6: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_data_storage_boundary_unit.py packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q --no-cov
pixi run -e dev pytest packages/data/tests/unit -q --no-cov
pixi run -e dev arch-check
pixi run -e dev type
```

Expected: no `ditto_data.models` exact imports from storage, arch-check kept.

**Step 7: Commit**

```bash
git add .importlinter packages/data packages/apps/tests/unit/architecture
git commit -m "refactor: remove data model barrel usage from storage"
```

---

## Task 3: Remove Remaining Data Storage Re-Exports of Platform Types

**Files:**
- Modify: `packages/data/src/ditto_data/storage/__init__.py`
- Modify: `packages/data/src/ditto_data/storage/base/__init__.py`
- Modify: `packages/data/src/ditto_data/storage/base/dataset_reader.py`
- Modify: `packages/data/src/ditto_data/storage/base/dataset_writer.py`
- Delete: `packages/data/src/ditto_data/storage/base/parquet_store.py`
- Delete: `packages/data/src/ditto_data/storage/base/protocols.py`
- Delete: `packages/data/src/ditto_data/storage/base/partition_strategy.py`
- Modify: all production and test consumers found by `rg`
- Modify: `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`

**Problem:**

`ditto_data.storage.base` still re-exports `ParquetStore`, `MergeResult`, `PartitionStrategy`, `YearlyPartition`, `DatasetReader`, `DatasetWriter`, `SqliteReader`, and `SqliteWriter` from platform. This violates the final rule that cross-package shared technical types must be imported from `ditto_platform`.

**Step 1: RED - Add forbidden storage re-export import patterns**

Update `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`:

```python
FORBIDDEN_IMPORTS = (
    ...
    "from ditto_data.storage.base import ParquetStore",
    "from ditto_data.storage.base import MergeResult",
    "from ditto_data.storage.base import PartitionStrategy",
    "from ditto_data.storage.base import YearlyPartition",
    "from ditto_data.storage.base import DatasetReader",
    "from ditto_data.storage.base import DatasetWriter",
    "from ditto_data.storage.base.parquet_store import",
    "from ditto_data.storage.base.protocols import",
    "from ditto_data.storage.base.partition_strategy import",
)
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q --no-cov
```

Expected: FAIL with current data storage consumers.

**Step 2: Replace production imports**

Locate:

```bash
rg -n "from ditto_data.storage.base import|from ditto_data.storage.base.(parquet_store|protocols|partition_strategy) import" packages -g '*.py'
```

Replace:

```python
from ditto_data.storage.base import ParquetStore
from ditto_data.storage.base import PartitionStrategy, YearlyPartition
from ditto_data.storage.base.parquet_store import ParquetStore
from ditto_data.storage.base.protocols import DatasetReader, DatasetWriter
from ditto_data.storage.base.partition_strategy import YearlyPartition
```

with canonical imports:

```python
from ditto_platform.foundation.storage import (
    MergeResult,
    ParquetStore,
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.protocols import (
    DatasetReader,
    DatasetWriter,
    SqliteReader,
    SqliteWriter,
)
```

Keep data-owned imports local:

```python
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_data.storage.base.sqlite_store import SQLiteStore
```

**Step 3: Shrink data storage barrels**

Modify `packages/data/src/ditto_data/storage/base/__init__.py` to export only data-owned types:

```python
"""Data-owned storage base helpers."""

from ditto_data.storage.base.dataset_reader import ParquetDatasetReader
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_data.storage.base.sqlite_store import SQLiteStore

__all__ = [
    "ParquetDatasetReader",
    "ParquetDatasetWriter",
    "SQLiteStore",
]
```

Modify `packages/data/src/ditto_data/storage/__init__.py` to stop exporting platform types. Export only data-owned storage helpers or leave it minimal.

Delete:

```text
packages/data/src/ditto_data/storage/base/parquet_store.py
packages/data/src/ditto_data/storage/base/protocols.py
packages/data/src/ditto_data/storage/base/partition_strategy.py
```

**Step 4: Verify deletion and imports**

Run:

```bash
test ! -f packages/data/src/ditto_data/storage/base/parquet_store.py
test ! -f packages/data/src/ditto_data/storage/base/protocols.py
test ! -f packages/data/src/ditto_data/storage/base/partition_strategy.py
rg -n "from ditto_data.storage.base import (ParquetStore|MergeResult|PartitionStrategy|YearlyPartition|DatasetReader|DatasetWriter)|from ditto_data.storage.base.(parquet_store|protocols|partition_strategy) import" packages -g '*.py'
```

Expected: `test` commands exit 0 and `rg` returns no matches.

**Step 5: Verify tests**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q --no-cov
pixi run -e dev pytest packages/data/tests/unit/storage -q --no-cov
pixi run -e dev arch-check
pixi run -e dev type
```

**Step 6: Commit**

```bash
git add packages/data packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py
git commit -m "refactor: remove platform storage reexports from data"
```

---

## Task 4: Tighten Apps Exact Barrel Isolation

**Files:**
- Modify: `.importlinter`
- Modify: `packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py`

**Problem:**

Apps boundary now forbids exact `ditto_data.models`, but other forbidden data barrels are still only covered through `**`: `ditto_data.services`, `ditto_data.errors`, `ditto_data.quality`, and `ditto_data.config`.

**Step 1: RED - Extend apps boundary test**

Modify `packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py`:

```python
FORBIDDEN_NON_REGISTRY_IMPORTS = (
    "from ditto_data.models",
    "import ditto_data.models",
    "from ditto_data.services",
    "import ditto_data.services",
    "from ditto_data.errors",
    "import ditto_data.errors",
    "from ditto_data.quality",
    "import ditto_data.quality",
    "from ditto_data.config",
    "import ditto_data.config",
)


def test_apps_non_registry_code_does_not_import_forbidden_data_barrels() -> None:
    offenders: list[str] = []
    for path in Path("packages/apps/src/ditto_apps").rglob("*.py"):
        rel = path.as_posix()
        if "/registry/" in rel or rel.endswith("/jobs/context.py"):
            continue
        source = path.read_text(encoding="utf-8")
        if any(pattern in source for pattern in FORBIDDEN_NON_REGISTRY_IMPORTS):
            offenders.append(rel)
    assert offenders == [], "\n".join(offenders)
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py -q --no-cov
```

Expected: PASS if current source is clean; this is a guard-hardening test.

**Step 2: Tighten import-linter exact barrels**

Modify `.importlinter` `apps-service-isolation`:

```ini
forbidden_modules =
    ditto_data.services.**
    ditto_data.services
    ditto_data.models.**
    ditto_data.models
    ditto_data.errors.**
    ditto_data.errors
    ditto_data.quality.**
    ditto_data.quality
    ditto_data.config.**
    ditto_data.config
```

Extend registry exact exceptions as needed:

```ini
ignore_imports =
    ditto_apps.registry.** -> ditto_data.services
    ditto_apps.registry.** -> ditto_data.services.**
    ditto_apps.registry.** -> ditto_data.quality
    ditto_apps.registry.** -> ditto_data.quality.**
    ditto_apps.registry.** -> ditto_data.config
    ditto_apps.registry.** -> ditto_data.config.**
    ditto_apps.jobs.context -> ditto_data.quality
    ditto_apps.jobs.context -> ditto_data.quality.protocols
```

Do not allow `ditto_data.models` for apps.

**Step 3: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py -q --no-cov
pixi run -e dev arch-check
```

Expected: import-linter kept, no unmatched ignore warnings.

**Step 4: Commit**

```bash
git add .importlinter packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py
git commit -m "test: tighten apps exact data barrel isolation"
```

---

## Task 5: Make Domain Error Hierarchies Real at Public Boundaries

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/alpha/validation.py`
- Modify: selected `packages/strategy/src/ditto_strategy/alpha/templates/*.py`
- Modify: `packages/execution/src/ditto_execution/brokerage.py`
- Modify: selected `packages/execution/src/ditto_execution/storage/sqlite/legacy/_sql.py`
- Modify: `packages/features/src/ditto_features/storage/parquet/factors/factor_writer.py`
- Modify: `packages/features/src/ditto_features/storage/parquet/features/technical/technical_indicator_writer.py`
- Modify: `packages/features/src/ditto_features/storage/sqlite/derived/writer.py`
- Modify: selected `packages/features/src/ditto_features/services/derived/queries.py`
- Modify/Create: package-specific error tests

**Problem:**

`StrategySpecError`, `OrderSubmitError`, `FillProcessingError`, `FeatureStorageError`, and related classes exist, but production code barely raises them. The hierarchy is mostly declarative, not operational.

**Important constraints:**

- Keep internal value-object invariants as `ValueError` where Python convention and existing tests expect it.
- Change public boundary validators, service facades, and storage adapters.
- Do not blanket-replace every `ValueError`.

**Step 1: RED - Strategy boundary tests**

Create or update `packages/strategy/tests/unit/test_strategy_boundary_errors_unit.py`:

```python
import pytest

from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec
from ditto_strategy.alpha.validation import validate_spec_params
from ditto_strategy.errors import StrategySpecError


def test_validate_spec_params_raises_strategy_spec_error_for_missing_param() -> None:
    spec = StrategySpec(
        name="momentum",
        params={},
        param_constraints=(ParamConstraint(name="lookback", dtype="int"),),
    )

    with pytest.raises(StrategySpecError) as exc_info:
        validate_spec_params(spec)

    assert exc_info.value.details["param_name"] == "lookback"
```

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit/test_strategy_boundary_errors_unit.py -q --no-cov
```

Expected: FAIL while `validate_spec_params` raises `ValueError`.

**Step 2: GREEN - Strategy boundary implementation**

Modify `packages/strategy/src/ditto_strategy/alpha/validation.py`:

```python
from ditto_strategy.errors import StrategySpecError


def _spec_error(message: str, *, param_name: str, reason: str) -> StrategySpecError:
    return StrategySpecError(message, param_name=param_name, reason=reason)
```

Replace boundary validation raises with `StrategySpecError`, including missing param, wrong dtype, unsupported enum, min/max failures.

Leave `StrategySpec.__post_init__` dataclass invariants as `ValueError` unless a public test proves the caller boundary should classify them.

**Step 3: RED - Execution boundary tests**

Create or update `packages/execution/tests/unit/test_execution_boundary_errors_unit.py`:

```python
from ditto_execution.errors import FillProcessingError


def test_brokerage_uses_fill_processing_error_for_fill_contract_violation() -> None:
    text = Path("packages/execution/src/ditto_execution/brokerage.py").read_text(
        encoding="utf-8"
    )
    assert "raise FillProcessingError(" in text
```

Use a behavioral test if an existing brokerage fixture can trigger mismatched fill quantities cheaply. Otherwise keep this source guard and record a concrete follow-up to replace it with a behavioral test when the fixture is simplified.

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/test_execution_boundary_errors_unit.py -q --no-cov
```

Expected: FAIL while brokerage raises generic `ExecutionError`.

**Step 4: GREEN - Execution boundary implementation**

Modify `packages/execution/src/ditto_execution/brokerage.py`:

```python
from ditto_execution.errors import FillProcessingError
```

Replace:

```python
raise ExecutionError(...)
```

with:

```python
raise FillProcessingError(
    "...",
    order_id=order.order_id,
    model_quantity=model_qty,
    leaves_quantity=fill_qty,
)
```

Inspect `packages/execution/src/ditto_execution/storage/sqlite/legacy/_sql.py`. If invalid order/fill/audit table operations cross a public adapter boundary, map them to `ReconciliationError` or `AuditError`; otherwise leave local SQL guard `ValueError`.

**Step 5: RED - Features storage/query boundary tests**

Create or update `packages/features/tests/unit/test_features_boundary_errors_unit.py`:

```python
from pathlib import Path


def test_feature_storage_adapters_raise_feature_storage_error() -> None:
    paths = [
        Path("packages/features/src/ditto_features/storage/parquet/factors/factor_writer.py"),
        Path("packages/features/src/ditto_features/storage/parquet/features/technical/technical_indicator_writer.py"),
        Path("packages/features/src/ditto_features/storage/sqlite/derived/writer.py"),
    ]
    offenders = [
        path.as_posix()
        for path in paths
        if "FeatureStorageError" not in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
```

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/test_features_boundary_errors_unit.py -q --no-cov
```

Expected: FAIL until adapters use domain errors.

**Step 6: GREEN - Features boundary implementation**

For duplicate/unknown storage strategy failures in:

- `packages/features/src/ditto_features/storage/parquet/factors/factor_writer.py`
- `packages/features/src/ditto_features/storage/parquet/features/technical/technical_indicator_writer.py`
- `packages/features/src/ditto_features/storage/sqlite/derived/writer.py`

Import and raise:

```python
from ditto_features.errors import FeatureStorageError
```

Use details:

```python
raise FeatureStorageError(
    msg,
    path=str(path) if available else "",
    on_duplicate=str(on_duplicate),
)
```

For public query DTO validation in `services/derived/queries.py`, use `FactorValidationError` only where invalid user query contracts cross the service boundary. Keep small private tuple coercion helpers as `ValueError` if they are internal and all callers translate them.

**Step 7: Verify no hierarchy is purely decorative**

Run:

```bash
rg -n "raise (StrategySpecError|SignalGenerationError|PipelineExecutionError|TemplateNotFoundError|OrderSubmitError|OrderStateError|FillProcessingError|ReconciliationError|AuditError|MaterializationError|EvaluationError|FactorValidationError|FeatureStorageError)" packages/strategy/src packages/execution/src packages/features/src -g '*.py'
```

Expected: at least one real production raise for the domain-specific errors that represent current public boundaries:

```text
StrategySpecError
FillProcessingError
FeatureStorageError
```

Other subclasses may remain future-facing only if no current boundary exists, but tests must document that choice.

**Step 8: Verify**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit packages/execution/tests/unit packages/features/tests/unit -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 9: Commit**

```bash
git add packages/strategy packages/execution packages/features
git commit -m "refactor: use domain errors at public capability boundaries"
```

---

## Task 6: Finish Active Documentation Cleanup and Guard Coverage

**Files:**
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify: `packages/apps/README.md`
- Modify: `packages/kernel/CLAUDE.md`
- Modify: `packages/platform/CLAUDE.md`
- Modify: any other active docs found by `rg`
- Modify: `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py`

**Problem:**

Active package docs still contain old terms. Current stale checker misses generic `interfaces/` and naked `analytics` in active package docs.

**Step 1: RED - Extend stale package reference guard**

Update `scripts/architecture/check_architecture_smells.py`:

```python
STALE_ACTIVE_PACKAGE_REFERENCES = (
    "ditto_app.",
    "ditto_analytics",
    "ditto_engine",
    "ditto_interfaces",
    "ditto_infra",
    "packages/app/",
    "packages/analytics",
    "packages/engine",
    "packages/infra",
    "interfaces/",
    "interfaces/tests",
    "interfaces/src",
    "apps → analytics",
    "analytics →",
    "→ analytics",
    "Analytics",
)
```

Update `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py` to assert the new stale patterns are covered:

```python
assert "interfaces/" in STALE_PKG_REFS
assert "apps → analytics" in STALE_PKG_REFS
assert "Analytics" in STALE_PKG_REFS
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py -q --no-cov
pixi run -e dev arch-check
```

Expected: test passes, `arch-check` fails until docs are cleaned.

**Step 2: Clean apps README**

Modify `packages/apps/README.md`:

```text
interfaces/ -> packages/apps/
apps → analytics ✅ -> apps → analysis ✅
```

Update changelog wording:

```text
包名从旧入口包重命名为 `ditto-apps`
```

Do not leave `ditto-interfaces` in active package README.

**Step 3: Clean kernel/platform CLAUDE docs**

Run:

```bash
rg -n "Analytics|analytics|interfaces/|ditto-interfaces|packages/infra|ditto_infra|ditto_analytics|ditto_interfaces" packages/*/CLAUDE.md packages/*/README.md -g '*.md'
```

Expected before cleanup: hits in `packages/kernel/CLAUDE.md`, `packages/platform/CLAUDE.md`, and `packages/apps/README.md`.

Replace:

```text
Analytics -> Features / Analysis by context
analytics -> features / analysis by context
```

Examples:

```text
CalendarId consumers: Features, Analysis
platform allowed consumers: data/features/analysis/application/apps
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py -q --no-cov
pixi run -e dev arch-check
rg -n "interfaces/|ditto-interfaces|apps → analytics|Analytics|ditto_analytics|packages/analytics" packages/*/CLAUDE.md packages/*/README.md -g '*.md'
```

Expected: no matches from final `rg`, except if the match is inside the guard test itself. If guard tests match, restrict `rg` to docs only as shown.

**Step 5: Commit**

```bash
git add scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py packages/*/CLAUDE.md packages/*/README.md
git commit -m "docs: remove stale capability package references"
```

---

## Task 7: Track or Retire Plan Documents

**Files:**
- Add or remove: `docs/plans/2026-05-04-capability-architecture-quality-remediation.md`
- Add: `docs/plans/2026-05-04-capability-architecture-final-completion-plan.md`

**Problem:**

The original quality remediation plan is currently untracked. A final architecture branch should not leave plan files floating outside git history.

**Step 1: Decide file status**

Run:

```bash
git status --short docs/plans/2026-05-04-capability-architecture-quality-remediation.md docs/plans/2026-05-04-capability-architecture-final-completion-plan.md
```

If both are useful, keep both:

- `quality-remediation`: original full remediation scope.
- `final-completion-plan`: remaining gap closure.

If the first is obsolete, remove it only with explicit user approval.

**Step 2: Verify plan files**

Run:

```bash
python - <<'PY'
from pathlib import Path

markers = ("TO" + "DO", "PLACE" + "HOLDER", "T" + "BD")
paths = (
    Path("docs/plans/2026-05-04-capability-architecture-quality-remediation.md"),
    Path("docs/plans/2026-05-04-capability-architecture-final-completion-plan.md"),
)
for path in paths:
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if any(marker in line for marker in markers):
            print(f"{path}:{line_no}:{line}")
PY
```

Expected: no vague placeholders or open-ended follow-up markers. If a follow-up is intentional, replace it with a concrete task.

**Step 3: Commit**

If keeping both:

```bash
git add docs/plans/2026-05-04-capability-architecture-quality-remediation.md docs/plans/2026-05-04-capability-architecture-final-completion-plan.md
git commit -m "docs: add final capability architecture completion plan"
```

If only keeping final plan:

```bash
git add docs/plans/2026-05-04-capability-architecture-final-completion-plan.md
git commit -m "docs: add final capability architecture completion plan"
```

---

## Task 8: Final Full Verification and Completion Evidence

**Files:**
- Modify only files required to fix verification failures.

**Step 1: Full check**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
ruff format . -> no changed files
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass except documented skips
import-linter -> 36 kept, 0 broken
architecture smell check passed
```

**Step 2: Architecture guard evidence**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

```text
Contracts: 36 kept, 0 broken.
Architecture smell check passed.
```

**Step 3: Source and docs grep evidence**

Run:

```bash
rg -n "from ditto_data.models import OnDuplicate|from ditto_data.models.common import OnDuplicate|from ditto_data.storage.base import (ParquetStore|MergeResult|PartitionStrategy|YearlyPartition|DatasetReader|DatasetWriter)|from ditto_data.storage.base.(parquet_store|protocols|partition_strategy) import" packages -g '*.py'
```

Expected: no matches.

Run:

```bash
rg -n "interfaces/|ditto-interfaces|apps → analytics|Analytics|ditto_analytics|packages/analytics" packages/*/CLAUDE.md packages/*/README.md -g '*.md'
```

Expected: no matches.

Run:

```bash
rg -n "from ditto_data.models import|import ditto_data.models" packages/data/src/ditto_data/storage packages/apps/src/ditto_apps -g '*.py'
```

Expected: no matches outside allowed registry patterns. Since data storage has no registry, it must have zero matches.

**Step 4: Package dependency graph snapshot**

Run:

```bash
python - <<'PY'
from __future__ import annotations
import ast
from pathlib import Path

roots = {
    "ditto_kernel": "kernel",
    "ditto_platform": "platform",
    "ditto_data": "data",
    "ditto_features": "features",
    "ditto_strategy": "strategy",
    "ditto_portfolio": "portfolio",
    "ditto_risk": "risk",
    "ditto_execution": "execution",
    "ditto_backtest": "backtest",
    "ditto_analysis": "analysis",
    "ditto_application": "application",
    "ditto_apps": "apps",
}
imports = {pkg: set() for pkg in roots.values()}
for pkg in roots.values():
    src = Path("packages") / pkg / "src"
    for path in src.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for mod in mods:
                dst = roots.get(mod.split(".")[0])
                if dst and dst != pkg:
                    imports[pkg].add(dst)
for pkg, deps in sorted(imports.items()):
    print(f"{pkg}: {', '.join(sorted(deps)) or '-'}")
PY
```

Expected final graph:

```text
analysis: kernel, platform
application: analysis, backtest, data, execution, features, kernel, platform, portfolio, risk, strategy
apps: analysis, application, data, execution, features, kernel, platform, strategy
backtest: data, execution, kernel, portfolio, risk, strategy
data: kernel, platform
execution: kernel, platform, portfolio
features: kernel, platform
kernel: -
platform: kernel
portfolio: kernel
risk: kernel, portfolio
strategy: kernel, platform
```

**Step 5: Final status**

Run:

```bash
git status --short
```

Expected: clean worktree.

**Step 6: Commit final verification fixes**

Only if Step 1-5 required additional changes:

```bash
git add -A
git commit -m "test: complete capability architecture remediation verification"
```

---

## Recommended Task Order

```text
Task 0 baseline
  -> Task 1 fix pytest import mode
  -> Task 2 close data storage exact barrel + OnDuplicate
  -> Task 3 remove data storage platform re-exports
  -> Task 4 tighten apps exact barrels
  -> Task 5 make domain errors operational
  -> Task 6 finish docs and stale guards
  -> Task 7 track/retire plan docs
  -> Task 8 final verification
```

Task 2 and Task 4 are related but should stay separate: Task 2 fixes data internal boundaries, Task 4 fixes apps boundary hardening. Task 5 can run after Task 1, but doing it after re-export cleanup reduces noisy type/import churn.

## Completion Criteria

- Full command `pixi run -e dev check` passes freshly.
- Full command `pixi run -e dev arch-check` passes freshly.
- No pytest collection errors with duplicate test basenames.
- `ditto_data.models` no longer re-exports platform-owned `OnDuplicate`.
- `ditto_data.storage.base` no longer re-exports platform storage types.
- Public domain boundary code raises specific domain errors where the current implementation has concrete boundary failures.
- Active package docs no longer carry old package names or old layer names.
- Worktree is clean except user-approved unrelated files.
