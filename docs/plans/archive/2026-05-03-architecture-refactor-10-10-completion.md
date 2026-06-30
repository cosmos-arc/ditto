# Architecture Refactor 10/10 Completion

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复所有残留架构问题，将架构审计评分从 9/10 提升到 10/10。消除最后一个 import-linter `ignore_imports` 技术债（features->data publication_safety），清理文档旧引用，提交所有未提交的改进。

**Branch:** `architecture-refactor`（已有大量未提交改进）

**Architecture:** 当前 12 包架构已就位。核心差距：(1) features->data 残耦 3 个文件；(2) ~300 行文档旧包名引用；(3) 12 个 stale egg-info 目录。

**Tech Stack:** Python 3.13, pixi, import-linter, basedpyright, ruff, pytest。

---

## Execution Rules

1. 每个 task 单独提交，提交前运行指定验证命令。
2. 不引入 backward compatibility shim。
3. 不用 `TYPE_CHECKING` 解决循环依赖。
4. 优先使用 `Edit` 工具修改文件，`Bash` 仅用于 shell 操作。

## Gap Inventory

| # | 问题 | 影响 | 难度 |
|---|------|------|------|
| G1 | features->data.models.publication_safety 残耦 (3 files) | 最后一个 `ignore_imports` 技术债 | M |
| G2 | 12 个 stale `.egg-info` 目录 | 构建产物污染 | S |
| G3 | ~300 行文档旧包名引用 (20+ files) | 文档准确性 | L |
| G4 | 未提交的改进需验证提交 | 分支完整性 | S |

## Uncommitted Changes (Already Done)

以下改进已在工作区但未提交，Task 1 负责验证：

- ✅ `AnalyticsError` → `FeaturesError` 重命名
- ✅ Analysis pyproject 移除 phantom deps (ditto-data, ditto-features)
- ✅ Apps pyproject 添加核心依赖
- ✅ Kernel 版本对齐 0.2.0 → 0.1.0
- ✅ TradingSettings 从 platform 迁移到 application
- ✅ Strategy/Portfolio/Risk/Execution contracts Protocol 实现
- ✅ Risk errors 层次结构实现
- ✅ BrokerGateway Protocol 扩展
- ✅ 对应测试文件

---

### Task 1: Verify Uncommitted Changes and Clean Stale Artifacts `[S]`

**Files:**
- Modify: `.gitignore`
- Delete: 12 个 `*.egg-info` 目录
- Verify: 所有已修改文件

**Step 1: Run full verification**

```bash
pixi run -e dev check
```

Expected: lint/type/test/arch-check 全部通过。如有失败，修复后再继续。

**Step 2: Delete stale egg-info**

```bash
find packages -name "*.egg-info" -type d -exec rm -rf {} +
```

**Step 3: Add egg-info to gitignore**

在 `.gitignore` 中添加：

```
# Build artifacts
*.egg-info/
```

**Step 4: Verify egg-info cleaned**

```bash
find packages -name "*.egg-info" -type d
```

Expected: 无输出。

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: verify uncommitted improvements and clean stale egg-info"
```

---

### Task 2: Move Publication Safety Records to Kernel `[M]`

> **核心变更**：将 6 个 publication_safety frozen dataclass 记录类型从 `ditto_data.models` 移至 `ditto_kernel`，
> 消除 features→data 最后一个 `ignore_imports`。
>
> **Kernel 准入分析**：
> - 跨层使用 ≥2 包：data + features + application（3 包使用） ✅
> - 零业务行为：frozen dataclass + 纯数据序列化 ✅
> - 高稳定性：记录类型极少变更 ✅
> - 零外部依赖：仅依赖 stdlib + kernel json_types ✅
> - 纯值语义：frozen dataclass ✅

**Files:**
- Create: `packages/kernel/src/ditto_kernel/publication_safety.py`
- Modify: `packages/kernel/src/ditto_kernel/__init__.py`
- Modify: `packages/kernel/CLAUDE.md`
- Modify: `packages/data/src/ditto_data/models/publication_safety.py` → thin re-export
- Modify: `packages/features/src/ditto_features/services/derived_shadow_slot_service.py`
- Modify: `packages/features/src/ditto_features/storage/derived_artifact_writer.py`
- Modify: `packages/features/src/ditto_features/services/derived/artifact_persistence_service.py`
- Modify: `.importlinter` (移除 features-boundary ignore_imports)
- Create: `packages/kernel/tests/unit/test_publication_safety_unit.py`

**Step 1: Create kernel publication_safety module**

将 `packages/data/src/ditto_data/models/publication_safety.py` 中的 6 个记录类复制到
`packages/kernel/src/ditto_kernel/publication_safety.py`，修改 import：

```python
# 原: from ditto_data.models.common import (...)
# 新: from ditto_kernel.json_types import (
#     JsonDict,
#     JsonValue,
#     require_bool,
#     require_int,
#     require_payload,
#     require_str,
# )
```

6 个类（保持原样，无需修改）：
- `CompatibilityManifestRecord`
- `DerivedMinimalDQSummaryRecord`
- `ShadowDiffReportRecord`
- `ShadowTraceRecordRecord`
- `CertificationReportRecord`
- `DerivedShadowSlotRecord`

**Step 2: Add kernel exports**

在 `packages/kernel/src/ditto_kernel/__init__.py` 的 `__all__` 中添加这 6 个类。

**Step 3: Update kernel CLAUDE.md**

在 Module Structure 的 business subdomain 列表中添加：

```
- publication_safety.py -- Publication safety runtime records (frozen dataclasses for derived certification/shadow/DQ)
```

**Step 4: Convert data.models.publication_safety to thin re-export**

替换 `packages/data/src/ditto_data/models/publication_safety.py` 全部内容为：

```python
"""Re-export publication safety records from kernel."""

from ditto_kernel.publication_safety import (  # noqa: F401
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)

__all__ = [
    "CertificationReportRecord",
    "CompatibilityManifestRecord",
    "DerivedMinimalDQSummaryRecord",
    "DerivedShadowSlotRecord",
    "ShadowDiffReportRecord",
    "ShadowTraceRecordRecord",
]
```

保留 `JsonDict` 和 `JsonValue` 的 re-export 仅当 data 内部消费者仍然通过此模块导入它们（检查 `rg -n "from ditto_data.models.publication_safety import JsonDict"` 后决定）。

**Step 5: Update 3 features files**

将 `from ditto_data.models.publication_safety import ...` 替换为 `from ditto_kernel.publication_safety import ...`：

1. `packages/features/src/ditto_features/services/derived_shadow_slot_service.py:7`
   - `DerivedShadowSlotRecord`
2. `packages/features/src/ditto_features/storage/derived_artifact_writer.py:12`
   - `CompatibilityManifestRecord`, `DerivedMinimalDQSummaryRecord`
3. `packages/features/src/ditto_features/services/derived/artifact_persistence_service.py:9`
   - `CompatibilityManifestRecord`, `DerivedMinimalDQSummaryRecord`

**Step 6: Remove features-boundary ignore_imports**

在 `.importlinter` 的 `features-boundary` contract 中，删除：

```ini
ignore_imports =
    # Features 引用 data publication safety 记录类型是合法的：记录含序列化方法不符合 kernel 准则
    ditto_features.** -> ditto_data.models.publication_safety
```

保留 `unmatched_ignore_imports_alerting = warn`。

**Step 7: Add kernel test**

创建 `packages/kernel/tests/unit/test_publication_safety_unit.py`：

```python
from ditto_kernel.publication_safety import (
    CertificationReportRecord,
    CompatibilityManifestRecord,
    DerivedMinimalDQSummaryRecord,
    DerivedShadowSlotRecord,
    ShadowDiffReportRecord,
    ShadowTraceRecordRecord,
)


def test_all_records_are_frozen_dataclasses() -> None:
    import dataclasses

    for cls in (
        CompatibilityManifestRecord,
        DerivedMinimalDQSummaryRecord,
        ShadowDiffReportRecord,
        ShadowTraceRecordRecord,
        CertificationReportRecord,
        DerivedShadowSlotRecord,
    ):
        assert dataclasses.is_dataclass(cls)
        assert hasattr(cls, "__dataclass_params__")
        assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_compatibility_manifest_round_trip() -> None:
    record = CompatibilityManifestRecord(
        derived_id="test",
        version=1,
        manifest_hash="abc",
        payload={"key": "value"},
        created_at="2026-01-01",
    )
    json_dict = record.to_json_dict()
    restored = CompatibilityManifestRecord.from_json_dict(json_dict)
    assert restored == record


def test_derived_shadow_slot_optional_fields() -> None:
    record = DerivedShadowSlotRecord(
        derived_id="test",
        candidate_version=2,
        baseline_version=None,
        activated_at="2026-01-01",
        disabled_at=None,
    )
    assert record.baseline_version is None
    assert record.disabled_at is None
```

**Step 8: Verify**

```bash
pixi run -e dev pytest packages/kernel/tests/unit/test_publication_safety_unit.py -q
pixi run -e dev type
pixi run -e dev arch-check
rg -n "from ditto_data" packages/features/src/ -g '*.py'
```

Expected:
- kernel test passes
- type check 0 errors
- arch-check: features-boundary 合同无 broken imports
- rg 无 features->data 引用

**Step 9: Commit**

```bash
git add packages/kernel packages/data/packages/features .importlinter
git commit -m "refactor: move publication safety records to kernel, eliminate features->data coupling"
```

---

### Task 3: Clean Documentation Stale References `[L]`

**Files:**
- Modify: ~20 文档文件（详见分类）

**分类策略：**

| 类别 | 策略 | 文件 |
|------|------|------|
| **活跃文档** | 全量替换旧包名 | README.md, docs/configuration.md, docs/ops-manual.md |
| **ADR 文档** | 全量替换 | docs/adr/0006, 0007, 0008, 0009 |
| **验证文档** | 全量替换 | docs/verification-plan-2025.md |
| **架构标准** | 全量替换 | docs/architecture/*.md |
| **设计文档** | 添加弃用头部 | docs/design/*.md |
| **Sprint 文档** | 添加弃用头部 | docs/sprints/*.md |
| **审计文档** | 添加弃用头部 | docs/reviews/audit/*.md |

**Step 1: Replace active documentation references**

替换规则（全局）：

```text
ditto_interfaces → ditto_apps
ditto_infra → ditto_platform
ditto_app. → ditto_application.（注意不匹配 ditto_apps）
ditto_analytics → ditto_features 或 ditto_analysis（按上下文）
ditto_engine.alpha → ditto_strategy.alpha
ditto_engine.portfolio → ditto_portfolio
ditto_engine.accounting → ditto_portfolio.accounting
ditto_engine.risk → ditto_risk
ditto_engine.execution → ditto_execution
ditto_engine.backtest → ditto_backtest
packages/engine/ → packages/{对应能力包}/
packages/analytics/ → packages/features/ 或 packages/analysis/
packages/app/ → packages/application/
packages/infra/ → packages/platform/
interfaces/src/ → packages/apps/src/
interfaces/tests/ → packages/apps/tests/
```

活跃文件（逐文件 Edit）：
1. `docs/ops-manual.md` — CLI/API 命令中的 `ditto_interfaces` 引用
2. `docs/operations/operations-manual.md` — 同上

**Step 2: Add deprecation header to historical docs**

对以下目录中的文件添加 2 行头部注释（Markdown 格式）：

```markdown
> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
```

目标目录：
- `docs/design/*.md`（~10 个文件）
- `docs/sprints/*.md`（~4 个文件）
- `docs/reviews/audit/*.md`（~8 个文件）
- `docs/brainstorms/*.md`（~2 个文件）
- `docs/reviews/2026-*.md`（非 archive 的旧 review）

**Step 3: Verify**

```bash
rg -n "ditto_engine|ditto_analytics|ditto_infra|ditto_interfaces|packages/engine|packages/analytics|packages/infra|packages/app/" docs/ -g '*.md' | grep -v "archive/" | grep -v "docs/plans/2" | grep -v "⚠️ Historical" | grep -v "旧架构"
```

Expected: 仅剩余 `⚠️ Historical` 头部后的原始内容和 `docs/plans/` 设计文档中的引用（设计文档保留历史记录）。

**Step 4: Commit**

```bash
git add docs/ README.md
git commit -m "docs: clean stale package references and add historical doc headers"
```

---

### Task 4: Final Verification `[S]`

**Step 1: Run full gate**

```bash
pixi run -e dev check
```

Expected:
```
ruff check . → All checks passed
basedpyright --warnings → 0 errors, 0 warnings
pytest --fast → all pass
import-linter → all contracts kept
architecture smell check passed
```

**Step 2: Verify import-linter has minimal ignore_imports**

```bash
rg -n "ignore_imports" .importlinter
```

Expected remaining `ignore_imports`（全部为 by-design）：
1. `platform.exceptions -> kernel.exceptions`（PlatformError 继承 DittoError）
2. `apps.registry.** -> ditto_data.**`（Composition Root 豁免）
3. `apps.jobs.context -> ditto_data.quality`（Context Bundle 构建）
4. `apps.api/cli -> ditto_data.models.common`（Dataset StrEnum）
5. `application.** -> platform.foundation/services`（编排层访问基础设施）
6. `data.storage.** -> data.models.**`（CQRS 类型耦合）

**不应存在**：
- ❌ `ditto_features.** -> ditto_data.models.publication_safety`（Task 2 已消除）

**Step 3: Verify no stale production code references**

```bash
rg -n "ditto_engine|ditto_analytics|ditto_infra|ditto_interfaces" packages/ -g '*.py'
```

Expected: 仅出现在 boundary test 的 forbidden_prefixes 列表中。

**Step 4: Verify kernel publication_safety**

```bash
pixi run -e dev pytest packages/kernel/tests/unit/test_publication_safety_unit.py -q
```

Expected: PASS

**Step 5: Final commit if needed**

```bash
git add -A
git commit -m "test: final verification for architecture refactor 10/10"
```

---

## Implementation Notes

### ignore_imports Classification

| ignore_imports | 类型 | 操作 |
|---|---|---|
| platform→kernel exceptions | **By-design**（继承根异常） | 保留 |
| features→data.publication_safety | **技术债** | Task 2 消除 |
| apps.registry→data.* | **By-design**（Composition Root） | 保留 |
| apps.context→data.quality | **By-design**（文档化豁免） | 保留 |
| apps.api/cli→data.models.common | **By-design**（StrEnum 列表） | 保留 |
| application→platform.foundation/services | **By-design**（编排层） | 保留 |
| data.storage→data.models | **By-design**（CQRS） | 保留 |

### Kernel Growth Justification

publication_safety records 移入 kernel 的理由：
- 3+ 包共享（data/features/application）
- 零业务行为（frozen dataclass + 数据序列化）
- 高稳定性（6 个记录类型自创建以来未变更结构）
- 零外部依赖（仅 stdlib + kernel.json_types）

Plan complete. Use `superpowers:executing-plans` to execute one task at a time.
