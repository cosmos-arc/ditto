# Capability Package Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Ditto 从当前 `infra/data/analytics/engine/app/interfaces` 抽象平面重构为 `kernel/platform/data/features/strategy/portfolio/risk/execution/backtest/analysis/application/apps` 能力包架构。

**Architecture:** 采用多 package monorepo。每个能力包拥有自己的模型、契约、存储实现、测试和 pyproject 依赖声明；`application` 编排所有能力包；`apps` 作为入口和 composition root。迁移过程中每个阶段必须保持 `lint/type/test-fast/arch-check` 通过，最终删除旧包与临时兼容层。

**Tech Stack:** Python 3.13, pixi, setuptools editable packages, ruff, basedpyright, pytest, import-linter, polars, FastAPI, Dishka, loguru/OpenTelemetry。

---

## Execution Rules

1. 每个 task 单独提交，提交前至少运行 task 内指定验证命令。
2. 不引入长期 backward compatibility；如果某一步必须用临时 shim，必须在同一 phase 的清理 task 删除。
3. 不用 `TYPE_CHECKING` 延迟导入解决循环依赖；发现循环依赖时重构契约归属。
4. 所有批量移动使用 `git mv` 保留历史；手写修改使用 `apply_patch`。
5. 每次改 import 先用 `rg` 定位引用，再改，再跑 `pixi run -e dev type` 和 `pixi run -e dev arch-check`。
6. 当前未跟踪文件 `docs/plans/2026-04-29-modular-quant-platform-architecture-design.md` 不属于本计划，执行时不要误提交。

## Target Package Names

| Current | Target package | Target import root |
|---|---|---|
| `packages/infra` | `packages/platform` | `ditto_platform` |
| `interfaces` | `packages/apps` | `ditto_apps` |
| `packages/app` | `packages/application` | `ditto_application` |
| `packages/analytics` | `packages/features` + `packages/analysis` | `ditto_features`, `ditto_analysis` |
| `packages/engine/src/ditto_engine/alpha` | `packages/strategy` | `ditto_strategy` |
| `packages/engine/src/ditto_engine/portfolio` + `accounting` | `packages/portfolio` | `ditto_portfolio` |
| `packages/engine/src/ditto_engine/risk` | `packages/risk` | `ditto_risk` |
| `packages/engine/src/ditto_engine/execution` | `packages/execution` | `ditto_execution` |
| `packages/engine/src/ditto_engine/backtest` | `packages/backtest` | `ditto_backtest` |
| `packages/kernel` | unchanged | `ditto_kernel` |
| `packages/data` | slimmed | `ditto_data` |

## Global Verification Commands

Use the smallest command while developing, then the full gate before final cleanup.

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
pixi run -e dev check
```

Expected final output:

```text
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all non-skipped tests pass
import-linter -> all contracts kept, 0 broken
architecture smell check passed
```

---

### Task 0: Prepare Isolated Refactor Worktree

**Files:**
- Read: `docs/plans/2026-04-29-capability-package-architecture-design.md`
- Read: `CLAUDE.md`
- Read: `.importlinter`
- Read: `pixi.toml`
- Read: `pyproject.toml`

**Step 1: Create the worktree**

Run from `/home/chevy/projects/ditto`:

```bash
git status --short
git worktree add ../ditto-capability-packages -b refactor/capability-packages
cd ../ditto-capability-packages
```

Expected: clean or only explicitly accepted unrelated untracked docs. If `git worktree add` fails because the branch already exists, use a new branch name such as `refactor/capability-packages-2`.

**Step 2: Verify baseline**

Run:

```bash
pixi run -e dev check
```

Expected: current baseline passes before touching architecture.

**Step 3: Commit checkpoint if needed**

No commit is needed if no files changed.

---

### Task 1: Add Capability Package Skeletons

**Files:**
- Create: `packages/features/pyproject.toml`
- Create: `packages/features/src/ditto_features/__init__.py`
- Create: `packages/features/src/ditto_features/py.typed`
- Create: `packages/features/tests/unit/test_import_unit.py`
- Create: `packages/analysis/pyproject.toml`
- Create: `packages/analysis/src/ditto_analysis/__init__.py`
- Create: `packages/analysis/src/ditto_analysis/py.typed`
- Create: `packages/analysis/tests/unit/test_import_unit.py`
- Create: `packages/strategy/pyproject.toml`
- Create: `packages/strategy/src/ditto_strategy/__init__.py`
- Create: `packages/strategy/src/ditto_strategy/py.typed`
- Create: `packages/strategy/tests/unit/test_import_unit.py`
- Create: `packages/portfolio/pyproject.toml`
- Create: `packages/portfolio/src/ditto_portfolio/__init__.py`
- Create: `packages/portfolio/src/ditto_portfolio/py.typed`
- Create: `packages/portfolio/tests/unit/test_import_unit.py`
- Create: `packages/risk/pyproject.toml`
- Create: `packages/risk/src/ditto_risk/__init__.py`
- Create: `packages/risk/src/ditto_risk/py.typed`
- Create: `packages/risk/tests/unit/test_import_unit.py`
- Create: `packages/execution/pyproject.toml`
- Create: `packages/execution/src/ditto_execution/__init__.py`
- Create: `packages/execution/src/ditto_execution/py.typed`
- Create: `packages/execution/tests/unit/test_import_unit.py`
- Create: `packages/backtest/pyproject.toml`
- Create: `packages/backtest/src/ditto_backtest/__init__.py`
- Create: `packages/backtest/src/ditto_backtest/py.typed`
- Create: `packages/backtest/tests/unit/test_import_unit.py`
- Modify: `pixi.toml`
- Modify: `pyproject.toml`

**Step 1: Write skeleton import tests**

Example for `packages/features/tests/unit/test_import_unit.py`:

```python
def test_import_ditto_features() -> None:
    import ditto_features

    assert ditto_features.__version__ == "0.1.0"
```

Repeat the same pattern for `ditto_analysis`, `ditto_strategy`, `ditto_portfolio`, `ditto_risk`, `ditto_execution`, and `ditto_backtest`.

**Step 2: Run one test to verify it fails**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/test_import_unit.py -q
```

Expected: FAIL because `ditto_features` does not exist yet.

**Step 3: Create minimal package modules**

Each `__init__.py` should contain:

```python
"""Ditto <capability> package."""

__version__ = "0.1.0"
```

Each `py.typed` is an empty marker file.

**Step 4: Create pyproject files**

Use this template, changing name and dependencies by capability:

```toml
[project]
name = "ditto-features"
requires-python = ">= 3.13"
version = "0.1.0"
dependencies = [
    "ditto-kernel",
    "ditto-data",
    "polars",
    "numpy",
    "cachebox",
    "orjson",
]

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"
```

Initial dependency targets:

```text
ditto-features: ditto-kernel, ditto-data, polars, numpy, cachebox, orjson
ditto-analysis: ditto-kernel, ditto-data, ditto-features, polars, numpy, orjson
ditto-strategy: ditto-kernel, ditto-data, ditto-features, polars, orjson
ditto-portfolio: ditto-kernel, ditto-data, ditto-strategy, polars, orjson
ditto-risk: ditto-kernel, ditto-portfolio, ditto-strategy, polars, orjson
ditto-execution: ditto-kernel, ditto-portfolio, ditto-risk, orjson
ditto-backtest: ditto-kernel, ditto-data, ditto-strategy, ditto-portfolio, ditto-risk, ditto-execution, polars, numpy, orjson
```

**Step 5: Register editable packages**

Modify `pixi.toml` `[pypi-dependencies]`:

```toml
ditto-features = { path = "packages/features", editable = true }
ditto-analysis = { path = "packages/analysis", editable = true }
ditto-strategy = { path = "packages/strategy", editable = true }
ditto-portfolio = { path = "packages/portfolio", editable = true }
ditto-risk = { path = "packages/risk", editable = true }
ditto-execution = { path = "packages/execution", editable = true }
ditto-backtest = { path = "packages/backtest", editable = true }
```

Modify `pyproject.toml` `extraPaths` and `pythonpath`:

```toml
"packages/features/src",
"packages/analysis/src",
"packages/strategy/src",
"packages/portfolio/src",
"packages/risk/src",
"packages/execution/src",
"packages/backtest/src",
```

**Step 6: Verify skeletons**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/test_import_unit.py packages/backtest/tests/unit/test_import_unit.py -q
pixi run -e dev type
```

Expected: all new import tests pass, type check reports 0 errors.

**Step 7: Commit**

```bash
git add packages/features packages/analysis packages/strategy packages/portfolio packages/risk packages/execution packages/backtest pixi.toml pyproject.toml
git commit -m "chore: add capability package skeletons"
```

---

### Task 2: Rename Infra to Platform

**Files:**
- Move: `packages/infra/` -> `packages/platform/`
- Move: `packages/platform/src/ditto_infra/` -> `packages/platform/src/ditto_platform/`
- Modify: `packages/platform/pyproject.toml`
- Modify: `pixi.toml`
- Modify: `pyproject.toml`
- Modify: `.importlinter`
- Modify: `packages/platform/CLAUDE.md`
- Modify imports matching `ditto_infra` across `packages/`, `interfaces/`, `typings/`, and `docs/architecture/`

**Step 1: Move package directories**

Run:

```bash
git mv packages/infra packages/platform
git mv packages/platform/src/ditto_infra packages/platform/src/ditto_platform
```

Expected: git records a rename, not delete/add noise.

**Step 2: Update package metadata**

In `packages/platform/pyproject.toml`:

```toml
[project]
name = "ditto-platform"
```

In `pixi.toml`, replace:

```toml
ditto-infra = { path = "packages/infra", editable = true }
```

with:

```toml
ditto-platform = { path = "packages/platform", editable = true }
```

In `pyproject.toml`, replace `packages/infra/src` with `packages/platform/src`.

**Step 3: Rewrite imports**

Run:

```bash
rg -n "ditto_infra|ditto-infra|packages/infra" .
```

Replace source imports:

```python
from ditto_infra.foundation import get_logger
```

with:

```python
from ditto_platform.foundation import get_logger
```

Keep docs references updated only when they describe current architecture. Historical archive docs can stay if explicitly historical.

**Step 4: Update import-linter**

In `.importlinter`:

```text
ditto_infra -> ditto_platform
Infra -> Platform
packages/infra -> packages/platform
```

Rename contract `foundation-isolation` to `platform-isolation`.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: platform tests pass; type and arch checks pass.

**Step 6: Commit**

```bash
git add packages/platform pixi.toml pyproject.toml .importlinter docs/architecture CLAUDE.md
git commit -m "refactor: rename infra package to platform"
```

---

### Task 3: Rename Interfaces to Apps ✅ DONE (baec3ff7)

**Files:**
- Move: `interfaces/` -> `packages/apps/`
- Move: `packages/apps/src/ditto_interfaces/` -> `packages/apps/src/ditto_apps/`
- Modify: `packages/apps/pyproject.toml`
- Modify: `pixi.toml`
- Modify: `pyproject.toml`
- Modify: `.importlinter`
- Modify: `packages/apps/CLAUDE.md`
- Modify: `deploy/docker/Dockerfile`
- Modify: `deploy/docker/docker-compose.yml`
- Modify: `pixi.toml` tasks `dev` and `server`
- Modify imports matching `ditto_interfaces`

**Step 1: Move package**

Run:

```bash
git mv interfaces packages/apps
git mv packages/apps/src/ditto_interfaces packages/apps/src/ditto_apps
```

Expected: tests move under `packages/apps/tests`.

**Step 2: Update package metadata**

In `packages/apps/pyproject.toml`:

```toml
[project]
name = "ditto-apps"
```

In `pixi.toml`:

```toml
ditto-apps = { path = "packages/apps", editable = true }
```

Remove `ditto-interfaces`.

In `pixi.toml` tasks:

```toml
dev = "granian ditto_apps.main:app --interface asgi --reload --host 0.0.0.0 --port 8000"
server = "granian ditto_apps.main:app --interface asgi --host 0.0.0.0 --port 8000 --workers 4"
```

In `pyproject.toml`, replace `interfaces/src` with `packages/apps/src`, and replace test/cov roots:

```toml
testpaths = ["packages/*/tests"]
pythonpath = [
    ...
    "packages/apps/src",
]
source = ["packages"]
```

**Step 3: Rewrite imports**

Run:

```bash
rg -n "ditto_interfaces|interfaces/tests|interfaces/src|interfaces/" .
```

Replace source imports:

```python
from ditto_interfaces.main import app
```

with:

```python
from ditto_apps.main import app
```

**Step 4: Update import-linter**

Replace root package and forbidden references:

```text
ditto_interfaces -> ditto_apps
Interfaces -> Apps
```

Contracts should keep the same semantics: apps can depend on application/platform/kernel and composition-root-specific internals only where explicitly allowed.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: apps tests pass; no stale `ditto_interfaces` imports.

**Step 6: Commit**

```bash
git add packages/apps pixi.toml pyproject.toml .importlinter deploy docs CLAUDE.md
git commit -m "refactor: rename interfaces package to apps"
```

---

### Task 4: Rename App to Application ✅ DONE

**Files:**
- Move: `packages/app/` -> `packages/application/`
- Move: `packages/application/src/ditto_app/` -> `packages/application/src/ditto_application/`
- Modify: `packages/application/pyproject.toml`
- Modify: `pixi.toml`
- Modify: `pyproject.toml`
- Modify: `.importlinter`
- Modify imports matching `ditto_app`
- Modify: `packages/apps/src/ditto_apps/registry/**`

**Step 1: Move package**

Run:

```bash
git mv packages/app packages/application
git mv packages/application/src/ditto_app packages/application/src/ditto_application
```

**Step 2: Update package metadata**

In `packages/application/pyproject.toml`:

```toml
[project]
name = "ditto-application"
dependencies = [
    "ditto-kernel",
    "ditto-data",
    "ditto-engine",
    "ditto-analytics",
    "ditto-platform",
]
```

This dependency list is temporary. Later tasks replace `ditto-engine` and `ditto-analytics` with capability packages.

In `pixi.toml`:

```toml
ditto-application = { path = "packages/application", editable = true }
```

Remove `ditto-app`.

**Step 3: Rewrite imports**

Run:

```bash
rg -n "ditto_app|ditto-app|packages/app" .
```

Replace source imports:

```python
from ditto_app.query.market import MarketQueryFacade
```

with:

```python
from ditto_application.query.market import MarketQueryFacade
```

**Step 4: Update import-linter**

Replace:

```text
ditto_app -> ditto_application
App -> Application
```

Keep the existing R8 query/command/process/builder rules until Task 12 renames internal directories.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit -q
pixi run -e dev pytest packages/apps/tests/registry -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: application and apps registry tests pass.

**Step 6: Commit**

```bash
git add packages/application packages/apps pixi.toml pyproject.toml .importlinter docs CLAUDE.md
git commit -m "refactor: rename app package to application"
```

---

### Task 5: Split Analytics into Features and Analysis ✅ DONE

**Files:**
- Move: `packages/analytics/src/ditto_analytics/expression/` -> `packages/features/src/ditto_features/expression/`
- Move: `packages/analytics/src/ditto_analytics/factors/` -> `packages/features/src/ditto_features/factors/`
- Move: `packages/analytics/src/ditto_analytics/materialization/` -> `packages/features/src/ditto_features/materialization/`
- Move: `packages/analytics/src/ditto_analytics/evaluation/` -> `packages/features/src/ditto_features/evaluation/`
- Move: `packages/analytics/src/ditto_analytics/models/` -> `packages/features/src/ditto_features/models/`
- Move: `packages/analytics/src/ditto_analytics/compile_cache.py` -> `packages/features/src/ditto_features/compile_cache.py`
- Move: `packages/analytics/src/ditto_analytics/validation.py` -> `packages/features/src/ditto_features/validation.py`
- Move: `packages/analytics/src/ditto_analytics/publication_safety.py` -> `packages/features/src/ditto_features/publication_safety.py`
- Move: `packages/analytics/src/ditto_analytics/exceptions.py` -> `packages/features/src/ditto_features/errors.py`
- Move: `packages/analytics/src/ditto_analytics/research/` -> `packages/analysis/src/ditto_analysis/research/`
- Move tests under `packages/analytics/tests/unit/expression`, `factors`, `evaluation`, `models` -> `packages/features/tests/unit/`
- Create: `packages/analysis/src/ditto_analysis/reports/__init__.py`
- Create: `packages/analysis/src/ditto_analysis/diagnostics/__init__.py`
- Create: `packages/analysis/src/ditto_analysis/experiments/__init__.py`
- Create: `packages/analysis/src/ditto_analysis/screeners/__init__.py`
- Modify imports matching `ditto_analytics`
- Modify: `packages/features/pyproject.toml`
- Modify: `packages/analysis/pyproject.toml`
- Modify: `packages/application/pyproject.toml`
- Modify: `.importlinter`

**Step 1: Move feature code**

Use `git mv` for each path listed above.

Expected: `packages/analytics/src/ditto_analytics` is empty or only contains temporary files scheduled for deletion in this task.

**Step 2: Rewrite imports**

Run:

```bash
rg -n "ditto_analytics" packages tests pyproject.toml .importlinter
```

Rules:

```text
ditto_analytics.expression -> ditto_features.expression
ditto_analytics.factors -> ditto_features.factors
ditto_analytics.materialization -> ditto_features.materialization
ditto_analytics.evaluation -> ditto_features.evaluation
ditto_analytics.models -> ditto_features.models
ditto_analytics.research -> ditto_analysis.research
ditto_analytics.exceptions -> ditto_features.errors
```

**Step 3: Update pyproject dependencies**

In `packages/application/pyproject.toml`, replace `ditto-analytics` with:

```toml
"ditto-features",
"ditto-analysis",
```

In `pixi.toml`, keep `ditto-analytics` only until this task completes, then remove it after all imports are gone.

**Step 4: Update import-linter**

Add roots:

```text
ditto_features
ditto_analysis
```

Remove `ditto_analytics`.

Contracts:

```text
features must not depend on strategy/portfolio/risk/execution/backtest/analysis/application/apps
analysis must not be imported by data/features/strategy/portfolio/risk/execution/backtest
features.expression must not import features.materialization
```

**Step 5: Delete old package**

After `rg -n "ditto_analytics|ditto-analytics|packages/analytics"` returns only archive/history references, remove `packages/analytics` from editable deps, paths, and commitizen if present.

Run:

```bash
git rm -r packages/analytics
```

**Step 6: Verify**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit -q
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: no `ditto_analytics` source imports remain.

**Step 7: Commit**

```bash
git add packages/features packages/analysis packages/application pixi.toml pyproject.toml .importlinter docs CLAUDE.md
git commit -m "refactor: split analytics into features and analysis"
```

---

### Task 6: Extract Strategy from Engine Alpha ✅ DONE

> **临时状态说明**: strategy 暂时依赖 ditto-engine（portfolio allocation/constraints + execution constants）。
> 在 .importlinter layers 中暂时排除 ditto_strategy，待 Task 7-10 提取 portfolio/execution/backtest 后恢复。

**Files:**
- Move: `packages/engine/src/ditto_engine/alpha/` -> `packages/strategy/src/ditto_strategy/alpha/`
- Move: `packages/engine/tests/unit/alpha/` -> `packages/strategy/tests/unit/alpha/`
- Move: `packages/engine/tests/integration/alpha/` -> `packages/strategy/tests/integration/alpha/`
- Create: `packages/strategy/src/ditto_strategy/signals/__init__.py`
- Create: `packages/strategy/src/ditto_strategy/signals/models.py`
- Create: `packages/strategy/src/ditto_strategy/signals/store.py`
- Create: `packages/strategy/src/ditto_strategy/contracts.py`
- Create: `packages/strategy/src/ditto_strategy/errors.py`
- Modify imports matching `ditto_engine.alpha`
- Modify: `packages/strategy/pyproject.toml`
- Modify: `packages/backtest/pyproject.toml`
- Modify: `packages/application/pyproject.toml`
- Modify: `.importlinter`

**Step 1: Add failing signal contract tests**

Create `packages/strategy/tests/unit/signals/test_store_contract_unit.py`:

```python
from typing import Protocol

from ditto_strategy.signals.store import SignalStore


def test_signal_store_is_protocol() -> None:
    assert issubclass(SignalStore, Protocol)
```

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit/signals/test_store_contract_unit.py -q
```

Expected: FAIL because `SignalStore` does not exist.

**Step 2: Move alpha code**

Run:

```bash
git mv packages/engine/src/ditto_engine/alpha packages/strategy/src/ditto_strategy/alpha
git mv packages/engine/tests/unit/alpha packages/strategy/tests/unit/alpha
```

Move integration alpha tests if the directory exists.

**Step 3: Create signal contracts**

In `packages/strategy/src/ditto_strategy/signals/store.py`:

```python
from __future__ import annotations

from typing import Protocol


class SignalStore(Protocol):
    """Persist and load strategy signal batches."""
```

Keep this minimal in the extraction task. Concrete models can be moved from data in Task 13.

**Step 4: Rewrite imports**

Run:

```bash
rg -n "ditto_engine\\.alpha|ditto_engine.alpha" .
```

Replace:

```python
from ditto_engine.alpha.pipeline import StrategyPipeline
```

with:

```python
from ditto_strategy.alpha.pipeline import StrategyPipeline
```

**Step 5: Update package dependencies**

`packages/strategy/pyproject.toml` must include:

```toml
"ditto-kernel",
"ditto-data",
"ditto-features",
"polars",
"orjson",
```

`packages/application/pyproject.toml` must include `ditto-strategy`.

**Step 6: Verify**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: strategy tests pass; no source imports from `ditto_engine.alpha`.

**Step 7: Commit**

```bash
git add packages/strategy packages/engine packages/application packages/backtest .importlinter pyproject.toml pixi.toml
git commit -m "refactor: extract strategy package from engine alpha"
```

---

### Task 7: Extract Portfolio and Accounting ✅ DONE

**Files:**
- Move: `packages/engine/src/ditto_engine/accounting/` -> `packages/portfolio/src/ditto_portfolio/accounting/`
- Move: `packages/engine/src/ditto_engine/portfolio/` -> `packages/portfolio/src/ditto_portfolio/rebalancing/`
- Move: `packages/engine/tests/unit/accounting/` -> `packages/portfolio/tests/unit/accounting/`
- Move: `packages/engine/tests/unit/portfolio/` -> `packages/portfolio/tests/unit/rebalancing/`
- Create: `packages/portfolio/src/ditto_portfolio/holdings/__init__.py`
- Create: `packages/portfolio/src/ditto_portfolio/target_portfolios/__init__.py`
- Create: `packages/portfolio/src/ditto_portfolio/positions/__init__.py`
- Create: `packages/portfolio/src/ditto_portfolio/contracts.py`
- Create: `packages/portfolio/src/ditto_portfolio/errors.py`
- Modify imports matching `ditto_engine.accounting` and `ditto_engine.portfolio`
- Modify: `packages/portfolio/pyproject.toml`
- Modify: `packages/risk/pyproject.toml`
- Modify: `packages/execution/pyproject.toml`
- Modify: `packages/backtest/pyproject.toml`
- Modify: `packages/application/pyproject.toml`

**Step 1: Move code**

Run:

```bash
git mv packages/engine/src/ditto_engine/accounting packages/portfolio/src/ditto_portfolio/accounting
git mv packages/engine/src/ditto_engine/portfolio packages/portfolio/src/ditto_portfolio/rebalancing
git mv packages/engine/tests/unit/accounting packages/portfolio/tests/unit/accounting
git mv packages/engine/tests/unit/portfolio packages/portfolio/tests/unit/rebalancing
```

**Step 2: Rewrite imports**

Run:

```bash
rg -n "ditto_engine\\.(accounting|portfolio)" .
```

Replace examples:

```python
from ditto_engine.accounting.account import Account
from ditto_engine.portfolio.allocation import EqualWeightAllocator
```

with:

```python
from ditto_portfolio.accounting.account import Account
from ditto_portfolio.rebalancing.allocation import EqualWeightAllocator
```

**Step 3: Update package dependencies**

`packages/portfolio/pyproject.toml`:

```toml
dependencies = [
    "ditto-kernel",
    "ditto-data",
    "ditto-strategy",
    "polars",
    "orjson",
]
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/portfolio/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: portfolio tests pass; no source imports from `ditto_engine.accounting` or `ditto_engine.portfolio`.

**Step 5: Commit**

```bash
git add packages/portfolio packages/engine packages/risk packages/execution packages/backtest packages/application .importlinter pyproject.toml pixi.toml
git commit -m "refactor: extract portfolio and accounting packages"
```

---

### Task 8: Extract Risk ✅ DONE

**Files:**
- Move: `packages/engine/src/ditto_engine/risk/` -> `packages/risk/src/ditto_risk/`
- Move: `packages/engine/tests/unit/risk/` -> `packages/risk/tests/unit/`
- Create: `packages/risk/src/ditto_risk/contracts.py`
- Create: `packages/risk/src/ditto_risk/models.py`
- Create: `packages/risk/src/ditto_risk/errors.py`
- Create: `packages/risk/src/ditto_risk/constraints/__init__.py`
- Create: `packages/risk/src/ditto_risk/exposure/__init__.py`
- Create: `packages/risk/src/ditto_risk/drawdown/__init__.py`
- Modify imports matching `ditto_engine.risk`
- Modify: `packages/risk/pyproject.toml`
- Modify: `packages/execution/pyproject.toml`
- Modify: `packages/backtest/pyproject.toml`
- Modify: `packages/application/pyproject.toml`

**Step 1: Move code**

Run:

```bash
git mv packages/engine/src/ditto_engine/risk packages/risk/src/ditto_risk
git mv packages/engine/tests/unit/risk packages/risk/tests/unit/risk_legacy
```

After move, flatten test paths only if imports stay clear; otherwise keep `risk_legacy` until the next cleanup task.

**Step 2: Rewrite imports**

Run:

```bash
rg -n "ditto_engine\\.risk|ditto_engine.risk" .
```

Replace:

```python
from ditto_engine.risk.pre_trade import PreTradeChecker
```

with:

```python
from ditto_risk.pre_trade import PreTradeChecker
```

**Step 3: Update dependencies**

`packages/risk/pyproject.toml`:

```toml
dependencies = [
    "ditto-kernel",
    "ditto-portfolio",
    "ditto-strategy",
    "polars",
    "orjson",
]
```

**Step 4: Add boundary test**

Create `packages/risk/tests/unit/test_import_boundary_unit.py`:

```python
def test_risk_imports_without_execution() -> None:
    import ditto_risk

    assert ditto_risk.__version__ == "0.1.0"
```

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: risk tests pass; no source imports from `ditto_engine.risk`.

**Step 6: Commit**

```bash
git add packages/risk packages/engine packages/execution packages/backtest packages/application .importlinter pyproject.toml pixi.toml
git commit -m "refactor: extract risk package"
```

---

### Task 9: Extract Execution ✅ DONE

**Files:**
- Move: `packages/engine/src/ditto_engine/execution/` -> `packages/execution/src/ditto_execution/`
- Move: `packages/engine/tests/unit/execution/` -> `packages/execution/tests/unit/`
- Move: `packages/data/src/ditto_data/services/trade/` -> `packages/execution/src/ditto_execution/storage/sqlite/trade/`
- Move: `packages/data/src/ditto_data/services/audit/` -> `packages/execution/src/ditto_execution/audit/`
- Move: `packages/data/src/ditto_data/storage/execution/` -> `packages/execution/src/ditto_execution/storage/sqlite/legacy/`
- Move: `packages/data/src/ditto_data/models/trade.py` -> `packages/execution/src/ditto_execution/models.py`
- Create: `packages/execution/src/ditto_execution/orders/__init__.py`
- Create: `packages/execution/src/ditto_execution/orders/store.py`
- Create: `packages/execution/src/ditto_execution/fills/__init__.py`
- Create: `packages/execution/src/ditto_execution/fills/store.py`
- Create: `packages/execution/src/ditto_execution/broker/contracts.py`
- Create: `packages/execution/src/ditto_execution/broker/gateways/__init__.py`
- Create: `packages/execution/src/ditto_execution/reconciliation/__init__.py`
- Create: `packages/execution/src/ditto_execution/contracts.py`
- Create: `packages/execution/src/ditto_execution/errors.py`
- Modify imports matching `ditto_engine.execution`, `ditto_data.services.trade`, `ditto_data.services.audit`, `ditto_data.storage.execution`, `ditto_data.models.trade`
- Modify: `packages/execution/pyproject.toml`
- Modify: `packages/backtest/pyproject.toml`
- Modify: `packages/application/pyproject.toml`
- Modify: `packages/data/pyproject.toml`
- Modify: `.importlinter`

**Step 1: Add failing broker contract test**

Create `packages/execution/tests/unit/broker/test_contracts_unit.py`:

```python
from typing import Protocol

from ditto_execution.broker.contracts import BrokerGateway


def test_broker_gateway_is_protocol() -> None:
    assert issubclass(BrokerGateway, Protocol)
```

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/broker/test_contracts_unit.py -q
```

Expected: FAIL because `BrokerGateway` does not exist.

**Step 2: Move engine execution code**

Run:

```bash
git mv packages/engine/src/ditto_engine/execution packages/execution/src/ditto_execution
git mv packages/engine/tests/unit/execution packages/execution/tests/unit/execution_legacy
```

If `packages/execution/src/ditto_execution/__init__.py` already exists, merge content manually and keep `__version__`.

**Step 3: Move data-owned execution runtime code**

Run:

```bash
mkdir -p packages/execution/src/ditto_execution/storage/sqlite
git mv packages/data/src/ditto_data/services/trade packages/execution/src/ditto_execution/storage/sqlite/trade
git mv packages/data/src/ditto_data/services/audit packages/execution/src/ditto_execution/audit
git mv packages/data/src/ditto_data/storage/execution packages/execution/src/ditto_execution/storage/sqlite/legacy
git mv packages/data/src/ditto_data/models/trade.py packages/execution/src/ditto_execution/models.py
```

Use `apply_patch` if `mkdir -p` is not acceptable in your execution environment; the important requirement is to preserve git history with `git mv` for existing files.

**Step 4: Create BrokerGateway contract**

In `packages/execution/src/ditto_execution/broker/contracts.py`:

```python
from __future__ import annotations

from typing import Protocol


class BrokerGateway(Protocol):
    """Boundary for real and simulated broker implementations."""
```

Keep it empty until moved order models are normalized; later tasks can add typed methods.

**Step 5: Rewrite imports**

Run:

```bash
rg -n "ditto_engine\\.execution|ditto_data\\.services\\.trade|ditto_data\\.services\\.audit|ditto_data\\.storage\\.execution|ditto_data\\.models\\.trade" .
```

Rewrite to:

```text
ditto_engine.execution -> ditto_execution
ditto_data.services.trade -> ditto_execution.storage.sqlite.trade
ditto_data.services.audit -> ditto_execution.audit
ditto_data.storage.execution -> ditto_execution.storage.sqlite.legacy
ditto_data.models.trade -> ditto_execution.models
```

**Step 6: Update dependencies**

`packages/execution/pyproject.toml`:

```toml
dependencies = [
    "ditto-kernel",
    "ditto-portfolio",
    "ditto-risk",
    "ditto-platform",
    "orjson",
]
```

If storage code still imports `ditto-data` models after the move, fix the ownership in this task rather than adding `ditto-data` to execution.

**Step 7: Verify**

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit -q
pixi run -e dev pytest packages/application/tests/unit/query/test_trade* -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: execution tests pass; no production source imports from data trade/execution paths.

**Step 8: Commit**

```bash
git add packages/execution packages/data packages/application packages/backtest .importlinter pyproject.toml pixi.toml
git commit -m "refactor: extract execution package"
```

---

### Task 10: Extract Backtest ✅ DONE

**Files:**
- Move: `packages/engine/src/ditto_engine/backtest/` -> `packages/backtest/src/ditto_backtest/`
- Move: `packages/engine/tests/unit/backtest/` -> `packages/backtest/tests/unit/`
- Move: `packages/engine/tests/integration/backtest/` -> `packages/backtest/tests/integration/`
- Move: `packages/engine/tests/benchmarks/` -> `packages/backtest/tests/benchmarks/`
- Modify imports matching `ditto_engine.backtest`
- Modify: `packages/backtest/pyproject.toml`
- Modify: `packages/application/pyproject.toml`
- Modify: `.importlinter`

**Step 1: Move code**

Run:

```bash
git mv packages/engine/src/ditto_engine/backtest packages/backtest/src/ditto_backtest
git mv packages/engine/tests/unit/backtest packages/backtest/tests/unit/backtest_legacy
```

Move integration and benchmark directories if present.

**Step 2: Rewrite imports**

Run:

```bash
rg -n "ditto_engine\\.backtest|ditto_engine.backtest" .
```

Replace:

```python
from ditto_engine.backtest.engine import EngineLoop
```

with:

```python
from ditto_backtest.engine import EngineLoop
```

**Step 3: Update dependencies**

`packages/backtest/pyproject.toml`:

```toml
dependencies = [
    "ditto-kernel",
    "ditto-data",
    "ditto-strategy",
    "ditto-portfolio",
    "ditto-risk",
    "ditto-execution",
    "polars",
    "numpy",
    "orjson",
]
```

**Step 4: Update import-linter**

Add explicit forbidden contracts:

```text
execution must not depend on backtest
backtest must not import execution broker gateways
production packages must not import analysis
```

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/backtest/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: backtest tests pass; no source imports from `ditto_engine.backtest`.

**Step 6: Commit**

```bash
git add packages/backtest packages/engine packages/application .importlinter pyproject.toml pixi.toml
git commit -m "refactor: extract backtest package"
```

---

### Task 11: Remove Empty Engine Package ✅ DONE

**Files:**
- Delete: `packages/engine/`
- Modify: `pixi.toml`
- Modify: `pyproject.toml`
- Modify: `.importlinter`
- Modify: `docs/architecture/**`
- Modify: `CLAUDE.md`
- Modify: `packages/*/CLAUDE.md` references to `engine`

**Step 1: Prove no engine imports remain**

Run:

```bash
rg -n "ditto_engine|ditto-engine|packages/engine" packages tests pyproject.toml pixi.toml .importlinter CLAUDE.md docs/architecture
```

Expected: only historical docs or explicit migration docs remain.

**Step 2: Delete old package**

Run:

```bash
git rm -r packages/engine
```

**Step 3: Remove config references**

Remove from:

```text
pixi.toml [pypi-dependencies]
pyproject.toml extraPaths
pyproject.toml pythonpath
pyproject.toml commitizen version_files
.importlinter root_packages and contracts
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev type
pixi run -e dev arch-check
pixi run -e dev test --fast
```

Expected: all pass without `ditto_engine`.

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy engine package"
```

---

### Task 12: Normalize Application Internal Directories ✅ DONE

**Files:**
- Move: `packages/application/src/ditto_application/command/` -> `packages/application/src/ditto_application/commands/`
- Move: `packages/application/src/ditto_application/query/` -> `packages/application/src/ditto_application/queries/`
- Move: `packages/application/src/ditto_application/process/` -> `packages/application/src/ditto_application/processes/`
- Keep: `packages/application/src/ditto_application/builders/`
- Create: `packages/application/src/ditto_application/runtime/__init__.py`
- Move runtime-like builder files as appropriate:
  - `builders/runtime_builder.py` -> `runtime/runtime_builder.py` if it owns runtime semantics
  - keep `builders/service_factory.py` if it only builds object graphs
- Modify imports matching `ditto_application.command`, `ditto_application.query`, `ditto_application.process`
- Modify: `.importlinter` R8 contracts
- Modify: `packages/application/CLAUDE.md`

**Step 1: Move directories**

Run:

```bash
git mv packages/application/src/ditto_application/command packages/application/src/ditto_application/commands
git mv packages/application/src/ditto_application/query packages/application/src/ditto_application/queries
git mv packages/application/src/ditto_application/process packages/application/src/ditto_application/processes
```

**Step 2: Rewrite imports**

Run:

```bash
rg -n "ditto_application\\.(command|query|process)" .
```

Replace:

```text
ditto_application.command -> ditto_application.commands
ditto_application.query -> ditto_application.queries
ditto_application.process -> ditto_application.processes
```

**Step 3: Update R8 rules**

In `.importlinter`, rename:

```text
ditto_application.query.** -> ditto_application.queries.**
ditto_application.command.** -> ditto_application.commands.**
ditto_application.process.** -> ditto_application.processes.**
```

Rules remain:

```text
queries must not import processes/builders/commands
builders must not import queries
commands must not import queries/builders
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: application tests pass; R8 contracts kept.

**Step 5: Commit**

```bash
git add packages/application packages/apps .importlinter docs CLAUDE.md
git commit -m "refactor: normalize application cqrs directories"
```

---

### Task 13: Slim Data Package Ownership ✅ DONE

**Files:**
- Move: `packages/data/src/ditto_data/storage/factors/` -> `packages/features/src/ditto_features/storage/parquet/factors/`
- Move: `packages/data/src/ditto_data/storage/features/` -> `packages/features/src/ditto_features/storage/parquet/features/`
- Move: `packages/data/src/ditto_data/services/derived/` -> `packages/features/src/ditto_features/services/derived/`
- Move: `packages/data/src/ditto_data/models/derived.py` -> `packages/features/src/ditto_features/models/derived.py`
- Move: `packages/data/src/ditto_data/models/strategy.py` -> `packages/strategy/src/ditto_strategy/models.py` or merge into existing models
- Move: `packages/data/src/ditto_data/models/strategy_run.py` -> `packages/strategy/src/ditto_strategy/runs/models.py`
- Move: `packages/data/src/ditto_data/models/strategy_audit.py` -> `packages/strategy/src/ditto_strategy/audit/models.py`
- Move: `packages/data/src/ditto_data/services/strategy/` -> `packages/strategy/src/ditto_strategy/storage/sqlite/`
- Move research runtime storage after classification:
  - `packages/data/src/ditto_data/storage/runtime/research_sqlite/` -> `packages/analysis/src/ditto_analysis/storage/sqlite/research/`
  - `packages/data/src/ditto_data/services/research_catalog_service.py` -> `packages/analysis/src/ditto_analysis/research/catalog_service.py`
  - `packages/data/src/ditto_data/services/research_artifact_service.py` -> `packages/analysis/src/ditto_analysis/research/artifact_service.py`
- Modify: `packages/data/pyproject.toml`
- Modify: `packages/features/pyproject.toml`
- Modify: `packages/strategy/pyproject.toml`
- Modify: `packages/analysis/pyproject.toml`
- Modify: `.importlinter`

**Step 1: Classify remaining data violations**

Run:

```bash
find packages/data/src/ditto_data -maxdepth 4 -type d | sort
rg -n "strategy|trade|execution|factor|feature|derived|research" packages/data/src/ditto_data
```

Expected: identify all non-market-fact ownership leaks before moving files.

**Step 2: Move factor and derived storage**

Run:

```bash
git mv packages/data/src/ditto_data/storage/factors packages/features/src/ditto_features/storage/parquet/factors
git mv packages/data/src/ditto_data/storage/features packages/features/src/ditto_features/storage/parquet/features
git mv packages/data/src/ditto_data/services/derived packages/features/src/ditto_features/services/derived
git mv packages/data/src/ditto_data/models/derived.py packages/features/src/ditto_features/models/derived.py
```

**Step 3: Move strategy storage and models**

Run:

```bash
mkdir -p packages/strategy/src/ditto_strategy/runs packages/strategy/src/ditto_strategy/audit packages/strategy/src/ditto_strategy/storage/sqlite
git mv packages/data/src/ditto_data/services/strategy packages/strategy/src/ditto_strategy/storage/sqlite/services
git mv packages/data/src/ditto_data/models/strategy.py packages/strategy/src/ditto_strategy/models.py
git mv packages/data/src/ditto_data/models/strategy_run.py packages/strategy/src/ditto_strategy/runs/models.py
git mv packages/data/src/ditto_data/models/strategy_audit.py packages/strategy/src/ditto_strategy/audit/models.py
```

If `packages/strategy/src/ditto_strategy/models.py` already exists, merge the moved model definitions with `apply_patch` and delete the old moved file.

**Step 4: Move research storage**

Run:

```bash
mkdir -p packages/analysis/src/ditto_analysis/storage/sqlite packages/analysis/src/ditto_analysis/research
git mv packages/data/src/ditto_data/storage/runtime/research_sqlite packages/analysis/src/ditto_analysis/storage/sqlite/research
git mv packages/data/src/ditto_data/services/research_catalog_service.py packages/analysis/src/ditto_analysis/research/catalog_service.py
git mv packages/data/src/ditto_data/services/research_artifact_service.py packages/analysis/src/ditto_analysis/research/artifact_service.py
```

**Step 5: Rewrite imports**

Run:

```bash
rg -n "ditto_data\\.(storage\\.(factors|features)|services\\.derived|models\\.derived|services\\.strategy|models\\.strategy|models\\.strategy_run|models\\.strategy_audit|storage\\.runtime\\.research_sqlite|services\\.research_)" .
```

Rewrite to the owning package paths.

**Step 6: Tighten data import-linter rules**

Update `.importlinter` data storage subdomain isolation to remove:

```text
ditto_data.storage.execution
ditto_data.storage.factors
ditto_data.storage.features
```

Add explicit forbidden rules:

```text
data must not import features/strategy/portfolio/risk/execution/backtest/analysis/application/apps
features storage must not import strategy/execution
strategy storage must not import execution
analysis must not be imported by production packages
```

**Step 7: Verify**

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit -q
pixi run -e dev pytest packages/features/tests/unit -q
pixi run -e dev pytest packages/strategy/tests/unit -q
pixi run -e dev pytest packages/analysis/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: data no longer owns factor, feature, strategy, trade, execution, or research runtime storage.

**Step 8: Commit**

```bash
git add packages/data packages/features packages/strategy packages/analysis .importlinter pyproject.toml pixi.toml
git commit -m "refactor: move business data ownership out of data package"
```

---

### Task 14: Finalize Import-Linter Capability Contracts ✅ DONE

**Files:**
- Modify: `.importlinter`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Test: add architecture checks under `packages/*/tests/unit/architecture/` only if needed

**Step 1: Replace old root package list**

In `.importlinter`:

```ini
[importlinter]
root_packages =
    ditto_kernel
    ditto_platform
    ditto_data
    ditto_features
    ditto_strategy
    ditto_portfolio
    ditto_risk
    ditto_execution
    ditto_backtest
    ditto_analysis
    ditto_application
    ditto_apps
```

**Step 2: Add final package contracts**

Required contracts:

```text
kernel-isolation
platform-isolation
data-boundary
features-boundary
strategy-no-execution
portfolio-no-execution
risk-no-execution
execution-no-backtest-analysis
backtest-no-real-broker-gateways
production-no-analysis
apps-boundary
application-no-apps-import
capability-packages-acyclic
```

**Step 3: Extend architecture smell checker**

Modify `scripts/architecture/check_architecture_smells.py`:

Add source roots:

```python
SRC_ROOTS = [
    ROOT / "packages",
]
```

Add checks:

```text
platform files must not contain business table prefixes:
  execution_
  strategy_
  portfolio_
  risk_
  features_

production packages must not import ditto_analysis.
core models must not import ditto_platform.
```

Implementation hint: keep checks string-based and low-noise, similar to existing f-string logging check.

**Step 4: Verify failing behavior locally**

Temporarily add a known-bad import in a scratch file under `/tmp`, not the repo, or write a small unit test for the checker helper function if helpers are extracted.

Expected: checker catches the bad pattern.

**Step 5: Verify real repo**

Run:

```bash
pixi run -e dev arch-check
```

Expected: all contracts kept, architecture smell check passed.

**Step 6: Commit**

```bash
git add .importlinter scripts/architecture/check_architecture_smells.py
git commit -m "test: enforce capability package architecture boundaries"
```

---

### Task 15: Update Project Docs and Package Guides ✅ DONE

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`
- Modify: `docs/architecture/agent-context-pack.md`
- Create/Modify: `packages/kernel/CLAUDE.md`
- Create/Modify: `packages/platform/CLAUDE.md`
- Create/Modify: `packages/data/CLAUDE.md`
- Create: `packages/features/CLAUDE.md`
- Create: `packages/strategy/CLAUDE.md`
- Create: `packages/portfolio/CLAUDE.md`
- Create: `packages/risk/CLAUDE.md`
- Create: `packages/execution/CLAUDE.md`
- Create: `packages/backtest/CLAUDE.md`
- Create: `packages/analysis/CLAUDE.md`
- Create: `packages/application/CLAUDE.md`
- Create: `packages/apps/CLAUDE.md`

**Step 1: Update root architecture model**

Replace the diamond model:

```text
interfaces -> app -> {data, analytics, engine} -> kernel
infra is horizontal foundation
```

with:

```text
apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel
platform is horizontal technical foundation
```

Also state:

```text
production packages must not depend on analysis
strategy must not depend on execution
execution must not depend on backtest
```

**Step 2: Write package guides**

Each `packages/<pkg>/CLAUDE.md` must include:

```text
定位
允许依赖
禁止依赖
内部目录职责
测试位置
典型导入示例
常用验证命令
```

**Step 3: Verify docs references**

Run:

```bash
rg -n "ditto_engine|ditto_analytics|ditto_app|ditto_infra|ditto_interfaces|packages/engine|packages/analytics|packages/app|packages/infra|interfaces" CLAUDE.md docs packages -g '*.md'
```

Expected: only historical/archive/design references remain; active architecture docs use new names.

**Step 4: Commit**

```bash
git add CLAUDE.md docs/architecture packages/*/CLAUDE.md
git commit -m "docs: update architecture guides for capability packages"
```

---

### Task 16: Update AI Coding Constraints and Agent Rules ✅ DONE

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `.claude/rules/architecture.md`
- Modify: `.claude/rules/config.md`
- Modify: `.claude/rules/dependencies.md`
- Modify: `.claude/rules/doc.md`
- Modify: `.claude/rules/noqa-ignore.md`
- Modify: `.claude/rules/python.md`
- Modify: `.claude/rules/python-test.md`
- Modify: `.claude/rules/workflow.md`
- Modify: `.claude/checklists/code-change.md`
- Modify: `.claude/checklists/debug.md`
- Modify: `.claude/commands/ditto-architecture-audit.md`
- Modify: `.claude/commands/ditto-dev.md`
- Modify: `.claude/commands/ditto-plan.md`
- Modify: `.claude/commands/ditto-review.md`
- Modify: `.claude/commands/ditto-sprint.md`
- Modify: `.claude/commands/architecture-audit.py`
- Modify: `.claude/hooks/py_after_write.py`
- Modify: `.claude/hooks/py_gate.py`
- Modify: `.factory/commands/ditto-architecture-audit.md`
- Modify: `.factory/commands/ditto-dev.md`
- Modify: `.factory/commands/ditto-plan.md`
- Modify: `.factory/commands/ditto-review.md`
- Modify: `.factory/commands/ditto-sprint.md`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Optional Test: `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py`

**Step 1: Inventory stale AI rule references**

Run:

```bash
rg -n "ditto_engine|ditto_analytics|ditto_app|ditto_infra|ditto_interfaces|packages/engine|packages/analytics|packages/app|packages/infra|interfaces/|\\bengine\\b|\\banalytics\\b|\\binfra\\b" AGENTS.md CLAUDE.md .claude .factory -g '*.md' -g '*.py' -g '*.json'
```

Expected: many hits before this task. Capture the list and classify each as:

```text
active rule to update
historical example to rewrite
valid generic word such as "execution engine" to keep
```

**Step 2: Rewrite canonical architecture rules**

In `.claude/rules/architecture.md`, replace the old diamond model with:

```text
apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel
platform is horizontal technical foundation
```

Add the package placement decision tree:

```text
市场事实、PIT、数据质量、外部数据源？ -> ditto_data
因子、指标、表达式、物化、因子评估？ -> ditto_features
策略定义、策略版本、信号、alpha pipeline？ -> ditto_strategy
持仓、目标组合、调仓、会计？ -> ditto_portfolio
盘前/盘后风控、约束、暴露、审计？ -> ditto_risk
订单、成交、OMS、券商网关、对账？ -> ditto_execution
回测运行时、模拟 broker、绩效？ -> ditto_backtest
报告、诊断、实验、筛选？ -> ditto_analysis
command/query/process 编排？ -> ditto_application
API/CLI/worker/web/DI composition root？ -> ditto_apps
配置、日志、metrics、trace、存储连接、锁、缓存？ -> ditto_platform
跨模块稳定值对象和错误根？ -> ditto_kernel
```

Also add hard constraints:

```text
production packages must not import ditto_analysis
ditto_strategy must not import ditto_execution
ditto_execution must not import ditto_backtest
ditto_backtest must not import real broker gateways
ditto_platform must not contain business schema or business table ownership
ditto_data must not own orders/signals/portfolio/risk/process state
```

**Step 3: Update workflow and coding rules**

Update `.claude/rules/*.md` so examples and commands use new paths:

```text
interfaces/src -> packages/apps/src
interfaces/tests -> packages/apps/tests
packages/infra -> packages/platform
packages/app -> packages/application
packages/analytics -> packages/features or packages/analysis by context
packages/engine -> packages/strategy/portfolio/risk/execution/backtest by context
ditto_infra -> ditto_platform
ditto_app -> ditto_application
ditto_interfaces -> ditto_apps
ditto_analytics -> ditto_features or ditto_analysis by context
ditto_engine.alpha -> ditto_strategy.alpha
ditto_engine.portfolio/accounting -> ditto_portfolio
ditto_engine.risk -> ditto_risk
ditto_engine.execution -> ditto_execution
ditto_engine.backtest -> ditto_backtest
```

Specific rule updates:

```text
.claude/rules/noqa-ignore.md:
  source globs become packages/*/src only; no interfaces/*/src.

.claude/rules/python-test.md:
  test layout examples use packages/<capability>/tests/unit and packages/apps/tests/e2e.

.claude/rules/python.md:
  py.typed table lists all 12 target packages.

.claude/rules/config.md:
  config loading examples use ditto_platform.foundation.config and packages/apps registry.

.claude/rules/doc.md:
  example paths use packages/execution or packages/features instead of packages/engine.

.claude/rules/workflow.md:
  architecture gate references capability package contracts.
```

**Step 4: Update AI command prompts**

Update `.claude/commands/*.md` and `.factory/commands/*.md`:

```text
Architecture audit scope:
  packages/kernel
  packages/platform
  packages/data
  packages/features
  packages/strategy
  packages/portfolio
  packages/risk
  packages/execution
  packages/backtest
  packages/analysis
  packages/application
  packages/apps

Audit forbidden examples:
  strategy -> execution
  execution -> backtest/analysis
  production -> analysis
  data -> strategy/portfolio/execution
  platform -> business packages
  apps -> capability internals outside composition root
```

Replace shell snippets:

```bash
grep -r "TYPE_CHECKING" packages/ --include="*.py"
grep -r "import pandas\|import sqlalchemy" packages/ --include="*.py"
grep -r "# type: ignore" packages/*/src --include="*.py"
```

Remove `interfaces/` from active command snippets.

**Step 5: Update hooks and gates**

Inspect:

```bash
sed -n '1,220p' .claude/hooks/py_after_write.py
sed -n '1,220p' .claude/hooks/py_gate.py
```

Update any hardcoded package roots, import names, or old path exemptions to the target package set. The hooks should understand:

```text
packages/apps/src/ditto_apps
packages/application/src/ditto_application
packages/platform/src/ditto_platform
```

and should not special-case `interfaces/`, `ditto_infra`, `ditto_app`, or `ditto_engine`.

**Step 6: Add AI rule stale-reference guard**

Extend `scripts/architecture/check_architecture_smells.py` with a low-noise check over active AI rule files:

```python
AI_RULE_ROOTS = [
    ROOT / "CLAUDE.md",
    ROOT / "AGENTS.md",
    ROOT / ".claude" / "rules",
    ROOT / ".claude" / "commands",
    ROOT / ".claude" / "checklists",
    ROOT / ".factory" / "commands",
]

STALE_AI_RULE_REFERENCES = (
    "ditto_infra",
    "ditto_interfaces",
    "ditto_app",
    "ditto_analytics",
    "ditto_engine",
    "packages/infra",
    "packages/app",
    "packages/analytics",
    "packages/engine",
    "interfaces/src",
    "interfaces/tests",
)
```

The check should scan only active AI rule/config surfaces, not `docs/plans` or archive material. It should report:

```text
.claude/rules/architecture.md: contains stale AI rule reference 'ditto_engine'
```

**Step 7: Write or update a guard test**

If script tests already exist, add a unit test there. If not, create `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py`:

```python
from scripts.architecture.check_architecture_smells import (
    STALE_AI_RULE_REFERENCES,
)


def test_stale_ai_rule_reference_list_covers_legacy_packages() -> None:
    assert "ditto_engine" in STALE_AI_RULE_REFERENCES
    assert "interfaces/src" in STALE_AI_RULE_REFERENCES
```

Keep the test small; the real behavioral verification is `pixi run -e dev arch-check`.

**Step 8: Verify no stale active AI rules remain**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py -q
pixi run -e dev arch-check
rg -n "ditto_engine|ditto_analytics|ditto_app|ditto_infra|ditto_interfaces|packages/engine|packages/analytics|packages/app|packages/infra|interfaces/src|interfaces/tests" AGENTS.md CLAUDE.md .claude .factory -g '*.md' -g '*.py' -g '*.json'
```

Expected:

```text
pytest passes
arch-check passes
rg has no active stale package references
```

Generic words like "engine" may remain only where they mean a runtime engine, not old `packages/engine`.

**Step 9: Commit**

```bash
git add AGENTS.md CLAUDE.md .claude .factory scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture
git commit -m "docs: update AI coding rules for capability packages"
```

---

### Task 17: Final Cleanup of Configuration and Tooling ✅ DONE

**Files:**
- Modify: `pixi.toml`
- Modify: `pyproject.toml`
- Modify: `pyright.tests.json`
- Modify: `.pre-commit-config.yaml`
- Modify: `scripts/test.py`
- Modify: `scripts/type.py`
- Modify: `deploy/**`
- Modify: `typings/**` if package paths changed

**Step 1: Remove stale package references**

Run:

```bash
rg -n "ditto_(infra|interfaces|app|analytics|engine)|ditto-(infra|interfaces|app|analytics|engine)|packages/(infra|app|analytics|engine)|interfaces/" .
```

For active source/config files, replace or remove every stale reference.

**Step 2: Update type and pytest config**

In `pyproject.toml`, ensure:

```toml
extraPaths = [
    "packages/kernel/src",
    "packages/platform/src",
    "packages/data/src",
    "packages/features/src",
    "packages/strategy/src",
    "packages/portfolio/src",
    "packages/risk/src",
    "packages/execution/src",
    "packages/backtest/src",
    "packages/analysis/src",
    "packages/application/src",
    "packages/apps/src",
]

testpaths = ["packages/*/tests"]
pythonpath = [
    same paths as above
]
```

In coverage:

```toml
source = ["packages"]
```

**Step 3: Update commitizen version files**

Use active packages only:

```toml
version_files = [
    "packages/kernel/src/ditto_kernel/__init__.py:__version__",
    "packages/platform/src/ditto_platform/__init__.py:__version__",
    "packages/data/src/ditto_data/__init__.py:__version__",
    "packages/features/src/ditto_features/__init__.py:__version__",
    "packages/strategy/src/ditto_strategy/__init__.py:__version__",
    "packages/portfolio/src/ditto_portfolio/__init__.py:__version__",
    "packages/risk/src/ditto_risk/__init__.py:__version__",
    "packages/execution/src/ditto_execution/__init__.py:__version__",
    "packages/backtest/src/ditto_backtest/__init__.py:__version__",
    "packages/analysis/src/ditto_analysis/__init__.py:__version__",
    "packages/application/src/ditto_application/__init__.py:__version__",
    "packages/apps/src/ditto_apps/__init__.py:__version__",
]
```

**Step 4: Verify tooling**

Run:

```bash
pixi run -e dev lint
pixi run -e dev fmt
pixi run -e dev type --all
pixi run -e dev test --fast
pixi run -e dev arch-check
```

Expected: all pass.

**Step 5: Commit**

```bash
git add pixi.toml pyproject.toml pyright.tests.json .pre-commit-config.yaml scripts deploy typings
git commit -m "chore: clean tooling for capability packages"
```

---

### Task 18: Full Verification and Final Commit ✅ DONE

**Files:**
- Modify only files required by verification failures.

**Step 1: Run final gate**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
ruff format . -> files unchanged or formatted
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass except documented skips
import-linter -> all contracts kept
architecture smell check passed
```

**Step 2: Run full CI gate**

Run:

```bash
pixi run -e dev ci
```

Expected: full lint, format-check, type-all, coverage test, arch-check pass. If coverage fails due moved files being counted differently, add missing tests instead of lowering thresholds.

**Step 3: Check final tree**

Run:

```bash
find packages -maxdepth 2 -type d | sort
git status --short
rg -n "ditto_(infra|interfaces|app|analytics|engine)|ditto-(infra|interfaces|app|analytics|engine)" packages pixi.toml pyproject.toml .importlinter
```

Expected:

```text
packages contain target package set
git status shows only intended changes before final commit
rg finds no active stale package references
```

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "refactor: complete capability package architecture"
```

---

## Implementation Notes

### Preferred Slice Order

Execute tasks in the order above. Do not extract `execution` before `portfolio` and `risk`, because execution should depend on those package contracts. Do not remove `data` ownership leaks before destination packages exist. Do not finalize import-linter before the old packages are removed, or every intermediate state becomes unnecessarily noisy.

### Temporary Shims

Temporary shims are allowed only inside one task or phase. Example:

```python
# Temporary during one commit only.
from ditto_features.expression import *  # noqa: F403
```

Before the phase ends:

```bash
rg -n "Temporary|F403|ditto_analytics|ditto_engine" packages
```

Expected: no temporary shims remain.

### Handling Circular Dependencies

If a new cycle appears:

1. Identify the consumer that truly owns the contract.
2. Move the Protocol to that consumer package.
3. Inject concrete implementations from `apps` composition root.
4. Rerun `pixi run -e dev arch-check`.

Do not use `TYPE_CHECKING` imports as the fix.

### Commit Cadence

Use the commit messages in each task. If a task becomes too large, split it by package but keep the same semantic prefix:

```text
refactor: extract strategy package models
refactor: extract strategy package imports
test: add strategy package boundary checks
```

---

Plan complete. Use `superpowers:executing-plans` in the implementation session and execute one task at a time.
