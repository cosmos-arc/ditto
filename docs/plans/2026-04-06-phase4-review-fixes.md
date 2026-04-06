# Phase 4 审查修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Phase 4 全库架构审查中发现的全部问题（6 维度 24 项），确保代码质量、可维护性和文档一致性。

**Architecture:** 按「死代码清理 → 重复消除 → 模块拆分 → 文档同步」顺序执行，每个 Task 独立可验证，确保 `pixi run -e dev check` 始终通过。

**Tech Stack:** Python 3.12+, polars, pytest, ruff, basedpyright, importlinter

---

## 修复范围总览

| 批次 | Task | 维度 | 复杂度 | 文件数 |
|------|-------|------|--------|--------|
| **Batch 1: 死代码清理** | Task 1-4 | 架构/可维护 | S | 8 |
| **Batch 2: 重复消除** | Task 5-8 | 可维护 | M-L | 60+ |
| **Batch 3: 代码质量** | Task 9-11 | 质量 | M | 6 |
| **Batch 4: 模块拆分** | Task 12 | 可维护 | L | 10 |
| **Batch 5: 文档同步** | Task 13-15 | 文档 | M | 12 |

---

## Batch 1: 死代码清理

### Task 1: 删除 DittoPortError 死代码 `[S]`

**背景**: `DittoPortError`（`interfaces/src/ditto_interfaces/errors.py`）零引用，完全死代码。

**Files:**
- 删除: `interfaces/src/ditto_interfaces/errors.py`
- 修改: `interfaces/CLAUDE.md` — 移除 errors.py 引用
- 修改: `interfaces/AGENTS.md` — 移除 errors.py 引用

**Step 1: 验证零引用**

Run: `grep -r "DittoPortError\|from ditto_interfaces.errors import\|from ditto_interfaces import.*errors" --include="*.py" interfaces/ packages/`
Expected: 零匹配（排除 errors.py 文件自身）

**Step 2: 删除 errors.py**

```bash
rm interfaces/src/ditto_interfaces/errors.py
```

**Step 3: 更新文档引用**

在 `interfaces/CLAUDE.md` 和 `interfaces/AGENTS.md` 中搜索 `errors.py` 或 `DittoPortError`，移除相关描述段落。

**Step 4: 验证**

Run: `pixi run -e dev check`
Expected: PASS

**Step 5: Commit**

```bash
git add -A && git commit -m "refactor: 删除 DittoPortError 死代码 — 零引用的废弃异常类"
```

---

### Task 2: 修复 golden.py 裸 except `[S]`

**背景**: `packages/data/src/ditto_data/quality/golden.py:118` 的 `except Exception` 吞掉所有异常（包括 MemoryError 等不应被吞掉的），应缩小为具体异常类型。

**Files:**
- 修改: `packages/data/src/ditto_data/quality/golden.py:116-120`

**Step 1: 读取当前代码**

Read `packages/data/src/ditto_data/quality/golden.py` L110-125

**Step 2: 缩小异常范围**

将 `except Exception:` 改为 `except (TypeError, ValueError):`（TickerSpec 构造只会抛这两种）：

```python
try:
    specs.append(TickerSpec(**item_dict))
except (TypeError, ValueError):
    msg = repr(cast(object, item))
    logger.debug("忽略无效的 TickerSpec: %s", msg)
```

**Step 3: 验证测试通过**

Run: `pixi run -e dev pytest packages/data/tests/unit/quality/test_golden_spec_unit.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add packages/data/src/ditto_data/quality/golden.py && git commit -m "fix: golden.py 缩小 except 范围 — except Exception → except (TypeError, ValueError)"
```

---

### Task 3: 修复 data↔analytics pyproject.toml 循环依赖 `[S]`

**背景**: `ditto-data` 依赖 `ditto-analytics`，但源码中 ditto_data 零导入 ditto_analytics。从 data 的 pyproject.toml 移除。

**Files:**
- 修改: `packages/data/pyproject.toml`

**Step 1: 验证零导入**

Run: `grep -r "ditto_analytics" --include="*.py" packages/data/src/`
Expected: 零匹配

**Step 2: 从 dependencies 移除 ditto-analytics**

Edit `packages/data/pyproject.toml`，将：
```toml
dependencies = ["ditto-kernel", "ditto-analytics", "ditto-infra"]
```
改为：
```toml
dependencies = ["ditto-kernel", "ditto-infra"]
```

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: PASS

**Step 4: Commit**

```bash
git add packages/data/pyproject.toml && git commit -m "fix: 移除 ditto-data 对 ditto-analytics 的虚假依赖 — 源码零导入"
```

---

### Task 4: 统一日志导入 — 6 处 loguru → observability `[M]`

**背景**: 6 处直接使用 `from loguru import logger`，应统一为 `from ditto_infra.foundation import logger`。

**Files:**
- 修改: `packages/app/src/ditto_app/process/cascade_orchestrator.py` L30
- 修改: `packages/app/src/ditto_app/query/derived.py` L20
- 修改: `packages/app/src/ditto_app/process/quality.py` L15
- 修改: `interfaces/src/ditto_interfaces/registry/init_providers.py` L14
- 修改: `interfaces/src/ditto_interfaces/registry/infra/notification.py` L20
- 修改: `interfaces/src/ditto_interfaces/registry/infra/config.py` L31

**Step 1: 逐文件替换导入**

每个文件：将 `from loguru import logger` 替换为 `from ditto_infra.foundation import logger`。

**Step 2: 验证**

Run: `pixi run -e dev check`
Expected: PASS

**Step 3: Commit**

```bash
git add -A && git commit -m "refactor: 统一日志导入 — 6 处 loguru → ditto_infra.foundation.logger"
```

---

## Batch 2: 重复消除

### Task 5: 删除 interfaces/tests 重复测试 — 37 个文件 `[M]`

**背景**: `interfaces/tests/unit/services/` 下约 37 个测试文件与 `packages/app/tests/unit/process/` 完全重复。业务逻辑已迁移至 app 层，旧测试是重构遗留物。

**Files:**
- 删除: `interfaces/tests/unit/services/` 整个目录

**重复对照（确认安全删除）:**

| 旧位置 (interfaces/.../services/) | 新位置 (app/.../process/) | 文件数 |
|---|---|---|
| derived/ | materialization/ | 11 |
| ingestion/quality/ | quality/ | 4 |
| ingestion/ | ingestion/ | 14 |
| strategy/ | strategy/ | 11 |

**仅在 interfaces 中存在（需检查是否迁移）:**
- `derived/test_query_facade_unit.py` — 检查 app 中是否有对应
- `derived/test_factor_evaluation_facade_unit.py` — 检查 app 中是否有对应
- `derived/test_research_dataset_facade_unit.py` — 检查 app 中是否有对应

**Step 1: 确认 app 测试覆盖完整**

Run: `diff <(ls interfaces/tests/unit/services/ingestion/*.py | xargs -I{} basename {}) <(ls packages/app/tests/unit/process/ingestion/*.py | xargs -I{} basename {})`

对 derived/→materialization/ 和 strategy/ 做同样比较。

**Step 2: 检查仅 interfaces 独有的 3 个测试**

读取这 3 个文件，确认其导入路径指向 ditto_app 还是 ditto_port。如果仍导入 ditto_port，说明是未迁移的旧测试，也应删除或迁移。

**Step 3: 删除整个 interfaces/tests/unit/services/ 目录**

```bash
rm -rf interfaces/tests/unit/services/
```

**Step 4: 验证测试仍全部通过**

Run: `pixi run -e dev test`
Expected: PASS（测试数量减少约 37 个文件对应的测试用例，无失败）

**Step 5: Commit**

```bash
git add -A && git commit -m "refactor: 删除 interfaces/tests 重复测试 — 业务逻辑已迁移至 app 层"
```

---

### Task 6: 提取 API Models 公共样板代码 `[M]`

**背景**: `_parse_date`、`_format_float`、`_format_date`、`DateField`、`validate_date_range` 在 `market.py` 和 `commodity.py` 间重复。`fx.py` 和 `macro.py` 也有类似重复。

**Files:**
- 创建: `interfaces/src/ditto_interfaces/models/_date_helpers.py`
- 修改: `interfaces/src/ditto_interfaces/models/market.py`
- 修改: `interfaces/src/ditto_interfaces/models/commodity.py`
- 修改: `interfaces/src/ditto_interfaces/models/fx.py`
- 修改: `interfaces/src/ditto_interfaces/models/macro.py`

**Step 1: 创建 _date_helpers.py**

```python
"""API 模型共享的日期/数值格式化工具."""

from __future__ import annotations

from datetime import date
from typing import Any, Annotated

from pydantic import BeforeValidator


def parse_date(v: Any) -> date | None:
    """解析日期值，支持字符串和 date 对象."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        return date.fromisoformat(v)
    raise ValueError(f"Invalid date format: {v}")


def format_float(value: float | None, decimals: int = 2) -> float | None:
    """格式化浮点数保留指定小数位."""
    if value is None:
        return None
    return round(value, decimals)


def format_date(value: date | str | None) -> str | None:
    """将日期转换为字符串格式 (YYYY-MM-DD)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


DateField = Annotated[date | None, BeforeValidator(parse_date)]
```

**Step 2: 更新 market.py / commodity.py / fx.py / macro.py**

在每个文件中：
1. 删除本地的 `_parse_date`、`_format_float`、`_format_date`、`DateField` 定义
2. 添加 `from ditto_interfaces.models._date_helpers import parse_date as _parse_date, format_float as _format_float, format_date as _format_date, DateField`
3. 如果 `validate_date_range` 也是逐字重复，提取到 `_date_helpers.py`

**Step 3: 验证**

Run: `pixi run -e dev test interfaces/tests/`
Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor: 提取 API Models 公共日期/格式化工具至 _date_helpers.py"
```

---

### Task 7: 提取 CLI Query 公共辅助函数 `[M]`

**背景**: `_output_json`、`_print_truncated_hint`、`_parse_date` 在 5 个 CLI query 命令文件中重复。

**Files:**
- 修改: `interfaces/src/ditto_interfaces/cli/utils/output.py` — 添加 query 通用函数
- 修改: `interfaces/src/ditto_interfaces/cli/commands/query/capital.py`
- 修改: `interfaces/src/ditto_interfaces/cli/commands/query/market.py`
- 修改: `interfaces/src/ditto_interfaces/cli/commands/query/fundamental.py`
- 修改: `interfaces/src/ditto_interfaces/cli/commands/query/metadata.py`
- 修改: `interfaces/src/ditto_interfaces/cli/commands/query/macro.py`

**Step 1: 在 cli/utils/output.py 添加公共函数**

```python
import json as stdlib_json
from typing import Any

import orjson

_TABLE_DISPLAY_LIMIT = 20


def output_json(items: list[Any]) -> None:
    """以 JSON 格式输出查询结果."""
    print(orjson.dumps([_serialize_item(i) for i in items]).decode())


def output_json_dicts(data: list[dict]) -> None:
    """以 JSON 格式输出字典列表."""
    print(orjson.dumps(data).decode())


def output_json_single(item: Any) -> None:
    """以 JSON 格式输出单个对象."""
    print(orjson.dumps(_serialize_item(item)).decode())


def print_truncated_hint(total: int) -> None:
    """打印截断提示."""
    if total > _TABLE_DISPLAY_LIMIT:
        print(f"\n显示前 {_TABLE_DISPLAY_LIMIT} 条，共 {total} 条结果")
```

**Step 2: 更新 5 个 query 命令文件**

每个文件中：
1. 删除本地的 `_output_json`、`_print_truncated_hint`、`_TABLE_DISPLAY_LIMIT` 定义
2. 添加 `from ditto_interfaces.cli.utils.output import output_json, print_truncated_hint`
3. 如果有 `_parse_date`/`_validate_date_range`，也提取到 `cli/utils/validation.py`

**Step 3: 验证**

Run: `pixi run -e dev test`
Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor: 提取 CLI Query 公共辅助函数至 cli/utils/"
```

---

### Task 8: 清理 re-export shim 中的冗余和 __all__ 不同步 `[M]`

**背景**: 4 个 re-export shim 文件 + process/__init__.py 的 __all__ 与子模块不同步。quality.py 缺少 `__all__`。

**Files:**
- 修改: `packages/app/src/ditto_app/process/quality.py` — 添加 `__all__`
- 修改: `packages/app/src/ditto_app/process/__init__.py` — 同步 `__all__`

**Step 1: 为 quality.py 添加 __all__**

读取 quality.py，找到所有公共符号（非 `_` 前缀的类、函数），添加：

```python
__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "L3BatchService",
    "QualityReconciliationService",
    "QualityService",
    "ReconciliationResult",
    "TdxSourceProtocol",
]
```

**Step 2: 同步 process/__init__.py 的 __all__**

确保 process/__init__.py 的 __all__ 与所有子模块的 __all__ 联集一致。特别检查 `prepare_input_frame` 是否被正确导出。

**Step 3: 验证**

Run: `pixi run -e dev type --all && pixi run -e dev lint`
Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor: 同步 process __all__ 定义 — quality.py 添加 __all__ + 修复不同步"
```

---

## Batch 3: 代码质量

### Task 9: 为 quality.py 添加 __all__ 并同步 process/__init__.py `[M]`

> 注意：此 Task 已合并到 Task 8 中实施。

---

### Task 10: 添加 `from __future__ import annotations` 至 74 个文件 `[M]`

**背景:** 74 个文件（packages 9 + interfaces 65）缺少 `from __future__ import annotations`。批量添加。

**Files:**
- 修改: 74 个 .py 文件（列表见附录 A）

**Step 1: 使用脚本批量添加**

对每个文件：如果第一行不是 `from __future__ import annotations`，则在文件 docstring 之后（或第一行非注释行之前）插入 `from __future__ import annotations`。

用 ruff 的 `from __future__ import annotations` 自动修复：

```bash
# 查找缺少的文件
grep -rL "from __future__ import annotations" packages/app/src/ interfaces/src/ --include="*.py" | head -80
```

对每个文件手动或脚本添加。注意：
- `__init__.py` 文件通常只有 docstring，加在 docstring 后
- 其他文件加在 module docstring 后、第一个 import 前

**Step 2: 验证**

Run: `pixi run -e dev check`
Expected: PASS（类型检查不应有新的 NameError）

**Step 3: Commit**

```bash
git add -A && git commit -m "style: 批量添加 from __future__ import annotations — 74 个文件"
```

---

### Task 11: 修复 interfaces/main.py DataStoreSettings 导入 `[S]`

**背景:** `interfaces/main.py:21` 直接导入 `ditto_data.config.data_store.DataStoreSettings`，违反 interfaces 层对 data 内部模块的直接依赖（registry 例外）。

**Files:**
- 修改: `interfaces/src/ditto_interfaces/main.py` L21, L122-128
- 修改: `interfaces/src/ditto_interfaces/registry/infra/config.py` — 添加 DataStoreSettings Provider

**Step 1: 读取 registry/infra/config.py**

确认是否已有 DataStoreSettings 相关 Provider。

**Step 2: 将 DataStoreSettings 导入移入 registry**

在 `registry/infra/config.py` 中添加 DataStoreSettings 的 Provider（如果还没有），然后在 main.py 中通过 DI 容器获取：

```python
# main.py 修改前:
from ditto_data.config.data_store import DataStoreSettings

# main.py 修改后（删除直接导入）:
# DataStoreSettings 通过 DI 容器注入
```

**Step 3: 验证**

Run: `pixi run -e dev check`
Expected: PASS

**Step 4: Commit**

```bash
git add -A && git commit -m "refactor: DataStoreSettings 导入移入 registry — 消除 interfaces 对 data 内部的直接依赖"
```

---

## Batch 4: 模块拆分（最大 Task）

### Task 12: 拆分 coordinator.py God Object `[L]`

**背景:** `coordinator.py` 1844 行、3 个类 + 1 个工厂。拆分为独立模块。

**Files:**
- 创建: `packages/app/src/ditto_app/process/ingestion_coordinator.py` — IngestionCoordinator (L229-844)
- 创建: `packages/app/src/ditto_app/process/backfill_manager.py` — BackfillManager (L1383-1627)
- 创建: `packages/app/src/ditto_app/process/retry_manager.py` — RetryManager (L1625-1750)
- 创建: `packages/app/src/ditto_app/process/coordinator_factory.py` — create_coordinator() + 常量 (L1-228 + L1751-1844)
- 修改: `packages/app/src/ditto_app/process/coordinator.py` — 改为 re-export shim
- 修改: `packages/app/src/ditto_app/process/ingestion.py` — 更新导入来源
- 修改: `packages/app/src/ditto_app/providers.py` — 更新导入路径（如有直接引用 coordinator）

**拆分方案:**

```
coordinator.py (1844行)
    ↓ 拆分为
├── coordinator_factory.py   (~230行) — 常量 + create_coordinator() 工厂
├── ingestion_coordinator.py (~620行) — IngestionCoordinator 类
├── backfill_manager.py      (~250行) — BackfillManager 类
├── retry_manager.py         (~130行) — RetryManager 类
└── coordinator.py           (~30行)  — re-export shim (保持向后兼容)
```

**Step 1: 写拆分后的测试（验证现有测试不受影响）**

Run: `pixi run -e dev pytest packages/app/tests/unit/process/ingestion/ -v`
Expected: PASS（记录当前测试数量作为基线）

**Step 2: 创建 ingestion_coordinator.py**

从 coordinator.py 提取 L229-844（IngestionCoordinator 类）到新文件。需要的导入从原文件复制。

注意：IngestionCoordinator 内部引用的辅助函数（如 `_infer_exchange_suffix`、`_is_source_fetch_error` 等）是模块级私有函数，应跟随 IngestionCoordinator 一起迁移。

```python
"""摄取协调器 — IngestionCoordinator."""

from __future__ import annotations

# ... imports ...

# 从 coordinator.py 迁移的模块级常量和辅助函数:
# SUPPORTED_INSTRUMENT_DATASETS, EXCHANGE_PREFIX_MAP, etc.
# _infer_exchange_suffix(), _is_source_fetch_error(), etc.

class IngestionCoordinator:
    # ... 完整类定义 ...
```

**Step 3: 创建 backfill_manager.py**

提取 L1349-1385（分组辅助）+ L1383-1627（BackfillManager 类）。

```python
"""回填管理器 — BackfillManager."""

from __future__ import annotations

# ... imports ...

class BackfillManager:
    # ... 完整类定义 ...
```

**Step 4: 创建 retry_manager.py**

提取 L1625-1750（RetryManager 类）。

```python
"""失败重试管理器 — RetryManager."""

from __future__ import annotations

# ... imports ...

class RetryManager:
    # ... 完整类定义 ...
```

**Step 5: 创建 coordinator_factory.py**

提取 L1-228（常量、映射、工厂依赖）+ L1751-1844（create_coordinator 工厂函数）。

```python
"""协调器工厂 — create_coordinator() 及共享常量."""

from __future__ import annotations

# ... imports ...

# 共享常量
SWIndustryProvider = ...
SUPPORTED_INSTRUMENT_DATASETS = ...
EXCHANGE_PREFIX_MAP = ...
# ... 其他常量 ...

def create_coordinator(...) -> IngestionCoordinator:
    # ... 工厂函数 ...
```

**Step 6: 将 coordinator.py 改为 re-export shim**

```python
"""摄取协调器 — re-export shim (模块拆分后保持向后兼容).

原始实现已迁移至:
- coordinator_factory.py: 工厂函数 + 共享常量
- ingestion_coordinator.py: IngestionCoordinator
- backfill_manager.py: BackfillManager
- retry_manager.py: RetryManager
"""

from ditto_app.process.coordinator_factory import (
    EXCHANGE_PREFIX_MAP,
    MARKET_INDEX_CODES,
    STYLE_INDEX_CODES,
    SUPPORTED_INSTRUMENT_DATASETS,
    SWIndustryProvider,
    create_coordinator,
    get_all_index_codes,
    get_default_index_codes,
    get_sw_index_codes,
)
from ditto_app.process.ingestion_coordinator import IngestionCoordinator
from ditto_app.process.backfill_manager import BackfillManager
from ditto_app.process.retry_manager import RetryManager

__all__ = [
    "BackfillManager",
    "EXCHANGE_PREFIX_MAP",
    "IngestionCoordinator",
    "MARKET_INDEX_CODES",
    "RetryManager",
    "SUPPORTED_INSTRUMENT_DATASETS",
    "STYLE_INDEX_CODES",
    "SWIndustryProvider",
    "create_coordinator",
    "get_all_index_codes",
    "get_default_index_codes",
    "get_sw_index_codes",
]
```

**Step 7: 更新 ingestion.py shim 的导入来源**

如果 `ingestion.py` shim 从 `coordinator` 导入了拆分到新模块的符号，更新为从新模块直接导入。

**Step 8: 运行全部测试验证**

Run: `pixi run -e dev test`
Expected: PASS（测试数量与 Step 1 基线一致）

**Step 9: 验证 importlinter**

Run: `pixi run -e dev arch-check`
Expected: 全部 KEPT

**Step 10: Commit**

```bash
git add -A && git commit -m "refactor: 拆分 coordinator.py God Object — 1844行 → 4 个独立模块 + shim"
```

---

## Batch 5: 文档同步

### Task 13: 同步 packages/data/CLAUDE.md 目录结构 `[M]`

**背景:** data CLAUDE.md 只描述 Reader/Writer/Service/Runtime/Source 五层，实际包结构更丰富（query/, stores/, helpers/, utils/, scripts/, events.py, provider.py, di/, config/, models/, ingestion/, quality/）。

**Files:**
- 修改: `packages/data/CLAUDE.md`

**Step 1: 读取实际目录结构**

Run: `find packages/data/src/ditto_data -type f -name "*.py" | sort`

**Step 2: 更新 CLAUDE.md 目录结构描述**

在 CLAUDE.md 中添加完整的目录结构树，与 app/CLAUDE.md 风格一致。每个子目录附一行说明。

**Step 3: Commit**

```bash
git add packages/data/CLAUDE.md && git commit -m "docs: 同步 data CLAUDE.md 目录结构描述"
```

---

### Task 14: 同步根 README.md 和 interfaces/CLAUDE.md `[M]`

**背景:** README.md 引用不存在的 tests/ 目录；interfaces/CLAUDE.md 可能引用已删除的 errors.py。

**Files:**
- 修改: `README.md`
- 修改: `interfaces/CLAUDE.md`

**Step 1: 验证 README.md 中引用的路径**

检查 README.md 中提到的所有目录路径是否实际存在。特别关注：
- `tests/` — 是否已不存在（测试在各包内）
- `apps/` — 是否已删除（迁移至 packages/ 和 interfaces/）

**Step 2: 修正 README.md**

将不存在的路径替换为正确的路径。更新项目架构树为当前实际结构。

**Step 3: 验证 interfaces/CLAUDE.md**

确认 Task 1 中删除 DittoPortError 后，CLAUDE.md 中的引用已更新。

**Step 4: Commit**

```bash
git add README.md interfaces/CLAUDE.md && git commit -m "docs: 同步 README.md 和 interfaces/CLAUDE.md — 修正不存在的路径引用"
```

---

### Task 15: 修复 .claude/rules/architecture.md 引用 `[S]`

**背景:** architecture.md 引用不存在的 engine.md 规则文件。

**Files:**
- 修改: `.claude/rules/architecture.md`

**Step 1: 检查引用**

搜索 architecture.md 中对 `engine.md` 或其他不存在文件的引用。

**Step 2: 修正引用**

如果 engine.md 的内容已合并到 architecture.md 中，移除引用。如果需要独立文件，创建它。

**Step 3: Commit**

```bash
git add .claude/rules/architecture.md && git commit -m "docs: 修正 architecture.md 中不存在的文件引用"
```

---

## 验证清单

所有 Task 完成后运行：

```bash
# 完整 CI 检查
pixi run -e dev check

# importlinter 架构检查
pixi run -e dev arch-check

# 测试数量对比（应比修复前少约 37 个重复测试文件）
pixi run -e dev test --unit
```

---

## 附录 A: 缺少 `from __future__ import annotations` 的文件列表

### packages/app/src/ (9 个)

1. `packages/app/src/ditto_app/__init__.py`
2. `packages/app/src/ditto_app/query/__init__.py`
3. `packages/app/src/ditto_app/types.py`
4. `packages/app/src/ditto_app/process/__init__.py`
5. `packages/app/src/ditto_app/process/strategy.py`
6. `packages/app/src/ditto_app/process/materialization.py`
7. `packages/app/src/ditto_app/process/ingestion.py`
8. `packages/app/src/ditto_app/builders/__init__.py`
9. `packages/app/src/ditto_app/builders/strategy.py`

### interfaces/src/ (65 个)

**顶层 (5):** `__init__.py`, `main.py`, `testing.py`, `middleware.py`, `exceptions.py`

**config (1):** `config/__init__.py`

**cli/ (6):** `__init__.py`, `main.py`, `executor.py`, `context.py`, `utils/__init__.py`, `utils/output.py`, `utils/validation.py`

**cli/commands/ (20):** `__init__.py`, `factory.py`, `ingest/__init__.py`, `ingest/metadata.py`, `ingest/macro.py`, `ingest/fundamental.py`, `ingest/capital.py`, `ingest/market.py`, `backfill/__init__.py`, `backfill/metadata.py`, `backfill/macro.py`, `backfill/fundamental.py`, `backfill/capital.py`, `backfill/market.py`, `query/__init__.py`, `query/metadata.py`, `query/macro.py`, `query/fundamental.py`, `query/capital.py`, `query/market.py`

**api/ (13):** `__init__.py`, `errors.py`, `routes/__init__.py`, `routes/metadata.py`, `routes/macro.py`, `routes/source.py`, `routes/fx.py`, `routes/fundamental.py`, `routes/commodity.py`, `routes/capital.py`, `routes/portfolio.py`, `routes/ingestion.py`, `routes/market.py`

**jobs/ (8):** `__init__.py`, `context.py`, `flows/__init__.py`, `flows/repair.py`, `flows/backfill.py`, `flows/daily.py`, `tasks/__init__.py`, `tasks/dq_batch.py`, `tasks/t0_meta.py`

**models/ (2):** `__init__.py`, `common.py`

**registry/ (10):** `__init__.py`, `container.py`, `contexts/__init__.py`, `contexts/strategy.py`, `contexts/bundle.py`, `contexts/materialization.py`, `contexts/ingestion.py`, `infra/__init__.py`, `infra/notification.py`, `infra/config.py`
