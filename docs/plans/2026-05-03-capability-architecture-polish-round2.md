# Capability Architecture Polish Round 2

> **Status:** ✅ COMPLETED (2026-05-03)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复架构审计发现的所有遗漏和偏差，消除 features→data 的 import-linter ignore_imports，对齐文档格式。

**Architecture:** 纯包结构和文档修复，不引入新功能。存储基类下沉到 platform；features 域类型回归 features；文档格式统一。

**Tech Stack:** Python 3.13, ruff, basedpyright, pytest, import-linter.

---

## Execution Rules

1. 每个 task 单独提交，提交前至少运行 task 内指定验证命令。
2. 不引入新功能，不改变外部行为。
3. 每次 import 变更先用 `rg` 定位引用，再改，再跑 type + arch-check。

## Global Verification Commands

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # import-linter + smell check
```

---

### Task 1: Stale Artifacts Cleanup & CLAUDE.md Alignment `[S]`

**Files:**
- Delete (local only): `packages/platform/src/ditto_infra.egg-info/`
- Delete (local only): `packages/application/src/ditto_app.egg-info/`
- Modify: `packages/application/CLAUDE.md`
- Modify: `packages/apps/CLAUDE.md`

**Context:** egg-info 目录已在 .gitignore 中（不在 git 里），只需本地清理。application 和 apps 的 CLAUDE.md 缺少标准格式段。

**Step 1: Delete stale egg-info artifacts**

```bash
rm -rf packages/platform/src/ditto_infra.egg-info
rm -rf packages/application/src/ditto_app.egg-info
```

**Step 2: Normalize application/CLAUDE.md**

将当前的单一 `## 依赖` 段拆分为 `## 允许依赖` + `## 禁止依赖`。添加 `## 典型导入示例` 和 `## 常用验证命令` 段。将 `## CQRS 模块结构` 重命名为 `## 内部目录职责`，`## 测试规范` 重命名为 `## 测试位置`。

保留所有现有内容，仅调整段名和格式，使其与 strategy/portfolio/risk/execution/backtest/features/analysis 的 7 段标准格式对齐：

```text
1. 定位
2. 允许依赖
3. 禁止依赖
4. 内部目录职责
5. 测试位置
6. 典型导入示例
7. 常用验证命令
```

**Step 3: Normalize apps/CLAUDE.md**

同样调整为标准 7 段格式。将 `## 模块结构` → `## 内部目录职责`，`## 依赖规则` → `## 允许依赖` + `## 禁止依赖`，`## 测试规范` → `## 测试位置`。

**Step 4: Verify**

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
```

**Step 5: Commit**

```bash
git add packages/application/CLAUDE.md packages/apps/CLAUDE.md
git commit -m "docs: normalize application and apps CLAUDE.md format"
```

---

### Task 2: Extract Storage Base Classes to Platform `[L]`

**Files:**
- Create: `packages/platform/src/ditto_platform/foundation/storage/__init__.py`
- Create: `packages/platform/src/ditto_platform/foundation/storage/parquet_store.py`
- Create: `packages/platform/src/ditto_platform/foundation/storage/partition_strategy.py`
- Create: `packages/platform/src/ditto_platform/foundation/storage/protocols.py`
- Create: `packages/platform/src/ditto_platform/foundation/storage/types.py`
- Create: `packages/platform/src/ditto_platform/foundation/storage/sqlite_client.py`
- Modify: `packages/platform/src/ditto_platform/foundation/__init__.py`
- Modify: `packages/data/src/ditto_data/storage/base/__init__.py`
- Modify: `packages/data/src/ditto_data/storage/base/parquet_store.py` → re-export from platform
- Modify: `packages/data/src/ditto_data/storage/base/partition_strategy.py` → re-export from platform
- Modify: `packages/data/src/ditto_data/storage/base/protocols.py` → re-export from platform
- Modify: `packages/data/src/ditto_data/models/storage.py` → re-export OnDuplicate/WriteStoreResult from platform
- Modify: `packages/data/src/ditto_data/storage/sqlite_client.py` → 使用 platform 的通用 SQLiteClient
- Modify: 4 features files (factor_writer, factor_reader, technical_indicator_reader, technical_indicator_writer)
- Modify: 7 features files (SQLiteClient usage: di/storage, factor_metadata_reader/writer, derived reader/writer, technical metadata reader/writer)
- Modify: 3 analysis files (SQLiteClient: di/storage, research reader/writer)
- Modify: `packages/features/src/ditto_features/models/derived.py` (imports from data.models.common)

**Context:** 当前 features 的 22 处 import 指向 data 的存储基类。将通用存储基础设施移到 platform，data 的 storage.base 变为从 platform re-export 的薄层，features 直接从 platform 导入。

**设计决策：**

1. **SQLiteClient 处理**：创建 platform 通用版（无 ALLOWED_TABLES），data 的 SQLiteClient 继承扩展
2. **ParquetStore**：整体移到 platform（纯 I/O 工具，无业务逻辑）
3. **OnDuplicate/WriteStoreResult**：移到 platform.foundation.storage.types（通用存储操作类型）
4. **data.storage.base 内部 re-export**：data 内部 20+ 文件仍从 `data.storage.base` 导入，改为 re-export platform 版本。这是同包 re-export（非跨包），不违反 re-export 规则。

**Step 1: Create platform.foundation.storage package**

创建 `packages/platform/src/ditto_platform/foundation/storage/` 目录。

`__init__.py`:
```python
"""Platform storage abstractions."""

from ditto_platform.foundation.storage.parquet_store import MergeResult, ParquetStore
from ditto_platform.foundation.storage.partition_strategy import (
    PartitionStrategy,
    YearlyPartition,
)
from ditto_platform.foundation.storage.protocols import (
    DatasetReader,
    DatasetWriter,
    SqliteReader,
    SqliteWriter,
)
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation.storage.types import (
    OnDuplicate,
    WriteStoreResult,
    WriteResult,
)

__all__ = [
    "DatasetReader",
    "DatasetWriter",
    "MergeResult",
    "OnDuplicate",
    "ParquetStore",
    "PartitionStrategy",
    "SQLiteClient",
    "SqliteReader",
    "SqliteWriter",
    "WriteResult",
    "WriteStoreResult",
    "YearlyPartition",
]
```

**Step 2: Move storage types to platform**

将以下文件内容复制（git mv 保留历史）到 platform，调整 import：

| 源文件 | 目标 |
|--------|------|
| `data.storage.base.parquet_store` | `platform.foundation.storage.parquet_store` |
| `data.storage.base.partition_strategy` | `platform.foundation.storage.partition_strategy` |
| `data.storage.base.protocols` | `platform.foundation.storage.protocols` |
| `data.models.storage` (OnDuplicate 移自 models.common) | `platform.foundation.storage.types` |
| 新文件：通用 SQLiteClient | `platform.foundation.storage.sqlite_client` |

关键变更：
- `parquet_store.py` 中的 `from ditto_data.models.storage import WriteStoreResult` → `from ditto_platform.foundation.storage.types import WriteStoreResult`
- `sqlite_client.py`：复制 data 版本但**去掉 ALLOWED_TABLES**，改为纯通用客户端
- `types.py`：包含 `OnDuplicate`（从 data.models.common 移入）、`WriteStoreResult`、`WriteResult`（从 data.models.storage 移入）

**Step 3: Update data.storage.base to re-export from platform**

`data.storage.base.__init__.py` 改为：
```python
"""Base store abstractions — re-exported from platform."""

from ditto_platform.foundation.storage import (  # noqa: F401
    DatasetReader,
    DatasetWriter,
    MergeResult,
    ParquetStore,
    PartitionStrategy,
    SQLiteStore,  # 注意：SQLiteStore 留在 data，不迁移
    SqliteReader,
    SqliteWriter,
    YearlyPartition,
)
```

注意：`SQLiteStore` 是 data 特有的（含 data 域 SQL 逻辑），留在 data 不迁移。

`data.storage.sqlite_client.py` 改为继承 platform 通用版：
```python
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient as _BaseSQLiteClient

class SQLiteClient(_BaseSQLiteClient):
    """Data-domain SQLite client with table whitelist."""
    ALLOWED_TABLES = frozenset([...])  # 保留原有白名单
```

`data.models.storage.py` 改为 re-export：
```python
from ditto_platform.foundation.storage.types import (  # noqa: F401
    FreezeManifest,
    WriteResult,
    WriteStoreResult,
)
```

**Step 4: Update features imports**

features 的 22 处 `from ditto_data.*` import 全部改为 `from ditto_platform.foundation.storage.*`：

```python
# Before
from ditto_data.storage.base import ParquetStore, YearlyPartition
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_data.models import OnDuplicate
from ditto_data.models.storage import WriteStoreResult as WriteResult

# After
from ditto_platform.foundation.storage import (
    ParquetStore, YearlyPartition, SQLiteClient, OnDuplicate, WriteStoreResult as WriteResult,
)
```

**Step 5: Update analysis imports**

analysis 的 3 处 SQLiteClient import 同样改为 platform：
```python
# Before
from ditto_data.storage.sqlite_client import SQLiteClient
# After
from ditto_platform.foundation.storage import SQLiteClient
```

**Step 6: Verify**

```bash
rg -n "from ditto_data\.(storage\.base|storage\.sqlite_client|models\.storage)" packages/features packages/analysis --include="*.py"
# Expected: 0 matches

pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/platform packages/data packages/features packages/analysis
git commit -m "refactor: extract storage base classes to platform package"
```

---

### Task 3: Re-Home Features-Domain Types `[M]`

**Files:**
- Modify: `packages/features/src/ditto_features/errors.py` — 添加 Derived* 错误类型
- Modify: `packages/features/src/ditto_features/models/derived.py` — 消除 data.models.common 依赖
- Create/Modify: `packages/features/src/ditto_features/models/publication_safety.py` — 添加记录类型
- Modify: `packages/features/src/ditto_features/publication_safety.py` — 如果引用 data 记录类型
- Modify: `packages/features/src/ditto_features/validation.py` — 改用 features.errors
- Modify: `packages/features/src/ditto_features/services/derived/*.py` — 改用 features.errors
- Modify: `packages/kernel/src/ditto_kernel/` — 添加 JSON 工具类型（如需要）

**Context:** features→data 的剩余依赖是 features 域类型（Derived* 错误、publication_safety 记录、JSON 工具类型）在初始拆分时留在了 data 中。

**Step 1: Move Derived* errors to features**

在 `packages/features/src/ditto_features/errors.py` 中添加：

```python
class DerivedError(DittoError):
    """Base for derived domain errors."""

class DerivedNotFoundError(DerivedError):
    ...

class DerivedVersionError(DerivedError):
    ...

class DerivedNotImplementedError(DerivedError):
    ...

class DerivedValidationError(DerivedError):
    ...
```

在 `data.errors.py` 中改为 re-export：
```python
from ditto_features.errors import (  # noqa: F401
    DerivedError,
    DerivedNotImplementedError,
    DerivedNotFoundError,
    DerivedValidationError,
    DerivedVersionError,
)
```

更新 features 的 3 处 import：
```python
# Before: from ditto_data.errors import DerivedNotFoundError
# After:  from ditto_features.errors import DerivedNotFoundError
```

**Step 2: Move JSON utility types to kernel**

将 `data.models.common` 中 features 需要的 JSON 类型移到 `ditto_kernel` 或保留在 features：

分析 `features/models/derived.py` 从 `data.models.common` 导入的具体符号：
- `JsonDict`, `JsonValue`, `JsonPrimitive` — 通用 JSON 类型 → kernel
- `require_str`, `require_int`, `require_bool`, `require_payload` — JSON 校验 → kernel

在 `kernel/` 添加 JSON 工具模块（或直接在 features 内定义）。

**策略**：如果 JSON 类型仅 features 和 data 使用，在 features 内部定义 + data re-export。如果 kernel 合理（无 data 依赖），放到 kernel。

**Step 3: Move publication_safety record types**

将 `data.models.publication_safety` 中 features 使用的记录类型移到 features：

```python
# features/models/publication_safety.py
# 从 data/models/publication_safety.py 移入 features 使用的类型：
# - DerivedShadowSlotRecord
# - CompatibilityManifestRecord
# - DerivedMinimalDQSummaryRecord
# - ShadowDiffReportRecord
# - ShadowTraceRecordRecord
# - CertificationReportRecord
```

data 的 `models/publication_safety.py` 改为从 features re-export（data 内部仍使用这些类型进行 publication_safety 存储操作）。

**Step 4: Update all features imports**

```bash
rg -n "from ditto_data\.(errors|models\.common|models\.publication_safety)" packages/features/src/ -g "*.py"
```

全部替换为 features 本地路径。

**Step 5: Verify**

```bash
rg -n "from ditto_data" packages/features/src/ -g "*.py"
# Expected: 0 matches

pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

**Step 6: Commit**

```bash
git add packages/features packages/data packages/kernel
git commit -m "refactor: re-home features-domain types from data to features"
```

---

### Task 4: Update Import-Linter Contracts `[S]`

**Files:**
- Modify: `.importlinter`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify: `packages/platform/CLAUDE.md` — 添加 storage 模块描述
- Modify: `packages/features/CLAUDE.md` — 更新依赖声明
- Modify: `packages/data/CLAUDE.md` — 更新依赖声明

**Context:** 移除 features-boundary 的全部 ignore_imports，更新合约反映新的依赖图。

**Step 1: Remove features-boundary ignore_imports**

在 `.importlinter` 的 `features-boundary` 合约中，删除所有 `ignore_imports`：

```ini
[importlinter:contract:features-boundary]
name = Features must not depend on Data/Engine/Strategy/Apps/Application/Analysis/Portfolio
type = forbidden
source_modules =
    ditto_features.**
forbidden_modules =
    ditto_data.**
    ditto_apps.**
    ditto_application.**
    ditto_analysis.**
    ditto_strategy.**
    ditto_portfolio.**
    ditto_risk.**
    ditto_execution.**
    ditto_backtest.**
# 无 ignore_imports — features 完全独立于 data
```

**Step 2: Add platform.storage contracts**

```ini
[importlinter:contract:platform-storage-no-business]
name = Platform storage must not contain business logic
type = forbidden
source_modules =
    ditto_platform.foundation.storage.**
forbidden_modules =
    ditto_data.**
    ditto_features.**
    ditto_strategy.**
    ditto_portfolio.**
    ditto_risk.**
    ditto_execution.**
    ditto_backtest.**
    ditto_analysis.**
    ditto_application.**
    ditto_apps.**
```

**Step 3: Update smell checker allowlist**

`PRODUCTION_ANALYSIS_WIRING_ALLOWLIST` 不变（application→analysis 依赖保持现状）。

确认 `PRODUCTION_PACKAGES` 中 features 不再需要特殊处理。

**Step 4: Update package CLAUDE.md docs**

更新以下文件的依赖段：
- `packages/platform/CLAUDE.md`：添加 storage 模块描述
- `packages/features/CLAUDE.md`：更新允许依赖（添加 `ditto_platform`，删除 `ditto_data`）
- `packages/data/CLAUDE.md`：注明 storage.base re-export from platform

**Step 5: Verify**

```bash
pixi run -e dev arch-check
pixi run -e dev type
pixi run -e dev test --fast
```

Expected: features-boundary contract KEPT with 0 ignore_imports.

**Step 6: Commit**

```bash
git add .importlinter scripts/architecture/check_architecture_smells.py packages/*/CLAUDE.md
git commit -m "test: remove features-boundary ignore_imports and update contracts"
```

---

### Task 5: Final Verification `[S]`

**Step 1: Run full gate**

```bash
pixi run -e dev check
```

Expected: all pass.

**Step 2: Verify no features→data imports remain**

```bash
rg -n "from ditto_data|import ditto_data" packages/features/src/ -g "*.py"
rg -n "from ditto_data|import ditto_data" packages/analysis/src/ -g "*.py"
```

Expected: 0 matches in features; analysis 只剩 `sqlite_client`（已迁移到 platform）。

**Step 3: Verify arch-check is clean**

```bash
pixi run -e dev arch-check
```

Expected: all 35+ contracts KEPT, 0 broken.

**Step 4: Commit any final fixes**

Only if verification reveals issues.

---

## Implementation Notes

### What this plan does NOT do

- **Application→Analysis**: 保持现状（application 作为编排层允许依赖 analysis）
- **SQLiteStore**: 留在 data（含 data 域 SQL 逻辑，不适合 platform）
- **data 内部 re-export 清理**: data.storage.base 对 platform 的 re-export 是同包便利层，长期可逐步消除
- **Execution 的 SQLiteClient 副本**: 本次不合并（execution 有自己的版本）

### Risk Assessment

| Task | Risk | Mitigation |
|------|------|-----------|
| Task 1 | 极低 | 文档编辑，不改代码 |
| Task 2 | 中 | 80+ import 变更，逐文件验证 type check |
| Task 3 | 中 | 类型迁移 + re-export，需验证 data 内部不受影响 |
| Task 4 | 低 | 纯配置变更，arch-check 即时反馈 |
| Task 5 | 极低 | 验证步骤 |

### Commit Cadence

4 substantive commits (Tasks 1-4) + 1 verification commit (Task 5, conditional).

Plan complete.
