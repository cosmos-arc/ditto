# Code Review Round 5 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PR #61 Code Review 发现的 4 个已确认问题（评分 >= 25）

**Architecture:** 纯清理修复，无架构变更。涉及 6 个文件（计划遗漏 `interfaces/models/__init__.py` 同步修改），总计修改约 40 行。

**Tech Stack:** Python, pixi

**Status:** ✅ 全部完成

---

## Task 1: 修复 source 参数未转发 [S] ✅

`backfill_missing_flow` 和 `repair_holes_flow` 接受 `source` 参数并传给 `create_ingestion_bundle`，但未传给 `backfill_manager.backfill_missing()`。当 source 非 "tushare" 时，空洞检测会查询错误的数据源日志。

**Files:**
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/backfill.py:112-115`
- Modify: `interfaces/src/ditto_interfaces/jobs/flows/repair.py:84-87`

**Step 1: 修复 backfill.py**

在 `backfill_missing()` 调用中添加 `source=source`：

```python
# 修改前 (line 112-115):
result = bundle.backfill_manager.backfill_missing(
    dataset=dataset,
    parallel=parallel,
)

# 修改后:
result = bundle.backfill_manager.backfill_missing(
    dataset=dataset,
    source=source,
    parallel=parallel,
)
```

**Step 2: 修复 repair.py**

在 `repair_holes_flow` 中的 `backfill_missing()` 调用同样添加 `source=source`：

```python
# 修改前 (line 84-87):
result = bundle.backfill_manager.backfill_missing(
    dataset=dataset,
    parallel=parallel,
)

# 修改后:
result = bundle.backfill_manager.backfill_missing(
    dataset=dataset,
    source=source,
    parallel=parallel,
)
```

**Step 3: 验证**

```bash
pixi run -e dev type --all
pixi run -e dev lint
```

**Step 4: Commit**

```bash
git add interfaces/src/ditto_interfaces/jobs/flows/backfill.py interfaces/src/ditto_interfaces/jobs/flows/repair.py
git commit -m "fix: forward source parameter to backfill_missing in flow functions"
```

---

## Task 2: 删除 build_display_map 死代码 [S] ✅

`strategy_types.py` 中的 `build_display_map` 函数零调用者，与 `builders/_resolution.py` 的 `resolve_instrument_display` 功能重复。Round 2 保留它以"避免循环导入"，但实际无代码引用。

**Files:**
- Modify: `packages/app/src/ditto_app/process/strategy_types.py:32-35,292-313`

**Step 1: 从 `__all__` 移除**

```python
# 修改前:
__all__ = [
    "RunLifecycleService",
    "StrategyInputAssembler",
    "build_display_map",
    "enrich_record_with_symbol",
    "write_backtest_artifacts",
]

# 修改后:
__all__ = [
    "RunLifecycleService",
    "StrategyInputAssembler",
    "enrich_record_with_symbol",
    "write_backtest_artifacts",
]
```

**Step 2: 删除函数定义及注释块**

删除 line 292-313（含分隔注释和函数体）。

**Step 3: 验证**

```bash
pixi run -e dev type --all
pixi run -e dev lint
```

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/process/strategy_types.py
git commit -m "refactor: remove dead build_display_map function (zero callers)"
```

---

## Task 3: 清理 types.py 无消费者 re-export [S] ✅

`types.py` 中 5 个类型（`IdentifierNotFoundError`, `BackfillResult`, `IngestionResult`, `ResultCounts`, `RetryResult`）在 interfaces 层零消费者。docstring 声称"so interfaces does not need to import from ditto_data directly"，但 interfaces 层本就被允许导入 ditto_data，措辞不准确。

**Files:**
- Modify: `packages/app/src/ditto_app/types.py`

**Step 1: 更新 docstring**

```python
# 修改前:
"""
Re-exported domain types for interface layer consumption.

These types are re-exported from ditto_data so that the interfaces layer
does not need to import from ditto_data directly.
"""

# 修改后:
"""
App 层公共类型聚合入口。

将 interfaces 层高频使用的 domain 类型集中 re-export，
减少跨包 import 路径。新增 re-export 前需确认：
  1. 类型被 >= 2 个外部消费者使用
  2. 类型不属于某个特定子模块的内部实现
"""
```

**Step 2: 删除无消费者类型的 import 和 `__all__` 条目**

删除 `IdentifierNotFoundError` import（line 16），以及整个 `ingestion` import 块中 `BackfillResult`、`IngestionResult`、`ResultCounts`、`RetryResult`：

```python
# 修改前 (line 15-27):
from ditto_data.errors import (
    AmbiguousTickerError,
    IdentifierNotFoundError,
    NoIdentifierProvidedError,
)
from ditto_data.models import Dataset, MacroCategory, MacroFrequency
from ditto_data.models.ingestion import (
    BackfillResult,
    IngestionResult,
    InstrumentIngestParams,
    ResultCounts,
    RetryResult,
)
from ditto_data.quality import QualityEngine
from ditto_data.quality.spec import DQIssue, DQResult

# 修改后:
from ditto_data.errors import (
    AmbiguousTickerError,
    NoIdentifierProvidedError,
)
from ditto_data.models import Dataset, MacroCategory, MacroFrequency
from ditto_data.models.ingestion import InstrumentIngestParams
from ditto_data.quality import QualityEngine
from ditto_data.quality.spec import DQIssue, DQResult
```

```python
# 修改前 __all__:
__all__ = [
    "AmbiguousTickerError",
    "BackfillResult",
    "DQIssue",
    "DQResult",
    "Dataset",
    "IdentifierNotFoundError",
    "IngestionResult",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroFrequency",
    "NoIdentifierProvidedError",
    "QualityEngine",
    "ResultCounts",
    "RetryResult",
]

# 修改后 __all__:
__all__ = [
    "AmbiguousTickerError",
    "DQIssue",
    "DQResult",
    "Dataset",
    "InstrumentIngestParams",
    "MacroCategory",
    "MacroFrequency",
    "NoIdentifierProvidedError",
    "QualityEngine",
]
```

**Step 3: 验证**

```bash
pixi run -e dev type --all
pixi run -e dev lint
```

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/types.py
git commit -m "refactor: remove unused re-exports and fix types.py docstring"
```

---

## Task 4: 更新过时 TODO "Phase 2+" [S] ✅

`instrument_rule_provider.py` 中两处注释引用已过去的 "Phase 2+" 里程碑，项目已进入 Phase 4。

**Files:**
- Modify: `packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py:7,67`

**Step 1: 更新模块 docstring (line 7)**

```python
# 修改前:
V1: 内存实现，Phase 2+ 接入真实 Data 存储后替换。

# 修改后:
V1: 内存实现，后续接入真实 Data 存储后替换。
```

**Step 2: 更新类 docstring (line 67)**

```python
# 修改前:
V1: 内存实现。Phase 2+ 从 Data metadata service 读取。

# 修改后:
V1: 内存实现。后续从 Data metadata service 读取。
```

**Step 3: 验证**

```bash
pixi run -e dev type --all
pixi run -e dev lint
```

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/services/strategy/instrument_rule_provider.py
git commit -m "docs: remove stale Phase 2+ milestone references from TODO comments"
```

---

## Task 5: 全量验证 [S] ✅

**Step 1: 运行完整检查**

```bash
pixi run -e dev check
```

Expected: 所有检查通过（lint + fmt + type + test --fast）

**Step 2: 确认分支状态**

```bash
git log --oneline -5
```

Expected: 4 个新 commit，对应 4 个 Task。
