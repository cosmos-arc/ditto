# Capability Architecture Zero Re-Export Debt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 清理 capability architecture 重构后的所有残留跨包 re-export、兼容 shim、遗漏门禁和未分类边界例外，使源码事实、设计意图和自动化检查完全一致。

**Architecture:** 以 canonical owner 为唯一导入源：领域共享类型放 `ditto_kernel`，技术基础设施放 `ditto_platform`，能力包只暴露自己拥有的模型、服务和协议。跨包 re-export 默认禁止；确实属于 composition/API 边界的例外必须精确列入 allowlist，并写清设计理由和迁移边界。修复顺序先补 AST 级门禁，再迁移消费者，最后删除 shim 和文档残留。

**Tech Stack:** Python 3.13, pixi, pytest, ruff, basedpyright, import-linter, custom architecture smell checker, `rg`, AST parsing.

---

## Why This Plan Exists

`pixi run -e dev check` 已经通过，但源码 review 发现仍有架构债没有被现有门禁捕获：

- `ditto_data.storage.sqlite_client` 仍从 `ditto_platform.foundation.storage.sqlite_client` re-export `SQLiteClient`。
- `ditto_data.__init__` 仍把 `SQLiteClient` 暴露为 data 顶层 API。
- `ditto_data.models.common` 仍把 `ditto_kernel.json_types` 的 `JsonDict`、`JsonValue`、`require_*` 暴露在 data 模型 API。
- `ditto_execution.rules`、`ditto_execution.reality.market`、`ditto_execution.reality.constants`、`ditto_execution.reality.fee` 仍把 kernel trading 类型/常量借 execution 暴露。
- `ditto_features.models.derived`、`ditto_features.publication_safety` 等模块仍在 `__all__` 中暴露 kernel 拥有的类型。
- 当前 `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py` 只做字符串黑名单，漏掉 exact barrel、`__all__` re-export、纯 shim 文件和未来新增同类问题。

本计划不再靠人工记黑名单收尾，而是把“禁止跨包 re-export”升级成源码级可验证规则。

## Required Final State

完成标准：

- `pixi run -e dev check` 退出码为 0。
- `pixi run -e dev arch-check` 退出码为 0。
- `scripts/architecture/check_architecture_smells.py --verbose` 报告跨包 re-export 检查通过。
- 全库没有生产或测试代码通过以下旧路径导入 canonical owner 类型：
  - `ditto_data.storage.sqlite_client.SQLiteClient`
  - `ditto_data.SQLiteClient`
  - `ditto_data.models.common.Json*`
  - `ditto_data.models.common.require_*`
  - `ditto_execution.reality.market.MarketSnapshot`
  - `ditto_execution.reality.constants.DEFAULT_*`
  - `ditto_execution.rules` 中的 kernel trading 类型
  - `ditto_execution.reality.fee.FeeModel`
- 所有保留的 facade 都是同包 facade 或精确 allowlist 项，allowlist 每一项都有注释说明为什么不是技术债。
- 不新增长期兼容 shim，不用 `TYPE_CHECKING` 隐藏依赖，不降低任何 lint/type/test/import-linter 规则。

## Current Inventory

### Must Remove

这些是明确架构违规，最终不应保留：

- `packages/data/src/ditto_data/storage/sqlite_client.py`
- `packages/data/src/ditto_data/__init__.py` 中的 `SQLiteClient`
- `packages/data/src/ditto_data/models/common.py` 中 JSON helper/type 的 public export
- `packages/data/src/ditto_data/quality/severity.py`
- `packages/execution/src/ditto_execution/reality/market.py`
- `packages/execution/src/ditto_execution/reality/constants.py`
- `packages/execution/src/ditto_execution/rules.py` 中 kernel trading 符号的 public export
- `packages/execution/src/ditto_execution/reality/fee.py` 中 `FeeModel` 的 public export
- `packages/features/src/ditto_features/models/derived.py` 中 JSON type 的 public export
- `packages/features/src/ditto_features/publication_safety.py` 中 kernel strategy 类型的 public export
- `packages/application/src/ditto_application/processes/materialization/helpers.py` 的 backward-compatible shim 说明和任何纯兼容路径

### Must Classify

这些不是立即删除前能凭字符串判断的问题，必须逐项做源码消费者检查，并在代码中删除、迁移或写入精确 allowlist：

- `packages/application/src/ditto_application/config.py`
  - `Dataset <- ditto_data.models`
  - `DataStoreSettings <- ditto_data.config.data_store`
- `packages/apps/src/ditto_apps/registry/infra/config.py`
  - `DataStoreSettings <- ditto_data.config.data_store`
- `packages/data/src/ditto_data/models/macro.py`
  - `MacroCategory`、`MacroFrequency <- ditto_kernel.market`
- `packages/data/src/ditto_data/errors.py`
  - `DataError`、`IdentifierError <- ditto_kernel.exceptions`
- `packages/execution/src/ditto_execution/audit/models.py`
  - `RiskScope <- ditto_kernel.strategy`
- `packages/portfolio/src/ditto_portfolio/accounting/order_book.py`
  - `OrderSide`、`OrderType <- ditto_kernel.order`
- `packages/risk/src/ditto_risk/post_trade.py`
  - `RiskScope <- ditto_kernel.strategy`
- `packages/risk/src/ditto_risk/pre_trade.py`
  - `InstrumentId <- ditto_kernel.instrument`
- `packages/risk/src/ditto_risk/constraints/context.py`
  - `InstrumentId <- ditto_kernel.instrument`

默认处理策略：如果符号只是类型注解所需，保留私有 import 但从 `__all__` 移除；如果外部消费者从非 owner 包导入该符号，迁移消费者到 owner 包；如果确实是 application composition API，必须创建精确 allowlist 注释，说明为什么这是边界契约而不是兼容 shim。

## Execution Rules

1. 用 TDD：先让门禁能捕获当前问题，再修源码。
2. 每个 task 单独提交。
3. 每次删除 shim 前先跑 `rg` 找所有消费者。
4. 不保留“为了兼容旧路径”的 re-export。
5. 不把跨包 re-export 从一个文件移动到另一个文件。
6. 不把架构违规改成 allowlist 来快速通过；allowlist 只能用于明确设计边界。
7. 所有手工编辑使用 `apply_patch`。

---

## Task 0: Baseline and Red Inventory

**Files:**
- Read: `docs/plans/2026-05-04-capability-architecture-quality-remediation.md`
- Read: `docs/plans/2026-05-04-capability-architecture-final-completion-plan.md`
- Read: `scripts/architecture/check_architecture_smells.py`
- Read: `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`

**Step 1: Confirm branch and cleanliness**

Run:

```bash
git branch --show-current
git status --short
```

Expected:

```text
architecture-refactor
```

Only this plan file may be untracked before implementation starts. If user changes exist, record them and do not revert them.

**Step 2: Prove current gates are green but incomplete**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> 6067 passed, 25 skipped
import-linter -> 36 kept, 0 broken
Architecture smell check passed.
```

**Step 3: Capture current offenders**

Run:

```bash
python - <<'PY'
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path("packages")
TOP_TO_PACKAGE = {
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

def owner_for(path: Path) -> str | None:
    parts = path.parts
    if len(parts) >= 4 and parts[0] == "packages":
        return parts[1]
    return None

for path in sorted(ROOT.glob("*/src/**/*.py")):
    owner = owner_for(path)
    if owner is None:
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: dict[str, str] = {}
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            src_owner = TOP_TO_PACKAGE.get(node.module.split(".")[0])
            if src_owner and src_owner != owner:
                for alias in node.names:
                    imports[alias.asname or alias.name] = node.module
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported.add(elt.value)
    matches = sorted((name, mod) for name, mod in imports.items() if name in exported)
    if matches:
        print(path)
        for name, mod in matches:
            print(f"  {name} <- {mod}")
PY
```

Expected: output includes the `Must Remove` and `Must Classify` inventory above.

**Step 4: Commit**

No code commit for baseline. Keep the inventory in the task notes or PR description.

---

## Task 1: Add AST Cross-Package Re-Export Gate

**Files:**
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify: `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`
- Create: `packages/apps/tests/unit/architecture/test_cross_package_reexport_detector_unit.py`

**Problem:**

Current guard is a string blacklist. It does not parse `__all__`, cannot detect newly introduced cross-package exports, and misses exact module barrels such as `ditto_data.storage.sqlite_client`.

**Step 1: RED - Add detector unit tests**

Create `packages/apps/tests/unit/architecture/test_cross_package_reexport_detector_unit.py`:

```python
"""Cross-package re-export detector behavior."""

from pathlib import Path

from scripts.architecture.check_architecture_smells import (
    CrossPackageExport,
    find_cross_package_exports,
)


def test_detector_finds_imported_symbol_exported_in_all(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "data" / "src" / "ditto_data" / "shim.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_platform.foundation.storage.sqlite_client import SQLiteClient\n"
        "__all__ = ['SQLiteClient']\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == [
        CrossPackageExport(
            path=src.relative_to(tmp_path).as_posix(),
            exported_name="SQLiteClient",
            imported_from="ditto_platform.foundation.storage.sqlite_client",
            owner_package="data",
            source_package="platform",
        )
    ]


def test_detector_ignores_private_annotation_imports(tmp_path: Path) -> None:
    src = tmp_path / "packages" / "risk" / "src" / "ditto_risk" / "model.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "from ditto_kernel.strategy import RiskScope\n"
        "__all__ = ['RiskResult']\n"
        "class RiskResult: ...\n",
        encoding="utf-8",
    )

    assert find_cross_package_exports(tmp_path) == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_cross_package_reexport_detector_unit.py -q --no-cov
```

Expected: FAIL because the detector does not exist.

**Step 2: GREEN - Implement detector in architecture smell checker**

Add a frozen dataclass and detector helpers to `scripts/architecture/check_architecture_smells.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CrossPackageExport:
    path: str
    exported_name: str
    imported_from: str
    owner_package: str
    source_package: str
```

Implement `find_cross_package_exports(root: Path = ROOT) -> list[CrossPackageExport]`:

- Walk `packages/*/src/**/*.py`.
- Determine owner from `packages/<owner>/src`.
- Parse `ast.ImportFrom` nodes.
- Record imported names whose top-level module maps to another Ditto package.
- Parse literal `__all__` string lists/tuples.
- Report any imported cross-package name that appears in `__all__`.
- Also report pure shim modules that contain only import/export statements and expose a cross-package symbol, even if `__all__` is missing.
- Skip test files and `__pycache__`.
- Apply `ALLOWED_CROSS_PACKAGE_EXPORTS` only for exact `(path, exported_name, imported_from)` triples with a reason comment.

Call this from `main()` so `pixi run -e dev arch-check` fails while current offenders remain.

**Step 3: Replace string blacklist test with checker integration**

Modify `packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py`:

```python
"""No hidden cross-package re-export debt."""

from pathlib import Path

from scripts.architecture.check_architecture_smells import check_cross_package_exports


def test_no_unapproved_cross_package_reexports() -> None:
    assert check_cross_package_exports(Path.cwd()) == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_cross_package_reexport_detector_unit.py packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py -q --no-cov
```

Expected: detector behavior tests PASS; architecture test FAIL and lists current offenders.

**Step 4: Commit**

```bash
git add scripts/architecture/check_architecture_smells.py packages/apps/tests/unit/architecture/test_no_cross_package_reexports_unit.py packages/apps/tests/unit/architecture/test_cross_package_reexport_detector_unit.py
git commit -m "test: detect cross-package re-export debt"
```

---

## Task 2: Remove Data Platform and Kernel Re-Export Debt

**Files:**
- Modify: `packages/data/src/ditto_data/__init__.py`
- Delete: `packages/data/src/ditto_data/storage/sqlite_client.py`
- Modify: `packages/data/src/ditto_data/models/common.py`
- Modify: `packages/data/src/ditto_data/models/__init__.py`
- Delete: `packages/data/src/ditto_data/quality/severity.py`
- Modify: `packages/data/src/ditto_data/errors.py`
- Modify: `packages/data/src/ditto_data/storage/runtime/publication_safety/_json_records.py`
- Modify: `packages/application/src/ditto_application/providers.py`
- Modify: all consumers found by `rg`

**Step 1: Locate consumers**

Run:

```bash
rg -n "from ditto_data\.storage\.sqlite_client import|from ditto_data import SQLiteClient|from ditto_data\.models\.common import (Json|.*Json|.*require_)|from ditto_data\.quality\.severity import|from ditto_data\.errors import (DataError|IdentifierError)" packages -g '*.py'
```

Expected before cleanup: many `SQLiteClient` matches and at least `_json_records.py` for `JsonDict`.

**Step 2: Migrate `SQLiteClient` to platform canonical owner**

Replace every:

```python
from ditto_data.storage.sqlite_client import SQLiteClient
```

and:

```python
from ditto_data import SQLiteClient
```

with:

```python
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
```

Do this in production and tests. Do not create another data-level alias.

**Step 3: Remove data top-level export**

Modify `packages/data/src/ditto_data/__init__.py`:

- Delete `from ditto_data.storage.sqlite_client import SQLiteClient`.
- Delete `"SQLiteClient"` from `__all__`.
- Keep only data-owned provider/event exports.

**Step 4: Delete sqlite shim**

Delete:

```text
packages/data/src/ditto_data/storage/sqlite_client.py
```

**Step 5: Migrate JSON helper imports to kernel**

In `packages/data/src/ditto_data/storage/runtime/publication_safety/_json_records.py`, replace:

```python
from ditto_data.models.common import JsonDict
```

with:

```python
from ditto_kernel.json_types import JsonDict
```

Then remove these names from `packages/data/src/ditto_data/models/common.py` `__all__`:

- `JsonDict`
- `JsonPrimitive`
- `JsonValue`
- `require_bool`
- `require_int`
- `require_payload`
- `require_str`

If `common.py` still needs them internally, keep private imports. If not, delete the imports.

**Step 6: Remove unused quality severity shim**

Run:

```bash
rg -n "ditto_data\.quality\.severity|from ditto_data\.quality import DQSeverity" packages -g '*.py'
```

Expected: no active consumers. Then delete `packages/data/src/ditto_data/quality/severity.py` and remove any package export pointing to it.

**Step 7: Remove inherited kernel errors from data public API**

In `packages/data/src/ditto_data/errors.py`, keep `DataError` / `IdentifierError` imports only if subclasses need them, but remove them from `__all__` unless a consumer truly imports them through `ditto_data.errors`.

Run:

```bash
rg -n "from ditto_data\.errors import (DataError|IdentifierError)" packages -g '*.py'
```

Expected after cleanup: no matches.

**Step 8: Verify data cleanup**

Run:

```bash
pixi run -e dev pytest packages/data/tests -q
pixi run -e dev pytest packages/application/tests/unit/process/materialization packages/apps/tests/unit/registry packages/apps/tests/integration/flows/test_research_dataset_integration.py -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: all pass except Task 1 cross-package guard may still fail on execution/features/classification items.

**Step 9: Commit**

```bash
git add packages/data packages/application packages/apps
git add -u packages/data/src/ditto_data/storage/sqlite_client.py packages/data/src/ditto_data/quality/severity.py
git commit -m "refactor: remove data cross-package re-export shims"
```

---

## Task 3: Remove Execution Kernel Trading Re-Export Debt

**Files:**
- Modify: `packages/execution/src/ditto_execution/rules.py`
- Delete: `packages/execution/src/ditto_execution/reality/market.py`
- Delete: `packages/execution/src/ditto_execution/reality/constants.py`
- Modify: `packages/execution/src/ditto_execution/reality/fee.py`
- Modify: `packages/execution/src/ditto_execution/reality/__init__.py`
- Modify: all production/test consumers found by `rg`

**Step 1: Locate consumers**

Run:

```bash
rg -n "from ditto_execution\.(rules|reality\.market|reality\.constants|reality\.fee) import" packages -g '*.py'
```

Expected before cleanup: consumers across `backtest`, `execution`, `risk`, `application`, and tests.

**Step 2: Migrate kernel trading types and constants**

Replace imports of these names from `ditto_execution.rules` with `ditto_kernel.trading`:

- `FeeSchedule`
- `InstrumentDefinition`
- `InstrumentRuleProvider`
- `InstrumentRules`
- `RulesGetter`
- `TradingRuleSet`
- `default_price_limit_pct`

Replace:

```python
from ditto_execution.reality.market import MarketSnapshot
```

with:

```python
from ditto_kernel.trading import MarketSnapshot
```

Replace:

```python
from ditto_execution.reality.constants import DEFAULT_COMMISSION_RATE
```

with canonical imports from:

```python
from ditto_kernel.trading import (
    DEFAULT_COMMISSION_RATE,
    DEFAULT_LOT_SIZE,
    DEFAULT_MIN_COMMISSION,
)
```

Replace:

```python
from ditto_execution.reality.fee import FeeModel
```

with:

```python
from ditto_kernel.trading import FeeModel
```

Keep imports of execution-owned concrete implementations in execution:

```python
from ditto_execution.rules import InMemoryRuleProvider
from ditto_execution.reality.fee import AShareFeeModel, SimpleFeeModel
```

**Step 3: Shrink `ditto_execution.rules` API**

Modify `packages/execution/src/ditto_execution/rules.py`:

- Keep private imports from `ditto_kernel.trading` for annotations and implementation.
- Keep `InMemoryRuleProvider`.
- Remove all kernel-owned names from `__all__`.
- Ensure `__all__ == ["InMemoryRuleProvider"]` unless the module defines additional execution-owned objects.

**Step 4: Delete pure re-export modules**

Delete:

```text
packages/execution/src/ditto_execution/reality/market.py
packages/execution/src/ditto_execution/reality/constants.py
```

Modify `packages/execution/src/ditto_execution/reality/__init__.py`:

- Remove `FeeModel`, `MarketSnapshot`, and any DEFAULT constants from imports and `__all__`.
- Keep only execution-owned concrete models and protocols defined in execution modules.

**Step 5: Verify execution cleanup**

Run:

```bash
pixi run -e dev pytest packages/execution/tests packages/backtest/tests packages/risk/tests packages/application/tests/unit/process/execution -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: tests/type pass; cross-package guard may still fail on Task 4/5 items only.

**Step 6: Commit**

```bash
git add packages/execution packages/backtest packages/risk packages/application
git add -u packages/execution/src/ditto_execution/reality/market.py packages/execution/src/ditto_execution/reality/constants.py
git commit -m "refactor: import trading contracts from kernel owner"
```

---

## Task 4: Remove Features and Domain Model Public Re-Export Debt

**Files:**
- Modify: `packages/features/src/ditto_features/models/derived.py`
- Modify: `packages/features/src/ditto_features/publication_safety.py`
- Modify: `packages/data/src/ditto_data/models/macro.py`
- Modify: `packages/execution/src/ditto_execution/audit/models.py`
- Modify: `packages/portfolio/src/ditto_portfolio/accounting/order_book.py`
- Modify: `packages/risk/src/ditto_risk/post_trade.py`
- Modify: `packages/risk/src/ditto_risk/pre_trade.py`
- Modify: `packages/risk/src/ditto_risk/constraints/context.py`
- Modify: all consumers found by `rg`

**Step 1: Locate exact consumers**

Run:

```bash
rg -n "from ditto_features\.models\.derived import (JsonDict|JsonValue)|from ditto_features\.publication_safety import (DerivedRole|MaterializationProfile)|from ditto_data\.models\.macro import (MacroCategory|MacroFrequency)|from ditto_execution\.audit\.models import RiskScope|from ditto_portfolio\.accounting\.order_book import (OrderSide|OrderType)|from ditto_risk\.(post_trade|pre_trade) import (RiskScope|InstrumentId)|from ditto_risk\.constraints\.context import InstrumentId" packages -g '*.py'
```

Expected: every match must be either migrated or documented as an exact allowed public API decision.

**Step 2: Remove JSON exports from features derived models**

In `packages/features/src/ditto_features/models/derived.py`:

- Keep `JsonDict` / `JsonValue` imports only if annotations require them.
- Remove them from `__all__`.
- Update any external consumer to import from `ditto_kernel.json_types`.

**Step 3: Remove strategy type exports from features publication safety**

In `packages/features/src/ditto_features/publication_safety.py`:

- Keep `DerivedRole` / `MaterializationProfile` imports only if implementation needs them.
- Remove them from `__all__`.
- Update consumers to import from `ditto_kernel.strategy`.

**Step 4: Clean model modules that only need annotation imports**

For each `Must Classify` model module:

1. If the imported kernel symbol is present in `__all__`, remove it.
2. If any consumer imports that symbol from the non-owner module, migrate consumer to canonical owner.
3. If the module only exposes classes that contain fields of that type, keep the import private and let the class remain public.

Canonical owners:

```text
MacroCategory, MacroFrequency -> ditto_kernel.market
RiskScope -> ditto_kernel.strategy
OrderSide, OrderType -> ditto_kernel.order
InstrumentId -> ditto_kernel.instrument
DataError, IdentifierError -> ditto_kernel.exceptions
```

**Step 5: Verify domain cleanup**

Run:

```bash
pixi run -e dev pytest packages/features/tests packages/risk/tests packages/portfolio/tests packages/execution/tests packages/data/tests -q
pixi run -e dev type
pixi run -e dev arch-check
```

Expected: all pass except any intentionally unresolved application composition API items from Task 5.

**Step 6: Commit**

```bash
git add packages/features packages/data packages/execution packages/portfolio packages/risk
git commit -m "refactor: stop exporting kernel types from capability modules"
```

---

## Task 5: Resolve Application and Apps Composition Boundary Exports

**Files:**
- Modify: `packages/application/src/ditto_application/config.py`
- Modify: `packages/apps/src/ditto_apps/registry/infra/config.py`
- Modify: consumer files found by `rg`
- Modify: `scripts/architecture/check_architecture_smells.py`

**Problem:**

`application.config` currently exposes lower-layer data types as an app-facing route. This was useful for blocking direct `apps -> data.models` imports, but it is still a cross-package public export unless it is treated as a deliberate application API.

**Step 1: Locate consumers**

Run:

```bash
rg -n "from ditto_application\.config import .*\\b(Dataset|DataStoreSettings)\\b|from ditto_apps\.registry\.infra\.config import .*\\bDataStoreSettings\\b|from ditto_data\.models import Dataset|from ditto_data\.config\.data_store import DataStoreSettings" packages -g '*.py'
```

**Step 2: Prefer owning application-facing DTOs**

If consumers only need configuration parsing or app scheduling, create application-owned types instead of re-exporting data-owned classes:

- Keep `DatasetSpec`, `TaskTier`, `T1ConfigSpec`, and helpers owned by `ditto_application.config`.
- Introduce an application-owned alias only if it is a real new type, not a re-export. Preferred names:
  - `DatasetKey` for app-facing dataset identifiers, if splitting from data `Dataset` is practical.
  - `ApplicationDataStoreSettings` if apps need config shape without direct data config import.

If this would be too large for this cleanup, use Step 3 and record a follow-up in docs, but do not hide it as a generic allowlist.

**Step 3: If retaining as boundary API, allowlist exactly**

Only if the source audit proves these are intentional composition boundary exports, add exact allowlist entries in `scripts/architecture/check_architecture_smells.py`:

```python
ALLOWED_CROSS_PACKAGE_EXPORTS = {
    (
        "packages/application/src/ditto_application/config.py",
        "Dataset",
        "ditto_data.models",
    ): "application.config is the app-facing dataset scheduling contract; apps are intentionally barred from ditto_data.models",
    (
        "packages/application/src/ditto_application/config.py",
        "DataStoreSettings",
        "ditto_data.config.data_store",
    ): "application config is the composition boundary for app data-store wiring",
}
```

Do not add broad module-level allowlists. Do not allowlist `apps.registry.infra.config` unless it is strictly registry-only wiring and cannot become an application-owned DTO yet.

**Step 4: Verify no accidental apps direct data imports**

Run:

```bash
rg -n "from ditto_data\.(models|services|errors|quality|config) import|import ditto_data\.(models|services|errors|quality|config)" packages/apps/src -g '*.py'
```

Expected: no matches outside documented registry exceptions already covered by import-linter.

**Step 5: Verify application boundary**

Run:

```bash
pixi run -e dev pytest packages/application/tests packages/apps/tests -q
pixi run -e dev arch-check
```

Expected: arch-check has no cross-package export errors except exact allowlist entries with reasons.

**Step 6: Commit**

```bash
git add packages/application packages/apps scripts/architecture/check_architecture_smells.py
git commit -m "refactor: classify application composition exports"
```

---

## Task 6: Remove Same-Package Compatibility Shim Language and Stale Docs

**Files:**
- Modify: `packages/application/src/ditto_application/processes/materialization/helpers.py`
- Modify: `packages/application/CLAUDE.md`
- Modify: `packages/data/CLAUDE.md`
- Modify: package docs found by `rg`
- Modify: source comments found by `rg`

**Step 1: Scan stale compatibility language**

Run:

```bash
rg -n "Re-export|re-export|backward compat|Backward-compatible|compatibility shim|canonical owner|moved to|Import them directly" packages docs/architecture CLAUDE.md -g '*.py' -g '*.md'
```

Expected before cleanup: source comments still mention backward compatibility and re-export shims.

**Step 2: Delete or rewrite stale source comments**

Rules:

- If the file is a pure compatibility shim and has no architectural value, delete it after consumers migrate.
- If it is a same-package public facade, rewrite the comment as public API organization, not backward compatibility.
- If it says a type “moved to canonical owner,” the file should no longer export that type.

Known required edits:

- `packages/application/src/ditto_application/processes/materialization/helpers.py`: either delete after consumers import split leaf helpers directly, or rewrite as same-package public facade with no “backward-compatible shim” language.
- `packages/data/CLAUDE.md`: remove “storage/base re-export from platform” as a recommended pattern once Task 2 completes.
- `packages/application/CLAUDE.md`: replace `__init__.py # re-export shim` wording with “public package API facade” only if the facade is same-package.

**Step 3: Verify stale language**

Run:

```bash
rg -n "backward compat|Backward-compatible|compatibility shim|Re-export .*from ditto_|re-export .*from ditto_" packages -g '*.py' -g '*.md'
```

Expected: no active source/package docs describe cross-package compatibility shims.

**Step 4: Commit**

```bash
git add packages docs/architecture CLAUDE.md
git commit -m "docs: remove stale compatibility shim guidance"
```

---

## Task 7: Final Architecture Gate and Exhaustive Negative Searches

**Files:**
- Verify only; no planned source edits.

**Step 1: Run targeted negative search**

Run:

```bash
rg -n "from ditto_data\.storage\.sqlite_client import|from ditto_data import SQLiteClient|from ditto_data\.models\.common import (Json|.*Json|.*require_)|from ditto_data\.quality\.severity import|from ditto_execution\.reality\.market import|from ditto_execution\.reality\.constants import|from ditto_execution\.rules import (FeeSchedule|InstrumentDefinition|InstrumentRuleProvider|InstrumentRules|RulesGetter|TradingRuleSet|default_price_limit_pct)|from ditto_execution\.reality\.fee import FeeModel|from ditto_features\.models\.derived import (JsonDict|JsonValue)|from ditto_features\.publication_safety import (DerivedRole|MaterializationProfile)" packages -g '*.py'
```

Expected:

```text
<no output>
```

If matches remain only in architecture tests that assert forbidden strings, update the test to use the AST checker and remove literal old-path strings from source scans.

**Step 2: Run AST inventory**

Run the inventory script from Task 0 again.

Expected:

- No `Must Remove` entries remain.
- Any `Must Classify` entry that remains is listed in `ALLOWED_CROSS_PACKAGE_EXPORTS` with exact path, symbol, imported module, and reason.

**Step 3: Run full quality gate**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . -> All checks passed
ruff format . -> files unchanged
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> pass
import-linter -> all contracts kept
Architecture smell check passed.
```

**Step 4: Run architecture gate explicitly**

Run:

```bash
pixi run -e dev arch-check
```

Expected:

```text
Architecture smell check passed.
```

**Step 5: Check worktree**

Run:

```bash
git status --short
```

Expected: only intentional committed changes; no stray generated files.

**Step 6: Final commit if needed**

If Task 7 required small verification fixes:

```bash
git add <fixed-files>
git commit -m "chore: close final architecture re-export gaps"
```

---

## Review Checklist

Before claiming completion, verify all items:

- [ ] No deleted shim path has active consumers.
- [ ] No capability package exports a symbol owned by another package through `__all__`.
- [ ] No pure cross-package shim file remains under `packages/*/src`.
- [ ] Application/apps exceptions, if any, are exact and justified.
- [ ] Same-package facades are described as public API organization, not backward compatibility.
- [ ] `pixi run -e dev check` passes.
- [ ] `pixi run -e dev arch-check` passes.
- [ ] The final PR summary includes the before/after import ownership rule.
