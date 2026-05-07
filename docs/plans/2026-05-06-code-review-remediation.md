# Code Review 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PR #63 code review 中 8 个得分 >= 20 的问题

**Architecture:** 纯清理工作 — 文档/注释过期修正、重复代码消除、git 垃圾清理、noqa 替换为 docstring

**Tech Stack:** Python (dishka DI), import-linter, markdown docs

---

## 任务清单

### Task 1: 删除 `.merge-backups/` 备份文件 `[S]`

**Files:**
- Delete: `.merge-backups/2026-05-05-capability-remediation/test_capability_semantic_ownership_unit.py.bak`

**Step 1: 删除文件**

```bash
git rm .merge-backups/2026-05-05-capability-remediation/test_capability_semantic_ownership_unit.py.bak
```

**Step 2: 检查目录是否为空，如果是也删除目录**

```bash
rmdir .merge-backups/2026-05-05-capability-remediation/ 2>/dev/null; rmdir .merge-backups/ 2>/dev/null
```

**Step 3: 确认无其他 merge-backups 残留**

```bash
git ls-files .merge-backups/
# Expected: no output
```

**Step 4: Commit**

```bash
git commit -m "chore: remove accidentally committed .merge-backups file"
```

**验收:** `git ls-files .merge-backups/` 返回空

---

### Task 2: 修复 `.importlinter` 中残留 "Engine" 引用 `[S]`

**Files:**
- Modify: `.importlinter:125,128,145,148`

"Engine" 包已不存在，更新注释和合约名中的描述性文本。实际 `forbidden_modules` 列表无需改动（它们是正确的）。

**Step 1: 替换 4 处过期引用**

Line 125: `# Data 层边界：禁止依赖 Engine/Apps/App` -> `# Data 层边界：禁止依赖上层/同级包`
Line 128: `name = Data must not depend on Engine/Apps/App/Analytics/...` -> `name = Data must not depend on Apps/Application/Analytics/...`
Line 145: `# Features 层隔离：禁止依赖 Data/Engine/Strategy 等` -> `# Features 层隔离：禁止依赖 Data/Strategy 等`
Line 148: `name = Features must not depend on Data/Engine/Strategy/...` -> `name = Features must not depend on Data/Strategy/...`

**Step 2: 验证 lint-imports 仍通过**

```bash
pixi run -e dev lint-imports
# Expected: all contracts pass
```

**Step 3: Commit**

```bash
git add .importlinter
git commit -m "docs: remove stale Engine references from importlinter comments"
```

**验收:** `.importlinter` 中不含 `Engine` 字符串；`lint-imports` 通过

---

### Task 3: 修复 `docs/architecture/agent-context-pack.md` 合约数 `[S]`

**Files:**
- Modify: `docs/architecture/agent-context-pack.md:59`

**Step 1: 移除硬编码合约数**

将:
```
pixi run -e dev lint-imports                                # 34 kept, 0 broken
```
改为:
```
pixi run -e dev lint-imports                                # all pass
```

**Step 2: Commit**

```bash
git add docs/architecture/agent-context-pack.md
git commit -m "docs: remove hardcoded importlinter contract count"
```

**验收:** 文件中不含 "34 kept"

---

### Task 4: 修复 `.claude/rules/python.md` 中残留 "Interfaces" 层名 `[S]`

**Files:**
- Modify: `.claude/rules/python.md:604-667`

将所有 "Interfaces" 引用替换为当前正确的层名：
- "Interfaces Service" -> "Apps Service"
- "Interfaces Flow" -> "Application Flow"（对应 `ditto_application` 的 processes）
- 依赖方向 `Interfaces Flow → Interfaces Service → App Service` -> `Application Flow → Apps Service → Data Service`
- 代码示例中的 `Interfaces 层` -> `Apps 层`

**Step 1: 替换所有过期引用**

编辑 `.claude/rules/python.md`，在 596-669 行范围内：
- Line 604: `| **Interfaces Service** |` -> `| **Apps Service** |`
- Line 605: `| **Interfaces Flow** |` -> `| **Application Flow** |`
- Line 611: `Interfaces Flow → Interfaces Service → App Service` -> `Application Flow → Apps Service → Data Service`
- Line 615: `❌ Interfaces → Data Store` -> `❌ Apps → Data Store`
- Line 616: `❌ Interfaces → Data Runtime` -> `❌ Apps → Data Runtime`
- Line 617: `❌ Interfaces 非 registry` -> `❌ Apps 非 registry`
- Line 618: `❌ Data → Interfaces` -> `❌ Data → Apps`
- Line 626: `# ❌ Interfaces 层禁止直接导入 Store` -> `# ❌ Apps 层禁止直接导入 Store`
- Line 629: `# ❌ Interfaces 层禁止直接导入 Runtime` -> `# ❌ Apps 层禁止直接导入 Runtime`
- Line 633: `# ✅ Interfaces 层应该使用 Service` -> `# ✅ Apps 层应该使用 Service（通过 DI 获取）`
- Line 655: `App 层 Service` -> `Apps 层 Service`
- Line 656: `App 层 Flow` -> `Application 层 Flow`
- Line 667: `❌ Interfaces 层重复实现` -> `❌ Apps 层重复实现`

**Step 2: 验证无遗漏**

```bash
grep -n "Interfaces" .claude/rules/python.md
# Expected: no output
```

**Step 3: Commit**

```bash
git add .claude/rules/python.md
git commit -m "docs: update stale Interfaces layer references in python.md"
```

**验收:** `grep "Interfaces" .claude/rules/python.md` 返回空

---

### Task 5: 修复 `.claude/commands/ditto-architecture-audit.md` 示例输出 `[S]`

**Files:**
- Modify: `.claude/commands/ditto-architecture-audit.md:315`

**Step 1: 替换过期层名**

将:
```
  2. [NAM-001] Interfaces层混用技术术语 `SQLBarLoader`
```
改为:
```
  2. [NAM-001] Apps层混用技术术语 `SQLBarLoader`
```

**Step 2: 验证无其他 Interfaces 残留**

```bash
grep -n "Interfaces" .claude/commands/ditto-architecture-audit.md
# Expected: no output
```

**Step 3: Commit**

```bash
git add .claude/commands/ditto-architecture-audit.md
git commit -m "docs: update stale Interfaces reference in audit command"
```

**验收:** 文件中不含 "Interfaces"

---

### Task 6: 提取 4 个 `di/__init__.py` 的 factory 函数到 `_factory.py` `[M]`

**Files:**
- Create: `packages/analysis/src/ditto_analysis/di/_factory.py`
- Create: `packages/execution/src/ditto_execution/di/_factory.py`
- Create: `packages/features/src/ditto_features/di/_factory.py`
- Create: `packages/strategy/src/ditto_strategy/di/_factory.py`
- Modify: `packages/analysis/src/ditto_analysis/di/__init__.py`
- Modify: `packages/execution/src/ditto_execution/di/__init__.py`
- Modify: `packages/features/src/ditto_features/di/__init__.py`
- Modify: `packages/strategy/src/ditto_strategy/di/__init__.py`

遵循 data 包已有的 `di/_factory.py` 模式。

**Step 1: 为每个包创建 `_factory.py`**

以 analysis 为例（其余 3 个同构）：

`packages/analysis/src/ditto_analysis/di/_factory.py`:
```python
"""Analysis 层 DI Provider 工厂."""

from __future__ import annotations

from dishka import Provider

from .storage import AnalysisStorageProvider

__all__ = ["get_analysis_providers"]


def get_analysis_providers() -> list[Provider]:
    """返回 Analysis 层的所有 Provider."""
    return [AnalysisStorageProvider()]
```

同理创建 execution、features、strategy 的 `_factory.py`。

**Step 2: 精简 `__init__.py` 为纯 re-export**

`packages/analysis/src/ditto_analysis/di/__init__.py`:
```python
"""Analysis 层 DI Provider."""

from ._factory import get_analysis_providers
from .storage import AnalysisStorageProvider

__all__ = ["AnalysisStorageProvider", "get_analysis_providers"]
```

同理修改 execution、features、strategy 的 `di/__init__.py`。

**Step 3: 验证导入路径不变**

```bash
python -c "from ditto_analysis.di import get_analysis_providers, AnalysisStorageProvider; print('OK')"
python -c "from ditto_execution.di import get_execution_providers, ExecutionStorageProvider; print('OK')"
python -c "from ditto_features.di import get_features_providers, FeaturesStorageProvider; print('OK')"
python -c "from ditto_strategy.di import get_strategy_providers, StrategyStorageProvider; print('OK')"
# Expected: all OK
```

**Step 4: 运行相关测试**

```bash
pixi run -e dev pytest packages/apps/tests/ -q -k "capability_boundary or container or provider"
pixi run -e dev pytest packages/execution/tests/ -q
pixi run -e dev pytest packages/strategy/tests/ -q
pixi run -e dev pytest packages/analysis/tests/ -q
pixi run -e dev pytest packages/features/tests/ -q
```

**Step 5: Commit**

```bash
git add packages/analysis/src/ditto_analysis/di/ \
       packages/execution/src/ditto_execution/di/ \
       packages/features/src/ditto_features/di/ \
       packages/strategy/src/ditto_strategy/di/
git commit -m "refactor: extract di factory functions to _factory.py (CLAUDE.md compliance)"
```

**验收:** 所有 `di/__init__.py` 仅含 re-export（from .xxx import + __all__），无内联函数定义；所有测试通过

---

### Task 7: 消除 Execution 包重复的 `SQLiteClient` `[M]`

**Files:**
- Delete: `packages/execution/src/ditto_execution/storage/sqlite_client.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/positions.py:9`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/intents.py:9`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/fills.py:9`
- Modify: `packages/execution/src/ditto_execution/di/storage.py:22`
- Modify: `packages/execution/tests/conftest.py:7`
- Modify: `packages/execution/tests/unit/trade/test_trade_service_unit.py:30`

**Step 1: 替换所有导入**

将所有 `from ditto_execution.storage.sqlite_client import SQLiteClient` 替换为:
```python
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
```

涉及文件：
- `packages/execution/src/ditto_execution/storage/sqlite/trade/positions.py`
- `packages/execution/src/ditto_execution/storage/sqlite/trade/intents.py`
- `packages/execution/src/ditto_execution/storage/sqlite/trade/fills.py`
- `packages/execution/src/ditto_execution/di/storage.py`
- `packages/execution/tests/conftest.py`
- `packages/execution/tests/unit/trade/test_trade_service_unit.py`

**Step 2: 删除重复文件**

```bash
git rm packages/execution/src/ditto_execution/storage/sqlite_client.py
```

**Step 3: 检查 execution CLAUDE.md 目录结构描述**

更新 `packages/execution/CLAUDE.md` 中 `storage/sqlite_client.py` 的引用，改为 `# SQLite 客户端（复用 platform.foundation.storage）`。

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/execution/tests/ -q
# Expected: all pass
```

**Step 5: Commit**

```bash
git add packages/execution/
git commit -m "refactor: remove duplicate SQLiteClient, import from platform"
```

**验收:** `ditto_execution.storage.sqlite_client` 不存在；所有 execution 测试通过；`from ditto_platform.foundation.storage.sqlite_client import SQLiteClient` 是唯一来源

---

### Task 8: 替换 `# noqa: D102` 为简短 docstring `[S]`

**Files:**
- Modify: `packages/execution/src/ditto_execution/di/storage.py:35`
- Modify: `packages/strategy/src/ditto_strategy/di/storage.py:40,47,54,61,68,75,82,93,104`

**Step 1: 替换 execution 的 1 处**

Line 35: 将 `def execution_audit_service(self, sqlite_pool: SQLitePool) -> ExecutionAuditService:  # noqa: D102`
改为:
```python
    def execution_audit_service(self, sqlite_pool: SQLitePool) -> ExecutionAuditService:
        """创建 ExecutionAuditService 并初始化 schema."""
```

**Step 2: 替换 strategy 的 9 处**

每个 `# noqa: D102` 方法加一行 docstring：

| 方法 | docstring |
|------|-----------|
| `strategy_spec_reader` | `"""提供策略规格读取器."""` |
| `strategy_spec_writer` | `"""提供策略规格写入器."""` |
| `strategy_artifact_reader` | `"""提供策略工件读取器."""` |
| `strategy_artifact_writer` | `"""提供策略工件写入器."""` |
| `strategy_run_reader` | `"""提供策略运行读取器."""` |
| `strategy_run_writer` | `"""提供策略运行写入器."""` |
| `strategy_catalog_service` | `"""提供策略目录服务."""` |
| `strategy_artifact_service` | `"""提供策略工件服务."""` |
| `strategy_run_service` | `"""提供策略运行服务."""` |

**Step 3: 验证无 noqa D102 残留**

```bash
grep -rn "noqa: D102" packages/execution/src/ packages/strategy/src/
# Expected: no output
```

**Step 4: 运行 lint 确认**

```bash
pixi run -e dev lint
# Expected: all checks pass
```

**Step 5: Commit**

```bash
git add packages/execution/src/ditto_execution/di/storage.py packages/strategy/src/ditto_strategy/di/storage.py
git commit -m "style: replace noqa D102 with docstrings in DI providers"
```

**验收:** `grep -rn "noqa: D102" packages/execution/src/ packages/strategy/src/` 返回空

---

### Task 9: 最终验证 `[S]`

**Step 1: 运行完整检查**

```bash
pixi run -e dev check
# Expected: lint + fmt + type + test --fast all pass
```

**Step 2: 验证所有 8 个问题已修复**

```bash
# 1. 无 merge-backups
git ls-files .merge-backups/
# Expected: empty

# 2. importlinter 无 Engine 引用
grep "Engine" .importlinter
# Expected: empty

# 3. agent-context-pack 无硬编码合约数
grep "34 kept" docs/architecture/agent-context-pack.md
# Expected: empty

# 4. python.md 无 Interfaces 引用
grep "Interfaces" .claude/rules/python.md
# Expected: empty

# 5. audit command 无 Interfaces 引用
grep "Interfaces" .claude/commands/ditto-architecture-audit.md
# Expected: empty

# 6. di/__init__.py 纯 re-export
grep -n "^def " packages/analysis/src/ditto_analysis/di/__init__.py packages/execution/src/ditto_execution/di/__init__.py packages/features/src/ditto_features/di/__init__.py packages/strategy/src/ditto_strategy/di/__init__.py
# Expected: empty

# 7. 无重复 SQLiteClient
test -f packages/execution/src/ditto_execution/storage/sqlite_client.py && echo "FAIL" || echo "OK"
# Expected: OK

# 8. 无 noqa D102
grep -rn "noqa: D102" packages/execution/src/ packages/strategy/src/
# Expected: empty
```

**Step 3: Commit（如有格式化变更）**

```bash
git add -A
git diff --cached --quiet || git commit -m "chore: post-remediation formatting"
```

**验收:** `pixi run -e dev check` 通过，8 项检查全部 OK

---

## 执行顺序

```
Task 1 (merge-backups)     ── 独立
Task 2 (importlinter)      ── 独立
Task 3 (contract count)    ── 独立
Task 4 (python.md)         ── 独立
Task 5 (audit command)     ── 独立
Task 6 (di factory)        ── 独立
Task 7 (SQLiteClient)      ── 独立
Task 8 (noqa D102)         ── 独立
Task 9 (final verify)      ── 依赖 1-8 全部完成
```

Task 1-8 之间无依赖关系，可并行执行。Task 9 是最终验证门。
