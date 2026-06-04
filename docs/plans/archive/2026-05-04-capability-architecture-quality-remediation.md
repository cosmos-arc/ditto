# Capability Architecture Quality Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复能力包架构重构后的质量缺口，使包依赖声明、架构门禁、领域契约、错误层级、文档语义和 risk 子域结构都与最终设计一致。

**Architecture:** 保持现有 12 包能力架构，但把源码事实、`pyproject.toml` 依赖、import-linter 规则和文档统一到同一张图上。业务包不新增反向依赖；需要跨包共享的纯值类型继续放入 `ditto_kernel`，技术基础设施放入 `ditto_platform`。`apps` 作为 composition root 可以装配能力包，但普通 API/CLI/jobs 代码必须通过 `application` 或显式 port 使用能力。

**Tech Stack:** Python 3.13, pixi, setuptools editable packages, ruff, basedpyright, pytest, import-linter, custom architecture smell checker.

---

## Plan Review

这份计划整合了 `docs/plans/2026-05-04-capability-architecture-quality-remediation.md` 原始草案和源码审计结论。

原草案覆盖得比较好的部分：

- `risk.contracts.PostTradeGuard` 和 `execution.contracts.TradeAuditor` 的裸 `object` 类型需要修复。
- `strategy`、`execution`、`features` 的错误层级过薄。
- `risk.models.py` 和 `constraints/drawdown/exposure` 目录仍是占位结构。

原草案遗漏或需要修正的部分：

- 没有处理 `pyproject.toml` 与源码 import 图不一致的问题。
- 没有关闭 `apps-service-isolation` 对 `from ditto_data.models import Dataset` 这类 barrel import 的漏洞。
- 没有处理 `InfraError`、`packages/infra`、`ditto_app`、`interfaces/tests` 等语义残留。
- `TradeAuditor` 不应为了类型化而依赖 `ditto_risk`；execution 已有 `RiskScanPayload` / `PreTradeDecisionPayload`，应使用 execution 自己的 audit DTO。
- 对 `raise ValueError` 的替换不能一刀切；仅迁移领域边界和公共服务中确实代表业务失败的 raise。
- 没有处理跨包 re-export 债，例如 `ditto_data.models.publication_safety -> ditto_kernel.publication_safety`。

## Execution Rules

1. 每个 task 单独提交，提交前至少运行 task 内指定验证命令。
2. TDD 流程：RED → GREEN → REFACTOR。
3. 不引入长期 backward compatibility shim；迁移期 facade 只允许用于同 task 内的测试稳定，最终任务必须删除或显式标注为短期技术债。
4. 不用 `TYPE_CHECKING` 延迟导入解决循环依赖。
5. 每次 import 变更前先 `rg` 定位消费者，再改，再跑 `pixi run -e dev type` 和 `pixi run -e dev arch-check`。
6. 不降低 import-linter、ruff、basedpyright 或测试门禁。

## Global Verification Commands

```bash
pixi run -e dev lint
pixi run -e dev fmt
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
pixi run -e dev check
```

---

## Task 0: Baseline and Inventory

**Files:**
- Read: `docs/plans/2026-04-29-capability-package-architecture-design.md`
- Read: `docs/plans/2026-04-29-capability-package-architecture-implementation-plan.md`
- Read: `.importlinter`
- Read: `scripts/architecture/check_architecture_smells.py`
- Read: all `packages/*/pyproject.toml`

**Step 1: Confirm working tree**

Run:

```bash
git status --short
```

Expected: only this plan file may be untracked before implementation starts.

**Step 2: Reproduce baseline gate**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> all pass except documented skips
import-linter -> all contracts kept
architecture smell check passed
```

Known baseline warning to eliminate later:

```text
Data storage must not import data models directly
- No matches for ignored import ditto_data.storage.** -> ditto_data.models.
```

**Step 3: Capture current internal import graph**

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
    for path in (Path("packages") / pkg / "src").rglob("*.py"):
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

Expected: use this as the pre-change graph for Task 1 and Task 2.

**Step 4: Commit**

No commit unless Task 0 produces an intentional baseline note.

---

## Task 1: Make Package Metadata Match Source Imports

**Files:**
- Modify: `packages/apps/pyproject.toml`
- Modify: `packages/application/pyproject.toml`
- Modify: `packages/features/pyproject.toml`
- Modify: `packages/strategy/pyproject.toml`
- Modify: `packages/execution/pyproject.toml`
- Modify: `packages/platform/pyproject.toml`
- Modify: `packages/kernel/pyproject.toml`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Create: `packages/apps/tests/unit/architecture/test_package_metadata_unit.py`

**Problem:**

源码 import 图和 package metadata 不一致：

- `apps` 源码直接 import `ditto_analysis`、`ditto_data`、`ditto_execution`、`ditto_features`、`ditto_kernel`、`ditto_strategy`，但 `packages/apps/pyproject.toml` 只声明 `ditto-application`、`ditto-platform`。
- `features` 声明 `ditto-data`，但源码已不依赖 data。
- `strategy` 声明 `ditto-data`、`ditto-features`，但源码当前不依赖它们。
- `execution` 声明 `ditto-risk`，但源码当前不依赖 risk。
- `platform` 源码 import `ditto_kernel.exceptions`，但 pyproject 未声明 `ditto-kernel`。
- `kernel` pyproject 是 `0.2.0`，运行时 `_version.py` 是 `0.1.0`。

**Step 1: RED — Add metadata guard test**

Create `packages/apps/tests/unit/architecture/test_package_metadata_unit.py`:

```python
from pathlib import Path

from scripts.architecture.check_architecture_smells import (
    check_package_metadata,
)


def test_package_metadata_matches_internal_imports() -> None:
    assert check_package_metadata(Path.cwd()) == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_package_metadata_unit.py -q
```

Expected: FAIL because `check_package_metadata` does not exist.

**Step 2: GREEN — Implement metadata checker**

Modify `scripts/architecture/check_architecture_smells.py`:

- Add `tomllib`, `ast`, and a helper that scans `packages/*/src/**/*.py`.
- For each internal `ditto_*` import, map it to the owning project dependency name.
- Compare actual direct imports to `[project].dependencies`.
- Also compare package runtime `_version.py` with `[project].version` when `_version.py` exists.
- Return low-noise messages such as:

```text
packages/apps/pyproject.toml: missing dependencies ['ditto-data']
packages/features/pyproject.toml: stale dependencies ['ditto-data']
packages/kernel/pyproject.toml: version 0.2.0 != src/ditto_kernel/_version.py 0.1.0
```

Call this checker from `main()` so `pixi run -e dev arch-check` catches future drift.

**Step 3: Fix pyproject files**

Expected final changes:

```toml
# packages/apps/pyproject.toml
dependencies = [
    "ditto-analysis",
    "ditto-application",
    "ditto-data",
    "ditto-execution",
    "ditto-features",
    "ditto-kernel",
    "ditto-platform",
    "ditto-strategy",
]

[tool.setuptools.package-dir]
"" = "src"
```

```toml
# packages/application/pyproject.toml
[tool.setuptools.package-dir]
"" = "src"
```

```toml
# packages/features/pyproject.toml
dependencies = [
    "ditto-kernel",
    "ditto-platform",
    "polars",
    "numpy",
    "cachebox",
    "orjson",
]
```

```toml
# packages/strategy/pyproject.toml
dependencies = [
    "ditto-kernel",
    "ditto-platform",
    "polars",
    "orjson",
]
```

```toml
# packages/execution/pyproject.toml
dependencies = [
    "ditto-kernel",
    "ditto-portfolio",
    "ditto-platform",
    "orjson",
]
```

```toml
# packages/platform/pyproject.toml
dependencies = [
    "ditto-kernel",
]
```

```toml
# packages/kernel/pyproject.toml
version = "0.1.0"
```

If `pixi.lock` changes after `pixi` refreshes editable dependency metadata, include it in the commit.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_package_metadata_unit.py -q
pixi run -e dev arch-check
pixi run -e dev type
```

Expected: metadata checker passes and arch-check remains clean.

**Step 5: Commit**

```bash
git add packages/*/pyproject.toml scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture/test_package_metadata_unit.py pixi.lock
git commit -m "test: enforce package metadata matches capability imports"
```

---

## Task 2: Close Apps Data Barrel Boundary Bypass

**Files:**
- Modify: `.importlinter`
- Modify: `packages/application/src/ditto_application/config.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/ingestion.py`
- Modify: `packages/apps/src/ditto_apps/cli/commands/ops.py`
- Modify: `packages/apps/src/ditto_apps/jobs/flows/daily.py`
- Modify: `packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py`
- Modify: `packages/apps/src/ditto_apps/jobs/tasks/t0_meta.py`
- Create: `packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py`

**Problem:**

`apps-service-isolation` forbids `ditto_data.models.**`, but does not forbid the exact barrel module `ditto_data.models`. Current source has `from ditto_data.models import Dataset` in apps jobs, which bypasses the intended rule.

**Step 1: RED — Add boundary test**

Create `packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py`:

```python
from pathlib import Path


def test_apps_non_registry_code_does_not_import_data_models() -> None:
    offenders: list[str] = []
    for path in Path("packages/apps/src/ditto_apps").rglob("*.py"):
        rel = path.as_posix()
        if "/registry/" in rel:
            continue
        source = path.read_text(encoding="utf-8")
        if "from ditto_data.models" in source or "import ditto_data.models" in source:
            offenders.append(rel)
    assert offenders == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py -q
```

Expected: FAIL with current jobs/API/CLI imports.

**Step 2: Route dataset enum through application**

Modify `packages/application/src/ditto_application/config.py`:

```python
__all__ = [
    "DEFAULT_INITIAL_CASH",
    "DataStoreSettings",
    "Dataset",
    "DatasetSpec",
    "TaskTier",
    "get_all_datasets",
    "get_dataset_config",
    "get_datasets_by_tier",
    "get_parallel_datasets",
    "now_iso",
]
```

Update apps imports:

```python
# before
from ditto_data.models import Dataset
from ditto_data.models.common import Dataset

# after
from ditto_application.config import Dataset
```

Target files:

- `packages/apps/src/ditto_apps/api/routes/ingestion.py`
- `packages/apps/src/ditto_apps/cli/commands/ops.py`
- `packages/apps/src/ditto_apps/jobs/flows/daily.py`
- `packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py`
- `packages/apps/src/ditto_apps/jobs/tasks/t0_meta.py`

**Step 3: Tighten import-linter exact barrel coverage**

In `.importlinter`, update `apps-service-isolation` forbidden modules:

```ini
forbidden_modules =
    ditto_data.services
    ditto_data.services.**
    ditto_data.models
    ditto_data.models.**
    ditto_data.errors
    ditto_data.errors.**
    ditto_data.quality
    ditto_data.quality.**
    ditto_data.config
    ditto_data.config.**
```

Remove old direct Dataset allowlist lines:

```ini
ditto_apps.api.routes.ingestion -> ditto_data.models.common
ditto_apps.cli.commands.ops -> ditto_data.models.common
```

Keep documented composition-root exceptions:

```ini
ditto_apps.registry.** -> ditto_data.services.**
ditto_apps.registry.** -> ditto_data.quality.**
ditto_apps.registry.** -> ditto_data.config.**
ditto_apps.jobs.context -> ditto_data.quality
ditto_apps.jobs.context -> ditto_data.quality.protocols
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py -q
pixi run -e dev arch-check
pixi run -e dev pytest packages/apps/tests/unit/jobs -q
pixi run -e dev type
```

Expected: no apps non-registry code imports `ditto_data.models`.

**Step 5: Commit**

```bash
git add .importlinter packages/application/src/ditto_application/config.py packages/apps/src/ditto_apps packages/apps/tests/unit/architecture/test_apps_data_boundary_unit.py
git commit -m "refactor: route apps dataset usage through application boundary"
```

---

## Task 3: Clean Import-Linter Stale Ignore and Boundary Names

**Files:**
- Modify: `.importlinter`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify: `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py`

**Problem:**

`data-storage-no-model-import` still has an unmatched ignore:

```ini
ditto_data.storage.** -> ditto_data.models
```

The comment also says `OnDuplicate` / `WriteStoreResult` live in data models, but those types have moved toward platform/kernel.

**Step 1: RED — Make stale ignore fail in tests**

Update `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py` or create a sibling test:

```python
from pathlib import Path


def test_importlinter_has_no_unmatched_ignore_warning_seed() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")
    assert "ditto_data.storage.** -> ditto_data.models\n" not in text
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture -q
```

Expected: FAIL until the stale line is removed.

**Step 2: Remove only the unmatched ignore**

In `.importlinter`, remove:

```ini
ditto_data.storage.** -> ditto_data.models
```

Keep specific ignores that still match until Task 8 removes the re-export debt:

```ini
ditto_data.storage.** -> ditto_data.models.storage
ditto_data.storage.** -> ditto_data.models.metadata
ditto_data.storage.** -> ditto_data.models.macro
ditto_data.storage.** -> ditto_data.models.publication_safety
ditto_data.storage.** -> ditto_data.models.ingestion
ditto_data.storage.** -> ditto_data.models.common
```

Update the comment to say these are temporary compatibility debts scheduled in Task 8.

**Step 3: Tighten stale active package reference check**

In `scripts/architecture/check_architecture_smells.py`, add active package-doc roots:

```python
ACTIVE_PACKAGE_DOC_ROOTS = [
    ROOT / "packages" / "apps" / "README.md",
    ROOT / "packages" / "platform" / "tests",
    ROOT / "packages" / "kernel" / "CLAUDE.md",
    ROOT / "packages" / "data" / "CLAUDE.md",
    ROOT / "packages" / "platform" / "CLAUDE.md",
]
```

Check these for stale terms:

```python
STALE_ACTIVE_PACKAGE_REFERENCES = (
    "ditto_app",
    "ditto_analytics",
    "ditto_engine",
    "ditto_interfaces",
    "ditto_infra",
    "packages/app/",
    "packages/analytics",
    "packages/engine",
    "packages/infra",
    "interfaces/tests",
    "interfaces/src",
)
```

Do not flag generic lowercase `engine` when it means a runtime engine.

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture -q
pixi run -e dev arch-check
```

Expected: no unmatched ignore warning from import-linter.

**Step 5: Commit**

```bash
git add .importlinter scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture
git commit -m "test: tighten architecture guards for stale ignores and docs"
```

---

## Task 4: Rename Infra Semantics to Platform

**Files:**
- Modify: `packages/platform/src/ditto_platform/exceptions.py`
- Modify: `packages/platform/src/ditto_platform/foundation/config/errors.py`
- Modify: `packages/platform/src/ditto_platform/foundation/concurrency/filelock.py`
- Modify: `packages/platform/tests/**`
- Modify: `packages/apps/README.md`
- Modify: `packages/platform/tests/README.md`
- Modify: `packages/platform/tests/unit/README.md`
- Modify: `packages/platform/tests/integration/README.md`
- Modify: `packages/apps/tests/e2e/conftest.py`
- Modify: `packages/kernel/CLAUDE.md`
- Modify: `packages/data/CLAUDE.md`
- Modify: `packages/platform/CLAUDE.md`

**Problem:**

The package was renamed to `platform`, but source and active docs still contain `InfraError`, `packages/infra`, `ditto_app`, `interfaces/tests`, and old `Interfaces/Analytics` wording.

**Step 1: RED — Locate stale references**

Run:

```bash
rg -n "InfraError|ditto_app|ditto_analytics|ditto_engine|ditto_interfaces|ditto_infra|packages/infra|packages/app/|interfaces/tests|interfaces/src|\\bInterfaces\\b|\\bAnalytics\\b" \
  packages/apps/README.md \
  packages/platform/tests \
  packages/*/CLAUDE.md \
  packages/platform/src \
  packages/apps/tests/e2e/conftest.py
```

Expected: current repo has hits.

**Step 2: Rename Platform exception root**

Change `packages/platform/src/ditto_platform/exceptions.py`:

```python
"""Platform exception root."""

from ditto_kernel.exceptions import DittoError


class PlatformError(DittoError):
    """平台基础设施错误根."""


__all__ = ["PlatformError"]
```

Update consumers:

```python
# before
from ditto_platform.exceptions import InfraError

# after
from ditto_platform.exceptions import PlatformError
```

Then update subclasses:

```python
class ConfigInitError(PlatformError): ...
class LockAcquisitionError(PlatformError): ...
```

Do not keep `InfraError` as a long-term alias.

**Step 3: Update active docs**

Required replacements:

```text
ditto_app -> ditto_application
ditto_interfaces -> ditto_apps
interfaces/ -> packages/apps/
packages/infra -> packages/platform
Interfaces 层 -> Apps 层
Analytics -> Features or Analysis by context
infra as old package name -> platform
```

`packages/apps/README.md` should describe `ditto-apps`, not `ditto-interfaces`.

`packages/apps/tests/e2e/conftest.py` report path should become:

```python
Path(f"packages/apps/tests/reports/e2e_validation_{date.today():%Y%m%d}.md")
```

**Step 4: Verify**

Run:

```bash
pixi run -e dev pytest packages/platform/tests/unit -q
pixi run -e dev pytest packages/apps/tests/e2e/test_reporter_unit.py -q
pixi run -e dev arch-check
pixi run -e dev type
```

Expected: no active stale references except deliberate `registry/infra/` path names if those directories remain intentionally named as a local subfolder.

**Step 5: Commit**

```bash
git add packages/platform packages/apps packages/kernel/CLAUDE.md packages/data/CLAUDE.md
git commit -m "refactor: rename platform error root and clean stale architecture docs"
```

---

## Task 5: Type Risk and Execution Contracts

**Files:**
- Modify: `packages/risk/src/ditto_risk/contracts.py`
- Modify: `packages/risk/src/ditto_risk/__init__.py`
- Create: `packages/risk/tests/unit/test_contracts_typed_unit.py`
- Modify: `packages/execution/src/ditto_execution/contracts.py`
- Create: `packages/execution/tests/unit/test_contracts_typed_unit.py`

**Problem:**

`risk.contracts.PostTradeGuard.scan()` uses `object`; `execution.contracts.TradeAuditor` uses `tuple[object, ...]`. These are type escape hatches.

**Step 1: RED — Risk contract test**

Create `packages/risk/tests/unit/test_contracts_typed_unit.py`:

```python
from typing import Protocol, get_type_hints

from ditto_risk.contracts import PostTradeGuard, RiskSlice


def test_post_trade_guard_scan_has_typed_params() -> None:
    hints = get_type_hints(PostTradeGuard.scan)
    assert "AccountView" in str(hints["account_view"])
    assert hints["slice_"] is RiskSlice


def test_risk_slice_protocol_exists() -> None:
    assert issubclass(RiskSlice, Protocol)
```

Run:

```bash
pixi run -e dev pytest packages/risk/tests/unit/test_contracts_typed_unit.py -q
```

Expected: FAIL because `RiskSlice` does not exist.

**Step 2: GREEN — Type risk contract**

Modify `packages/risk/src/ditto_risk/contracts.py`:

```python
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.account import AccountView

from ditto_risk.post_trade import RiskAction

__all__ = ["PostTradeGuard", "RiskSlice"]


class RiskSlice(Protocol):
    """盘后风控扫描所需的最小市场切片."""

    @property
    def bars(self) -> dict[InstrumentId, Any]:
        """当前 bar 数据，按 instrument_id 索引."""
        ...


@runtime_checkable
class PostTradeGuard(Protocol):
    """盘后风控扫描接口."""

    def scan(self, account_view: AccountView, slice_: RiskSlice) -> list[RiskAction]:
        """扫描账户状态，返回触发的风控动作列表."""
        ...

    def reset(self) -> None:
        """重置风控扫描状态."""
        ...
```

Update `packages/risk/src/ditto_risk/__init__.py` to re-export `RiskSlice`.

**Step 3: RED — Execution contract test**

Create `packages/execution/tests/unit/test_contracts_typed_unit.py`:

```python
from typing import get_type_hints

from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)
from ditto_execution.contracts import TradeAuditor


def test_trade_auditor_save_risk_log_uses_risk_payload() -> None:
    hints = get_type_hints(TradeAuditor.save_risk_log)
    assert "object" not in str(hints["records"])
    assert "RiskScanPayload" in str(hints["records"])


def test_trade_auditor_save_pre_trade_log_uses_pre_trade_payload() -> None:
    hints = get_type_hints(TradeAuditor.save_pre_trade_log)
    assert "object" not in str(hints["records"])
    assert "PreTradeDecisionPayload" in str(hints["records"])
```

Run:

```bash
pixi run -e dev pytest packages/execution/tests/unit/test_contracts_typed_unit.py -q
```

Expected: FAIL because current records type is `tuple[object, ...]`.

**Step 4: GREEN — Type execution contract without adding risk dependency**

Modify `packages/execution/src/ditto_execution/contracts.py`:

```python
from collections.abc import Sequence

from ditto_execution.audit.models import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)


class TradeAuditor(Protocol):
    """交易审计接口 — 记录执行审计日志."""

    def save_risk_log(self, run_id: str, records: Sequence[RiskScanPayload]) -> int:
        """保存风控扫描审计日志."""
        ...

    def save_pre_trade_log(
        self,
        run_id: str,
        records: Sequence[PreTradeDecisionPayload],
    ) -> int:
        """保存盘前决策审计日志."""
        ...
```

Do not import `ditto_risk` in execution for this task.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/risk/tests/unit/test_contracts_typed_unit.py packages/execution/tests/unit/test_contracts_typed_unit.py -q
pixi run -e dev pytest packages/risk/tests/unit packages/execution/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: no `object` in public contract parameter types.

**Step 6: Commit**

```bash
git add packages/risk packages/execution
git commit -m "refactor: replace object escapes in risk and execution contracts"
```

---

## Task 6: Expand Domain Error Hierarchies

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/errors.py`
- Modify: selected `packages/strategy/src/ditto_strategy/alpha/**/*.py`
- Create/Modify: `packages/strategy/tests/unit/test_errors_unit.py`
- Modify: `packages/execution/src/ditto_execution/errors.py`
- Modify: selected `packages/execution/src/ditto_execution/**/*.py`
- Create/Modify: `packages/execution/tests/unit/test_errors_unit.py`
- Modify: `packages/features/src/ditto_features/errors.py`
- Modify: selected `packages/features/src/ditto_features/**/*.py`
- Create/Modify: `packages/features/tests/unit/test_errors_unit.py`

**Problem:**

`StrategyError`、`ExecutionError`、`FeaturesError` are too thin. Public callers cannot distinguish validation, generation, storage, audit, and materialization failures.

**Important constraint:**

Do not blindly replace every `ValueError`. Keep local value-object invariant errors as `ValueError` where tests and Python conventions expect them. Replace only domain-boundary failures in public services, facades, validators, and storage adapters.

**Step 1: RED — Strategy error tests**

Create/update `packages/strategy/tests/unit/test_errors_unit.py`:

```python
from ditto_strategy.errors import (
    PipelineExecutionError,
    SignalGenerationError,
    StrategyError,
    StrategySpecError,
    TemplateNotFoundError,
)


def test_strategy_error_hierarchy() -> None:
    assert issubclass(StrategySpecError, StrategyError)
    assert issubclass(SignalGenerationError, StrategyError)
    assert issubclass(PipelineExecutionError, StrategyError)
    assert issubclass(TemplateNotFoundError, StrategyError)


def test_strategy_spec_error_carries_details() -> None:
    err = StrategySpecError("invalid spec", spec_name="momentum_v1")
    assert err.spec_name == "momentum_v1"
    assert err.details["spec_name"] == "momentum_v1"
```

**Step 2: GREEN — Strategy errors**

Implement in `packages/strategy/src/ditto_strategy/errors.py`:

```python
class StrategyError(DittoError):
    """策略域基础异常."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class StrategySpecError(StrategyError): ...
class SignalGenerationError(StrategyError): ...
class PipelineExecutionError(StrategyError): ...
class TemplateNotFoundError(StrategyError): ...
```

Then migrate selected public failures found by:

```bash
rg -n "raise ValueError|raise RuntimeError|raise StrategyError" packages/strategy/src -g '*.py'
```

Primary targets:

- `packages/strategy/src/ditto_strategy/alpha/validation.py`
- `packages/strategy/src/ditto_strategy/alpha/specs.py`
- `packages/strategy/src/ditto_strategy/alpha/templates/*.py`

**Step 3: RED/GREEN — Execution errors**

Create/update `packages/execution/tests/unit/test_errors_unit.py`:

```python
from ditto_execution.errors import (
    AuditError,
    ExecutionError,
    FillProcessingError,
    OrderStateError,
    OrderSubmitError,
    ReconciliationError,
)


def test_execution_error_hierarchy() -> None:
    assert issubclass(OrderSubmitError, ExecutionError)
    assert issubclass(OrderStateError, ExecutionError)
    assert issubclass(FillProcessingError, ExecutionError)
    assert issubclass(ReconciliationError, ExecutionError)
    assert issubclass(AuditError, ExecutionError)
```

Implement in `packages/execution/src/ditto_execution/errors.py`:

```python
class ExecutionError(DittoError): ...
class OrderSubmitError(ExecutionError): ...
class OrderStateError(ExecutionError): ...
class FillProcessingError(ExecutionError): ...
class ReconciliationError(ExecutionError): ...
class AuditError(ExecutionError): ...
```

Migrate selected public failures found by:

```bash
rg -n "raise ExecutionError|raise ValueError|raise RuntimeError" packages/execution/src -g '*.py'
```

Primary targets:

- `packages/execution/src/ditto_execution/brokerage.py`
- `packages/execution/src/ditto_execution/storage/sqlite/legacy/_sql.py`
- `packages/execution/src/ditto_execution/audit/execution_audit_service.py` if it wraps persistence failures.

**Step 4: RED/GREEN — Features errors**

Create/update `packages/features/tests/unit/test_errors_unit.py`:

```python
from ditto_features.errors import (
    EvaluationError,
    FactorValidationError,
    FeaturesError,
    FeatureStorageError,
    MaterializationError,
)


def test_features_error_hierarchy() -> None:
    assert issubclass(MaterializationError, FeaturesError)
    assert issubclass(EvaluationError, FeaturesError)
    assert issubclass(FactorValidationError, FeaturesError)
    assert issubclass(FeatureStorageError, FeaturesError)
```

Implement:

```python
class FeaturesError(DittoError): ...
class MaterializationError(FeaturesError): ...
class EvaluationError(FeaturesError): ...
class FactorValidationError(FeaturesError): ...
class FeatureStorageError(FeaturesError): ...
```

Migrate selected public failures found by:

```bash
rg -n "raise FeaturesError|raise ValueError|raise RuntimeError" packages/features/src -g '*.py'
```

Primary targets:

- `packages/features/src/ditto_features/services/derived/queries.py`
- `packages/features/src/ditto_features/storage/parquet/factors/factor_writer.py`
- `packages/features/src/ditto_features/storage/parquet/features/technical/technical_indicator_writer.py`
- `packages/features/src/ditto_features/storage/sqlite/derived/writer.py`
- `packages/features/src/ditto_features/evaluation/metrics/*.py` where errors cross public API.

**Step 5: Verify**

Run:

```bash
pixi run -e dev pytest packages/strategy/tests/unit/test_errors_unit.py packages/execution/tests/unit/test_errors_unit.py packages/features/tests/unit/test_errors_unit.py -q
pixi run -e dev pytest packages/strategy/tests/unit packages/execution/tests/unit packages/features/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 6: Commit**

```bash
git add packages/strategy packages/execution packages/features
git commit -m "refactor: expand capability package error hierarchies"
```

---

## Task 7: Implement Risk Models and Extract Risk Subdomains

**Files:**
- Modify: `packages/risk/src/ditto_risk/models.py`
- Modify: `packages/risk/src/ditto_risk/pre_trade.py`
- Modify: `packages/risk/src/ditto_risk/post_trade.py`
- Modify: `packages/risk/src/ditto_risk/constraints/__init__.py`
- Create: `packages/risk/src/ditto_risk/constraints/context.py`
- Create: `packages/risk/src/ditto_risk/constraints/checks.py`
- Modify: `packages/risk/src/ditto_risk/drawdown/__init__.py`
- Create: `packages/risk/src/ditto_risk/drawdown/rules.py`
- Modify: `packages/risk/src/ditto_risk/exposure/__init__.py`
- Create: `packages/risk/src/ditto_risk/exposure/rules.py`
- Create: `packages/risk/src/ditto_risk/exposure/checks.py`
- Modify: `packages/risk/src/ditto_risk/__init__.py`
- Move/modify: `packages/risk/tests/unit/**`

**Problem:**

`risk.models.py` is a placeholder, while core data types live inside `pre_trade.py` and `post_trade.py`. `constraints/`, `drawdown/`, and `exposure/` directories are placeholders even though the top-level files contain those subdomains.

**Step 1: RED — Risk model tests**

Create `packages/risk/tests/unit/test_models_unit.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from ditto_risk.models import (
    DrawdownStats,
    ExposureData,
    RiskMetrics,
)


def test_risk_metrics_is_frozen() -> None:
    metrics = RiskMetrics(
        max_drawdown=0.15,
        current_drawdown=0.08,
        sharpe_ratio=1.2,
        volatility=0.18,
    )
    with pytest.raises(FrozenInstanceError):
        metrics.max_drawdown = 0.0


def test_exposure_data_tracks_concentration() -> None:
    data = ExposureData(
        total_exposure=1.0,
        top1_weight=0.35,
        top5_weight=0.72,
        sector_count=8,
    )
    assert data.top1_weight == 0.35


def test_drawdown_stats_tracks_recovery() -> None:
    stats = DrawdownStats(
        max_drawdown=0.22,
        current_drawdown=0.05,
        peak_date="2026-01-15",
        trough_date="2026-03-01",
        recovery_days=45,
    )
    assert stats.recovery_days == 45
```

**Step 2: GREEN — Implement risk summary models**

Modify `packages/risk/src/ditto_risk/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DrawdownStats", "ExposureData", "RiskMetrics"]


@dataclass(frozen=True)
class RiskMetrics:
    """风控指标汇总."""

    max_drawdown: float
    current_drawdown: float
    sharpe_ratio: float
    volatility: float


@dataclass(frozen=True)
class ExposureData:
    """暴露度数据."""

    total_exposure: float
    top1_weight: float
    top5_weight: float
    sector_count: int


@dataclass(frozen=True)
class DrawdownStats:
    """回撤统计."""

    max_drawdown: float
    current_drawdown: float
    peak_date: str
    trough_date: str
    recovery_days: int
```

**Step 3: Extract constraints**

Move from `pre_trade.py`:

- `Decision`
- `PreTradeContext`
- `OrderCheckResult`
- `PreTradeRiskCheck`
- `NoShortSellCheck`
- `PriceValidityCheck`
- `LotSizeCheck`
- `BuyingPowerCheck`
- `DailyTurnoverPreCheck`

Targets:

```text
packages/risk/src/ditto_risk/constraints/context.py
packages/risk/src/ditto_risk/constraints/checks.py
```

Move `ConcentrationPreCheck` to:

```text
packages/risk/src/ditto_risk/exposure/checks.py
```

Keep `packages/risk/src/ditto_risk/pre_trade.py` as a facade that imports and re-exports public symbols. This preserves existing imports while making subdomain ownership clear.

**Step 4: Extract drawdown and exposure rules**

Move from `post_trade.py`:

- `MaxDrawdownRule` and `SingleLossLimitRule` -> `drawdown/rules.py`
- `ConcentrationLimitRule` and `MarketAnomalyRule` -> `exposure/rules.py`
- `RiskAction`, `RiskActionType`, `RiskSeverity`, `PostTradeRiskGuard` can remain in `post_trade.py` during this task unless moving them to `models.py` is low-risk.

Keep `packages/risk/src/ditto_risk/post_trade.py` as a facade that imports and re-exports public symbols.

**Step 5: Update package exports**

Update:

- `packages/risk/src/ditto_risk/constraints/__init__.py`
- `packages/risk/src/ditto_risk/drawdown/__init__.py`
- `packages/risk/src/ditto_risk/exposure/__init__.py`
- `packages/risk/src/ditto_risk/__init__.py`

All public symbols should be available from both old facade paths and new subdomain paths.

**Step 6: Move tests**

Split existing risk tests:

```text
packages/risk/tests/unit/constraints/
packages/risk/tests/unit/drawdown/
packages/risk/tests/unit/exposure/
```

Keep a small compatibility test:

```python
def test_pre_trade_facade_exports_checks() -> None:
    from ditto_risk.pre_trade import NoShortSellCheck
    from ditto_risk.constraints import NoShortSellCheck as NewPath

    assert NoShortSellCheck is NewPath
```

**Step 7: Verify**

Run:

```bash
pixi run -e dev pytest packages/risk/tests/unit -q
pixi run -e dev pytest packages/backtest/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 8: Commit**

This task is large; split commits if needed:

```bash
git add packages/risk
git commit -m "feat: add risk summary models"
git add packages/risk
git commit -m "refactor: extract pre-trade risk constraints subdomain"
git add packages/risk
git commit -m "refactor: extract post-trade drawdown and exposure subdomains"
```

---

## Task 8: Remove Cross-Package Re-Export Debt

**Files:**
- Modify: `packages/data/src/ditto_data/models/storage.py`
- Delete or shrink: `packages/data/src/ditto_data/models/publication_safety.py`
- Modify: `packages/data/src/ditto_data/storage/**/*.py`
- Modify: `packages/application/src/ditto_application/processes/materialization/publication_facade.py`
- Modify: `packages/application/src/ditto_application/queries/research.py`
- Modify: `packages/features/tests/unit/test_features_validation_unit.py`
- Modify: tests under `packages/data/tests/unit/storage/runtime/**`
- Modify: `.importlinter`

**Problem:**

The architecture says cross-package re-export is forbidden, but current code still has compatibility re-exports:

- `ditto_data.models.publication_safety` re-exports from `ditto_kernel.publication_safety`.
- `ditto_data.models.storage` re-exports `WriteResult` / `WriteStoreResult` from `ditto_platform.foundation.storage.types`.
- `ditto_data.errors` re-exports Derived errors from `ditto_kernel.exceptions`.

**Step 1: RED — Add canonical import test**

Create `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`:

```python
from pathlib import Path


FORBIDDEN_IMPORTS = (
    "from ditto_data.models.publication_safety import",
    "from ditto_data.models.storage import WriteResult",
    "from ditto_data.models.storage import WriteStoreResult",
    "from ditto_data.errors import Derived",
)


def test_source_uses_canonical_cross_package_types() -> None:
    offenders: list[str] = []
    for root in (Path("packages"),):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if any(pattern in text for pattern in FORBIDDEN_IMPORTS):
                offenders.append(path.as_posix())
    assert offenders == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q
```

Expected: FAIL.

**Step 2: Replace publication safety imports**

Use:

```bash
rg -n "ditto_data.models.publication_safety" packages -g '*.py'
```

Replace production and tests with:

```python
from ditto_kernel.publication_safety import ...
```

After all consumers are moved, delete `packages/data/src/ditto_data/models/publication_safety.py` unless data package docs intentionally retain it for a short deprecation period. If retained, record a concrete deletion issue and keep it out of production imports.

**Step 3: Replace storage type imports**

Use:

```bash
rg -n "from ditto_data.models.storage import (WriteResult|WriteStoreResult)|from ditto_data.models.storage import" packages -g '*.py'
```

Replace:

```python
from ditto_data.models.storage import WriteResult, WriteStoreResult
```

with:

```python
from ditto_platform.foundation.storage.types import WriteResult, WriteStoreResult
```

Keep `FreezeManifest` in `ditto_data.models.storage`.

**Step 4: Replace Derived error imports**

Use:

```bash
rg -n "from ditto_data.errors import Derived" packages -g '*.py'
```

Replace:

```python
from ditto_data.errors import DerivedNotFoundError, DerivedValidationError
```

with:

```python
from ditto_kernel.exceptions import DerivedNotFoundError, DerivedValidationError
```

Do this in production code and tests. Keep non-Derived data errors in `ditto_data.errors`.

**Step 5: Tighten import-linter**

After imports move, remove no-longer-needed ignores:

```ini
ditto_data.storage.** -> ditto_data.models.storage
ditto_data.storage.** -> ditto_data.models.publication_safety
```

Keep data-domain model ignores that are still legitimate, such as ingestion or metadata records, until those are separately redesigned.

**Step 6: Verify**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q
pixi run -e dev pytest packages/data/tests/unit packages/application/tests/unit packages/features/tests/unit -q
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages .importlinter
git commit -m "refactor: replace cross-package re-export imports with canonical owners"
```

---

## Task 9: Align Architecture Docs with the Stricter Final Design

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`
- Modify: `docs/architecture/agent-context-pack.md`
- Modify: `packages/features/CLAUDE.md`
- Modify: `packages/strategy/CLAUDE.md`
- Modify: `packages/analysis/CLAUDE.md`
- Modify: `packages/apps/CLAUDE.md`
- Modify: `packages/platform/CLAUDE.md`
- Modify: `docs/plans/2026-04-29-capability-package-architecture-design.md` or add a dated amendment note

**Problem:**

The original design says:

- `features` may depend on `data`.
- `strategy` may depend on `data` and `features`.
- `analysis` may read production package results directly.

The final implementation is stricter:

- `features` depends only on `kernel/platform`.
- `strategy` currently depends only on `kernel/platform`.
- `analysis` depends only on `kernel/platform`; production access should go through application queries, read-model exports, or explicit future ports.

**Step 1: Update canonical docs**

In root `CLAUDE.md`, state the effective final dependency model:

```text
data -> kernel/platform
features -> kernel/platform
strategy -> kernel/platform
portfolio -> kernel
risk -> kernel/portfolio
execution -> kernel/platform/portfolio
backtest -> kernel/data/strategy/portfolio/risk/execution
analysis -> kernel/platform
application -> all capability packages
apps -> application/platform plus composition-root wiring
```

Clarify:

```text
features 不直接读取 data；市场输入由 application/backtest 注入。
analysis 不进入生产依赖路径；研究/报告通过 application query/read-model 边界读取结果。
```

**Step 2: Add design amendment**

At the top of `docs/plans/2026-04-29-capability-package-architecture-design.md`, add a short dated amendment:

```markdown
> **2026-05-04 Amendment:** 后续实现将 `features` 与 `analysis` 进一步收窄：
> `features` 不直接依赖 `data`，`analysis` 不直接依赖生产包。
> 这是比原 Accepted plan 更严格的最终约束，源码和 import-linter 以此为准。
```

**Step 3: Verify stale references**

Run:

```bash
rg -n "ditto_app|ditto_analytics|ditto_engine|ditto_interfaces|ditto_infra|packages/infra|packages/app/|packages/analytics|packages/engine|interfaces/src|interfaces/tests" \
  CLAUDE.md docs/architecture packages/*/CLAUDE.md -g '*.md'
```

Expected: no active stale references.

**Step 4: Commit**

```bash
git add CLAUDE.md docs/architecture docs/plans/2026-04-29-capability-package-architecture-design.md packages/*/CLAUDE.md
git commit -m "docs: align architecture guides with stricter capability boundaries"
```

---

## Task 10: Final Verification

**Files:**
- Modify only files needed to fix verification failures.

**Step 1: Full gate**

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
import-linter -> all contracts kept, 0 unmatched ignore warnings
architecture smell check passed
```

**Step 2: Verify dependency metadata guard**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

```text
Architecture smell check passed.
```

No package metadata mismatch messages.

**Step 3: Verify no stale source references**

Run:

```bash
rg -n "ditto_engine|ditto_analytics|ditto_infra|ditto_interfaces|ditto_app\\b" packages -g '*.py'
```

Expected: no production source matches. Boundary tests may mention stale names only inside explicit forbidden-reference lists.

**Step 4: Verify no cross-package re-export imports remain**

Run:

```bash
rg -n "from ditto_data.models.publication_safety import|from ditto_data.models.storage import Write|from ditto_data.errors import Derived" packages -g '*.py'
```

Expected: no production source matches.

**Step 5: Commit final fixes**

```bash
git add -A
git commit -m "test: verify capability architecture quality remediation"
```

---

## Task Dependency Order

```text
Task 0 baseline
  -> Task 1 package metadata guard
  -> Task 2 apps boundary tightening
  -> Task 3 stale ignore guard
  -> Task 4 platform/docs semantic cleanup
  -> Task 5 typed contracts
  -> Task 6 error hierarchies
  -> Task 7 risk models/subdomains
  -> Task 8 re-export debt cleanup
  -> Task 9 architecture docs alignment
  -> Task 10 final verification
```

Task 5 and Task 6 are independent once Task 1-4 are complete. Task 7 depends on Task 5. Task 8 should run after Task 1-4 so guards are already in place. Task 9 should be near the end so docs describe the final state, not an intermediate one.

## Success Criteria

- `pixi run -e dev check` passes.
- `arch-check` has 0 broken contracts and 0 unmatched ignore warnings.
- Package pyproject dependencies match actual direct internal imports.
- No active source imports old package names.
- Non-registry apps code no longer imports `ditto_data.models` directly.
- Public contracts no longer use bare `object` for domain payloads.
- Strategy, execution, and features have domain-specific error hierarchies.
- Risk subdomain directories contain real implementation, not placeholder-only modules.
- Cross-package re-export imports are replaced with canonical owner imports.
