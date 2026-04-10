# Phase 4 Code Review Round 8+9 修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 Phase 4 综合代码审查发现的 11 个 MAJOR 问题，分两轮完成。

**Architecture:** Round 8 聚焦架构边界修复（interfaces DI 泄漏 + 违规依赖）和文档一致性。Round 9 聚焦代码可维护性（quality.py 拆分、data_writer 去重、runtime_builder 提取）和质量改进（异常粒度）。

**Tech Stack:** Python 3.12+, polars, dishka (DI), import-linter

---

## Round 8: 架构边界 + 文档一致性（5 项）

### Task 1: 修复 AGENTS.md 依赖路径错误 [S]

**问题:** AGENTS.md 第 68 行 `ditto_analytics → ditto_engine → ditto_kernel` 错误，实际 analytics 仅依赖 kernel。

**Files:**
- Modify: `AGENTS.md:68`

**Step 1: 修正依赖路径**

```markdown
# 修改前
ditto_interfaces → ditto_analytics → ditto_engine → ditto_kernel

# 修改后
ditto_interfaces → ditto_analytics → ditto_kernel
```

**Step 2: 补充 app → analytics 路径**

在 `ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra` 行后添加：

```markdown
ditto_app → ditto_analytics → ditto_kernel
```

**Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: fix analytics dependency path in AGENTS.md"
```

---

### Task 2: 修复 CLAUDE.md 架构原则 [S]

**问题:** CLAUDE.md 第 68 行同样的 analytics 路径错误，且缺少 app → analytics 路径。

**Files:**
- Modify: `CLAUDE.md:66-69`

**Step 1: 修正依赖层级**

```markdown
# 修改后
依赖层级（从高到低）:
  ditto_interfaces → ditto_app → ditto_engine → ditto_data → ditto_infra
  ditto_interfaces → ditto_analytics → ditto_kernel
  ditto_interfaces → ditto_data → ditto_kernel, ditto_infra
  ditto_app → ditto_analytics → ditto_kernel
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: fix analytics path + add app→analytics in CLAUDE.md"
```

---

### Task 3: 添加 Analytics↔App importlinter 互斥合约 [S]

**问题:** .importlinter 缺少 analytics↔app 互斥合约，Analytics CLAUDE.md 声明禁止 analytics→app 但 CI 不强制。

**Files:**
- Modify: `.importlinter:150-157`（在 `engine-no-analytics-dependency` 之后插入）

**Step 1: 添加两条合约**

在 `engine-no-analytics-dependency` 合约之后（第 157 行后）插入：

```ini
# ═══════════════════════════════════════════════════════════════════
# Analytics 与 App 互斥：平行平面，互不依赖
# App 通过 builders 层使用 Analytics（表达式编译/因子计算）
# Analytics 禁止反向依赖 App
# ═══════════════════════════════════════════════════════════════════
[importlinter:contract:analytics-no-app-dependency]
name = Analytics must not depend on App
type = forbidden
source_modules =
    ditto_analytics.**
forbidden_modules =
    ditto_app.**
```

> 注意：`app → analytics` 是允许的依赖方向，不需要反向禁止。
> `layered-architecture` 合约已隐含 app 在 analytics 之上（app 在 layers 中，analytics 不在），所以不需要额外 `app-no-analytics` 合约。

**Step 2: 验证**

```bash
pixi run -e dev arch-check
```

Expected: 所有合约通过，新增 `analytics-no-app-dependency` 显示 GREEN。

**Step 3: Commit**

```bash
git add .importlinter
git commit -m "arch: add analytics-no-app-dependency importlinter contract"
```

---

### Task 4: 修复 interfaces/api/routes/source.py 违规依赖 [M]

**问题:** `source.py:13` 直接导入 `ditto_data.sources.base.DataSource`，非 registry 代码违反 `interfaces-service-isolation` 合约。

**修复方案:** 将 `_get_data_source` 和 `_fetch_source_data` 的类型注解改为 `Any`（这些是内部实现函数，不暴露类型），或将 `DataSource` 类型通过 `SourceQueryFacade` 间接获取。

**Files:**
- Modify: `interfaces/src/ditto_interfaces/api/routes/source.py`

**Step 1: 移除 DataSource 直接导入，通过 facade 方法间接获取**

将 `_get_data_source` 的返回类型从 `DataSource` 改为 `Any`，因为 route 层不需要知道 data 层的具体类型。将 `_fetch_source_data` 的参数类型也改为 `Any`。

```python
# 修改前
from ditto_data.sources.base import DataSource

def _get_data_source(facade: SourceQueryFacade, source: str) -> DataSource:
    ...

def _fetch_source_data(
    source: DataSource,
    ...
) -> pl.DataFrame:
    ...

# 修改后
from typing import Any

# 删除 from ditto_data.sources.base import DataSource

def _get_data_source(facade: SourceQueryFacade, source: str) -> Any:
    ...

def _fetch_source_data(
    source: Any,
    ...
) -> pl.DataFrame:
    ...
```

> 注意：`_get_data_source` 仅在内部使用，类型注解不影响 API 契约。
> `DataSource` 是一个 Protocol/ABC，route 不应了解其具体类型。

**Step 2: 验证**

```bash
pixi run -e dev arch-check  # interfaces-service-isolation 合约应通过
pixi run -e dev type         # 类型检查通过
```

**Step 3: Commit**

```bash
git add interfaces/src/ditto_interfaces/api/routes/source.py
git commit -m "fix: remove direct DataSource import from API route (arch boundary)"
```

---

### Task 5: 修复 interfaces CLI/Jobs DI 泄漏 [L]

**问题:** 7 处 interfaces 代码直接导入 `ditto_app.process` 和 `ditto_app.config` 具体类，绕过 DI 容器。

**涉及文件:**

| 文件 | 当前导入 | 问题类型 |
|------|---------|---------|
| `cli/commands/strategy.py` | `BacktestServiceConfig`, `StrategyRunMode`, `StrategyRunServiceConfig` | Config dataclass |
| `cli/executor.py` | `BackfillManager`, `IngestionCoordinator` | 类型注解 |
| `jobs/tasks/dq_batch.py` | `L3BatchService`, `MetadataQueryFacade` | 直接实例化 |
| `jobs/context.py` | `QualityEngineProtocol`, `MarketQueryFacade`, `MetadataQueryFacade`, `QualityEngine` | 混合 |
| `jobs/flows/daily.py` | `TaskTier`, `get_datasets_by_tier`, `get_parallel_datasets`, `count_results` | Config+工具 |
| `jobs/tasks/t0_meta.py` | `INGESTION_SPECS` | Config 常量 |

**修复策略（分层处理）:**

**5a. Config dataclass 导入（strategy.py, daily.py, t0_meta.py）— 可接受**

Config dataclass (`BacktestServiceConfig`, `StrategyRunMode`, `INGESTION_SPECS`) 是数据传输对象（DTO），不携带行为。interfaces 层依赖 app.config 是架构允许的（`layered-architecture` 中 interfaces > app）。**无需修改。**

但需确认 `interfaces-service-isolation` 合约不覆盖 `ditto_app`（仅覆盖 `ditto_data`）。查看 `.importlinter:179`，确认 source_modules 为 `ditto_data.services/models/errors/quality/config`，不涉及 `ditto_app`。**结论：这些导入合规，不修改。**

**5b. CLI executor 类型注解（executor.py）— 最小修改**

`CLIExecutor.__init__` 接收 `IngestionCoordinator` 和 `BackfillManager` 作为参数。当前类型注解直接引用 app.process 类。

修改方案：使用 `typing.Any` 替代，因为 CLI executor 由 DI context manager 创建，调用方已知类型。

```python
# 修改前
from ditto_app.process.backfill_manager import BackfillManager
from ditto_app.process.ingestion_coordinator import IngestionCoordinator

class CLIExecutor:
    def __init__(
        self,
        coordinator: IngestionCoordinator,
        backfill_manager: BackfillManager,
    ) -> None:

# 修改后
from __future__ import annotations

from typing import Any

class CLIExecutor:
    def __init__(
        self,
        coordinator: Any,
        backfill_manager: Any,
    ) -> None:
```

> 注意：`executor.py` 是纯编排层，由 `create_cli_executor` 上下文管理器注入具体类型。
> 使用 `Any` 是合理的权衡——interfaces 不应了解 app 层的具体实现类型。

**5c. Jobs context.py — Protocol 导入合规，Facade 导入需修复**

`QualityEngineProtocol` 是 Protocol（类型级依赖，合规）。`MarketQueryFacade`/`MetadataQueryFacade` 是具体类（但用于 DI 容器 `container.get()` 的 key，合规）。

`QualityEngine` 来自 `ditto_data.quality`，已在 `interfaces-service-isolation` 的 `ignore_imports` 中豁免（`jobs.context -> ditto_data.quality`）。**合规，不修改。**

**5d. Jobs dq_batch.py — 直接实例化 L3BatchService**

这是最严重的 DI 泄漏：`dq_batch_check` 函数直接 `L3BatchService(engine, market_facade, metadata_facade)` 构造实例。

修改方案：通过 DI 容器获取 `L3BatchService` 实例。

```python
# 修改前
from ditto_app.process.quality import L3BatchService
from ditto_app.query.metadata import MetadataQueryFacade

async def dq_batch_check(...):
    with create_dq_and_metadata_context() as (engine, metadata_service, market_service):
        l3_service = L3BatchService(
            engine=engine,
            market_facade=market_service,
            metadata_facade=metadata_service,
        )

# 修改后
# 删除 L3BatchService 和 MetadataQueryFacade 的直接导入
# 改为通过容器获取

from ditto_app.process.quality import L3BatchService  # 仅用于 container.get() key
from ditto_app.query.metadata import MetadataQueryFacade  # 仅用于 container.get() key

async def dq_batch_check(...):
    with create_prefect_host() as container:
        l3_service = container.get(L3BatchService)
        metadata_service = container.get(MetadataQueryFacade)
        resolved_date = _resolve_trade_date(trade_date, metadata_service)
        ...
```

> **更优方案：** 在 `app/providers.py` 中将 `L3BatchService` 注册到 DI 容器，
> 然后 `dq_batch.py` 通过 `container.get(L3BatchService)` 获取。
> 这样 `dq_batch.py` 仍需 import `L3BatchService` 作为 key，但不再直接实例化。

> **最小改动原则：** 考虑到 `L3BatchService` 的 import 仅用作 DI key，
> 且 `interfaces → app` 依赖在 layered architecture 中是允许的，
> 真正的问题在于**直接实例化**而非**import**。
> 将实例化改为 DI 获取即可。

**Step 1: 修改 executor.py — 替换类型注解**

```python
# interfaces/src/ditto_interfaces/cli/executor.py
# 移除 from ditto_app.process... 导入
# 用 Any 替代类型注解
```

**Step 2: 修改 dq_batch.py — 改为 DI 获取**

将 `L3BatchService` 直接构造改为 `container.get(L3BatchService)`。需要确保 `L3BatchService` 在 `providers.py` 中已注册。

**Step 3: 验证**

```bash
pixi run -e dev arch-check  # 所有合约通过
pixi run -e dev type         # 类型检查通过
pixi run -e dev test --fast  # 测试通过
```

**Step 4: Commit**

```bash
git add interfaces/src/ditto_interfaces/cli/executor.py \
       interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py
git commit -m "fix: resolve interfaces DI leaks — use DI container instead of direct instantiation"
```

---

### Round 8 验证

```bash
pixi run -e dev check  # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 所有 importlinter 合约通过
```

---

## Round 9: 可维护性 + 质量（6 项）

### Task 6: 拆分 quality.py 为独立模块 [L]

**问题:** quality.py 826 行，包含 3 个独立职责的类 + 4 个 Protocol。

**Files:**
- Create: `packages/app/src/ditto_app/process/quality_check.py`
- Create: `packages/app/src/ditto_app/process/quality_l3.py`
- Create: `packages/app/src/ditto_app/process/quality_reconciliation.py`
- Create: `packages/app/src/ditto_app/process/quality_protocols.py`
- Modify: `packages/app/src/ditto_app/process/quality.py`（改为 re-export shim）
- Modify: `packages/app/src/ditto_app/process/__init__.py`（更新 re-export）

**Step 1: 创建 quality_protocols.py**

提取 4 个 Protocol + `ReconciliationResult` dataclass（约 80 行）：

- `ReconciliationResult` (L36-64)
- `QualityEngineProtocol` (L464-496)
- `InstrumentStoreProtocol` (L498-504)
- `TdxSourceProtocol` (L506-514)
- `ComparisonStoreProtocol` (L516-524)

**Step 2: 创建 quality_check.py**

提取 `QualityService`（L72-214），import Protocol 从 `quality_protocols`。

**Step 3: 创建 quality_l3.py**

提取 `L3BatchService`（L216-462），import Protocol 从 `quality_protocols`。

**Step 4: 创建 quality_reconciliation.py**

提取 `QualityReconciliationService`（L526-826），import Protocol 从 `quality_protocols`。
同时将 `_send_alerts` 和 `_send_alert` 合并为一个模块级函数（修复 C4）：

```python
def _log_quality_alert(trade_date: str, dataset: str, issues: list[DQIssue]) -> None:
    """统一的告警日志函数."""
    for issue in issues:
        logger.warning(
            "Quality alert",
            ...
        )
```

**Step 5: 修改 quality.py 为 re-export shim**

```python
"""质量服务 — re-export shim（向后兼容）."""
from ditto_app.process.quality_check import QualityService
from ditto_app.process.quality_l3 import L3BatchService
from ditto_app.process.quality_protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    QualityEngineProtocol,
    ReconciliationResult,
    TdxSourceProtocol,
)
from ditto_app.process.quality_reconciliation import QualityReconciliationService

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "L3BatchService",
    "QualityEngineProtocol",
    "QualityReconciliationService",
    "QualityService",
    "ReconciliationResult",
    "TdxSourceProtocol",
]
```

**Step 6: 更新 `process/__init__.py` 的 re-export**

确保 `__all__` 列表不变（quality.py shim 保持了对外接口不变）。

**Step 7: 验证**

```bash
pixi run -e dev test --fast
pixi run -e dev type
```

**Step 8: Commit**

```bash
git add packages/app/src/ditto_app/process/quality*.py
git commit -m "refactor: split quality.py into focused modules (check/l3/reconciliation/protocols)"
```

---

### Task 7: 提取 data_writer 重复 instrument_id 解析模式 [M]

**问题:** `_write_market_bars`、`_write_index_bars`、`_write_stock_status`、`_write_adj_factor` 各自内联了相同的 instrument_id 解析 + enrich 模式。`_enrich_and_filter_fk_dataframe` 已部分提取了此逻辑。

**Files:**
- Modify: `packages/app/src/ditto_app/process/data_writer.py`

**Step 1: 提取 `_enrich_with_instrument_id_if_missing` 方法**

在 `IngestionDataWriter` 类中添加统一方法（利用已有的 `_enrich_and_filter_fk_dataframe` 的 enrich 部分，但不过滤 null FK）：

```python
def _resolve_and_enrich_instrument_id(
    self,
    df: pl.DataFrame,
    source_ticker_col: str,
) -> pl.DataFrame:
    """解析 instrument_id 并 enrich（统一入口）."""
    if "instrument_id" in df.columns:
        return df
    source_tickers = df[source_ticker_col].unique().to_list()
    mapping = self._metadata_service.resolve_instrument_ids_batch(
        identifiers=source_tickers,
        source=self._source_name,
        asof=None,
    )
    return _enrich_with_instrument_id(df, mapping, source_ticker_col, self._source_name)
```

**Step 2: 重构 `_write_market_bars` 和 `_write_index_bars` 使用统一方法**

替换 4 行重复模式为 1 行调用：

```python
def _write_market_bars(self, ...):
    enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
    bars_dataset = cast(Literal["stock_daily", "etf_daily"], dataset_enum.value)
    rows_written = self._market_write_service.save_bars(...)
    return _to_write_result(dataset, year, enriched_df, rows_written)

def _write_index_bars(self, ...):
    enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
    rows_written = self._market_write_service.save_bars(dataset="index_daily", ...)
    return _to_write_result(dataset, year, enriched_df, rows_written)
```

**Step 3: 重构 `_write_stock_status` 和 `_write_adj_factor`**

同样替换内联模式为 `self._resolve_and_enrich_instrument_id()` 调用。

**Step 4: 验证**

```bash
pixi run -e dev test --fast
pixi run -e dev type
```

**Step 5: Commit**

```bash
git add packages/app/src/ditto_app/process/data_writer.py
git commit -m "refactor: extract _resolve_and_enrich_instrument_id in data_writer"
```

---

### Task 8: 合并 _write_market_bars 和 _write_index_bars [S]

**问题:** `_write_market_bars` 和 `_write_index_bars` 结构几乎一致，仅 dataset 参数不同。

**前置:** Task 7 完成后执行。

**Files:**
- Modify: `packages/app/src/ditto_app/process/data_writer.py`

**Step 1: 合并为 `_write_traded_bars`**

```python
def _write_traded_bars(
    self,
    dataset: str,
    df: pl.DataFrame,
    year: int,
    on_duplicate: OnDuplicate,
    source_ticker_col: str,
    bars_dataset: str,
) -> WriteResult:
    """写入行情 K 线数据（stock/etf/index 共用）."""
    enriched_df = self._resolve_and_enrich_instrument_id(df, source_ticker_col)
    rows_written = self._market_write_service.save_bars(
        dataset=bars_dataset,
        df=enriched_df,
        year=year,
        on_duplicate=on_duplicate,
    )
    return _to_write_result(dataset, year, enriched_df, rows_written)
```

**Step 2: 更新 `_build_dataset_handlers` 中的 lambda 调用**

```python
# 修改前
Dataset.STOCK_DAILY: lambda: self._write_market_bars(...),
Dataset.ETF_DAILY: lambda: self._write_market_bars(...),
Dataset.INDEX_DAILY: lambda: self._write_index_bars(...),

# 修改后
Dataset.STOCK_DAILY: lambda: self._write_traded_bars(
    ..., bars_dataset="stock_daily"
),
Dataset.ETF_DAILY: lambda: self._write_traded_bars(
    ..., bars_dataset="etf_daily"
),
Dataset.INDEX_DAILY: lambda: self._write_traded_bars(
    ..., bars_dataset="index_daily"
),
```

**Step 3: 删除 `_write_market_bars` 和 `_write_index_bars`**

**Step 4: 验证**

```bash
pixi run -e dev test --fast
```

**Step 5: Commit**

```bash
git add packages/app/src/ditto_app/process/data_writer.py
git commit -m "refactor: merge _write_market_bars/_write_index_bars into _write_traded_bars"
```

---

### Task 9: 提取 runtime_builder 值读取器 [M]

**问题:** `runtime_builder.py` 616 行，其中 12 个 static value-reader 方法（L476-616，约 140 行）是通用 JSON 反序列化工具。

**Files:**
- Create: `packages/app/src/ditto_app/builders/_spec_deserializer.py`
- Modify: `packages/app/src/ditto_app/builders/runtime_builder.py`

**Step 1: 创建 `_spec_deserializer.py`**

提取以下 12 个 static 方法为模块级函数：

- `_as_object_dict`, `_as_sequence`, `_as_str_tuple`, `_as_float_tuple`
- `_read_required_str`, `_read_optional_str`, `_read_str_value`
- `_read_int`, `_read_optional_int`
- `_read_float`, `_read_optional_float`, `_read_bool`

```python
"""Spec 反序列化工具函数."""

from __future__ import annotations

from typing import Any


def as_object_dict(value: Any) -> dict[str, Any]:
    """将值转换为 dict[str, Any]."""
    ...

# ... 其余 11 个函数
```

**Step 2: 更新 runtime_builder.py**

将 `self._as_object_dict(...)` 改为 `as_object_dict(...)`，import 从 `_spec_deserializer`。

```python
from ditto_app.builders._spec_deserializer import (
    as_object_dict,
    as_sequence,
    ...
)
```

**Step 3: 验证**

```bash
pixi run -e dev test --fast
pixi run -e dev type
```

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/builders/_spec_deserializer.py \
       packages/app/src/ditto_app/builders/runtime_builder.py
git commit -m "refactor: extract spec deserializer from runtime_builder"
```

---

### Task 10: 细化 ingestion_coordinator.py 异常捕获 [M]

**问题:** `ingestion_coordinator.py` 有 7 处 `except Exception`，粒度过粗。

**Files:**
- Modify: `packages/app/src/ditto_app/process/ingestion_coordinator.py`

**Step 1: 分析每处 `except Exception` 上下文，识别可预期的异常类型**

常见可预期异常：
- `polars.exceptions.*` (ComputeError, SchemaError)
- `httpx.HTTPStatusError`（数据源调用）
- `ValueError`, `KeyError`（数据解析）
- `FileNotFoundError`（文件操作）

**Step 2: 对每处 `except Exception` 添加具体异常捕获**

模式：

```python
# 修改前
try:
    ...
except Exception as e:
    logger.error(...)

# 修改后
try:
    ...
except (ValueError, KeyError, pl_exceptions.ComputeError) as e:
    logger.warning("Data processing error", ...)
except Exception as e:
    logger.exception("Unexpected error", ...)
```

**Step 3: 验证**

```bash
pixi run -e dev test --fast
pixi run -e dev type
```

**Step 4: Commit**

```bash
git add packages/app/src/ditto_app/process/ingestion_coordinator.py
git commit -m "refactor: narrow exception handling in ingestion_coordinator"
```

---

### Task 11: 细化 quality.py 异常捕获 [S]

**问题:** `quality.py`（现在已拆分为独立模块）有 3 处 `except Exception`。

**前置:** Task 6 完成后执行。

**Files:**
- Modify: `packages/app/src/ditto_app/process/quality_check.py`
- Modify: `packages/app/src/ditto_app/process/quality_l3.py`
- Modify: `packages/app/src/ditto_app/process/quality_reconciliation.py`

**Step 1: 在拆分后的各模块中细化异常捕获**

- `quality_check.py`: `QualityService._save_quarantine_issue` 的 `except Exception`
- `quality_l3.py`: `L3BatchService.check_dataset` 和 `_handle_check_error` 的 `except Exception`
- `quality_reconciliation.py`: `QualityReconciliationService._handle_reconciliation_error` 的 `except Exception`

同 Task 10 的模式，添加具体异常类型。

**Step 2: 验证**

```bash
pixi run -e dev test --fast
```

**Step 3: Commit**

```bash
git add packages/app/src/ditto_app/process/quality_*.py
git commit -m "refactor: narrow exception handling in quality modules"
```

---

### Round 9 验证

```bash
pixi run -e dev check  # lint + fmt + type + test --fast
pixi run -e dev arch-check  # 所有 importlinter 合约通过
```

---

## 依赖关系

```
Round 8（可并行执行）:
  Task 1 (AGENTS.md) ─┐
  Task 2 (CLAUDE.md)  ─┼─→ Round 8 验证
  Task 3 (importlinter)┤
  Task 4 (source.py)  ─┤
  Task 5 (DI leaks)   ─┘

Round 9（有依赖链）:
  Task 6 (quality 拆分) ──→ Task 11 (quality 异常细化)
  Task 7 (data_writer 提取) ──→ Task 8 (data_writer 合并)
  Task 9 (runtime_builder 提取)  [独立]
  Task 10 (coordinator 异常)      [独立]
```

## 复杂度总结

| Task | 复杂度 | 文件数 | 预估代码行 |
|------|--------|--------|-----------|
| 1 | S | 1 | ~5 |
| 2 | S | 1 | ~5 |
| 3 | S | 1 | ~10 |
| 4 | M | 1 | ~15 |
| 5 | L | 2-3 | ~60 |
| 6 | L | 5 | ~200 (拆分+shim) |
| 7 | M | 1 | ~40 |
| 8 | S | 1 | ~25 |
| 9 | M | 2 | ~150 |
| 10 | M | 1 | ~50 |
| 11 | S | 3 | ~20 |
